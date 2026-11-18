"""Resumable offline structure benchmark, using the installed SongFormer.

This extracts actual predictions; it does not train or install a model. Scores
against each human annotator are kept separate. STOP pauses between songs.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

from cue_benchmark import sha,write,structure_score


def predict(structure,app,row,folder,provenance,convert):
    from analysis_progress import reporting,track_structure
    start=time.time();audio=Path(row['audio']);prediction=folder/'prediction.json'
    with reporting(prediction,'structure'),track_structure(app,str(audio),60):
        raw=structure.segments_from_app(app,str(audio),60)
        if sha(audio)!=row['audioSHA256']:raise ValueError('Audio changed during inference')
        saved=dict(audioSHA256=row['audioSHA256'],provenance=provenance,raw=raw,
                   sections=convert(raw,row['duration']),inferenceSeconds=time.time()-start)
        # Publish before reporting finishes, and retain inference if scoring
        # fails later. A completed progress bar always has its prediction file.
        write(prediction,saved)
    return saved


def run(manifest,output,engine,limit=None):
    import fcntl
    output.mkdir(parents=True,exist_ok=True)
    lock=(output/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.nice(10)
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','REACUE_CPU_THREADS'):os.environ[key]='2'
    os.environ.update(HF_HUB_OFFLINE='1',REACUE_DEVICE='cpu',REACUE_STRUCTURE_DIR=str(engine/'structure'),
        NUMBA_CACHE_DIR=str(output/'numba'),MPLCONFIGDIR=str(output/'matplotlib'),PYTORCH_ENABLE_MPS_FALLBACK='1')
    rows=json.loads(manifest.read_text())['tracks'];rows=rows[:limit] if limit else rows
    provenance=dict(manifestSHA256=sha(manifest),runnerSHA256=sha(__file__),
                    scoringSHA256=sha(Path(__file__).with_name('cue_benchmark.py')),
                    structureWrapperSHA256=sha(engine/'reacue_structure.py'),windowSeconds=60,
                    checkpointSHA256={str(f.relative_to(engine)):sha(f) for f in sorted((engine/'structure').rglob('*'))
                        if f.is_file() and f.suffix in ('.safetensors','.ckpt','.pth','.pt','.bin')})
    seal=output/'protocol.json'
    if seal.exists() and json.loads(seal.read_text())!=provenance:raise ValueError('Experiment code/input changed; use a new output directory')
    write(seal,provenance)
    (output/'source').mkdir(exist_ok=True)
    for name in ('run_full_song_benchmark.py','cue_benchmark.py'):
        shutil.copy2(Path(__file__).with_name(name),output/'source'/name)
    status=lambda stage,**kw:write(output/'status.json',dict(stage=stage,pid=os.getpid(),updated=time.time(),total=len(rows),**kw))
    sys.path.insert(0,str(engine))
    import reacue_structure as structure
    import torch
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    from worker import sections
    results=[];app=None
    try:
        for row in rows:
            if (output/'STOP').exists():status('paused',completed=len(results));return
            audio=Path(row['audio']);folder=output/row['id'];folder.mkdir(exist_ok=True)
            if sha(audio)!=row['audioSHA256']:raise ValueError('Audio changed: '+row['id'])
            prediction=folder/'prediction.json'
            status('analyzing',completed=len(results),current=row['id'],artist=row['artist'],title=row['title'])
            if prediction.exists():
                saved=json.loads(prediction.read_text())
                if saved['audioSHA256']!=row['audioSHA256'] or saved['provenance']!=provenance:raise ValueError('Stale prediction')
            else:
                if app is None:app=structure.load_app();structure.init_models(app)
                saved=predict(structure,app,row,folder,provenance,sections)
            scores=[dict(annotator=r['annotator'],referenceSHA256=r['sha256'],
                         metrics=structure_score(r,saved['sections'])) for r in row['references']]
            result=dict(id=row['id'],artist=row['artist'],title=row['title'],duration=row['duration'],
                        inferenceSeconds=saved['inferenceSeconds'],scores=scores)
            results.append(result);write(folder/'scores.json',result)
            write(output/'report.json',dict(completed=len(results),total=len(rows),complete=len(results)==len(rows),
                scope='Development diagnostics; pretraining overlap unknown; structural boundaries only, no beat/cue-lead ground truth.',
                modelInstalled=False,provenance=provenance,results=results))
            print(json.dumps(dict(completed=len(results),total=len(rows),current=row['id'],seconds=saved['inferenceSeconds'])),flush=True)
        status('complete',completed=len(results))
    except BaseException as error:
        status('failed',completed=len(results),error=type(error).__name__+': '+str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--limit',type=int)
    a=p.parse_args();run(a.manifest.resolve(),a.output.resolve(),a.engine.resolve(),a.limit)
