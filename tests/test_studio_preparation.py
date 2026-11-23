"""A validation must bind the exact preparation, including portable rendered media."""
import copy
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))
import preparation
from services import atomic, read_rpp, reaper_filename, import_reaper
from test_studio_services import project, generate, ENGINE


def approve(p, root):
    snapshot = root / 'snapshot.json'
    atomic(snapshot, p)
    preparation.validate_project(snapshot, root / 'review.json')
    p['preparation'] = json.loads((root / 'review.json').read_text())['preparation']
    atomic(snapshot, p)
    return snapshot


def test_direct_export_checks_current_media_without_claiming_listening(tmp_path,monkeypatch):
    p=project(tmp_path);generate(p,tmp_path,monkeypatch)
    snapshot=tmp_path/'snapshot.json';atomic(snapshot,p);out=tmp_path/'result.json'
    preparation.export_validated(snapshot,out,ENGINE,preflight=True)
    rpp=Path(json.loads(out.read_text())['path'])
    receipt=json.loads((rpp.parent/'validation.json').read_text())
    assert receipt['approval']['kind']=='technical'
    assert receipt['approval']['fingerprint']==preparation.fingerprint(p)
    assert 'preparation' not in json.loads(snapshot.read_text())
    # The fast path leaves PCM samples byte-identical and has no extra audio tree.
    tree=read_rpp(rpp)
    source=next(t for t in tree['children'] if t['kind']=='TRACK')
    item=next(c for c in source['children'] if c['kind']=='ITEM')
    audio=next(c for c in item['children'] if c['kind']=='SOURCE')
    relative=next(row[1] for row in audio['lines'] if row[0]=='FILE')
    assert (rpp.parent/relative).read_bytes()==(tmp_path/'Audio/source.wav').read_bytes()
    assert not (tmp_path/'PreparedAudio').exists()
    p['sections'][1]['start']=7;atomic(snapshot,p)
    with pytest.raises(ValueError,match='chevauchent'):
        preparation.export_validated(snapshot,tmp_path/'bad.json',ENGINE,preflight=True)
    assert not (tmp_path/'bad.json').exists()


def test_unmodified_export_needs_no_decoder_or_intermediate_copy(tmp_path,monkeypatch):
    p=project(tmp_path)
    monkeypatch.setattr(preparation,'run',lambda *a,**kw:pytest.fail('No audio transform required'))
    monkeypatch.setattr(preparation.shutil,'copy2',lambda *a,**kw:pytest.fail('No intermediate copy required'))
    assert preparation.transformed(p,tmp_path/'unused',ENGINE)==p


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


def test_export_tempo_uses_the_song_pulse_when_the_intro_misses_beats(tmp_path):
    p=project(tmp_path)
    p['settings'].update(gridMode='detected',exportGuides=False,pulseUnit='dottedQuarter')
    p.update(bpm=80,beats=[0,4.5,5.25,6.,6.75,7.5])
    assert preparation.review(p)['bpm']==120


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
    assert float(field(item, 'POSITION')[0]) == pytest.approx(4/.75)
    assert float(field(item, 'LENGTH')[0]) == pytest.approx(16, abs=.02)
    wave = rpp.parent / field(item['children'][0], 'FILE')[0]
    assert frequency(wave) == pytest.approx(880, abs=3)
    region = next(row for row in tree['lines'] if row[0] == 'MARKER' and 'Refrain' in row)
    assert float(region[2]) == pytest.approx((8+4)/.75)
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


def test_reported_windows_export_keeps_project_audio_and_backups_below_path_limit():
    name='Green Day - Wake Me Up When September Ends (Official Audio) [pGhwBFYtn1s]'
    root=PureWindowsPath('C:/Users/pasca/Music/BandStudioDev')/(name+' f4ff40a9.bandstudio')
    old=root/'Exports'/(name+'-20261122-141148-123abc')/(name+'.rpp')
    assert len(str(old))==311
    folder,filename=preparation.export_destination(root,name)
    assert folder.parent==root/'Exports'
    for relative in (filename,filename+'-bak','Audio/00000000-0000-0000-0000-000000000000.wav.reapeaks','bandstudio-project.json'):
        assert len(str(folder/relative).encode('utf-16-le'))//2<=240


def test_deep_song_folder_uses_shorter_library_export_and_rejects_impossible_paths():
    library=PureWindowsPath('C:/Music/BandStudio')
    root=library/('long song '*17+'.bandstudio')
    folder,filename=preparation.export_destination(root,'Très long morceau 🎵 '*20)
    assert folder.parent==library/'Exports'
    assert len(str(folder/filename).encode('utf-16-le'))//2<=240
    with pytest.raises(ValueError,match='dossier plus court'):
        preparation.export_destination(PureWindowsPath('C:/')/('deep/'*60)/'song.bandstudio','Song')
    assert reaper_filename('CON',folder).startswith('Morceau-CON')


def test_long_unicode_export_is_portable_unique_and_keeps_original_title():
    with tempfile.TemporaryDirectory(prefix='BS-export-') as directory:
        base=Path(directory)
        name='Green Day - Wake Me Up When September Ends (Official Audio) [pGhwBFYtn1s] · Été 🎵'
        root=base/(name+' f4ff40a9.bandstudio');root.mkdir()
        p=project(root);p['name']=name;p['settings'].update(exportGuides=False,exportCount=False)
        p['sections'][0]['name']='Entrée 🎵'
        original=(root/'Audio/source.wav').read_bytes()
        snapshot=approve(p,root);out=base/'result.json'
        preparation.export_validated(snapshot,out,ENGINE)
        info=json.loads(out.read_text());rpp=Path(info['path'])
        tree=read_rpp(rpp)
        assert any('Entrée 🎵' in row for row in tree['lines'])
        for track in (c for c in tree['children'] if c['kind']=='TRACK'):
            for item in (c for c in track['children'] if c['kind']=='ITEM'):
                media=rpp.parent/field(item['children'][0],'FILE')[0]
                assert media.is_file() and sf.info(media).frames>0
        assert all(len(str(f).encode('utf-16-le'))//2<=240 for f in rpp.parent.rglob('*'))
        assert json.loads((rpp.parent/'bandstudio-project.json').read_text())['name']==name
        imported=base/'import/result.json';import_reaper(rpp,imported,ENGINE,snapshot)
        restored=Path(json.loads(imported.read_text())['project'])
        assert json.loads((restored/'project.json').read_text())['name']==name
        first=rpp.read_bytes()
        preparation.export_validated(snapshot,out,ENGINE)
        assert json.loads(out.read_text())['path']!=str(rpp) and rpp.read_bytes()==first
        assert (root/'Audio/source.wav').read_bytes()==original
        assert not list(rpp.parent.parent.glob('.export-*'))


def test_deep_library_uses_compact_folder_and_budgets_the_final_rpp_path():
    with tempfile.TemporaryDirectory(prefix='BS-path-') as tmp:
        base=Path(tmp)
        library=base/('L'*(160-len(str(base).encode('utf-16-le'))//2-1))
        root=library/('Recorded session '*3+'.bandstudio');root.mkdir(parents=True)
        p=project(root);p['settings'].update(exportGuides=False,exportCount=False)
        snapshot=root/'snapshot.json';atomic(snapshot,p);result=root/'export.json'
        preparation.export_validated(snapshot,result,ENGINE,preflight=True)
        rpp=Path(json.loads(result.read_text())['path'])
        assert rpp.is_file() and rpp.parent.parent==library/'Exports' and rpp.parent.name.startswith('R-')
        assert all(len(str(f).encode('utf-16-le'))//2<=240 for f in rpp.parent.rglob('*'))
        assert not list(rpp.parent.parent.glob('.export-*'))
