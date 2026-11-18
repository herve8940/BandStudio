import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
sys.path.insert(0,str(ROOT/'tools'))
import rhythm_quality
from rhythm_benchmark import score,select
from services import calibrate_grid


def evidence():
    beats=np.arange(64)*.5
    beat=np.full(1600,-8.);down=beat.copy()
    beat[(beats*50).astype(int)]=6
    down[(beats[::4]*50).astype(int)]=6
    result=calibrate_grid(dict(beats=beats.tolist(),downbeats=beats[::4].tolist(),bpm=120))
    return result,beat,down


def test_learned_review_preserves_timing_and_survives_worker_host_recalibration(tmp_path,monkeypatch):
    path=tmp_path/'model.json';monkeypatch.setattr(rhythm_quality,'MODEL_PATH',path)
    n=len(rhythm_quality.FEATURES)
    model=dict(schema=1,features=list(rhythm_quality.FEATURES),approved=True,mean=[0]*n,scale=[1]*n,weights=[0]*n,intercept=-4,threshold=.5,version='test')
    path.write_text(json.dumps(model))
    result,b,d=evidence();before=copy.deepcopy(result)
    checked=rhythm_quality.assess(result,b,d)
    assert result==before
    assert checked['gridReviewRequired'] and checked['learnedReviewRequired']
    assert checked['beats']==result['beats'] and checked['firstBeat']==result['firstBeat']
    assert checked==calibrate_grid(calibrate_grid(checked))
    # A learned high score never bypasses insufficient musical evidence.
    model['intercept']=4;path.write_text(json.dumps(model))
    result['downbeats']=result['downbeats'][:2];result=calibrate_grid(result)
    assert rhythm_quality.assess(result,b,d)['gridReviewRequired']


@pytest.mark.parametrize('content',['{', '{}', '{"schema": 500}'])
def test_missing_or_invalid_optional_model_keeps_existing_analysis(tmp_path,monkeypatch,content):
    path=tmp_path/'model.json';monkeypatch.setattr(rhythm_quality,'MODEL_PATH',path)
    r,b,d=evidence();assert rhythm_quality.assess(r,b,d)==r
    path.write_text(content);assert rhythm_quality.assess(r,b,d)==r


def test_scoring_never_matches_one_annotation_to_two_predictions():
    assert score([6,7],[5.96,6.04,7])==pytest.approx(.8)
    assert score([1,2,6,7],[6,7])==1
    assert score([6,7],[])==0


def test_split_assignment_precedes_complexity_selection(tmp_path):
    directory=tmp_path/'beat_this_annotations-1.0/gtzan/annotations/beats';directory.mkdir(parents=True)
    for i in (0,1,59,60,79,80,99):
        np.savetxt(directory/f'gtzan_jazz_{i:05}.beats',np.c_[np.arange(32)*.5,np.arange(32)%4+1])
    selected=select(tmp_path)
    ids={s:{r['id'] for r in selected if r['split']==s} for s in ('train','validation','test')}
    assert len(ids['train'])==3 and len(ids['validation'])==len(ids['test'])==2
    assert not ids['train']&ids['test'] and not ids['validation']&ids['test']
    assert 'gtzan_jazz_00080' in ids['test']


def test_calibration_change_invalidates_cached_confidence(tmp_path,monkeypatch):
    import analysis_cache
    monkeypatch.setattr(analysis_cache,'__file__',str(tmp_path/'analysis_cache.py'))
    for name in ('advanced.py','services.py','rhythm_quality.py'):(tmp_path/name).write_text('# implementation')
    engine=tmp_path/'engine';(engine/'rhythm').mkdir(parents=True);(engine/'rhythm/final0.ckpt').write_bytes(b'weights')
    path=tmp_path/'rhythm-quality.json';path.write_text('{"threshold":0.3}')
    before=analysis_cache.model_signature(engine,'rhythm')
    path.write_text('{"threshold":0.4}')
    assert analysis_cache.model_signature(engine,'rhythm')!=before


def test_update_packages_allow_only_the_named_calibration_data():
    from updater import allowed_path
    assert allowed_path('engine/rhythm-quality.json')
    assert not allowed_path('engine/other.json')
    assert not allowed_path('engine/web/rhythm-quality.json')
    assert not allowed_path('engine/../rhythm-quality.json')
