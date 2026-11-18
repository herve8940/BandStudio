"""Fit on train, choose regularization/threshold on validation, audit test once.

Run after rhythm_benchmark.py. The saved report includes rejected candidates;
only --publish copies a model that passed the predeclared promotion criteria.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from rhythm_quality import FEATURES,features,probability


def fit(x,y,penalty):
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.05)
    a=np.c_[np.ones(len(x)),(x-mean)/scale];w=np.zeros(a.shape[1])
    regularizer=np.eye(len(w))*penalty;regularizer[0,0]=1e-5
    for _ in range(80):
        p=1/(1+np.exp(-np.clip(a@w,-40,40)))
        gradient=a.T@(p-y)+regularizer@w
        hessian=(a.T*(p*(1-p)))@a+regularizer
        step=np.linalg.solve(hessian,gradient);w-=step
        if np.linalg.norm(step)<1e-7:break
    return dict(mean=mean.tolist(),scale=scale.tolist(),intercept=float(w[0]),weights=w[1:].tolist())


def metrics(rows,model=None):
    y=np.array([r['target'] for r in rows],dtype=bool)
    auto=np.array([not r['grid']['gridReviewRequired'] for r in rows])
    probs=np.array([probability(r['features'],model) for r in rows]) if model else auto.astype(float)
    accepted=auto & (probs>=model['threshold']) if model else auto
    return dict(count=len(rows),correct=int(y.sum()),automatic=int(accepted.sum()),
                unsafeAutomatic=int((accepted & ~y).sum()),correctAutomatic=int((accepted & y).sum()),
                brier=float(np.mean((probs-y)**2)))


def train(args):
    rows=json.loads((args.run/'baseline.json').read_text())
    if len(rows)<110:raise ValueError('Wait for the complete benchmark; no partial training run')
    for row in rows:row['evidenceRoot']=args.run
    if args.holdout:
        # Round 1 test has been inspected: it becomes development data, never
        # a test score again. New held-out files have not participated in fitting.
        for row in rows:
            if row['split']=='test':row['split']='validation'
        fresh=json.loads((args.holdout/'baseline.json').read_text())
        if len(fresh)<55:raise ValueError('Fresh holdout incomplete')
        assert not {r['inputSHA256'] for r in rows}&{r['inputSHA256'] for r in fresh}
        rows += [{**r,'evidenceRoot':args.holdout,'split':'test'} for r in fresh]
    for row in rows:
        z=np.load(row['evidenceRoot']/(row['id']+'.npz'),allow_pickle=False)
        row['features']=features(row['grid'],z['beat'],z['downbeat'])
        row['target']=int(min(row['beatF1'],row['barF1'])>=.8)
    groups={s:[r for r in rows if r['split']==s and r['features'] is not None] for s in ('train','validation','test')}
    tr,va,te=(groups[k] for k in ('train','validation','test'))
    x=np.array([r['features'] for r in tr]);y=np.array([r['target'] for r in tr])
    if len(set(y))<2:raise ValueError('Both correct and incorrect grids are required')
    candidates=[]
    before=metrics(va)
    retention=.95 if args.holdout else .8
    for penalty in (.1,1.,10.,100.):
        model=fit(x,y,penalty)
        for threshold in (.05,.1,.2,.3,.4,.5,.6,.7,.8):
            candidate={**model,'threshold':threshold}
            report=metrics(va,candidate)
            # Round 2 explicitly addresses excessive review requests found in
            # round 1: preserve >=95% of correct development-set auto grids.
            if report['correctAutomatic']>=max(1,retention*before['correctAutomatic']):
                candidates.append((report['unsafeAutomatic'],report['brier'],-report['correctAutomatic'],penalty,candidate))
    if not candidates:raise ValueError('No calibration meets validation coverage; no model published')
    best=min(candidates,key=lambda r:r[:4]);model=best[-1]
    summary={s:dict(before=metrics(group),after=metrics(group,model)) for s,group in groups.items()}
    test=summary['test'];validation=summary['validation']
    approved=bool(validation['after']['unsafeAutomatic']<validation['before']['unsafeAutomatic']
        and test['after']['unsafeAutomatic']<test['before']['unsafeAutomatic']
        and test['after']['correctAutomatic']>=max(1,.8*test['before']['correctAutomatic']))
    model.update(schema=1,version='gtzan-quality-2' if args.holdout else 'gtzan-quality-1',features=list(FEATURES),approved=approved,
        training=dict(dataset='GTZAN / Zenodo 13922116',positive='beat F1 >= .80 AND bar F1 >= .80 at 70 ms, after 5 seconds',
            trainIDs=[r['id'] for r in tr],validationIDs=[r['id'] for r in va],testIDs=[r['id'] for r in te],l2=best[3]))
    report=dict(approved=approved,metrics=summary,validationRetention=retention,protocol='Network frozen. Logistic quality head trained on train only. L2 and decision threshold chosen on validation only. Test used once for promotion; at least 80% correct-auto coverage and fewer false-auto grids required on both sets.',
        developmentHistory='Round 1 rejected; its 24 test files moved into validation. 60 new holdout files selected without scores.' if args.holdout else 'Initial 72/24/24 split',
        limitation='Targeted 30-second excerpts, 6 genres; quality gate only, no proof of full-song section accuracy or arbitrary meter handling.',
        excerpts=[dict(id=r['id'],split=r['split'],beatF1=r['beatF1'],barF1=r['barF1'],estimatedQuality=probability(r['features'],model),beforeAutomatic=not r['grid']['gridReviewRequired'],afterAutomatic=not r['grid']['gridReviewRequired'] and probability(r['features'],model)>=model['threshold']) for r in rows])
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'rhythm-quality.json').write_text(json.dumps(model,indent=2))
    (args.output/'quality-report.json').write_text(json.dumps(report,indent=2))
    if args.publish and approved:
        (ROOT/'desktop/studio/rhythm-quality.json').write_text(json.dumps(model,indent=2))
    print(json.dumps(dict(approved=approved,metrics=summary,threshold=model['threshold']),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--publish',action='store_true');p.add_argument('--holdout',type=Path)
    train(p.parse_args())
