"""A first-import quality replay must not inherit the user's manual answers."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('automatic_benchmark', ROOT / 'tools/check_studio_automatic.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_replay_keeps_audio_but_excludes_edits_memory_and_analysis_cache(tmp_path):
    from windows.project import fresh, track
    source = tmp_path / 'original.bandstudio'
    source.mkdir()
    audio = source / 'audio.wav'
    sf.write(audio, np.ones((22050, 2)) * .1, 44100)
    p = fresh('Example')
    t = track(audio, source, 'Edited track name', 'source', offset=12)
    t.update(gain=.1, muted=True, solo=True)
    p.update(tracks=[t], bpm=231, beats=[.1, .2, .3], downbeats=[.1], gridLocked=True,
             sections=[dict(start=0, end=.5, name='Edited', locked=True, reviewed=True, origin='manual')],
             lyrics=[dict(start=0, end=.5, text='Edited lyrics', manual=True)],
             chords=[dict(start=0, end=.5, text='Abm', manual=True)], key='Abm', capo=8,
             preparation=dict(validatedAt=123), chordReference=dict(selectedURL='edited'),
             structureProposal=dict(memory=True), analysesCompleted=['smartgrid', 'lyrics'])
    p['settings'].update(firstBeat=12, manualBPM=231, beatsPerBar=7, gridMode='fixed')
    (source / 'project.json').write_text(json.dumps(p))
    for folder in ('Cache/models/rhythm', 'Learning', 'References', '.bandstudio-memory'):
        path = source / folder
        path.mkdir(parents=True)
        (path / 'manual.json').write_text('{}')
    (source / 'Artwork.json').write_text(json.dumps(dict(title='Example', artist='Artist', album='Unrelated release')))
    before = benchmark.digest(source / 'project.json')
    target = tmp_path / 'isolated' / 'clean.bandstudio'
    provenance = benchmark.clean_copy(source, target)
    clean = json.loads((target / 'baseline.json').read_text())
    assert clean['id'] != p['id'] and clean['name'] == p['name']
    assert clean['bpm'] == 0 and not clean['gridLocked']
    assert all(not clean[key] for key in ('beats', 'downbeats', 'sections', 'lyrics', 'chords', 'key', 'capo', 'analysesCompleted'))
    assert not any(key in clean for key in ('preparation', 'chordReference', 'structureProposal', 'timingGrid'))
    assert clean['settings']['firstBeat'] == 0 and clean['settings']['beatsPerBar'] == 4
    assert clean['settings']['gridMode'] == 'detected'
    copied = clean['tracks'][0]
    assert copied['offset'] == 0 and copied['gain'] == .8 and not copied['muted'] and not copied['solo']
    assert benchmark.digest(target / copied['file']) == benchmark.digest(audio)
    assert json.loads((target / 'Artwork.json').read_text()) == dict(title='Example', artist='Artist')
    assert not any((target / directory).exists() for directory in ('Cache', 'Learning', 'References', '.bandstudio-memory'))
    assert benchmark.digest(source / 'project.json') == before == provenance['projectSHA256']
    # A second invocation cannot silently evaluate a previously edited copy.
    import pytest
    with pytest.raises(FileExistsError):
        benchmark.clean_copy(source, target)
