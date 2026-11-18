"""Exercise the installed worker on real cached SongFormer evidence, without model inference."""
import argparse
import json
from pathlib import Path
import sys


def run(output,engine):
    sys.path.insert(0,str(engine))
    from cue_corrector_runtime import load_approved
    model,reason=load_approved(engine,60)
    if model is None:raise ValueError('Installed corrector is unavailable: '+reason)
    report=json.loads((output/'fresh-report.json').read_text())
    target=next(row for row in report['results'] if row['changes'])
    row=next(r for r in json.loads((output/'analysis/manifest.json').read_text())['tracks'] if r['id']==target['id'])
    raw=json.loads((output/'analysis'/row['id']/'prediction.json').read_text())['raw']
    root=output/'installation-smoke';root.mkdir(exist_ok=True)
    project=dict(_root=str(root),beats=[],sections=[])
    snapshot=root/'project.json';snapshot.write_text(json.dumps(project))
    from analysis_cache import AnalysisCache
    cache=AnalysisCache.create(project,'structure',row['audio'],engine,dict(window=60));cache.store(dict(segments=raw))
    import reacue_structure as structure
    structure.choose_window=lambda:60
    def no_inference():raise RuntimeError('Installation test unexpectedly attempted model inference')
    structure.load_app=no_inference
    import worker
    result_path=root/'result.json';worker.analyze(row['audio'],result_path,'structure',engine,snapshot)
    result=json.loads(result_path.read_text())
    if not result['cacheHit'] or not result['cueCorrection']['applied']:
        raise ValueError('Installed worker did not apply the tested corrector')
    expected=target['correctedSections'];actual=result['sections']
    if len(expected)!=len(actual):raise ValueError('Installed section count differs')
    for a,b in zip(actual,expected):
        if a['name']!=b['name'] or abs(a['start']-b['start'])>1e-5 or abs(a['end']-b['end'])>1e-5:
            raise ValueError('Installed timestamps differ from holdout result')
    if cache.load()['segments']!=raw:raise ValueError('Raw cache was modified')
    proof=dict(passed=True,id=row['id'],cachedInference=True,correctedBoundaries=len(result['cueCorrection']['changes']),
               productionPython=sys.executable,maximumTimestampDifference=max(abs(a['start']-b['start']) for a,b in zip(actual,expected)))
    (root/'verification.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--engine',type=Path,required=True)
    a=p.parse_args();run(a.output.resolve(),a.engine.resolve())
