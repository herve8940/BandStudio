import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'desktop/studio')]
import cue_benchmark as benchmark
import cue_feedback as feedback
import fetch_cue_corpus as corpus


def project():
    return dict(id='song',tracks=[dict(id='t',file='Audio/a.wav',role='source',offset=0,duration=60)],
                settings=dict(gridMode='detected',firstBeat=0,beatsPerBar=4),beats=[0,.5,1],
                sections=[dict(id='a',name='Couplet',start=0,end=20,reviewed=False),
                          dict(id='b',name='Refrain',start=20,end=60,reviewed=False)],cues=[])


def persist(root,p):
    feedback.record(root,p);(root/'project.json').write_text(json.dumps(p))


def events(root):return [json.loads(p.read_text()) for p in (root/'Learning/events').glob('*.json')]


def test_corrections_need_review_and_undo_revokes_training_example(tmp_path):
    p=project();persist(tmp_path,p)
    p['sections'][1]['start']=21;persist(tmp_path,p)
    assert feedback.references(p,events(tmp_path))==[]
    p['sections'][1]['reviewed']=True;persist(tmp_path,p)
    ref=feedback.references(p,events(tmp_path))[0]
    assert ref['original']['start']==20 and ref['marker']['start']==21 and ref['eventID']
    assert ref['beatReference'] is False
    p['sections'][1]['reviewed']=False;persist(tmp_path,p)
    assert feedback.references(p,events(tmp_path))==[]
    p['sections'][1]['reviewed']=True;persist(tmp_path,p)
    p['sections'].pop();persist(tmp_path,p)
    assert feedback.references(p,events(tmp_path))==[]


def test_failed_project_save_does_not_make_a_reference(tmp_path):
    p=project();persist(tmp_path,p)
    changed=copy.deepcopy(p);changed['sections'][0]['reviewed']=True
    feedback.record(tmp_path,changed) # journal exists, project replacement failed
    saved=json.loads((tmp_path/'project.json').read_text())
    assert feedback.references(saved,events(tmp_path))==[]


def test_volume_changes_do_not_create_examples_and_new_audio_invalidates_pair(tmp_path):
    p=project();persist(tmp_path,p);n=len(events(tmp_path))
    p['settings']['clickGain']=.5;persist(tmp_path,p)
    assert len(events(tmp_path))==n
    p['sections'][1]['reviewed']=True;persist(tmp_path,p)
    p['tracks'][0]['file']='Audio/replacement.wav'
    assert feedback.references(p,events(tmp_path))[0]['original'] is None


def test_new_review_does_not_reuse_a_proposal_from_an_old_grid(tmp_path):
    p=project();persist(tmp_path,p)
    p['settings']['firstBeat']=.2;p['sections'][1]['start']=21;persist(tmp_path,p)
    p['sections'][1]['reviewed']=True;persist(tmp_path,p)
    ref=feedback.references(p,events(tmp_path))[0]
    assert ref['original']['start']==21 # 20 belonged to a different grid


def test_legacy_reviews_do_not_invent_a_prediction_or_beat_ground_truth():
    p=project();p['sections'][0]['reviewed']=True
    ref=feedback.references(p)[0]
    assert ref['original'] is None and ref['eventID'] is None and not ref['beatReference']


def test_boundaries_are_matched_one_to_one_and_choose_minimum_error():
    assert benchmark.match([10,10.2],[10.1],.15)==[(0,0)]
    assert benchmark.match([10],[9.6,10.01],.5)==[(0,1)]
    ref=[dict(start=10,labels=['chorus'])];pred=[dict(start=10,name='Refrain'),dict(start=10.1,name='Refrain')]
    score=benchmark.boundary_score(ref,pred,.5,complete=True)
    assert score['matched']==1 and score['extra']==1 and score['f1']==2/3


def test_partial_reviews_cannot_count_unreviewed_sections_as_false_positives():
    ref=[dict(start=10,labels=['chorus'])];pred=[dict(start=10,name='Refrain'),dict(start=20,name='Pont')]
    score=benchmark.boundary_score(ref,pred,complete=False)
    assert score['recall']==1 and score['precision'] is None and score['extra'] is None


def test_salami_preserves_simultaneous_labels_and_unknown_spans(tmp_path):
    path=tmp_path/'annotation.txt'
    path.write_text('0 Silence\n1 Intro\n4 Verse\n8 Verse\n12 Instrumental\n12 Solo\n16 no_function\n20 End\n')
    r=benchmark.parse_salami(path)
    assert r['segments'][2]==dict(start=4.,end=12.,labels=['verse'])
    assert r['segments'][3]['labels']==['inst','solo']
    assert r['duration']==20
    s=benchmark.structure_score(r,[dict(start=4,name='Couplet'),dict(start=18,name='Pont')])['0.5']
    assert s['predictionCount']==1 and s['matched']==1


def test_archive_derivative_resolution_never_substitutes_another_recording(tmp_path):
    import pytest
    folder=tmp_path/'metadata';folder.mkdir()
    (folder/'a.json').write_text(json.dumps(dict(files=[dict(name='concert_t02.mp3',format='VBR MP3',original='concert_t02.flac')])))
    row=dict(id='a',url='https://archive.org/download/concert/concert_t02_vbr.mp3')
    assert corpus.resolve_audio(row,tmp_path)['downloadURL']=='https://archive.org/download/concert/concert_t02.mp3'
    row['url']='https://archive.org/download/concert/concert_t03_vbr.mp3'
    with pytest.raises(ValueError,match='no longer listed'):corpus.resolve_audio(row,tmp_path)


def test_human_disagreement_does_not_turn_into_a_precise_training_label():
    a=dict(duration=60,segments=[dict(start=10,end=30,labels=['verse']),dict(start=30,end=60,labels=['chorus'])])
    b=dict(duration=60,segments=[dict(start=10.2,end=31,labels=['verse']),dict(start=31,end=60,labels=['chorus'])])
    result=benchmark.consensus_references([a,b])
    assert result['anchors']==[dict(earliest=10,latest=10.2,labels=['verse'],annotators=2)]
    assert len(result['unresolved'])==2 and result['complete'] is False and result['beatReference'] is False


def test_completed_inference_is_saved_before_reporting_finishes(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import analysis_progress
    import run_full_song_benchmark as runner
    monkeypatch.setattr(analysis_progress,'track_structure',lambda *a:nullcontext())
    audio=tmp_path/'audio.wav';audio.write_bytes(b'unchanged input')
    raw=[dict(start=0,end=20,label='verse')]
    model=SimpleNamespace(segments_from_app=lambda *a:raw)
    row=dict(audio=str(audio),audioSHA256=benchmark.sha(audio),duration=20)
    result=runner.predict(model,None,row,tmp_path,{},lambda x,d:x)
    assert result['raw']==raw
    assert json.loads((tmp_path/'prediction.json').read_text())['raw']==raw
    assert json.loads((tmp_path/'progress.json').read_text())['finished'] is True


def test_training_cases_use_two_humans_and_leave_ambiguous_spans_unlabelled():
    from build_cue_examples import classify
    segments=[dict(start=0,end=10,labels=['intro']),dict(start=10,end=30,labels=['verse']),
              dict(start=30,end=50,labels=['chorus']),dict(start=50,end=60,labels=['unknown'])]
    row=dict(duration=60,references=[dict(duration=60,segments=segments),dict(duration=60,segments=copy.deepcopy(segments))])
    pred=[dict(start=10,name='Couplet'),dict(start=20,name='Refrain'),dict(start=32,name='Refrain'),dict(start=55,name='Pont')]
    result=classify(row,pred)
    assert [r['kind'] for r in result['examples']]==['keep_boundary','extra_boundary','move_boundary']
    assert result['unlabelledPredictions']==[pred[-1]]
    assert result['examples'][2]['timingErrorLowerBoundSeconds']==2
