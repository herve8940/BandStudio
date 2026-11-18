"""Supervised decoder-bias search, with validation and a held-out promotion gate.

This fits two scalar decision parameters, not the pretrained network weights.
Rejected settings remain in the report and are never installed automatically.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from rhythm_benchmark import score

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from advanced import grid_from_frames


def run(args):
    rows=json.loads((args.run/'baseline.json').read_text())
    if len(rows)<110:raise ValueError('Benchmark incomplete')
    evidence={r['id']:np.load(args.run/(r['id']+'.npz'),allow_pickle=False) for r in rows}
    reference={r['id']:np.loadtxt(args.data/r['annotation'],ndmin=2) for r in rows}
    def evaluate(group,beat_bias,bar_bias):
        output=[]
        for row in group:
            z=evidence[row['id']];ref=reference[row['id']]
            result=grid_from_frames(z['beat']-beat_bias,z['downbeat']-bar_bias,float(z['duration']),quality=False)
            beats=np.asarray(result['beats']);phase=int(np.argmin(abs(beats-result['firstBeat']))) if len(beats) else 0
            output.append(dict(id=row['id'],beatF1=score(ref[:,0],beats),barF1=score(ref[ref[:,1]==1,0],beats[phase::result['beatsPerBar']])))
        return output
    def average(group):return {k:float(np.mean([r[k] for r in group])) for k in ('beatF1','barF1')}
    groups={split:[r for r in rows if r['split']==split] for split in ('train','validation','test')}
    train=[]
    for b in (-1.,0.,1.):
        for d in (-1.,0.,1.):
            metrics=average(evaluate(groups['train'],b,d))
            train.append(dict(beatBias=b,barBias=d,train=metrics))
            print('Training candidate',b,d,metrics,flush=True)
    finalists=sorted(train,key=lambda r:-sum(r['train'].values()))[:3]
    # Always retain the unmodified decoder as a validation candidate.
    if not any(r['beatBias']==r['barBias']==0 for r in finalists):
        finalists.append(next(r for r in train if r['beatBias']==r['barBias']==0))
    for candidate in finalists:
        candidate['validation']=average(evaluate(groups['validation'],candidate['beatBias'],candidate['barBias']))
    best=max(finalists,key=lambda r:(sum(r['validation'].values()),-abs(r['beatBias'])-abs(r['barBias'])))
    tested=evaluate(groups['test'],best['beatBias'],best['barBias'])
    before=average(groups['test']);after=average(tested)
    baseval=average(groups['validation'])
    regressions=[r['id'] for r in tested if min(r[k]-next(s[k] for s in groups['test'] if s['id']==r['id']) for k in ('beatF1','barF1'))<-.1]
    approved=bool(sum(after.values())>sum(before.values())+.01 and all(after[k]>=before[k]-.005 for k in before)
                  and sum(best['validation'].values())>sum(baseval.values())+.005 and not regressions)
    report=dict(schema=1,approved=approved,best=best,testBefore=before,testAfter=after,regressions=regressions,candidates=train,validation=finalists,test=tested,
        protocol='Two decoder biases learned with supervised search on train. Top three selected on validation. Fixed held-out promotion: improvement > .005 mean F1, neither beat nor bar F1 falls > .005, and no excerpt falls > .10. No test-driven retuning.')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'decoder-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(approved=approved,best=best,testBefore=before,testAfter=after,regressions=regressions),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
