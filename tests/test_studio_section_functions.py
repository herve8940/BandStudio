"""Functional proposals must be anchored to the recording, never a web clock."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chart_sections as charts
import section_functions as functions
import structure_review as review
from test_studio_services import project


def song():
    rows=[(0,20,'Intro'),(20,60,'Couplet'),(60,100,'Refrain'),(100,140,'Couplet'),(140,180,'Refrain')]
    return dict(tracks=[dict(role='source',offset=0,duration=180)],beats=np.arange(0,180,.5).tolist(),
                downbeats=np.arange(0,180,2).tolist(),settings=dict(gridMode='detected',beatsPerBar=4),
                sections=[dict(id=str(i),start=a,end=b,name=n,locked=False,origin='analysis') for i,(a,b,n) in enumerate(rows)])


def features():
    edges=np.arange(0,180.25,.25);n=len(edges)-1
    f=dict(edges=edges,middle=(edges[:-1]+edges[1:])/2,available=np.ones(3,dtype=bool))
    for family in ('harmony','bass','voice','drums'):
        f[family+'Energy']=np.ones(n);f[family+'Coverage']=np.ones(n,dtype=bool)
    for family in ('harmony','bass','texture'):f[family]=np.ones((n,12))/np.sqrt(12)
    return f


def event(time,kind,**kw):
    return dict(time=time,kind=kind,method='timed-reference',reason='Test evidence',**kw)


@pytest.mark.parametrize('name,expected',[('Pré-refrain 2','prechorus'),('prechorus','prechorus'),
    ('Post-chorus 1','postchorus'),('postchorus','postchorus'),('Break','break'),('Puente','bridge')])
def test_function_names_do_not_collapse_into_chorus(name,expected):
    assert review.kind(name)==expected
    assert review.kind(review.label(expected))==expected


def test_chart_extracts_only_headed_passages_as_fingerprints():
    page='<nav>[Verse] advertising outside the chart must be ignored</nav><pre>[Pre-Chorus 2]\n<b>Am</b> Amber rivers carry gentle echoes through the night\n[Segunda Parte]\nSilver mornings bring the distant sailors home again\n<script>ignore these unrelated words from a script</script>\n[Break]\nE|-------</pre>'
    blocks=charts.extract(page)
    assert [b['kind'] for b in blocks]==['prechorus','unknown']
    assert blocks[0]['words']==charts.fingerprints('Amber rivers carry gentle echoes through the night')
    assert all(len(w)==20 for b in blocks for w in b['words'])
    assert charts.heading('repeat chorus') is None
    assert charts.fingerprints('L’été')==charts.fingerprints("L'ete")


def test_fingerprint_matching_tolerates_one_wrong_word_but_not_a_generic_hook():
    phrase='Amber rivers carry gentle echoes through the quiet night'
    tokens=charts.fingerprints(phrase)
    words=[dict(key=k,start=20+i*.5,end=20.4+i*.5) for i,k in enumerate(tokens)]
    words[4]['key']=charts.fingerprints('storms')[0]
    assert functions.locate(dict(words=tokens),words)[0]['time']==20
    assert not functions.locate(dict(words=charts.fingerprints('oh oh oh oh oh oh oh oh')),words)


def test_line_only_timing_never_invents_subline_entry_and_stale_words_are_ignored():
    p=dict(lyrics=[dict(text='Amber rivers carry gentle echoes through the night',start=20,end=26,
        words=[dict(text='unrelated earlier transcript',start=10,end=12)])])
    words=functions.timed_words(p)
    assert words[0]['start']==20 and all(w['start'] is None for w in words[1:])
    assert not functions.locate(dict(words=charts.fingerprints('rivers carry gentle echoes through the night')),words)


def test_multilandmark_offset_handles_preroll_but_never_extrapolates_a_different_tail():
    p=song();p['tracks'][0]['duration']+=9
    for row in p['sections']:row['start']+=9;row['end']+=9
    ref=dict(duration=180,entries=[dict(time=s['start']-9,name=s['name']) for s in p['sections']])
    fit=functions.fit_reference(p,ref)
    assert fit['whole'] and fit['offset']==9
    assert functions.mapped_time(fit,170)==179
    p['tracks'][0]['duration']+=20
    fit=functions.fit_reference(p,ref)
    assert not fit['whole'] and functions.mapped_time(fit,170) is None
    assert functions.mapped_time(fit,50)==59


def test_missing_or_ambiguous_landmarks_cannot_fit_reference():
    p=song();ref=dict(duration=180,entries=[dict(time=20,name='Couplet'),dict(time=60,name='Refrain')])
    assert functions.fit_reference(p,ref) is None
    p['sections']=[dict(id=str(t),start=t,end=t+20,name='Couplet') for t in range(0,180,20)]
    ref['entries']=[dict(time=t,name='Couplet') for t in range(20,141,20)]
    assert functions.fit_reference(p,ref) is None


def test_short_stops_and_vocal_gaps_are_not_structural_breaks():
    p=song();f=features();mask=(f['middle']>=30)&(f['middle']<31)
    for key in ('harmony','bass','drums'):f[key+'Energy'][mask]=0
    assert not functions.break_events(p,f)
    f=features();f['voiceEnergy'][(f['middle']>=30)&(f['middle']<34)]=0
    assert not functions.break_events(p,f)


def test_band_break_restores_the_current_function_and_keeps_both_edges():
    p=song();f=features();mask=(f['middle']>=34)&(f['middle']<38)
    for key in ('harmony','bass','drums'):f[key+'Energy'][mask]=0
    breaks=functions.break_events(p,f)
    assert [(b['time'],b['end']) for b in breaks]==[(34,38)]
    rows,changes,_=functions.place_events(p,[event(30,'chorus')]+breaks,f)
    assert [(r['start'],r['name']) for r in rows if 30<=r['start']<=38]==[(30,'Refrain'),(34,'Break'),(38,'Refrain')]
    assert len(changes)==3
    f['bassCoverage'][mask]=False
    assert not functions.break_events(p,f)


@pytest.mark.parametrize('protection',[('locked',True),('reviewed',True),('origin','manual')])
def test_multiple_insertions_and_renames_never_touch_protected_regions(protection):
    p=song();p['sections'][1][protection[0]]=protection[1];before=copy.deepcopy(p)
    rows,changes,_=functions.place_events(p,[event(20,'prechorus'),event(30,'chorus'),event(50,'bridge')],features())
    assert rows==p['sections'] and not changes and p==before


def test_no_bar_phase_no_split_and_gaps_remain_gaps():
    p=song();p['downbeats']=[]
    assert not functions.place_events(p,[event(30,'chorus')],features())[1]
    p=song();p['sections'][1]['end']=30
    rows,changes,_=functions.place_events(p,[event(40,'chorus')],features())
    assert not changes and rows==p['sections']


def test_manual_pulse_wins_over_stale_detected_beats():
    p=song();p['settings'].update(gridMode='fixed',manualBPM=90,firstBeat=0)
    assert functions.pulse(p)==pytest.approx(2/3)


def test_sung_interlude_cannot_become_instrumental(monkeypatch):
    p=song();ref=dict(duration=180,publisher='Example',entries=[dict(time=t,name=n) for t,n in ((0,'Intro'),(20,'Verse'),(40,'Interlude'),(60,'Chorus'),(100,'Verse'),(140,'Chorus'))])
    monkeypatch.setattr(functions,'transition_support',lambda *args:(4,4.))
    events,fit=functions.timed_events(p,ref,features(),[],[])
    assert fit and not any(e['kind']=='instrumental' for e in events)


def test_repeated_singing_requires_audio_coverage_and_matching_harmony():
    f=features();a=dict(time=20,end=30);b=dict(time=60,end=70)
    assert functions.similar_singing(f,a,b)
    f['harmonyCoverage'][(f['middle']>=60)&(f['middle']<70)]=False
    assert not functions.similar_singing(f,a,b)
    f=features();f['harmony'][(f['middle']>=60)&(f['middle']<70)]=0
    assert not functions.similar_singing(f,a,b)


def test_a_named_later_refrain_recovers_a_missing_earlier_occurrence():
    p=song();f=features();words=charts.fingerprints('Amber rivers carry gentle echoes through the quiet night')
    anchors=[dict(time=t,end=t+8,score=.95,kind='unknown',words=words,publisher='Example') for t in (30,60)]
    events=functions.lyric_events(p,f,anchors)
    assert [(e['time'],e['kind']) for e in events]==[(30,'chorus')]
    rows,_,_=functions.place_events(p,events,f)
    assert any(s['start']==30 and s['name']=='Refrain' for s in rows)
    p['sections'][1]['reviewed']=True
    assert not functions.lyric_events(p,f,anchors)


def test_conflicting_sources_are_visible_in_the_proposal(monkeypatch):
    p=song();f=features();ref=dict(duration=180,publisher='Map',entries=[dict(time=t,name=n) for t,n in ((0,'Intro'),(20,'Verse'),(50,'Pre-Chorus'),(60,'Chorus'),(100,'Verse'),(130,'Pre-Chorus'),(140,'Chorus'))])
    monkeypatch.setattr(functions,'transition_support',lambda *args:(2,2.))
    anchors=[dict(time=50,end=58,score=.95,kind='chorus')]
    events,_=functions.timed_events(p,ref,f,[],anchors)
    disputed=next(e for e in events if e['time']==50)
    assert disputed['disputed'] and 'Autre lecture publiée' in disputed['reason']
    rows,changes,warnings=functions.place_events(p,events,f)
    assert warnings and any(c['after']=='Pré-refrain' for c in changes)


def test_malformed_saved_fingerprints_are_ignored():
    p=dict(lyrics=[],chordReference=dict(sources=[dict(anchorSchema=charts.SCHEMA,sectionAnchors=[{},None,dict(kind='verse',name='Verse',words=['wrong']*6)])]))
    assert not functions.chart_anchors(p)


def test_pending_completion_is_not_a_manual_lock_or_new_evidence(monkeypatch):
    p=song();placement=copy.deepcopy(p['sections'])
    placement[2]['end']=80;placement[2]['locked']=True
    placement.insert(3,dict(id='pending',start=80,end=100,name='Post-refrain',locked=True,origin='reference'))
    def timed(initial,*args):
        assert initial['sections']==p['sections']  # No self-confirmation from the pending split.
        return [event(60,'prechorus'),event(70,'chorus')],None
    monkeypatch.setattr(functions,'timed_events',timed)
    result=functions.analyse(p,features(),{'reference':True},placement)
    assert [(s['start'],s['name']) for s in result['sections'] if 60<=s['start']<=80]==[(60,'Pré-refrain'),(70,'Refrain'),(80,'Post-refrain')]


def test_full_proposal_includes_functions_without_changing_saved_document(tmp_path,monkeypatch):
    import structure_sources
    p=project(tmp_path);before=copy.deepcopy(p)
    monkeypatch.setattr(review,'memory_proposal',lambda p:None)
    monkeypatch.setattr(structure_sources,'collect',lambda *a:dict(timed=None,note='',sources=[],checks=[],chart=dict(sources=[],checkedAt=10**12)))
    changed=copy.deepcopy(p['sections']);changed[-1]['name']='Pré-refrain'
    monkeypatch.setattr(functions,'analyse',lambda *a:dict(sections=changed,changes=[dict(id='test',kind='rename',time=changed[-1]['start'],before=p['sections'][-1]['name'],after='Pré-refrain',reason='Test')],warnings=['À écouter'],evidence=dict(timedAnchors=3)))
    result=review.propose(p)
    assert result['sections'][-1]['name']=='Pré-refrain'
    assert result['anchors']==3 and 'À écouter' in result['warnings']
    assert p==before
