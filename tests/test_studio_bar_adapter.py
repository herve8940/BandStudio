import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import rhythm_adapter as adapter
from services import calibrate_grid


def evidence():
    beats=(np.arange(64)*.5).tolist()
    result=calibrate_grid(dict(beats=beats,downbeats=beats[::3]))
    down=np.full(1600,-6.)
    for t in beats[1::4]:down[round(t*50)]=8
    return result,np.zeros_like(down),down


@pytest.mark.parametrize('content',['','{}','{"approved":false}','not json'])
def test_missing_or_unapproved_model_never_changes_a_grid(tmp_path,monkeypatch,content):
    p=tmp_path/'model.json';monkeypatch.setattr(adapter,'MODEL_PATH',p)
    r,b,d=evidence();assert adapter.adapt(r,b,d)==r
    p.write_text(content);assert adapter.adapt(r,b,d)==r


def test_confident_grid_is_never_overridden_even_by_an_approved_model(tmp_path,monkeypatch):
    r,b,d=evidence();assert not r['gridReviewRequired']
    weights=[0.]*len(adapter.FEATURES);weights[adapter.FEATURES.index('meter4')]=1.
    model=dict(schema=1,features=list(adapter.FEATURES),scale=[1.]*len(weights),weights=weights,approved=True,margin=.1,version='test')
    p=tmp_path/'model.json';p.write_text(json.dumps(model));monkeypatch.setattr(adapter,'MODEL_PATH',p)
    assert adapter.adapt(r,b,d)==r


def test_learned_proposal_stays_reviewable_and_expires_if_beats_change(tmp_path,monkeypatch):
    r,b,d=evidence();r['gridReviewRequired']=True
    weights=[0.]*len(adapter.FEATURES);weights[adapter.FEATURES.index('barMean')]=1.
    model=dict(schema=1,features=list(adapter.FEATURES),scale=[1.]*len(weights),weights=weights,approved=True,margin=.1,version='test')
    p=tmp_path/'model.json';p.write_text(json.dumps(model));monkeypatch.setattr(adapter,'MODEL_PATH',p)
    proposed=adapter.adapt(r,b,d)
    assert proposed['beats']==r['beats'] and proposed['gridReviewRequired']
    assert proposed['learnedBarProposal']['firstBeat']==.5
    assert calibrate_grid(proposed)==proposed
    changed={**proposed,'beats':[t+.1 for t in proposed['beats']]}
    recalibrated=calibrate_grid(changed)
    assert recalibrated['firstBeat']!=.5
