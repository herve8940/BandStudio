"""New imports calibrate the audible downbeat once, without changing saved edits."""
import copy
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import batch_project
import services
from windows import project as model
from windows.host import Api


def evidence(meter=4,phase=1):
    beats=np.cumsum([.25]+[.48,.5,.52]*16).tolist()
    return dict(beats=beats,downbeats=beats[phase::meter],bpm=120,firstBeat=2.635)


@pytest.mark.parametrize('meter,phase',[(4,1),(3,2)])
def test_variable_tempo_keeps_pulses_and_places_one_on_consistent_bars(meter,phase):
    raw=evidence(meter,phase);before=copy.deepcopy(raw)
    checked=services.calibrate_grid(raw)
    assert raw==before and checked['beats']==raw['beats']
    assert checked['firstBeat']==raw['beats'][phase]
    assert checked['beatsPerBar']==meter and not checked['gridReviewRequired']


@pytest.mark.parametrize('kind',['missing','irregular','offbeat','short'])
def test_ambiguous_evidence_is_flagged_and_never_reuses_another_song_offset(kind):
    raw=evidence()
    if kind=='missing':raw['downbeats']=[]
    elif kind=='irregular':raw['downbeats']=[raw['beats'][i] for i in [0,3,7,10,14,19,23,28]]
    elif kind=='offbeat':raw['downbeats']=[t+.21 for t in raw['downbeats']]
    else:raw['downbeats']=raw['downbeats'][:3]
    checked=services.calibrate_grid(raw)
    assert checked['gridReviewRequired'] and 'à vérifier' in checked['gridStatus']
    assert checked['firstBeat']==raw['beats'][0]


@pytest.mark.parametrize('protection',['locked','fixed','validated','existing','completed'])
def test_calibration_preserves_previous_results(protection):
    p=model.fresh();p['settings']['firstBeat']=2.635
    if protection=='locked':p['gridLocked']=True
    elif protection=='fixed':p['settings']['gridMode']='fixed'
    elif protection=='validated':p['preparation']=dict(fingerprint='approved')
    elif protection=='existing':p['beats']=[.1,.6,1.1]
    else:p['analysesCompleted']=['smartgrid']
    before=copy.deepcopy(p);model.apply_grid(p,evidence())
    assert p==before


def test_queue_resets_inherited_grid_and_calibrates_before_guides(tmp_path):
    library=tmp_path/'library';library.mkdir();root=tmp_path/'song';root.mkdir()
    settings={**model.GUIDE_DEFAULTS,'firstBeat':2.635,'gridMode':'fixed','manualBPM':94,'beatsPerBar':3,'clickGain':1.28}
    services.atomic(library/'defaults.json',settings)
    p=batch_project.snapshot(root,library,'Next song')
    assert p['settings']['firstBeat']==0 and p['settings']['gridMode']=='detected'
    assert p['settings']['clickGain']==1.28
    p['sessionDuration']=30;model.save(p,root)
    folder=tmp_path/'result';folder.mkdir();services.atomic(folder/'result.json',evidence())
    saved=batch_project.apply(dict(id='queue-test',title='Next song'),'smartgrid',root,folder,library)
    assert saved['settings']['firstBeat']==evidence()['beats'][1]
    assert 'automatiquement' in saved['analysisNote']
    before=copy.deepcopy(saved)
    services.atomic(folder/'result.json',evidence(3,2))
    again=batch_project.apply(dict(id='queue-test',title='Next song'),'smartgrid',root,folder,library)
    assert again==before


def test_import_automatically_calibrates_renders_and_reuses_the_grid(tmp_path,monkeypatch):
    engine=tmp_path/'engine';library=tmp_path/'library';library.mkdir()
    from platform_tools import python_for
    python=python_for(engine,'.venv-demucs');python.parent.mkdir(parents=True);python.touch()
    packages='Lib/site-packages' if python.suffix=='.exe' else 'lib/python3.12/site-packages'
    (engine/'.venv-demucs'/packages/'beat_this').mkdir(parents=True)
    source=tmp_path/'New song.wav';sf.write(source,np.zeros((30*44100,2)),44100,subtype='FLOAT')
    services.atomic(library/'defaults.json',{**model.GUIDE_DEFAULTS,'firstBeat':2.635,'clickGain':1.28,'countVoice':False})
    api=Api(engine,library);calls=[]
    monkeypatch.setattr(api,'_decode',lambda source,target:shutil.copy2(source,target))
    monkeypatch.setattr('catalog.extract',lambda *a,**kw:None)
    monkeypatch.setattr('artwork.seed',lambda *a,**kw:None)
    def work(kind,input=None,args=()):
        calls.append(kind);folder=tmp_path/('job-'+str(len(calls)));folder.mkdir()
        out=folder/'result.json'
        if kind=='smartgrid':services.atomic(out,evidence())
        elif kind=='guides':
            snapshot=folder/'project.json';services.atomic(snapshot,api._project)
            services.guides(snapshot,out)
        else:pytest.fail('Unexpected model '+kind)
        return out,json.loads(out.read_text())
    monkeypatch.setattr(api,'_work',work)
    api._import([source])
    assert calls==['smartgrid','guides']
    p=model.load(api._root);assert p['settings']['clickGain']==1.28
    assert p['settings']['firstBeat']==evidence()['beats'][1]
    wave,sr=sf.read(api._root/p['guideFiles']['click'])
    for i,beat in enumerate(p['beats']):
        pulse=wave[round(beat*sr):round(beat*sr)+int(.035*sr),0];t=np.arange(len(pulse))/sr
        hi=abs(np.sum(pulse*np.exp(-2j*np.pi*1760*t)))
        lo=abs(np.sum(pulse*np.exp(-2j*np.pi*1100*t)))
        assert (hi>lo)==(i%4==1)
    api._load(api._root)
    from windows.advanced_host import advanced_task
    advanced_task(api,'smartgrid',{})
    assert calls==['smartgrid','guides']
    assert 'smartgrid' not in api._plan() and 'grid' not in api._plan()
