"""Evaluate the frozen corrected model once on the new holdout, then deploy only if eligible."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
import train_cue_corrector as training
from build_cue_examples import build
from cue_benchmark import sha,write
from cue_corrector import audio_features,boundary_features
from cue_corrector_runtime import apply_model


def verify_plan(plan):
    for name,expected in plan['sources'].items():
        if sha(name)!=expected:raise ValueError('Sealed source changed: '+name)
    for name,expected in plan['inputs'].items():
        if sha(name)!=expected:raise ValueError('Sealed input changed: '+name)


def independent_rows(old,rows):
    keys=lambda data,field:{training.canonical(r[field]) for r in data}
    if len(rows)!=24 or len({r['id'] for r in rows})!=24:raise ValueError('Exactly 24 new songs are required')
    for field in ('artist','title'):
        values=keys(rows,field)
        if len(values)!=24 or values & keys(old,field):raise ValueError('Holdout '+field+' overlap')
    for field in ('id','audioSHA256'):
        if {r[field] for r in rows} & {r[field] for r in old}:raise ValueError('Holdout recording overlap')


def confidence_interval(records):
    """Paired bootstrap by artist/song, keeping the two annotators together."""
    values=[]
    for row in records:
        differences=[s['after']['0.5']['f1']-s['before']['0.5']['f1'] for s in row['scores']
                     if s['after']['0.5']['f1'] is not None and s['before']['0.5']['f1'] is not None]
        if differences:values.append(float(np.mean(differences)))
    if len(values)!=24:raise ValueError('Incomplete holdout metrics')
    rng=np.random.default_rng(20261118);values=np.asarray(values)
    draws=values[rng.integers(0,len(values),size=(5000,len(values)))].mean(axis=1)
    lower,upper=np.quantile(draws,[.025,.975])
    return dict(method='Paired artist/song bootstrap; both annotators stay together',samples=5000,
                lower=float(lower),upper=float(upper),mean=float(values.mean()),level=.95)


def load_old_validation(plan):
    base=Path(plan['base']);previous=base/'corrector-v1-resume'
    rows=json.loads((base/'analysis/manifest.json').read_text())['tracks']
    examples={r['id']:r for r in json.loads((previous/'examples.json').read_text())['tracks']}
    splits=json.loads((previous/'split.json').read_text())['assignment']
    features=json.loads((previous/'feature-manifest.json').read_text())
    snapshot=json.loads((previous/'dataset.json').read_text())
    data=[]
    for row in rows:
        if splits[row['id']]['split']!='validation':continue
        f=previous/'features'/(row['id']+'.json');p=base/'analysis'/row['id']/'prediction.json'
        if sha(f)!=features[row['id']] or sha(p)!=snapshot['inputs'][row['id']]['predictionSHA256']:
            raise ValueError('Original validation evidence changed')
        data.append(dict(row=row,sections=json.loads(p.read_text())['sections'],x=np.asarray(json.loads(f.read_text())['features']),
                         examples=examples[row['id']]['examples']))
    return data


def evaluate(output,plan,state):
    candidate=json.loads((output/'candidate.json').read_text());model=candidate['model']
    rows=json.loads((output/'analysis/manifest.json').read_text())['tracks']
    old=json.loads((Path(plan['base'])/'analysis/manifest.json').read_text())['tracks']
    independent_rows(old,rows)
    ready,_=training.ready(output/'analysis',rows)
    if not ready:raise ValueError('New holdout analysis is incomplete')
    state('verifying_holdout',songs=len(rows))
    examples=build(output/'analysis/manifest.json',output/'analysis',output/'holdout-examples.json')
    cases={r['id']:r for r in examples['tracks']}
    baseline=json.loads((output/'analysis/protocol.json').read_text())
    if baseline['windowSeconds']!=60:raise ValueError('Untested inference window')
    feature_folder=output/'holdout-features';feature_folder.mkdir(exist_ok=True)
    data=[];provenance=[]
    for i,row in enumerate(rows):
        if (output/'STOP').exists():raise InterruptedError('STOP requested')
        state('extracting_holdout_features',completed=i,total=len(rows),current=row['id'])
        if sha(row['audio'])!=row['audioSHA256']:raise ValueError('New audio changed')
        path=output/'analysis'/row['id']/'prediction.json';prediction=json.loads(path.read_text())
        if prediction['provenance']!=baseline or prediction['audioSHA256']!=row['audioSHA256']:
            raise ValueError('New prediction provenance mismatch')
        descriptors=audio_features(row['audio'])
        duration_check=training.validate_decoded_duration(row,descriptors['duration'])
        x=boundary_features(prediction['sections'],descriptors,row['duration'])
        if sha(row['audio'])!=row['audioSHA256']:raise ValueError('New audio changed during feature extraction')
        feature_path=feature_folder/(row['id']+'.json')
        write(feature_path,dict(features=x.tolist(),audioSHA256=row['audioSHA256'],predictionSHA256=sha(path),durationCheck=duration_check))
        data.append(dict(row=row,sections=prediction['sections'],x=x,examples=cases[row['id']]['examples']))
        provenance.append(dict(id=row['id'],audioSHA256=row['audioSHA256'],predictionSHA256=sha(path),featureSHA256=sha(feature_path)))
    verify_plan(plan)
    # No fitting or candidate selection occurs here. The exact production
    # transform (including scope/gap guards) is used for all reported results.
    state('evaluating_frozen_candidate',songs=len(rows))
    validation=training.evaluate(load_old_validation(plan),model,transform=apply_model)
    tested=training.evaluate(data,model,transform=apply_model)
    interval=confidence_interval(tested['records'])
    checks=dict(validation=training.gate(validation['summary']),holdout=training.gate(tested['summary']),
                positive95PercentConfidence=interval['lower']>0,
                knownRegressionPreserved=all(r['unchanged'] for r in candidate['knownRegressionChecks']),
                newPreviouslyGoodTransitionsPreserved=tested['summary']['brokenGood']==0)
    passed=checks['validation']['passed'] and checks['holdout']['passed'] and all(checks[k] for k in
        ('positive95PercentConfidence','knownRegressionPreserved','newPreviouslyGoodTransitionsPreserved'))
    result=dict(schema=1,completedAt=time.time(),candidateSHA256=sha(output/'candidate.json'),
                releasePlanSHA256=sha(output/'release-plan.json'),freshSongs=24,passed=bool(passed),checks=checks,
                validation=validation['summary'],holdout=tested['summary'],confidenceInterval=interval,
                results=tested['records'],provenance=provenance,modelInstalled=False,
                decision='eligible_for_installation' if passed else 'rejected_keep_current_engine',
                limitation='New to this corrector; SALAMI overlap with SongFormer pretraining unknown. Structural transition timing only.')
    write(output/'fresh-report.json',result)
    return result


def run(output,install=False):
    import fcntl
    with (output/'release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10)
        state=lambda stage,**kw:write(output/'release-status.json',dict(stage=stage,pid=os.getpid(),updated=time.time(),**kw))
        try:
            plan=json.loads((output/'release-plan.json').read_text());verify_plan(plan)
            start=time.time();last=None
            while True:
                if (output/'STOP').exists():raise InterruptedError('STOP requested')
                phase=json.loads((output/'holdout-status.json').read_text())
                if phase['stage'] in ('failed','paused'):raise RuntimeError('Holdout job '+phase['stage'])
                if phase['stage']=='complete':break
                status_path=output/'analysis/status.json'
                status=json.loads(status_path.read_text()) if status_path.exists() else {}
                completed=status.get('completed',0)
                if completed!=last:state('waiting_for_holdout',completed=completed,total=24);last=completed
                try:os.kill(phase['pid'],0)
                except ProcessLookupError:raise RuntimeError('Holdout job exited without completion')
                progress=output/'analysis'/str(status.get('current',''))/'progress.json'
                latest=max(phase.get('updated',0),status.get('updated',0),progress.stat().st_mtime if progress.exists() else 0)
                if time.time()-latest>3600 or time.time()-start>48*3600:raise RuntimeError('Holdout progress timed out')
                time.sleep(20)
            verify_plan(plan)
            path=output/'fresh-report.json'
            if path.exists():
                report=json.loads(path.read_text())
                if report['releasePlanSHA256']!=sha(output/'release-plan.json') or report['candidateSHA256']!=sha(output/'candidate.json'):
                    raise ValueError('Final holdout already evaluated under a different protocol')
            else:report=evaluate(output,plan,state)
            if report['passed'] and install:
                state('installing_validated_corrector')
                from install_cue_corrector import install as deploy
                receipt=deploy(output,plan)
                state('complete',decision='installed',modelInstalled=True,installation=str(output/'installation.json'),report=str(path))
            else:
                state('complete',decision=report['decision'],modelInstalled=False,report=str(path))
            return report
        except BaseException as error:
            state('paused' if isinstance(error,InterruptedError) else 'failed',error=type(error).__name__+': '+str(error),modelInstalled=False)
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--install-if-passed',action='store_true')
    a=p.parse_args();run(a.output.resolve(),a.install_if_passed)
