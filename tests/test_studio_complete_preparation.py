"""One-click orchestration, trustworthy automatic decisions and chart selection."""
import copy
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from test_studio_structure_review import proposal, review
from test_studio_services import project
from test_studio_advanced import Api, model
from platform_tools import python_for
import batch_project
import chord_choice


def installed(root):
    for env in ('.venv','.venv-demucs','.venv-creative','.venv-words','.venv-structure'):
        path=python_for(root,env);path.parent.mkdir(parents=True,exist_ok=True);path.touch()
    for name in ('drumsep/49469ca8.th','creative/UVR_MDXNET_KARA_2.onnx'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
    return root


def test_pipeline_order_and_resume_without_duplicate_chords(tmp_path):
    engine=installed(tmp_path/'engine');p=project(tmp_path)
    p['settings']['gridMode']='detected';p['key']='';p['sections']=[]
    api=Api(engine,tmp_path/'library');api._project=p;api._root=tmp_path
    assert api._plan()==['separate','drumsep','vocalsplit','grid','structure','key','lyrics','prepareReview','guides']
    queue=batch_project.plan(engine)
    assert queue==['import',*api._plan()]
    # An interrupted partial drum separation must not count as complete.
    for role in ('drums','vocals','bass','other','drum_kick'):
        p['tracks'].append({**p['tracks'][0],'id':role,'role':role})
    assert api._plan()[:2]==['drumsep','vocalsplit']
    for role in ('drum_snare','drum_toms','drum_cymbals','vocal_lead','vocal_backing'):
        p['tracks'].append({**p['tracks'][0],'id':role,'role':role})
    p.update(analysesCompleted=['grid','structure','lyrics'],key='A',lyricsReference={'status':'not_found'},structureProposal={'status':'prepared'})
    p['guideKey']=model.guide_key(p)
    assert api._plan()==['prepareReview','guides']
    p['structureProposal']['sectionTimingVersion']=1
    assert api._plan()==[]
    p['chordReference']={'status':'unavailable','sources':[],'checks':[{'id':'publisher','status':'unavailable'}]}
    assert api._plan()==['chords']
    p['chordReference']['retryAfter']=float('inf')
    assert api._plan()==[]
    # A manual edit invalidates only final review and affected guides.
    p.pop('structureProposal');assert api._plan()==['prepareReview','guides']


def test_missing_optional_models_do_not_claim_separations(tmp_path):
    engine=tmp_path/'engine';engine.mkdir();p=project(tmp_path)
    api=Api(engine,tmp_path/'library');api._project=p;api._root=tmp_path
    assert api._plan()==['key','prepareReview','guides']


def test_batch_preserves_each_lyric_timing_warning(tmp_path):
    p=project(tmp_path)
    edited=dict(id='protected',text='My line',start=2,end=2.5,manual=True)
    p['lyrics']=[edited];model.save(p,tmp_path)
    job=tmp_path/'job';job.mkdir()
    (job/'result.json').write_text(json.dumps(dict(segments=[
        dict(t=.2,end=.7,text='uncertain',timingReview=True,confidence=.8,words=[dict(w='uncertain',t=.2,end=.7,timingReview=True)]),
        dict(t=1,end=1.5,text='aligned',timingReview=False,confidence=.8),
        dict(t=2,end=2.3,text='overlapping guess')])))
    result=batch_project.apply(dict(id='clean',title='Example'),'lyrics',tmp_path,job,tmp_path.parent)
    assert [row['timingReview'] for row in result['lyrics'][:2]]==[True,False]
    saved=model.load(tmp_path)['lyrics']
    assert saved[0]['words'][0]['timingReview'] and saved==result['lyrics']
    assert len(saved)==3 and saved[-1]==edited


@pytest.mark.parametrize('kind,parent_role,roles',[
    ('drumsep','drums',['drum_kick','drum_snare','drum_toms','drum_cymbals']),
    ('vocalsplit','vocals',['vocal_lead','vocal_backing'])])
def test_new_subtracks_keep_parent_mix_and_existing_subtrack_edits(tmp_path,monkeypatch,kind,parent_role,roles):
    p=project(tmp_path);parent={**p['tracks'][0],'id':'parent','role':parent_role,'gain':.31,'pan':-.4,'muted':True}
    old={**parent,'id':'child','role':roles[0],'gain':.72,'pan':.6,'muted':False,'solo':True}
    p['tracks'] += [parent,old]
    engine=tmp_path/'engine';engine.mkdir();api=Api(engine,tmp_path/'library');api._project=p;api._root=tmp_path
    folder=tmp_path/'job';folder.mkdir();path=folder/'result.json'
    target=folder/'part.wav';shutil.copy2(tmp_path/'Audio/source.wav',target)
    result=dict(tracks=[dict(role=role,path=str(target)) for role in roles])
    monkeypatch.setattr(api,'_work',lambda *a,**kw:(path,result))
    if kind=='drumsep':api._analysis(kind,{})
    else:
        from windows.creative_host import creative_task
        creative_task(api,kind,{})
    for role in roles:
        track=next(t for t in api._project['tracks'] if t['role']==role)
        expected=old if role==roles[0] else parent
        assert all(track[k]==expected[k] for k in ('gain','pan','muted'))
        if role==roles[0]:assert track['id']==old['id'] and track['solo']


def test_automatic_final_review_keeps_manual_work_and_has_honest_receipt(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections'][1].update(locked=False,origin='analysis')
    p['chords']=[dict(id='hand',start=0,end=2,text='A',manual=True)]
    p['preparation']=dict(rate=1,pitch=0,mode='mix',fingerprint='human',validatedAt=1)
    draft=proposal(p);draft['sections'][1].update(name='Pont',locked=True,reviewed=False,origin='reference')
    monkeypatch.setattr(review,'propose',lambda current:copy.deepcopy(draft))
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p));output=tmp_path/'result.json'
    review.finish_preparation(snapshot,output,tmp_path)
    after=json.loads(output.read_text())['project']
    assert after['sections'][0]==p['sections'][0]
    assert after['sections'][1]['name']=='Pont' and after['sections'][1]['origin']=='automatic-review'
    assert not after['sections'][1]['locked'] and not after['sections'][1]['reviewed']
    for key in ('tracks','cues','chords','settings','beats'):assert after[key]==p[key]
    assert 'validatedAt' not in after['preparation']
    receipt=after['structureProposal'];assert receipt['status']=='prepared'
    from musical_timing import prepare_clock
    clock,correction=prepare_clock(after)
    assert correction is None and after['timingGrid']==clock.payload()
    assert receipt['beforeSections']==p['sections'] and receipt['sections']==after['sections']
    assert receipt['fingerprint']==review.fingerprint(after)
    event=json.loads(next((tmp_path/'Learning/structure-reviews').glob('*.json')).read_text())
    assert event['action']=='prepared_automatically' and 'no marker' in event['labelPolicy']
    with pytest.raises(ValueError,match='déjà'):review.apply_proposal(after)
    assert json.loads(snapshot.read_text())==p


def test_automatic_review_rejects_protected_edits_and_changed_media(tmp_path,monkeypatch):
    p=project(tmp_path);draft=proposal(p);draft['sections'][0]['name']='Unwanted'
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p));out=tmp_path/'result.json'
    monkeypatch.setattr(review,'propose',lambda current:copy.deepcopy(draft))
    with pytest.raises(ValueError,match='protégée'):review.finish_preparation(snapshot,out,tmp_path)
    assert not out.exists()
    draft=proposal(p)
    def changed(current):
        with (tmp_path/'Audio/source.wav').open('ab') as f:f.write(b'changed')
        return draft
    monkeypatch.setattr(review,'propose',changed)
    with pytest.raises(ValueError,match='changé'):review.finish_preparation(snapshot,out,tmp_path)
    assert not out.exists()


def test_chart_choice_prioritizes_recording_and_keeps_explicit_choice():
    harmony=np.zeros((64,12));harmony[:,[0,4,7]]=1/np.sqrt(3)
    features=dict(harmony=harmony,harmonyEnergy=np.ones(64),harmonyCoverage=np.ones(64,dtype=bool))
    wrong=dict(url='wrong',chords=['F#'],rating=5,ratingCount=100000)
    right=dict(url='right',chords=['C'],rating=1,ratingCount=1)
    picked,reason=chord_choice.choose({},[wrong,right],features)
    assert picked==right and 'concordance' in reason and 'populaire' not in reason
    assert chord_choice.choose({'chordReference':dict(selectedURL='wrong',selectionMode='manual')},[wrong,right],features)[0]==wrong


def test_chart_in_another_key_requires_agreement_throughout_the_recording():
    from chord_alignment import tones
    from musical_patterns import ROLES
    from chord_sources import transposed_chart
    source=dict(url='written',chords=['C/E','Am','F','G'],transitions=[['F','G']],
                sectionSequences=[dict(kind='verse',chords=['C/E','Am'],repeat=2)])
    original=copy.deepcopy(source)
    sounding=transposed_chart(source,3)
    h=np.zeros((160,12));b=np.zeros_like(h)
    for i in range(len(h)):
        pcs,root=tones(sounding['chords'][(i//5)%4])
        h[i,pcs]=1/np.sqrt(len(pcs));b[i,root]=1
    on=np.ones(len(h),dtype=bool)
    f=dict(harmony=h,bass=b,harmonyEnergy=on,bassEnergy=on,harmonyCoverage=on,bassCoverage=on,
           roles=[r in ('other','bass') for r in ROLES])
    picked,_=chord_choice.choose({},[source],f)
    assert picked['recordingTranspose']==3 and picked['chords']==['D#/G','Cm','G#','A#']
    assert picked['transitions']==[['G#','A#']] and picked['sectionSequences'][0]['chords']==['D#/G','Cm']
    assert original==source
    assert chord_choice.choose({},[source,{**sounding,'url':'original'}],f)[0]['url']=='original'
    assert 'recordingTranspose' not in chord_choice.choose({},[source],{**f,'bassCoverage':~on})[0]
    h[:40]=np.roll(h[:40],-3,axis=1);b[:40]=np.roll(b[:40],-3,axis=1)
    assert 'recordingTranspose' not in chord_choice.choose({},[source],f)[0]


@pytest.mark.parametrize('name,value,count,expected',[
    ('Starlight chords',4.6,100,True),('Whole website',5,900000,False),
    ('Starlight',float('inf'),3,False),('Starlight',6,10,False),('Starlight',4,-1,False)])
def test_public_ratings_must_belong_to_the_song(name,value,count,expected):
    page='<script type="application/ld+json">'+json.dumps(dict(name=name,aggregateRating=dict(ratingValue=value,ratingCount=count)))+'</script>'
    assert bool(chord_choice.reputation(page,'Starlight'))==expected
