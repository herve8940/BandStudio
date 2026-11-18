"""Transactional engine-only installation after the frozen fresh holdout passes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from cue_benchmark import sha,write
from cue_corrector_runtime import stamp


def install(output,plan):
    from validate_cue_release import verify_plan
    verify_plan(plan)
    report=json.loads((output/'fresh-report.json').read_text())
    if report.get('passed') is not True or report['decision']!='eligible_for_installation':
        raise ValueError('A rejected corrector must never be installed')
    if report['releasePlanSHA256']!=sha(output/'release-plan.json') or report['candidateSHA256']!=sha(output/'candidate.json'):
        raise ValueError('Deployment does not match the evaluated model')
    engine=Path(plan['engine']);stage=output/'stage';receipt=output/'installation.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if all(sha(engine/name)==digest for name,digest in previous['installedFiles'].items()):return previous
        raise ValueError('Previously installed files have since changed')
    names=['cue_corrector.py','cue_corrector_runtime.py','worker.py']
    for name in names:
        target=engine/name;actual=sha(target) if target.exists() else None
        if actual!=plan['engineBefore'][name]:raise ValueError('Engine changed since staging: '+name)
        if sha(stage/name)!=plan['stageSHA256'][name]:raise ValueError('Staged code changed')
    baseline=json.loads((output/'analysis/protocol.json').read_text())
    if sha(engine/'reacue_structure.py')!=baseline['structureWrapperSHA256']:raise ValueError('Structure engine changed')
    structure_files={}
    for name,expected in baseline['checkpointSHA256'].items():
        path=(engine/name).resolve()
        if not path.is_relative_to(engine.resolve()/'structure') or sha(path)!=expected:
            raise ValueError('Structure weights changed')
        structure_files[name]=dict(sha256=expected,stamp=stamp(path))
    if len(structure_files)<3:raise ValueError('Incomplete structure model provenance')
    library=Path(plan['library'])
    projects={str(p):sha(p) for p in library.glob('*.bandstudio/project.json')}
    suffix=time.strftime('%Y%m%d-%H%M%S')
    backup=engine/'code-backups'/('cue-corrector-'+suffix);backup.mkdir(parents=True,exist_ok=False)
    existed={name:(engine/name).exists() for name in names}
    for name in names:
        if existed[name]:shutil.copy2(engine/name,backup/name)
    bundle=engine/'cue-corrector';prior_bundle=bundle.exists()
    if prior_bundle:shutil.copytree(bundle,backup/'previous-bundle')
    write(backup/'manifest.json',dict(files=existed,priorBundle=prior_bundle,projects=projects))
    staging=engine/('.cue-corrector-'+suffix);staging.mkdir(exist_ok=False)
    model=json.loads((output/'candidate.json').read_text())['model'];model['approved']=True
    write(staging/'model.json',model)
    approval=dict(schema=1,approved=True,enabled=True,version=model['version'],windowSeconds=60,
                  correctorSourceSHA256=sha(stage/'cue_corrector.py'),runtimeSourceSHA256=sha(stage/'cue_corrector_runtime.py'),
                  structureWrapperSHA256=baseline['structureWrapperSHA256'],structureFiles=structure_files,
                  modelSHA256=sha(staging/'model.json'),freshReportSHA256=sha(output/'fresh-report.json'),
                  candidateSHA256=sha(output/'candidate.json'),releasePlanSHA256=sha(output/'release-plan.json'),
                  scope='New 60-second-window SongFormer analyses, 120–600 seconds, no manual/reviewed sections. Maximum shift 250 ms.')
    write(staging/'approval.json',approval)
    try:
        # Publish dependencies first and the approval directory last. Existing
        # workers retain already imported code; new workers see a complete bundle.
        if prior_bundle:os.rename(bundle,backup/'removed-bundle')
        for name in names:
            temp=engine/(name+'.cue-update');shutil.copy2(stage/name,temp);os.replace(temp,engine/name)
        os.rename(staging,bundle)
        command=[str(engine/'.venv-structure/bin/python'),str(Path(__file__).with_name('smoke_cue_installation.py')),
                 '--output',str(output),'--engine',str(engine)]
        with (output/'installation-smoke.log').open('w') as log:
            subprocess.run(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True,
                           timeout=180,env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2'))
        if any(sha(p)!=expected for p,expected in projects.items()):raise ValueError('A user project changed during installation')
    except BaseException:
        # Disable the new model before restoring code, and preserve failed
        # artifacts for diagnosis. No project restoration writes are performed.
        if bundle.exists():os.rename(bundle,backup/'failed-bundle')
        for name in names:
            if existed[name]:shutil.copy2(backup/name,engine/name)
            else:(engine/name).unlink(missing_ok=True)
        if prior_bundle:shutil.copytree(backup/'previous-bundle',bundle)
        raise
    files=names+['cue-corrector/model.json','cue-corrector/approval.json']
    result=dict(installed=True,installedAt=time.time(),engine=str(engine),backup=str(backup),
                freshReportSHA256=sha(output/'fresh-report.json'),projectsPreserved=len(projects),appRestartRequired=False,
                installedFiles={name:sha(engine/name) for name in files},
                smoke=json.loads((output/'installation-smoke/verification.json').read_text()))
    write(receipt,result)
    return result
