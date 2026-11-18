"""Freeze a conservative candidate using ONLY the already exposed corpus."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time

import train_cue_corrector as training
from cue_benchmark import sha, write
from cue_corrector import correct


def prepare(base, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output/'candidate.json').exists():
        raise ValueError('Candidate already frozen; do not retune a started holdout')
    previous=base/'corrector-v1-resume'
    frozen=json.loads((previous/'frozen-model.json').read_text())
    report=json.loads((previous/'report.json').read_text())
    assert sha(previous/'frozen-model.json')==report['frozenModelSHA256']
    feature_seal=json.loads((previous/'feature-manifest.json').read_text())
    snapshot=json.loads((previous/'dataset.json').read_text())
    original_protocol=json.loads((previous/'protocol.json').read_text())
    manifest=base/'analysis/manifest.json'
    assert sha(manifest)==original_protocol['manifestSHA256']
    rows=json.loads(manifest.read_text())['tracks']
    examples={r['id']:r for r in json.loads((previous/'examples.json').read_text())['tracks']}
    split=json.loads((previous/'split.json').read_text())
    data=[]
    for row in rows:
        features=previous/'features'/(row['id']+'.json');prediction=base/'analysis'/row['id']/'prediction.json'
        assert sha(features)==feature_seal[row['id']]
        assert sha(prediction)==snapshot['inputs'][row['id']]['predictionSHA256']
        data.append(dict(row=row,sections=json.loads(prediction.read_text())['sections'],
                         x=training.np.asarray(json.loads(features.read_text())['features']),
                         examples=examples[row['id']]['examples'],split=split['assignment'][row['id']]['split']))
    alternatives=[frozen['fitting']['timingFits'][key]['weights'] for key in ('constant','ridge_1.0')]
    candidates=[]
    for tolerance in (.1,.15):
        model=copy.deepcopy(frozen['model'])
        model.update(version='cue-corrector-v2',name='ensemble-guard-'+str(tolerance),maximumShiftSeconds=.25,
                     deleteThreshold=0.,approved=False,uncertaintyGuard=dict(kind='ensemble_abstention',
                     maximumDisagreementSeconds=tolerance,alternativeWeights=alternatives))
        validation=training.evaluate([r for r in data if r['split']=='validation'],model)
        candidates.append(dict(model=model,validation=validation,gate=training.gate(validation['summary'])))
    eligible=[c for c in candidates if c['gate']['passed']]
    if not eligible:
        write(output/'preparation-failure.json',candidates)
        raise RuntimeError('No guarded candidate passed the original validation criteria')
    best=max(eligible,key=lambda c:(c['validation']['summary']['after']['f1HalfSecond'],
                                  -c['validation']['summary']['after']['intervalMAESeconds']))
    # This test has been seen and used to motivate the new guard. It is now
    # explicitly a development/regression set, never an independent test again.
    regression=training.evaluate([r for r in data if r['split']=='test'],best['model'])
    previously_broken={(r['id'],p['id']) for r in report['testResults'] for p in r['intervals'] if p['broken']}
    checked=[]
    for item in data:
        target=[s for s in item['sections'] if (item['row']['id'],s['id']) in previously_broken]
        if not target:continue
        corrected,_=correct(item['sections'],item['x'],best['model'],item['row']['duration'])
        after={s['id']:s for s in corrected}
        for s in target:
            unchanged=after[s['id']]['start']==s['start']
            checked.append(dict(song=item['row']['id'],section=s['id'],before=s['start'],after=after[s['id']]['start'],unchanged=unchanged))
    if not checked or not all(r['unchanged'] for r in checked):
        raise RuntimeError('The known regression is not fully preserved')
    record=dict(created=time.time(),model=best['model'],validation=best['validation'],validationGate=best['gate'],
                previousTestNowDevelopment=True,oldRegression=regression,knownRegressionChecks=checked,
                trainingFrozenSHA256=sha(previous/'frozen-model.json'),oldManifestSHA256=sha(manifest),
                correctorSourceSHA256=sha(Path(__file__).resolve().parents[1]/'desktop/studio/cue_corrector.py'),
                evaluatedCandidates=[dict(name=c['model']['name'],summary=c['validation']['summary'],gate=c['gate']) for c in candidates],
                holdoutUsedForSelection=False,approved=False)
    write(output/'candidate.json',record)
    print(json.dumps(dict(candidate=best['model']['name'],validation=best['validation']['summary'],
                         oldRegression=regression['summary'],knownRegressionChecks=checked),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.base.resolve(),a.output.resolve())
