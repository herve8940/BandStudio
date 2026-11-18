"""Fit a NumPy pairwise linear ranker on TRAIN; select margin/L2 on validation.

Freeze the complete model before a separate --test invocation. Test is never
used for tuning. This learns the meter and first-beat proposal, not Beat This
weights, structural section names, or individual cue texts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from rhythm_benchmark import score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'desktop/studio'))
from advanced import grid_from_frames
from rhythm_adapter import FEATURES, choose, proposals

RUN = ROOT/'tmp/cue-learning'
OUT = ROOT/'output/cue-learning'
DATA = ROOT/'tmp/learning-benchmark/data'


def load(splits):
    rows = json.loads((RUN/'manifest.json').read_text())['excerpts']
    output=[]
    for row in rows:
        if row['split'] not in splits: continue
        z=np.load(RUN/'evidence'/f'{row["id"]}.npz', allow_pickle=False)
        result=grid_from_frames(z['beat'], z['downbeat'], float(z['duration']), quality=False)
        ref=np.loadtxt(DATA/row['annotation'], ndmin=2)
        items=proposals(result, z['downbeat']); beats=np.asarray(result['beats'])
        for item in items:
            item['barF1']=score(ref[ref[:,1]==1,0], beats[item['phase']::item['meter']])
        output.append(dict(row=row, grid=result, down=z['downbeat'], items=items,
                           beatF1=score(ref[:,0], beats)))
    return output


def evaluate(rows, model):
    results=[]
    for r in rows:
        if not r['items']: continue
        selected=choose(r['grid'], r['down'], model)
        choice=next((i for i in r['items'] if selected and i['meter']==selected['meter'] and i['phase']==selected['phase']), r['items'][0])
        results.append(dict(id=r['row']['id'], genre=r['row']['genre'], artist=r['row']['artist'], title=r['row']['title'],
            before=r['items'][0]['barF1'], after=choice['barF1'], beatF1=r['beatF1'], changed=selected is not None,
            beforeMeter=r['items'][0]['meter'], afterMeter=choice['meter'],
            beforeFirst=r['items'][0]['firstBeat'], afterFirst=choice['firstBeat']))
    return results


def summary(rows):
    return dict(count=len(rows), before=float(np.mean([r['before'] for r in rows])),
        after=float(np.mean([r['after'] for r in rows])),
        beatF1=float(np.mean([r['beatF1'] for r in rows])), changed=sum(r['changed'] for r in rows),
        improved=sum(r['after']-r['before']>.1 for r in rows),
        regressions=[r['id'] for r in rows if r['after']-r['before']<-.1])


def train():
    data=load(('train','validation'))
    train=[r for r in data if r['row']['split']=='train']
    validation=[r for r in data if r['row']['split']=='validation']
    x=[]; y=[]; weights=[]
    for r in train:
        if not r['items']: continue
        center=np.mean([i['features'] for i in r['items']],axis=0)
        target=np.mean([i['barF1'] for i in r['items']])
        for candidate in r['items']:
            x.append(np.asarray(candidate['features'])-center)
            y.append(candidate['barF1']-target)
            weights.append(1/len(r['items']))
    x=np.asarray(x); y=np.asarray(y); scale=np.maximum(x.std(axis=0), .05)
    x=x/scale; w=np.sqrt(weights); xw=x*w[:,None]; yw=y*w
    candidates=[]
    for l2 in (.1,1.,10.,100.):
        beta=np.linalg.solve(xw.T@xw+l2*np.eye(x.shape[1]), xw.T@yw)
        for margin in (.025,.05,.1,.15,.2,.3,.5):
            model=dict(schema=1, features=list(FEATURES), scale=scale.tolist(), weights=beta.tolist(),
                       margin=margin, l2=l2, approved=False, version='bar-ranker-20261118-v1')
            metrics=summary(evaluate(validation,model))
            candidates.append((model, metrics))
    eligible=[c for c in candidates if not c[1]['regressions']]
    best=max(eligible or candidates, key=lambda c:(c[1]['after']-c[1]['before'], -c[1]['changed'],c[0]['margin']))
    frozen=dict(model=best[0],validation=best[1],
        validationResults=evaluate(validation,best[0]),train=summary(evaluate(train,best[0])),
        candidates=[dict(l2=m['l2'],margin=m['margin'],**s) for m,s in candidates],
        manifestSHA256=hashlib.sha256((RUN/'manifest.json').read_bytes()).hexdigest(),
        trainerSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        adapterSHA256=hashlib.sha256((ROOT/'desktop/studio/rhythm_adapter.py').read_bytes()).hexdigest(),
        promotion='Validation and test bar F1 each improve by > .01; no excerpt loses > .10 F1; no genre mean falls > .01. Beats unchanged. All adapted grids require listening review. No test-driven retuning.')
    OUT.mkdir(exist_ok=True)
    (OUT/'frozen.json').write_text(json.dumps(frozen,indent=2,ensure_ascii=False))
    print(json.dumps({k:frozen[k] for k in ('train','validation')},indent=2))


def test():
    path=OUT/'frozen.json'; frozen=json.loads(path.read_text())
    assert frozen['trainerSHA256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert frozen['adapterSHA256']==hashlib.sha256((ROOT/'desktop/studio/rhythm_adapter.py').read_bytes()).hexdigest()
    assert frozen['manifestSHA256']==hashlib.sha256((RUN/'manifest.json').read_bytes()).hexdigest()
    rows=evaluate(load(('test',)), frozen['model']); metrics=summary(rows)
    genres={g:summary([r for r in rows if r['genre']==g]) for g in sorted({r['genre'] for r in rows})}
    approved=bool(frozen['validation']['after']-frozen['validation']['before']>.01
        and not frozen['validation']['regressions'] and metrics['after']-metrics['before']>.01
        and not metrics['regressions'] and all(m['after']>=m['before']-.01 for m in genres.values()))
    report=dict(approved=approved,test=metrics,genres=genres,results=rows,frozenSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),
                promotion=frozen['promotion'])
    (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    model={**frozen['model'],'approved':approved,'validation':frozen['validation'],'test':metrics,
           'reportSHA256':hashlib.sha256((OUT/'report.json').read_bytes()).hexdigest()}
    (OUT/'rhythm-adapter.json').write_text(json.dumps(model,indent=2))
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--test',action='store_true'); a=p.parse_args()
    test() if a.test else train()
