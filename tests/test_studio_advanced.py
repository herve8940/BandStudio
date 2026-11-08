"""Exercise the new local tools on real media and portable documents."""
import copy
import json
import os
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request
import zipfile
import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import advanced
import phone
from services import atomic,export_reaper,import_reaper
from windows import project as model
from windows.audio import Audio
from windows.host import Api
ENGINE=Path(os.environ.get('BANDSTUDIO_TEST_ENGINE',str(ROOT/'desktop-build/standalone/Engine')))


def project(root):
    (root/'Audio').mkdir(parents=True)
    p=model.fresh('Essai électricité <test>')
    p['settings'].update(countBars=0,countVoice=False,callsEnabled=False,regionCountEnabled=False,exportCount=False,exportGuides=False)
    p['bpm']=120;p['beats']=[.25+i*.5 for i in range(23)];p['capo']=2;p['key']='D'
    for role,hz in [('source',440),('drums',880),('drum_kick',110),('drum_snare',660),('bass',220)]:
        t=np.arange(12*44100)/44100;wave=.1*np.sin(2*np.pi*hz*t)
        sf.write(root/'Audio'/(role+'.wav'),np.column_stack([wave,wave]),44100,subtype='FLOAT')
        p['tracks'].append(model.track(root/'Audio'/(role+'.wav'),root,role,role))
    p['sections']=[dict(id='a',name='Couplet',start=0,end=6,locked=True,origin='manual'),dict(id='b',name='Refrain',start=6,end=12,locked=True,origin='manual')]
    p['lyrics']=[dict(id='lyric',start=1,end=3,text='Été lumineux',manual=True,words=[dict(start=1,end=2,text='Été'),dict(start=2,end=3,text='lumineux')])]
    p['chords']=[dict(id='chord',start=0,end=12,text='D/F#',manual=True)]
    p['_root']=str(root);return p


def test_measure_estimator_requires_consistent_bars():
    beats=np.arange(50)*.5+.25
    result=advanced.musical_grid(beats,beats[3::4],26)
    assert result['beatsPerBar']==4 and result['firstBeat']==1.75
    triple=advanced.musical_grid(beats,beats[1::3],26)
    assert triple['beatsPerBar']==3 and triple['firstBeat']==.75
    irregular=advanced.musical_grid(beats,beats[[0,4,7,11,14,18]],26)
    assert irregular['firstBeat'] is None
    assert advanced.musical_grid([],[],10)['bpm']==0


def test_lyric_formats_roundtrip_offsets_and_boundaries(tmp_path):
    rows=advanced.parse_lyrics('[offset:-250]\n[00:01.25]Été\n[00:02.50][00:04.00]Lumière',5)
    assert [(x['start'],x['end']) for x in rows]==[(1,2.25),(2.25,3.75),(3.75,5)]
    p={'lyrics':rows};advanced.lyric_file(p,tmp_path/'a.srt','srt')
    restored=advanced.parse_lyrics((tmp_path/'a.srt').read_text(),5)
    assert [(x['start'],x['end'],x['text']) for x in restored]==[(x['start'],x['end'],x['text']) for x in rows]
    with pytest.raises(ValueError):advanced.parse_lyrics('Texte sans horaires',5)
    with pytest.raises(ValueError):advanced.parse_lyrics('[99:00]Hors du morceau',5)


def test_portable_archive_has_only_referenced_media(tmp_path):
    p=project(tmp_path/'song');(tmp_path/'song/Analyses').mkdir();(tmp_path/'song/Analyses/private.log').write_text('not shared')
    advanced.portable_project(p,tmp_path/'song',tmp_path/'project.zip')
    with zipfile.ZipFile(tmp_path/'project.zip') as archive:
        assert not any('Analyses' in f for f in archive.namelist())
        doc=json.loads(archive.read(next(f for f in archive.namelist() if f.endswith('project.json'))))
        assert '_root' not in doc and doc['capo']==2
        archive.extractall(tmp_path/'opened')
    restored=model.load(next((tmp_path/'opened').glob('*.bandstudio')))
    assert restored['lyrics'][0]['words']==p['lyrics'][0]['words']
    p['tracks'][0]['file']='../outside.wav'
    with pytest.raises(ValueError):advanced.portable_project(p,tmp_path/'song',tmp_path/'invalid.zip')


def test_drum_parts_replace_parent_in_mix_and_follow_modes(tmp_path):
    p=project(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path)
    def strength(x,hz):
        x=x[4410:22050,0];return abs(np.mean(x*np.exp(-2j*np.pi*hz*np.arange(len(x))/44100)))
    a.mode='mix';mix=a.mix(0,44100)
    assert strength(mix,880)<1e-5 and strength(mix,110)>.03 and strength(mix,220)>.03
    a.mode='minus';mix=a.mix(0,44100)
    assert strength(mix,110)<1e-5 and strength(mix,660)<1e-5 and strength(mix,220)>.03
    a.mode='drums';mix=a.mix(0,44100)
    assert strength(mix,110)>.03 and strength(mix,220)<1e-5
    a.project['tracks'][1]['solo']=True;mix=a.mix(0,44100)
    assert strength(mix,880)>.03 and strength(mix,110)<1e-5


@pytest.mark.parametrize('fmt',['wav','flac','mp3','m4a'])
def test_real_stem_encoders_preserve_duration(tmp_path,fmt):
    p=project(tmp_path);target=tmp_path/('encoded.'+fmt)
    advanced.encode_audio(tmp_path/'Audio/drum_kick.wav',target,ENGINE,fmt)
    decoded=tmp_path/'decoded.wav';advanced.ffmpeg(ENGINE,['-v','error','-i',target,decoded])
    info=sf.info(decoded)
    assert info.duration==pytest.approx(12,abs=.05) and info.channels==2
    x,_=sf.read(decoded);assert np.max(abs(x))>.05


def test_level_normalization_measures_actual_output(tmp_path):
    p=project(tmp_path);target=tmp_path/'master.wav';source=tmp_path/'Audio/source.wav'
    before=source.read_bytes();result=advanced.master(source,target,ENGINE,dict(lufs=-16,peak=-1,lra=11))
    assert source.read_bytes()==before
    assert float(result['after']['input_i'])==pytest.approx(-16,abs=.5)
    assert float(result['after']['input_tp'])<=-.8
    assert sf.info(target).subtype=='PCM_24' and sf.info(target).samplerate==48000
    silent=tmp_path/'silent.wav';sf.write(silent,np.zeros(44100),44100)
    with pytest.raises(ValueError):advanced.master(silent,tmp_path/'bad.wav',ENGINE,{})


def test_audio_report_and_pdf_handle_real_text(tmp_path):
    p=project(tmp_path);info=advanced.audio_report(tmp_path/'Audio/source.wav')
    assert info['peakDBFS']==pytest.approx(-20,abs=.1) and info['nearFullScalePercent']==0
    p['lyrics']*=12
    target=tmp_path/'sheet.pdf';advanced.practice_sheet(p,target,dict(pitch=0))
    assert target.read_bytes().startswith(b'%PDF-') and target.stat().st_size>10000
    assert phone.transpose('D/F#',-2)=='C/E'


def test_word_edits_and_grid_lock_are_saved_and_rejected_atomically(tmp_path):
    p=project(tmp_path);model.save(p,tmp_path);api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path;api._audio.load(p,tmp_path)
    api.command(dict(command='musicSettings',projectID=p['id'],args=dict(capo=4,gridLocked=True)))
    assert model.load(tmp_path)['capo']==4 and api._project['gridLocked']
    api.command(dict(command='studioTask',projectID=p['id'],args=dict(kind='smartgrid')))
    assert 'protégé' in api._notice and not api._busy
    words=[dict(start=1,end=2,text='Très'),dict(start=2,end=2.9,text='bien')]
    api.command(dict(command='annotation',projectID=p['id'],args=dict(kind='lyrics',id='lyric',start=1,end=3,text='Très bien',words=words)))
    assert model.load(tmp_path)['lyrics'][0]['words']==words
    words[1]['start']=1.5
    api.command(dict(command='annotation',projectID=p['id'],args=dict(kind='lyrics',id='lyric',start=1,end=3,text='Bad',words=words)))
    assert model.load(tmp_path)['lyrics'][0]['text']=='Très bien'


def test_reaper_roundtrip_preserves_capo_and_new_drum_routing(tmp_path):
    p=project(tmp_path);p['downbeats']=p['beats'][::4];p['gridLocked']=True;p['_mode']='mix'
    snap=tmp_path/'snapshot.json';atomic(snap,p)
    output=tmp_path/'rpp.json';export_reaper(snap,output);rpp=Path(json.loads(output.read_text())['path'])
    text=rpp.read_text();start=text.index('NAME "drums"');assert 'MUTESOLO 1 0 0' in text[start:start+100]
    imported=tmp_path/'import.json';import_reaper(rpp,imported,ENGINE,snap)
    result=json.loads((Path(json.loads(imported.read_text())['project'])/'project.json').read_text())
    assert result['capo']==2 and result['downbeats']==p['downbeats'] and result['gridLocked']
    assert [t['role'] for t in result['tracks']]==[t['role'] for t in p['tracks']]


def test_phone_requires_session_key_and_exposes_only_stage(tmp_path):
    p=project(tmp_path);atomic(tmp_path/'project.json',p);atomic(tmp_path/'transport.json',dict(position=1.5,playing=True,pitch=0,rate=1,countRemaining=0))
    token='test-session-'+'a'*32;server=phone.server(tmp_path,token)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}/'
    try:
        for path in ['state',token+'/project.json',token+'/../project.json',token+'/Audio/source.wav']:
            with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+path)
            assert error.value.code==404
        with urllib.request.urlopen(base+token+'/state') as response:
            stage=json.load(response);assert response.headers['Cache-Control']=='no-store'
        assert stage['chord']=='C/E' and stage['words'][0]['active']
        assert 'tracks' not in stage and '_root' not in stage and 'sourceURL' not in stage
        assert stage['section']=='Couplet'
    finally:server.shutdown();server.server_close();thread.join()
