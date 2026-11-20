"""Exact recall and independently checked repeats preserve musical decisions."""
import copy
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import song_memory as memory
import musical_patterns as patterns
import structure_review as review
from test_studio_services import project,ENGINE
from test_studio_manual_editor import manual_page
from test_studio_structure_review import ui_proposal


def two_projects(tmp_path):
    a=tmp_path/'original.bandstudio';a.mkdir();p=project(a);p['_library']=str(tmp_path)
    p['id']='original';p['name']='Already reviewed';p['settings']['gridMode']='detected'
    p['beats']=np.arange(0,12,.5).tolist();p['downbeats']=np.arange(0,12,2).tolist();p['gridLocked']=True
    p['chords']=[dict(id='c',start=0,end=12,text='Am',manual=True)]
    b=tmp_path/'renamed.bandstudio';b.mkdir();q=project(b);q['_library']=str(tmp_path);q['id']='renamed';q['name']='Different filename'
    q['settings']['gridMode']='detected';q['sections']=[];q['beats']=[];q['downbeats']=[]
    return p,q


def test_exact_audio_restores_decisions_under_another_filename(tmp_path):
    p,q=two_projects(tmp_path);before=copy.deepcopy(q)
    memory.remember(p,accepted=True);proposal=review.memory_proposal(q)
    assert proposal['memory']['scope']=='accepted' and proposal['memory']['name']==p['name']
    restored=review.apply_proposal({**q,'structureProposal':proposal})
    assert [(s['start'],s['end'],s['name']) for s in restored['sections']]==[(s['start'],s['end'],s['name']) for s in p['sections']]
    assert restored['beats']==p['beats'] and restored['gridLocked']
    assert restored['chords'][0]['manual'] and restored['chords'][0]['text']=='Am'
    assert restored['tracks']==q['tracks'] and q==before


def test_existing_reviewed_project_is_discovered_without_registration_click(tmp_path):
    p,q=two_projects(tmp_path)
    (Path(p['_root'])/'project.json').write_text(json.dumps({k:v for k,v in p.items() if not k.startswith('_')}))
    proposal=review.memory_proposal(q)
    assert proposal and proposal['memory']['scope']=='reviewed'
    assert len(proposal['sections'])==2 and proposal['restoredGrid']['gridLocked']


def test_metadata_change_is_ignored_but_other_audio_is_not(tmp_path):
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    path=Path(q['_root'])/q['tracks'][0]['file'];audio,sr=sf.read(path,dtype='float32')
    # Same samples in a different lossless WAV representation.
    sf.write(path,audio,sr,subtype='DOUBLE')
    assert memory.recall(q)[1]=='found'
    audio[1000,0]+=.01;sf.write(path,audio,sr,subtype='FLOAT')
    assert memory.recall(q)[0] is None


def test_reviewed_markers_do_not_memorize_unreviewed_predictions(tmp_path):
    p,q=two_projects(tmp_path)
    p['sections'][1].update(origin='analysis',locked=False,reviewed=False)
    p['chords'][0]['manual']=False
    saved=memory.remember(p)
    assert saved['scope']=='reviewed' and len(saved['sections'])==1 and not saved['chords']
    assert saved['grid'] is not None
    recalled,_=memory.recall(q)
    assert len(recalled['project']['sections'])==1 and not recalled['project']['chords']


def test_partial_recall_preserves_uncovered_spans_without_duplicates(tmp_path):
    p,q=two_projects(tmp_path)
    p['sections']=[dict(id='a',name='Verse',start=2,end=4,reviewed=True),dict(id='b',name='Chorus',start=8,end=10,reviewed=True)]
    p['chords']=[];q['sections']=[dict(id='all',name='Instrumental',start=0,end=12,origin='analysis')]
    memory.remember(p);result,_=memory.recall(q)
    assert [(s['start'],s['end']) for s in result['project']['sections']]==[(0,2),(2,4),(4,8),(8,10),(10,12)]


def test_protected_current_decision_wins_over_memory(tmp_path):
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    q['sections']=[dict(id='mine',start=0,end=12,name='My choice',origin='manual')]
    assert memory.recall(q)[1]=='protected_conflict'
    assert review.memory_proposal(q) is None


def test_conflicting_memories_and_tampering_abstain(tmp_path):
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    other=copy.deepcopy(p);other['id']='second';other['sections'][0]['name']='Different'
    memory.remember(other,accepted=True)
    assert memory.recall(q)[1]=='conflict'
    for path in memory.folder(p).glob('*/*.json'):
        v=json.loads(path.read_text());v['sections'][0]['start']=999;path.write_text(json.dumps(v))
    assert memory.recall(q)[0] is None


def test_grid_and_manual_chords_are_preserved_during_recall(tmp_path):
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    q['gridLocked']=True;q['beats']=[0,1,2,3];q['settings'].update(manualBPM=60)
    recalled,_=memory.recall(q)
    assert recalled['project']['beats']==q['beats'] and recalled['project']['settings']==q['settings']
    q['chords']=[dict(id='mine',start=0,end=12,text='D',manual=True)]
    assert memory.recall(q)[1]=='protected_conflict'


def test_manual_grid_correction_updates_previous_accepted_memory(tmp_path):
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    p['beats']=[t+.1 for t in p['beats'] if t+.1<12];p['downbeats']=[t+.1 for t in p['downbeats']]
    p['settings']['firstBeat']=.1
    saved=memory.remember(p)
    assert saved['scope']=='reviewed' and saved['grid']['firstBeat']==.1
    assert memory.recall(q)[0]['project']['beats']==p['beats']


def test_recalled_preparation_exports_actual_regions_and_chord_items(tmp_path):
    from services import atomic,read_rpp
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    q['settings'].update(exportGuides=False,exportCount=False)
    q['structureProposal']=review.memory_proposal(q)
    snap=Path(q['_root'])/'snapshot.json';atomic(snap,q)
    work=Path(q['_root'])/'work';work.mkdir();output=work/'result.json'
    review.export_proposal(snap,output,ENGINE)
    result=json.loads(output.read_text());tree=read_rpp(Path(result['path']))
    chord_track=next(t for t in tree['children'] if ['NAME','Accords'] in t['lines'])
    assert ['NAME','Am'] in chord_track['children'][0]['lines']
    assert result['project']['sections'][0]['name']==p['sections'][0]['name']
    assert result['project']['beats']==p['beats']
    assert result['project']['tracks'][0]['file']==q['tracks'][0]['file']


def test_batch_acceptance_does_not_create_individual_ground_truth(tmp_path):
    p,q=two_projects(tmp_path)
    for s in p['sections']:s.update(origin='reference',locked=True,reviewed=False)
    p['chords'][0]['manual']=False
    memory.remember(p,accepted=True);saved=memory.remember(p)
    assert saved is None # No individually verified labels to register.
    proposal=review.memory_proposal(q)
    assert proposal and not any(review.confirmed(s) for s in proposal['sections'])
    assert not any(c['manual'] for c in proposal['chords'])


def synthetic():
    n=192;edges=np.arange(n+1)*.25;idx=np.arange(n)%64
    harmony=np.eye(12)[(idx//16)%4];bass=harmony.copy();texture=np.tile([.5,.5,.5,.5,0,0],(n,1))
    features=dict(edges=edges,middle=(edges[1:]+edges[:-1])/2,harmony=harmony,bass=bass,texture=texture,
                  harmonyEnergy=np.ones(n),voiceEnergy=np.ones(n)*.5,drumsEnergy=np.tile([1,.6,.2,.3],n//4),available=np.array([1,1,1]))
    p=dict(sections=[dict(id=str(i),name='Couplet' if i==0 else 'Instrumental',start=i*16,end=(i+1)*16,
                         origin='analysis',reviewed=i==0,locked=i==0) for i in range(3)],
           settings=dict(gridMode='fixed',manualBPM=120,firstBeat=0,beatsPerBar=4),beats=[],
           tracks=[dict(role='source',offset=0,duration=48)],chords=[])
    return p,features


def test_one_confirmed_phrase_can_name_two_matching_occurrences():
    p,f=synthetic();before=copy.deepcopy(p)
    result=patterns.analyse(p,f)
    assert result['groups']==[[0,1,2]] and len(result['changes'])==2
    assert all(s['name']=='Couplet' for s in result['sections'])
    assert all(not s['reviewed'] for s in result['sections'][1:]) and p==before


@pytest.mark.parametrize('mismatch',['voice','bass','drums','missing_stem','contradictory_label','locked'])
def test_similar_riff_is_not_enough_to_overwrite_a_passage(mismatch):
    p,f=synthetic();p['sections']=p['sections'][:2]
    if mismatch=='voice':f['voiceEnergy'][64:128]=0
    if mismatch=='bass':f['bass'][64:128]=np.roll(f['bass'][64:128],5,axis=1)
    if mismatch=='drums':f['drumsEnergy'][64:128]=np.tile([0,0,0,1],16)
    if mismatch=='missing_stem':f['available'][1]=0
    if mismatch=='contradictory_label':p['sections'][1].update(reviewed=True,name='Refrain')
    if mismatch=='locked':p['sections'][1]['locked']=True
    result=patterns.analyse(p,f)
    assert not result['changes']


def test_complete_manual_chord_phrase_transfers_without_marking_target_validated():
    p,f=synthetic();pattern=patterns.analyse(p,f);p['sections']=pattern['sections']
    p['chords']=[dict(id=str(i),start=i*4,end=(i+1)*4,text=name,manual=True) for i,name in enumerate(['Am','F','C','G'])]
    chords,transfers=patterns.transfer_chords(p,pattern,f)
    assert len(transfers)==2 and len(chords)==12
    assert chords[:4]==p['chords']
    assert all(not c['manual'] and c['confidence']<.5 for c in chords[4:])
    assert [c['text'] for c in chords]==['Am','F','C','G']*3
    p['chords'].pop()
    assert not patterns.transfer_chords(p,pattern,f)[1]


def test_one_changed_chord_vetoes_transfer_despite_matching_section_average():
    p,f=synthetic();pattern=patterns.analyse(p,f);p['sections']=pattern['sections']
    p['chords']=[dict(id=str(i),start=i,end=i+1,text='Am',manual=True) for i in range(16)]
    # Four cells out of 64: the whole-section similarity can still pass.
    f['harmony'][124:128]=np.roll(f['harmony'][124:128],5,axis=1)
    chords,transfers=patterns.transfer_chords(p,pattern,f)
    assert not any(t['target']=='1' for t in transfers)
    assert any(t['target']=='2' for t in transfers)
    assert not any(16<=c['start']<32 for c in chords)


def test_review_queue_covers_all_uncertain_chords_including_unnamed_spans():
    p,_=synthetic();p['sections']=p['sections'][:2]
    p['chords']=[dict(start=2,end=4,text='Am',confidence=.2),dict(start=18,end=20,text='F',confidence=.3),dict(start=40,end=42,text='C',confidence=.1)]
    clips=patterns.listening_plan(p,[],dict(groups=[[0,1]]))
    assert all(any(clip['start']<=c['start'] and clip['end']>=c['end'] for clip in clips) for c in p['chords'])


def test_windows_recall_reuses_music_and_keeps_existing_stem_preparation(tmp_path,monkeypatch):
    from windows.host import Api
    p,q=two_projects(tmp_path);memory.remember(p,accepted=True)
    host=Api(ENGINE,tmp_path);host._project=q;host._root=Path(q['_root'])
    monkeypatch.setattr(host,'_op',lambda title,work,**kw:work())
    plans=[]
    monkeypatch.setattr(host,'_prepare_all',lambda *a,**kw:plans.append(kw['only']))
    def work(kind):
        assert kind=='structureMemory'
        return tmp_path/'unused.json',dict(proposal=review.memory_proposal(q))
    monkeypatch.setattr(host,'_work',work)
    try:
        host.command(dict(command='reviewStructure',projectID=q['id'],args={}))
        assert host._project['structureProposal']['memory']['sections']==2
        assert plans==[{'separate'}]
    finally:host._audio.close()


def test_chord_only_uncertainty_uses_existing_one_click_listening(manual_page):
    page,p=manual_page;proposal=ui_proposal(p);proposal.update(changes=[],reviewPassages=[dict(id='c',start=2,end=6,reason='Accords'),dict(id='d',start=12,end=16,reason='Variante')],repeatedGroups=1)
    p['structureProposal']=proposal
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert page.locator('#listenStructure').is_enabled()
    assert '2 passages à écouter' in page.locator('#structureReviewListening').inner_text()
    page.locator('#listenStructure').click()
    assert page.evaluate('sent.at(-1).args')==dict(start=2,end=6)
    page.evaluate('studioReceive({type:"transport",position:5.9,playing:true,rate:1,pitch:0,mode:"original",loop:true,loopStart:2,loopEnd:6})')
    assert page.evaluate('sent.at(-1).args')==dict(start=12,end=16)


def test_recall_still_needs_only_existing_two_click_flow(manual_page):
    page,p=manual_page
    page.evaluate('sent=[]')
    page.locator('#reviewStructure').click()
    p['structureProposal']={**ui_proposal(p),'changes':[],'reviewPassages':[],
                            'memory':dict(name='Renamed <song>',scope='accepted',sections=10,chords=50)}
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert 'Préparation retrouvée' in page.locator('#structureReviewSummary').inner_text()
    assert page.locator('#listenStructure').is_disabled()
    page.locator('#exportStructure').click()
    assert page.evaluate('sent.map(m=>m.command)')==['reviewStructure','exportStructure']
    assert page.locator('#prepareAllStructure').is_visible()
