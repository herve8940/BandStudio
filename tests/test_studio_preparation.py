"""A validation must bind the exact preparation, including portable rendered media."""
import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))
import preparation
from services import atomic, read_rpp
from test_studio_services import project, generate, ENGINE


def approve(p, root):
    snapshot = root / 'snapshot.json'
    atomic(snapshot, p)
    preparation.validate_project(snapshot, root / 'review.json')
    p['preparation'] = json.loads((root / 'review.json').read_text())['preparation']
    atomic(snapshot, p)
    return snapshot


@pytest.mark.parametrize('change', ['gain', 'section', 'rate', 'pitch', 'mode', 'media'])
def test_changes_require_new_approval(tmp_path, monkeypatch, change):
    p = project(tmp_path)
    generate(p, tmp_path, monkeypatch)
    snapshot = approve(p, tmp_path)
    if change == 'gain': p['tracks'][0]['gain'] = .5
    if change == 'section': p['sections'][0]['name'] = 'Couplet'
    if change == 'rate': p['_rate'] = .8
    if change == 'pitch': p['_pitch'] = 2
    if change == 'mode': p['_mode'] = 'original'
    if change == 'media':
        path = tmp_path / p['tracks'][0]['file']
        path.touch()
    atomic(snapshot, p)
    with pytest.raises(ValueError, match='changé'):
        preparation.export_validated(snapshot, tmp_path / 'result.json', ENGINE)
    assert not (tmp_path / 'Exports').exists()


def test_missing_or_invalid_grid_cannot_be_approved(tmp_path):
    p = project(tmp_path)
    p['settings'].update(gridMode='detected', exportGuides=False)
    with pytest.raises(ValueError, match='Détecte les temps'):
        approve(p, tmp_path)
    p['beats'] = [0, .5, .4]
    with pytest.raises(ValueError, match='Détecte les temps'):
        approve(p, tmp_path)


def test_missing_media_and_overlapping_sections_are_reported(tmp_path):
    p = project(tmp_path)
    p['settings']['exportGuides'] = False
    p['sections'][1]['start'] = 7
    with pytest.raises(ValueError, match='chevauchent'):
        approve(p, tmp_path)
    p['sections'][1]['start'] = 8
    (tmp_path / p['tracks'][0]['file']).unlink()
    with pytest.raises(ValueError, match='Média absent'):
        approve(p, tmp_path)


def field(chunk, name):
    return next(row[1:] for row in chunk['lines'] if row[0] == name)


def frequency(path):
    audio, sr = sf.read(path, always_2d=True)
    samples = audio[sr:2*sr, 0]
    return np.argmax(np.abs(np.fft.rfft(samples))) * sr / len(samples)


def test_export_renders_pitch_rate_and_all_timeline_positions_together(tmp_path, monkeypatch):
    p = project(tmp_path)
    generate(p, tmp_path, monkeypatch)
    p.update(_rate=.75, _pitch=12, _mode='original', key='D',
             lyrics=[dict(id='line', start=3, end=6, text='Bonjour', words=[dict(start=3, end=4, text='Bonjour')])],
             chords=[dict(id='chord', start=0, end=12, text='D/F#')],
             drumHits=[dict(time=3, pitch=36, velocity=100)])
    original = (tmp_path / 'Audio/source.wav').read_bytes()
    snapshot = approve(p, tmp_path)
    output = tmp_path / 'result.json'
    preparation.export_validated(snapshot, output, ENGINE)
    result = json.loads(output.read_text())
    rpp = Path(result['path'])
    assert rpp.is_file() and rpp.parent.parent == tmp_path / 'Exports'
    tree = read_rpp(rpp)
    assert float(field(tree, 'TEMPO')[0]) == pytest.approx(90)
    source = next(t for t in tree['children'] if t['kind'] == 'TRACK' and field(t, 'NAME')[0].startswith('Original'))
    item = source['children'][0]
    assert float(field(item, 'POSITION')[0]) == pytest.approx(0)
    assert float(field(item, 'LENGTH')[0]) == pytest.approx(16, abs=.02)
    wave = rpp.parent / field(item['children'][0], 'FILE')[0]
    assert frequency(wave) == pytest.approx(880, abs=3)
    region = next(row for row in tree['lines'] if row[0] == 'MARKER' and 'Refrain' in row)
    assert float(region[2]) == pytest.approx(8/.75)
    metadata = json.loads((rpp.parent / 'bandstudio-project.json').read_text())
    assert metadata['lyrics'][0]['start'] == pytest.approx(4)
    assert metadata['lyrics'][0]['words'][0]['end'] == pytest.approx(4/.75)
    assert metadata['drumHits'][0]['time'] == pytest.approx(4)
    assert metadata['key'] == 'D'  # An octave changes the sound, not the chord names.
    assert (tmp_path / 'Audio/source.wav').read_bytes() == original
    assert (rpp.parent / 'validation.json').is_file()
    # Exporting again never overwrites a session the musician has edited in REAPER.
    before = rpp.read_bytes()
    preparation.export_validated(snapshot, output, ENGINE)
    assert json.loads(output.read_text())['path'] != str(rpp)
    assert rpp.read_bytes() == before


def test_generated_guides_do_not_revoke_a_musical_approval(tmp_path, monkeypatch):
    p = project(tmp_path)
    generate(p, tmp_path, monkeypatch)
    approve(p, tmp_path)
    signature = preparation.fingerprint(p)
    p['tracks'][-1]['id'] = 'new-derived-guide'
    p['guideKey'] = 'new-cache'
    assert preparation.fingerprint(p) == signature


def test_chord_transposition_preserves_slash_bass():
    assert preparation.transpose('D/F#', -2) == 'C/E'
    assert preparation.transpose('Bbm', 2) == 'Cm'


def test_opening_an_old_project_does_not_inherit_the_previous_song_speed(tmp_path, monkeypatch):
    from windows.host import Api
    from windows import project as model
    prepared = tmp_path / 'prepared.bandstudio'; prepared.mkdir()
    p = project(prepared)
    p['preparation'] = dict(rate=.75, pitch=2, mode='mix')
    model.save(p, prepared)
    old = tmp_path / 'old.bandstudio'; old.mkdir()
    model.save(project(old), old)
    host = Api(ENGINE, tmp_path / 'library')
    monkeypatch.setattr(host, '_guides', lambda: None)
    host._load(prepared)
    assert host._audio.rate == .75 and host._audio.pitch == 2 and host._audio.mode == 'mix'
    host._load(old)
    assert host._audio.rate == 1 and host._audio.pitch == 0 and host._audio.mode == 'original'
    host._audio.close()
