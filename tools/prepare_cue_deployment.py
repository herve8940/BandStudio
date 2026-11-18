"""Seal the reviewed implementation and conditional installation before new scores exist."""
import argparse
import json
from pathlib import Path
import shutil
import time

from cue_benchmark import sha,write
import train_cue_corrector as training


def prepare(base,output,installation_record):
    root=Path(__file__).resolve().parents[1]
    if (output/'fresh-report.json').exists() or (output/'release-plan.json').exists():
        raise ValueError('Release already sealed or new holdout already evaluated')
    candidate=json.loads((output/'candidate.json').read_text())
    if sha(root/'desktop/studio/cue_corrector.py')!=candidate['correctorSourceSHA256']:
        raise ValueError('Frozen corrector changed')
    verification=json.loads((output/'verification.json').read_text())
    if verification['testsPassed']<60:raise ValueError('Required implementation checks did not pass')
    installation=json.loads(installation_record.read_text());engine=Path(installation['engine']);library=Path(installation['library'])
    stage=output/'stage';stage.mkdir(exist_ok=True)
    names=['cue_corrector.py','cue_corrector_runtime.py','worker.py']
    for name in names:shutil.copy2(root/'desktop/studio'/name,stage/name)
    sources=[root/'desktop/studio'/name for name in names]
    sources += [Path(__file__).with_name(name) for name in (
        'prepare_cue_deployment.py','prepare_cue_release.py','run_cue_holdout.py','run_full_song_benchmark.py',
        'validate_cue_release.py','install_cue_corrector.py','smoke_cue_installation.py',
        'train_cue_corrector.py','cue_benchmark.py','build_cue_examples.py')]
    inputs=[output/'candidate.json',output/'selection.json',output/'verification.json',
            output/'analysis/manifest.json',output/'analysis/protocol.json',base/'analysis/manifest.json',installation_record]
    inputs += [base/'corrector-v1-resume'/name for name in (
        'frozen-model.json','examples.json','split.json','feature-manifest.json','dataset.json')]
    plan=dict(schema=1,created=time.time(),base=str(base),engine=str(engine),library=str(library),
              sources={str(p):sha(p) for p in sources},inputs={str(p):sha(p) for p in inputs},
              stageSHA256={name:sha(stage/name) for name in names},
              engineBefore={name:sha(engine/name) if (engine/name).is_file() else None for name in names},
              gates=training.CONFIG['gates'],freshHoldoutSongs=24,
              additionalGates=['Positive lower bound of paired 95% bootstrap F1 gain','Zero newly broken previously good transitions','Known regression preserved exactly'],
              newHoldoutUsedForModelSelection=False,installOnlyIfPassed=True,rollbackOnSmokeFailure=True,
              sourceScope='120–600 second recordings; 60 second SongFormer window; fresh contiguous unreviewed sections only.')
    write(output/'release-plan.json',plan)
    print(json.dumps(dict(stage=str(stage),engine=str(engine),sealedSources=len(sources),freshHoldout=24,
                          conditionalInstallation=True,planSHA256=sha(output/'release-plan.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--installation-record',type=Path,required=True)
    a=p.parse_args();prepare(a.base.resolve(),a.output.resolve(),a.installation_record.resolve())
