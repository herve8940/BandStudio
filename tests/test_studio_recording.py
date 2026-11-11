import json
import sys
import time
import types
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from windows import recording,project
from windows.host import Api
import advanced
ENGINE=Path(__import__('os').environ.get('BANDSTUDIO_TEST_ENGINE',ROOT/'desktop-build/standalone/Engine'))

def test_selected_capture_writes_named_synchronized_wav24(tmp_path,monkeypatch):
    block=np.tile(np.arange(1,19,dtype=np.float32)/100,(4800,1))
    class Stream:
        def __init__(self,**kw):self.callback=kw['callback'];assert kw['channels']==18
        def start(self):
            for i in range(10):self.callback(block,4800,types.SimpleNamespace(inputBufferAdcTime=10+i*.1,currentTime=10+i*.1),False)
        def stop(self):pass
        def close(self):pass
    fake=types.SimpleNamespace(InputStream=Stream,query_devices=lambda:[dict(name='XR test',hostapi=0,max_input_channels=18,default_samplerate=48000)],query_hostapis=lambda i:dict(name='Test'))
    monkeypatch.setitem(sys.modules,'sounddevice',fake)
    host=Api(ENGINE,tmp_path/'library');recording.command(host,dict(action='new',name='Répétition'))
    channels=[dict(input=i,name=n) for i,n in [(1,'Kick'),(3,'Snare'),(18,'Ambiance')]]
    recording.command(host,dict(action='configure',settings={**recording.DEFAULTS,'mode':'live','deviceUID':'Test::XR test','channels':channels}))
    recording.start(host);assert host._record.elapsed==1;recording.stop(host)
    takes=[t for t in host._project['tracks'] if t['role']=='take'];assert len(takes)==3
    for c,t in zip(channels,takes):
        file=host._root/t['file'];info=sf.info(file);data,_=sf.read(file)
        assert info.subtype=='PCM_24' and info.channels==1 and info.frames==48000
        assert t['offset']==0 and t['name']==c['name']+' · prise'
        assert np.allclose(data,c['input']/100,atol=2e-7)
    assert project.load(host._root)['capture']['channels']==channels

def test_mastering_chain_changes_tone_and_mono_width_with_peak_ceiling(tmp_path):
    sr=44100;t=np.arange(sr*8)/sr
    low=np.sin(2*np.pi*80*t)*.04;high=np.sin(2*np.pi*8000*t)*.04
    source=tmp_path/'source.wav';target=tmp_path/'master.wav';sf.write(source,np.column_stack([low+high,low-high]),sr,subtype='FLOAT')
    original=source.read_bytes()
    report=advanced.master(source,target,ENGINE,dict(lowDB=6,highDB=-6,width=0,ratio=2,compressDB=-25,lufs=-16,peak=-1))
    audio,rate=sf.read(target);assert np.allclose(audio[:,0],audio[:,1],atol=2e-7)
    assert float(report['after']['input_tp'])<=-.8
    assert report['chain']['ratio']==2 and report['chain']['lowDB']==6
    assert source.read_bytes()==original
    assert not list(tmp_path.glob('.master-processing-*'))

def test_capture_plan_rejects_duplicate_or_nonexistent_numbers():
    with pytest.raises(ValueError):recording.settings(dict(channels=[dict(input=1,name='A'),dict(input=1,name='B')]))
    with pytest.raises(ValueError):recording.settings(dict(channels=[dict(input=33,name='A')]))
    with pytest.raises(ValueError):recording.settings(dict(latencyMS=float('nan')))

@pytest.mark.parametrize('command',['bandpilot','bridge','studioControl','record','newSession','captureSettings'])
def test_preparation_host_refuses_retired_capture_and_bridge_commands(tmp_path,command):
    host=Api(ENGINE,tmp_path/'library')
    with pytest.raises(ValueError,match='prépare les morceaux'):
        host._command(dict(command=command,args={'on':True,'action':'record'}))


@pytest.mark.parametrize('action',['record','play'])
def test_stop_cancels_transport_while_guides_are_preparing(tmp_path,monkeypatch,action):
    host=Api(ENGINE,tmp_path/'library');recording.command(host,dict(action='new',name='Session'))
    host._project['capture']['mode']='overdub'
    queued=[];started=[]
    monkeypatch.setattr(host,'_op',lambda title,work:queued.append(work))
    monkeypatch.setattr(host,'_guides',lambda:None)
    monkeypatch.setattr(host,'_ready_guides',lambda:False)
    monkeypatch.setattr(recording,'start',lambda host:started.append('record'))
    monkeypatch.setattr(host._audio,'play',lambda:started.append('play'))
    recording.command(host,dict(action=action))
    assert len(queued)==1
    recording.command(host,dict(action='stop'))
    queued[0]()
    assert started==[]
