import csv
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'desktop/studio'))
from services import atomic
from show_export import export_show
from test_studio_services import ENGINE, project


def build_library(tmp_path):
    projects = []
    for key, name in [('a','Été & feu'), ('b','Finale')]:
        folder = tmp_path/(name+'.bandstudio')
        folder.mkdir()
        song = project(folder)
        song.update(id=key,name=name,_library=str(tmp_path))
        song['settings'].update(exportCount=False, exportGuides=False)
        song['lyrics']=[dict(start=2,end=4,text='Un mot',words=[dict(start=2.125,end=2.35,text='Un')])]
        song['chords']=[dict(start=3,end=4,text='Am')]
        atomic(folder/'project.json',song)
        projects.append(song)
    return projects


def export(tmp_path, songs, **options):
    source = Path(songs[0]['_root'])/'project.json'
    out = tmp_path/'result.json'
    export_show(source,out,ENGINE,dict(paths=[s['_root'] for s in songs],**options))
    return Path(json.loads(out.read_text())['path'])


@pytest.mark.parametrize('export_guides', [False, True])
def test_live_set_media_positions_mix_and_locators(tmp_path, monkeypatch, export_guides):
    def reject_speech(*args):
        pytest.fail('A click-only export requested speech synthesis')
    monkeypatch.setattr('services.voice_wav', reject_speech)
    songs=build_library(tmp_path)
    song=songs[0]
    song['tracks'][0].update(offset=-.25,gain=.55,pan=.3)
    song['sections'][-1]['end']=11.75
    song['settings'].update(exportCount=True, exportGuides=export_guides)
    song['settings'].update(countVoice=False,callsEnabled=False,regionCountEnabled=False,speakCues=False)
    atomic(Path(song['_root'])/'project.json',song)
    bundle=export(tmp_path,[song],kind='live')
    document=ET.fromstring(gzip.open(next(bundle.glob('*.als'))).read())
    tracks=document.findall('LiveSet/Tracks/AudioTrack')
    assert len(tracks)>=2
    track=tracks[0]
    assert track.find('DeviceChain/Mixer/Pan/Manual').get('Value')=='0.3'
    assert track.find('DeviceChain/Mixer/Volume/Manual').get('Value')=='0.55'
    clip=track.find('DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events/AudioClip')
    media=bundle/clip.find('SampleRef/FileRef/RelativePath').get('Value')
    assert media.is_file() and clip.find('IsWarped').get('Value')=='false'
    assert {e.get('Value') for e in document.findall('.//Locator/Name')}=={'Intro','Refrain','Stop'}
    ids=[e.get('Id') for e in document.iter() if 'Id' in e.attrib and (e.tag=='Pointee' or e.tag.endswith('Target'))]
    assert len(ids)==len(set(ids))


def test_count_without_guide_tracks_synthesizes_only_spoken_numbers(tmp_path, monkeypatch):
    spoken = set()
    def synthesize(text, folder, settings):
        spoken.add(text)
        path = folder / (text + '.wav')
        sf.write(path, np.full((4410, 2), .25), 44100)
        return path
    monkeypatch.setattr('services.voice_wav', synthesize)
    song = build_library(tmp_path)[0]
    song['settings'].update(exportCount=True, exportGuides=False, countVoice=True)
    atomic(Path(song['_root']) / 'project.json', song)
    bundle = export(tmp_path, [song], kind='live')
    assert next(bundle.glob('*.als')).is_file()
    assert spoken == {'un', 'deux', 'trois', 'quatre'}


@pytest.mark.parametrize('layout,num',[('concert',1),('songs',2),('both',3)])
def test_console_layouts_media_and_timing(tmp_path,layout,num):
    songs=build_library(tmp_path)
    bundle=export(tmp_path,songs,kind='regie',name='Concert',layout=layout,sound='both',fps=25)
    ma=bundle/'grandMA3/gma3_library/datapools'
    sequences=list((ma/'sequences').glob('*.xml'))
    timecodes=list((ma/'timecodes').glob('*.xml'))
    assert len(sequences)==2 and len(timecodes)==num
    names={ET.parse(s).find('Sequence').get('Name') for s in sequences}
    for tc in timecodes:
        for track in ET.parse(tc).findall('.//Track'):
            assert track.get('Name') in names
            assert track.findall('.//CmdEvent')
    rows=list(csv.DictReader((bundle/'Conduite.csv').open(encoding='utf-8-sig')))
    assert rows[0]['SMPTE']=='01:00:02:00'
    notes=(bundle/'Paroles-Accords.csv').read_text(encoding='utf-8-sig')
    assert '01:00:04:03' in notes and 'Am' in notes
    script=(bundle/'Build QLab.applescript').read_text()
    assert 'set mode of songGroup to timeline' in script and 'LTC → grandMA3' in script
    stem=next((bundle/'01-Été & feu/audio').glob('001-*.wav'))
    mix=bundle/'01-Été & feu/audio/FOH.wav'
    assert np.allclose(sf.read(mix)[0],sf.read(stem)[0],atol=1e-6)
    other=export(tmp_path,list(reversed(songs)),kind='regie',name='Concert',layout=layout,sound='mix',lyricsPrompter=True)
    assert not list(other.rglob('*.mp4'))
    assert '"video"' not in (other/'Build QLab.applescript').read_text()
    reordered=list(csv.DictReader((other/'Conduite.csv').open(encoding='utf-8-sig')))
    assert {r['Titre / Song']:r['SMPTE'] for r in rows}=={r['Titre / Song']:r['SMPTE'] for r in reordered}
    assert len(list(other.glob('*/audio/*.wav')))==2
    assert (bundle/'Build QLab.applescript').is_file()


def test_batch_failure_publishes_no_partial_show(tmp_path):
    songs=build_library(tmp_path)
    (Path(songs[1]['_root'])/'Audio/source.wav').unlink()
    with pytest.raises(ValueError,match='Finale'):
        export(tmp_path,songs,kind='regie')
    assert not list((tmp_path/'Exports').iterdir())


def test_address_follows_song_and_only_extended_song_moves(tmp_path):
    import sqlite3
    from show_export import time_addresses
    def allocate(songs):
        with sqlite3.connect(tmp_path/'ranges.db') as db:
            return time_addresses(db,songs)
    first = dict(id='one', name='One', duration=20)
    second = dict(id='two', name='Two', duration=20)
    initial, changed = allocate([first, second])
    assert not changed
    assert allocate([second])[0]['two'] == initial['two']
    updated, changed = allocate([dict(first, duration=150), second])
    assert changed == {'one': initial['one']}
    assert updated['one'] > updated['two'] == initial['two']


def test_live_variable_tempo_and_meter(tmp_path):
    from live_set import write_live_set
    points = [dict(time=0,bpm=120,numerator=4,denominator=4,flags=1),
              dict(time=4,bpm=90,numerator=3,denominator=4,flags=1)]
    path = write_live_set(tmp_path,'Tempo.als',[],[dict(time=6,name='Départ')],points,8)
    song = ET.fromstring(gzip.open(path).read()).find('LiveSet')
    assert song.find('Locators/Locators/Locator/Time').get('Value') == '11.0'
    assert song.find('Transport/LoopLength').get('Value') == '14.0'
    tempo = song.find('MasterTrack/DeviceChain/Mixer/Tempo/AutomationTarget').get('Id')
    envelopes = song.findall('MasterTrack/AutomationEnvelopes/Envelopes/AutomationEnvelope')
    env = next(e for e in envelopes if e.find('EnvelopeTarget/PointeeId').get('Value')==tempo)
    assert [(float(e.get('Time')),float(e.get('Value'))) for e in env.find('Automation/Events')][-2:] == [(8,120),(8,90)]
