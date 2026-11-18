"""Explicit user requests recalculate; automatic preparation and edits stay protected."""
import copy
import json

import pytest
from test_studio_advanced import project, model, Api, ENGINE
from services import atomic


@pytest.mark.parametrize('kind',['grid','smartgrid'])
def test_explicit_request_replaces_validated_grid_and_can_be_undone(tmp_path,monkeypatch,kind):
    p=project(tmp_path);p['analysesCompleted']=['smartgrid']
    p['preparation']=dict(fingerprint='approved',rate=1,pitch=0,mode='mix')
    before=copy.deepcopy(p)
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path;api._audio.load(p,tmp_path)
    calls=[]
    result=dict(beats=[.1+n*60/113 for n in range(22)],downbeats=[],bpm=113)
    def work(task,audio,args):
        calls.append((task,args));return tmp_path/'result.json',result
    monkeypatch.setattr(api,'_work',work)
    monkeypatch.setattr(api,'_op',lambda title,work:work())
    command='studioTask' if kind=='smartgrid' else 'analyze'
    args=dict(kind=kind,options=dict(reanalyze=True)) if kind=='smartgrid' else dict(kind=kind,reanalyze=True)
    api.command(dict(command=command,projectID=p['id'],args=args))
    assert len(calls)==1
    if kind=='grid':assert '--reanalyze' in calls[0][1]
    else:assert json.loads(calls[0][1][1])['reanalyze'] is True
    saved=model.load(tmp_path)
    assert saved['bpm']==113 and saved['beats']==result['beats']
    assert not saved['preparation'].get('fingerprint')
    assert saved['sections']==before['sections'] and saved['chords']==before['chords']
    assert api._audio.project['beats']==saved['beats']
    api.command(dict(command='undo',projectID=p['id'],args={}))
    assert model.load(tmp_path)['beats']==before['beats']
    assert api._project['bpm']==before['bpm'] and api._project['sections']==before['sections']


@pytest.mark.parametrize('kind',['grid','smartgrid'])
def test_explicit_request_still_respects_grid_lock(tmp_path,monkeypatch,kind):
    p=project(tmp_path);p['gridLocked']=True;before=copy.deepcopy(p)
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path
    monkeypatch.setattr(api,'_work',lambda *a,**kw:pytest.fail('Locked grid reached worker'))
    from windows.advanced_host import advanced_task
    with pytest.raises(ValueError,match='Décoche'):
        if kind=='smartgrid':advanced_task(api,kind,dict(reanalyze=True))
        else:api._analysis(kind,dict(reanalyze=True))
    assert p==before


@pytest.mark.parametrize('kind',['structure','lyrics','chords'])
def test_rerun_preserves_manual_regions_and_annotations(tmp_path,monkeypatch,kind):
    p=project(tmp_path)
    field='sections' if kind=='structure' else kind
    p[field][0]['end']=3
    if kind=='structure':p[field]=p[field][:1]
    keep=copy.deepcopy(p[field])
    p['analysesCompleted']=[kind]
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path
    result={'sections':[dict(start=0,end=12,name='Proposition',origin='analysis',locked=False)]} if kind=='structure' else {'segments':[dict(start=0,end=2,text='Collision',label='C'),dict(start=4,end=6,text='Nouveau',label='G')]}
    if kind=='chords':
        result.update(engine='web-reference',reference=dict(query='Essai',status='found',sources=[],checkedAt=1,message='Calage proposé'))
        for row in result['segments']:row.update(sourceURL='https://www.cifraclub.com/example/song/',confidence=.8)
    monkeypatch.setattr(api,'_work',lambda *a:(tmp_path/'result.json',result))
    api._analysis(kind,dict(reanalyze=True))
    assert all(item in p[field] for item in keep)
    assert len(p[field])==len(keep)+1
    assert p[field][-1]['start']>=3


def test_failed_rerun_keeps_previous_grid_and_validation(tmp_path,monkeypatch):
    p=project(tmp_path);p['preparation']=dict(fingerprint='approved',rate=1,pitch=0,mode='mix')
    model.save(p,tmp_path);before=copy.deepcopy(p)
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path
    def failed(*a):raise RuntimeError('model failed')
    monkeypatch.setattr(api,'_work',failed)
    with pytest.raises(RuntimeError,match='model failed'):api._analysis('grid',dict(reanalyze=True))
    assert p==before and model.load(tmp_path)['preparation']['fingerprint']=='approved'


def test_simple_grid_explicit_rerun_refreshes_cache(tmp_path,monkeypatch):
    import worker
    from test_studio_analysis_cache import setup
    engine,audio,p=setup(tmp_path)
    (engine/'worker.py').write_text('# worker')
    snapshot=tmp_path/'snapshot.json';atomic(snapshot,p)
    calls=[]
    def detect(audio):
        calls.append(audio);return dict(beats=[.25,.75,1.25],bpm=120,downbeats=[])
    monkeypatch.setattr(worker,'grid',detect)
    for index,force in enumerate([False,False,True,False]):
        out=tmp_path/f'job{index}/result.json'
        worker.analyze(audio,out,'grid',engine,snapshot,reanalyze=force)
        assert json.loads(out.read_text())['cacheHit']==(index in (1,3))
    assert len(calls)==2
