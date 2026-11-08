"""Portable document edits and real offline audio mixing for the Windows host."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'desktop/studio'))
from windows import project as model
from windows.audio import Audio
from windows.host import Api

ENGINE=Path(os.environ.get('BANDSTUDIO_TEST_ENGINE',str(ROOT/'desktop-build/standalone/Engine')))


def fixture(root):
    (root/'Audio').mkdir(parents=True,exist_ok=True);p=model.fresh('Essai Windows');p['settings'].update(countBars=0,callsEnabled=False,countVoice=False,regionCountEnabled=False)
    for role,hz in [('source',440),('drums',880),('bass',220)]:
        x=(.15*np.sin(np.arange(2*44100)*2*np.pi*hz/44100)).astype('float32');path=root/'Audio'/(role+'.wav');sf.write(path,np.column_stack((x,x)),44100,subtype='FLOAT');p['tracks'].append(model.track(path,root,role,role))
    p['sections']=[dict(id='one',name='Intro',start=0,end=2,locked=True,origin='manual')];model.save(p,root);return p


def strength(x,hz):
    x=x[4410:22050,0];n=np.arange(len(x));return abs(np.sum(x*np.exp(-2j*np.pi*hz*n/44100)))/len(x)


def test_portable_modes_mute_and_stereo_pan(tmp_path):
    p=fixture(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path)
    for mode,present,absent in [('original',[440],[880,220]),('mix',[880,220],[440]),('drums',[880],[440,220]),('minus',[220],[440,880])]:
        a.mode=mode;x=a.mix(0,44100)
        assert all(strength(x,hz)>.04 for hz in present)
        assert all(strength(x,hz)<.0001 for hz in absent)
    a.mode='drums';a.project['tracks'][1]['pan']=-1;x=a.mix(0,44100);assert np.max(abs(x[:,1]))==0 and np.max(abs(x[:,0]))>.1


def test_loop_has_exact_boundaries_and_preserves_position(tmp_path):
    p=fixture(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path);a.loop=True;a.loopStart=.4;a.loopEnd=.9;a.position=.4;a.play(hardware=False)
    x=a.block(44100);assert a.laps==2 and a.position==pytest.approx(.4,abs=1/44100)
    assert np.max(abs(x))>.05
    a.pause();assert not a.running


def test_native_document_roundtrip_and_path_validation(tmp_path):
    p=fixture(tmp_path);assert model.load(tmp_path)['id']==p['id'];p['tracks'][0]['file']='../private.wav'
    with pytest.raises(ValueError):model.validate(p,tmp_path)


def test_host_edits_reject_stale_project_and_keep_manual_sections(tmp_path):
    p=fixture(tmp_path/'song.bandstudio');api=Api(ENGINE,tmp_path);api._project=p;api._root=tmp_path/'song.bandstudio';api._audio.load(p,api._root)
    api.command(dict(command='notes',args={'value':'bad'},projectID='wrong'));assert p['notes']==''
    api.command(dict(command='splitSection',args={'id':'one','time':.75},projectID=p['id']));assert [s['end'] for s in api._project['sections']]==[.75,2]
    model.apply_sections(api._project,[dict(start=0,end=2,name='Automatic',locked=False,origin='analysis')]);assert len(api._project['sections'])==2
    api.command(dict(command='track',args={'id':p['tracks'][0]['id'],'pan':3},projectID=p['id']));assert api._project['tracks'][0]['pan']==0
    assert model.load(api._root)['sections'][0]['end']==.75


def test_installer_paths_are_not_the_users_reaper_directory():
    source=(ROOT/'desktop/studio/windows/host.py').read_text()
    assert "REAPER_RESOURCE_PATH=str(self._engine/'worker-state')" in source
    assert 'js_api=api' in (ROOT/'desktop/studio/windows/launcher.py').read_text()


def test_slowdown_preserves_pitch_when_ffmpeg_is_available(tmp_path):
    from platform_tools import executable
    if not executable(ENGINE,'ffmpeg').exists():pytest.skip('Prepared engine required')
    p=fixture(tmp_path);a=Audio(ENGINE);a.rate=.75;a.load(p,tmp_path);a.mode='drums';a.render(tmp_path/'slow.wav',0,1.5,False)
    x,sr=sf.read(tmp_path/'slow.wav');assert len(x)==88200 and strength(x,880)>.02 and strength(x,660)<.002
