"""Audio placements and portable exchange, using real files rather than UI labels."""
import importlib.util
import json
import os
import sys
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
ENGINE=Path(os.environ.get('BANDSTUDIO_TEST_ENGINE',str(ROOT/'desktop-build/standalone/Engine')))
sys.path.insert(0,str(ROOT/'desktop/studio'))
from platform_tools import executable
spec=importlib.util.spec_from_file_location('studio_services',ROOT/'desktop/studio/services.py')
services=importlib.util.module_from_spec(spec);spec.loader.exec_module(services)


def project(tmp_path):
    settings=dict(clickEnabled=True,clickGain=.45,clickPan=-1,subdivision=2,beatsPerBar=4,firstBeat=0,
                  gridMode='fixed',manualBPM=120,countBars=2,countClick=True,countVoice=True,countGain=.8,countPan=0,
                  countEveryLoop=True,countOnSeek=True,callsEnabled=True,callsGain=.9,callsPan=1,leadBeats=8,
                  voice='Thomas',language='fr',speechRate=210,speakCues=True,regionCountEnabled=True,regionCountBeats=4,
                  exportGuides=True,exportCount=True,loopStep=.05,loopEvery=4,loopMaxRate=1)
    (tmp_path/'Audio').mkdir(exist_ok=True)
    x=(.1*np.sin(np.arange(12*44100)/44100*2*np.pi*440)).astype('float32')
    sf.write(tmp_path/'Audio/source.wav',np.column_stack([x,x]),44100,subtype='FLOAT')
    tracks=[dict(id='source',name='Original "test"',file='Audio/source.wav',role='source',duration=12,offset=0,gain=.8,pan=0,muted=False,solo=False,peaks=[.1]*720)]
    return dict(version=1,id='fixture',name='Morceau test',tracks=tracks,sections=[dict(id='intro',name='Intro',start=0,end=8,locked=True,origin='manual'),dict(id='chorus',name='Refrain',start=8,end=12,locked=True,origin='manual')],
                cues=[dict(id='stop',time=11,name='Stop')],settings=settings,bpm=90,beats=[],notes='',guideFiles={},guideKey='',lyrics=[],chords=[],drumHits=[],key='',sourceURL='',_root=str(tmp_path))


def generate(p,root,monkeypatch):
    def voice(text,folder,settings):
        # A known audible signal lets us verify exact placement and trimming.
        target=folder/(str(abs(hash(text)))+'.wav')
        x=np.full((int(44100*.12),2),.25,dtype='float32');sf.write(target,x,44100,subtype='FLOAT');return target
    monkeypatch.setattr(services,'voice_wav',voice)
    snapshot=root/'snapshot.json';snapshot.write_text(json.dumps(p))
    folder=root/'generated';folder.mkdir(exist_ok=True)
    services.guides(snapshot,folder/'result.json')
    result=json.loads((folder/'result.json').read_text())
    p['guideFiles']={key:str(Path(path).relative_to(root)) for key,path in result['files'].items()}
    for key,role in [('click','guide_click'),('calls','guide_voice'),('counts','guide_count')]:
        p['tracks'].append(dict(id=key,name=key,file=p['guideFiles'][key],role=role,duration=12,offset=0,gain=1,pan=0,muted=False,solo=False,peaks=[]))
    return result


def test_guides_have_audible_calls_counts_and_exact_subdivision(tmp_path,monkeypatch):
    p=project(tmp_path);result=generate(p,tmp_path,monkeypatch)
    click,sr=sf.read(result['files']['click']);calls,_=sf.read(result['files']['calls']);counts,_=sf.read(result['files']['counts'])
    assert sr==44100 and click.shape==(12*sr,2)
    assert result['beats'][1]==.5 # fixed setting must win over the detected BPM=90
    assert np.max(np.abs(click[int(.25*sr):int(.28*sr)]))>.1
    assert np.max(np.abs(click[int(.29*sr):int(.45*sr)]))==0
    assert [(e['time'],e['target']) for e in result['events']]==[(4,8),(7,11)]
    assert calls[int(4*sr),0]==pytest.approx(.25)
    for at in [6,6.5,7,7.5]:assert np.max(np.abs(counts[int(at*sr):int((at+.1)*sr)]))>.2
    assert np.max(np.abs(counts[:int(6*sr)]))==0
    assert np.max(np.abs(counts[int(8*sr):]))==0


def test_variable_grid_anticipation_and_manual_first_beat():
    beats=[0,.5,1,1.6,2.2,2.8,3.5]
    assert services.before_beat(3.6,4,beats,120)==pytest.approx(1.1)
    assert services.before_beat(.5,4,beats,120)==pytest.approx(-1.5)


@pytest.mark.parametrize('target,grid,expected',[
    (8.13,[],[6,6.5,7,7.5]),
    (7.88,[],[6,6.5,7,7.5]),
    (8,[],[6,6.5,7,7.5]),
    (8.07,[0,.52,1.03,1.55,2.1,2.65,3.2,3.75,4.31,4.86,5.42,5.99,6.55,7.10,7.64,8.2,8.75,9.3,9.85,10.4,10.95,11.5],
     [5.99,6.55,7.10,7.64]),
])
def test_offbeat_region_counts_land_on_audible_metronome_clicks(tmp_path,monkeypatch,target,grid,expected):
    p=project(tmp_path);p['sections']=[dict(id='region',name='Refrain',start=target,end=12,locked=True,origin='manual')]
    p['beats']=grid;p['settings'].update(gridMode='detected' if grid else 'fixed',countClick=False,leadBeats=0)
    result=generate(p,tmp_path,monkeypatch)
    click,sr=sf.read(result['files']['click']);counts,_=sf.read(result['files']['counts'])
    assert [x['time'] for x in result['countEvents']]==expected
    assert [x['number'] for x in result['countEvents']]==[1,2,3,4]
    starts=np.flatnonzero(np.diff(np.r_[False,counts[:,0]>.1].astype(int))==1)
    assert list(starts)==[round(at*sr) for at in expected]
    for at in starts:
        assert np.max(np.abs(click[at:at+100]))>.2
        assert np.max(np.abs(counts[max(0,at-100):at]))==0
    assert np.max(np.abs(counts[round(target*sr):]))==0
    assert result['events'][0]['time']+.12<=expected[0]-.049
    assert p['sections'][0]['start']==target # Do not move manual or estimated region boundaries.


def test_region_count_uses_only_available_beats_and_keeps_number_order():
    assert services.region_count_beats(0,4,[0,.5,1])==[]
    assert [(e['number'],e['time']) for e in services.region_count_beats(1,4,[0,.5,1])]==[(3,0),(4,.5)]
    assert services.region_count_beats(10,4,[0,.5,1])==[] # No fabricated count after detection stops.


def test_manual_downbeat_accent_uses_the_chosen_beat_without_moving_pulses(tmp_path,monkeypatch):
    p=project(tmp_path);p['beats']=[1+i*.5 for i in range(20)]
    p['settings'].update(gridMode='detected',firstBeat=6.5,subdivision=1)
    result=generate(p,tmp_path,monkeypatch);click,sr=sf.read(result['files']['click'])
    assert result['beats']==p['beats']
    for i,beat in enumerate(p['beats']):
        at=round(beat*sr);pulse=click[at:at+int(sr*.035),0];t=np.arange(len(pulse))/sr
        low=abs(np.sum(pulse*np.exp(-2j*np.pi*1100*t)))
        high=abs(np.sum(pulse*np.exp(-2j*np.pi*1760*t)))
        assert (high>low*5) if i%4==3 else (low>high*5)


def test_portable_reaper_export_keeps_counts_regions_pan_and_original_mute(tmp_path,monkeypatch):
    p=project(tmp_path);generate(p,tmp_path,monkeypatch)
    p['tracks'].append({**p['tracks'][0],'id':'drums','role':'drums','name':'Batterie','solo':True})
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p));out=tmp_path/'result.json'
    services.export_reaper(snapshot,out)
    result=json.loads(out.read_text());rpp=Path(result['path']);text=rpp.read_text()
    assert result['preroll']==4
    assert 'TEMPO 120 4 4' in text
    assert 'MARKER 2 12.000000000 "Refrain" 1' in text
    assert 'MARKER 3 15.000000000 "Stop" 0' in text
    assert 'MUTESOLO 1 0 0' in text
    assert 'VOLPAN 0.90000000 1.00000000' in text
    assert 'Annonce de départ' in text
    assert str(tmp_path) not in text
    for line in text.splitlines():
        if line.strip().startswith('FILE '):assert (rpp.parent/line.strip()[6:-1]).is_file()
    count,sr=sf.read(rpp.parent/'Audio/count-in.wav');assert len(count)==4*sr
    assert np.max(np.abs(count[int(2*sr):]))>.2


@pytest.mark.parametrize('url',['file:///etc/passwd','javascript:alert(1)','https://user:pass@example.com/a','https://example.com/a\n--exec=oops'])
def test_link_rejects_non_public_url_syntax(url):
    with pytest.raises(ValueError):services.checked_url(url)


@pytest.mark.parametrize('extension,codec',[('mp3','libmp3lame'),('flac','flac'),('ogg','libvorbis'),('opus','libopus'),('wma','wmav2'),('aiff','pcm_s16be'),('m4a','aac'),('mkv','flac')])
def test_ffmpeg_import_real_audio_formats(tmp_path,extension,codec):
    ffmpeg=executable(ENGINE,'ffmpeg')
    if not ffmpeg.exists():pytest.skip('Prepared local engine required')
    src=tmp_path/('audio.'+extension);dest=tmp_path/'decoded.wav'
    services.run([ffmpeg,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.4','-c:a',codec,src])
    services.decode(src,dest,ENGINE)
    x,sr=sf.read(dest);assert sr==44100 and x.shape[1]==2
    assert .35<len(x)/sr<.6 and np.max(np.abs(x))>.03


def test_export_midi_real_smf_header_and_drum_channel(tmp_path):
    path=tmp_path/'drums.mid';services.export_midi({'drumHits':[dict(time=1,pitch=36,velocity=110)]},path)
    data=path.read_bytes();assert data[:4]==b'MThd' and data[14:18]==b'MTrk'
    assert b'\x99\x24\x6e' in data and data.endswith(b'\xff\x2f\x00')


def test_reaper_audio_region_count_roundtrip(tmp_path,monkeypatch):
    if not (executable(ENGINE,'ffmpeg')).exists():pytest.skip('Prepared engine required')
    p=project(tmp_path);generate(p,tmp_path,monkeypatch)
    p['lyrics']=[dict(id='line',start=1,end=2,text='Hello',manual=True)]
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    services.export_reaper(snapshot,tmp_path/'export.json')
    rpp=Path(json.loads((tmp_path/'export.json').read_text())['path'])
    output=tmp_path/'import/result.json';services.import_reaper(rpp,output,ENGINE,snapshot)
    imported=json.loads((Path(json.loads(output.read_text())['project'])/'project.json').read_text())
    assert imported['tracks'][0]['offset']==4
    assert imported['tracks'][0]['duration']==pytest.approx(12,abs=.001)
    assert [(x['name'],x['start'],x['end']) for x in imported['sections']]==[('Intro',4,12),('Refrain',12,16)]
    assert imported['cues'][0]['time']==15
    assert imported['settings']['countBars']==0
    assert imported['settings']['manualBPM']==120
    assert imported['lyrics'][0]['start']==5 and imported['lyrics'][0]['manual'] is True


def test_reaper_import_keeps_source_offset_and_item_rate(tmp_path):
    if not (executable(ENGINE,'ffmpeg')).exists():pytest.skip('Prepared engine required')
    p=project(tmp_path);snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    rpp=tmp_path/'offset.rpp';rpp.write_text('''<REAPER_PROJECT 0.1 7.0 1
 TEMPO 96 4 4
 <TRACK
 NAME "Batterie"
 VOLPAN 0.7 -0.5
 MUTESOLO 0 0 0
 <ITEM
 POSITION 1.25
 SOFFS 2
 LENGTH 3
 PLAYRATE 0.75 1 0 -1 0
 <SOURCE WAVE
 FILE "Audio/source.wav"
 >
 >
 >
>
''')
    output=tmp_path/'import/result.json';services.import_reaper(rpp,output,ENGINE,snapshot)
    root=Path(json.loads(output.read_text())['project']);track=json.loads((root/'project.json').read_text())['tracks'][0]
    assert track['offset']==1.25 and track['duration']==pytest.approx(3,abs=.01)
    assert track['role']=='drums' and track['pan']==-.5 and track['gain']==.7
    x,sr=sf.read(root/track['file']);window=x[int(sr):int(2*sr),0];freq=np.argmax(abs(np.fft.rfft(window)))
    assert abs(freq-440)<=2 # slowdown preserves pitch
