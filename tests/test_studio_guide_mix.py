"""Guide controls must change audible audio and survive regeneration and export."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from windows import project as model
from windows.audio import Audio
from windows.host import Api
import preparation
from services import export_reaper, read_rpp
from test_studio_windows import fixture, strength, ENGINE

GUIDES=[('guide_click','clickGain',1100),('guide_voice','callsGain',1320),
        ('guide_cue','cuesGain',1540),('guide_count','countGain',1760)]


def guide_project(root):
    p=fixture(root)
    p['settings'].update(clickEnabled=True,callsEnabled=True,speakCues=True,regionCountEnabled=True,
                         gridMode='fixed',manualBPM=120,exportCount=False)
    for role,key,hz in GUIDES:
        x=(.15*np.sin(np.arange(2*44100)*2*np.pi*hz/44100)).astype('float32')
        file=root/'Audio'/(role+'.wav');sf.write(file,np.column_stack((x,x)),44100,subtype='FLOAT')
        p['tracks'].append(model.track(file,root,role,role));p['settings'][key]=.8
    p['_root']=str(root)
    return p


@pytest.mark.parametrize('role,key,hz',GUIDES)
def test_audible_guide_gain_mute_solo_and_music_solo(tmp_path,role,key,hz):
    p=guide_project(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path);a.mode='mix'
    t=next(t for t in a.project['tracks'] if t['role']==role)
    baseline=strength(a.mix(0,44100),hz);assert baseline>.04
    a.project['settings'][key]=.2
    assert strength(a.mix(0,44100),hz)==pytest.approx(baseline/4,abs=1e-6)
    t['muted']=True;assert strength(a.mix(0,44100),hz)<1e-6
    t.update(muted=False,solo=True)
    for mode in ('original','mix','solo:bass','minus:bass'):
        a.mode=mode;x=a.mix(0,44100)
        assert strength(x,hz)>.01
        assert all(strength(x,other)<1e-6 for other in [440,880,220]+[g[2] for g in GUIDES if g[2]!=hz])
    t['muted']=True;assert np.max(np.abs(a.mix(0,44100)))==0
    t.update(muted=False,solo=False);a.mode='mix';a.project['tracks'][1]['solo']=True
    x=a.mix(0,44100);assert strength(x,880)>.04
    assert all(strength(x,g[2])<1e-6 for g in GUIDES)


def test_host_saves_controls_undoes_them_and_rebuild_keeps_solo(tmp_path,monkeypatch):
    p=guide_project(tmp_path);api=Api(ENGINE,tmp_path);api._root=tmp_path;api._project=p;api._audio.load(p,tmp_path)
    guide=p['tracks'][-2];ident=guide['id'];key=model.guide_key(p)
    def command(name,args={}):
        assert api.command(dict(command=name,args=args,projectID=p['id']))['ok']
    command('track',dict(id=ident,muted=True,solo=True))
    assert model.load(tmp_path)['tracks'][-2]['muted']
    command('undo');assert not api._project['tracks'][-2]['muted']
    command('redo');assert api._project['tracks'][-2]['solo']
    command('guideMix',dict(key='cuesGain',value=.35))
    assert model.load(tmp_path)['settings']['cuesGain']==.35
    assert model.guide_key(api._project)==key
    files={name:str(tmp_path/t['file']) for name,t in zip(['click','calls','cues','counts'],p['tracks'][-4:])}
    monkeypatch.setattr(api,'_work',lambda _: (tmp_path/'result.json',dict(files=files)))
    api._guides(force=True)
    restored=next(t for t in model.load(tmp_path)['tracks'] if t['role']=='guide_cue')
    assert restored['id']==ident and restored['muted'] and restored['solo']
    assert api._project['settings']['cuesGain']==.35


def test_validation_binds_guide_mix_but_not_regenerated_ids(tmp_path):
    p=guide_project(tmp_path);before=preparation.fingerprint(p)
    p['tracks'][-1]['muted']=True;assert preparation.fingerprint(p)!=before
    p['tracks'][-1].update(muted=False,solo=True);assert preparation.fingerprint(p)!=before
    p['tracks'][-1].update(solo=False,id='regenerated');assert preparation.fingerprint(p)==before


def test_reaper_export_matches_guide_solo_and_muting(tmp_path):
    p=guide_project(tmp_path);p['tracks'][-2]['solo']=True;p['settings']['cuesGain']=.35
    def export(name):
        snapshot=tmp_path/(name+'.json');snapshot.write_text(json.dumps(p))
        result=tmp_path/(name+'-result.json');export_reaper(snapshot,result)
        tree=read_rpp(Path(json.loads(result.read_text())['path']))
        def field(t,k):return next(x[1:] for x in t['lines'] if x[0]==k)
        return {field(t,'NAME')[0]:(field(t,'MUTESOLO')[0],float(field(t,'VOLPAN')[0])) for t in tree['children'] if t['kind']=='TRACK'}
    mix=export('solo');assert mix['guide_cue']==('0',.35)
    assert all(muted=='1' for name,(muted,gain) in mix.items() if name!='guide_cue')
    p['tracks'][-2]['muted']=True
    assert all(muted=='1' for muted,gain in export('muted').values())


def test_count_in_does_not_leak_during_cue_solo(tmp_path):
    p=guide_project(tmp_path);p['settings'].update(countBars=2,countClick=True)
    p['tracks'][-2]['solo']=True;a=Audio(ENGINE);a.load(p,tmp_path)
    assert np.max(np.abs(a.make_count(0)))==0
