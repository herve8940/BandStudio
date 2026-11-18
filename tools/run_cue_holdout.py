"""Fetch unseen artist/work recordings, then run frozen baseline inference.

Selection is independent of prediction scores. This is a new holdout for the
corrector; SALAMI overlap with SongFormer pretraining remains unknown.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from cue_benchmark import sha,write
from fetch_cue_corpus import fetch
from train_cue_corrector import canonical


def novel_candidates(old, candidates):
    ids={r['id'] for r in old};artists={canonical(r['artist']) for r in old};titles={canonical(r['title']) for r in old}
    rows=[r for r in candidates if r['id'] not in ids and canonical(r['artist']) not in artists
          and canonical(r['title']) not in titles and canonical(r['title']) not in ('unknown','untitled','intro','outro')]
    return sorted(rows,key=lambda r:hashlib.sha256(('cue-holdout-20261118|'+r['id']).encode()).hexdigest())


def run(base,output,engine,count=24):
    import fcntl
    output.mkdir(parents=True,exist_ok=True)
    with (output/'holdout.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.nice(5)
        candidate=output/'candidate.json'
        if not candidate.exists():raise ValueError('Freeze the corrector before collecting holdout recordings')
        old=json.loads((base/'analysis/manifest.json').read_text())['tracks']
        rows=novel_candidates(old,json.loads((base/'public/candidates.json').read_text())['tracks'])
        selection=dict(candidateSHA256=sha(candidate),sourceManifestSHA256=sha(base/'analysis/manifest.json'),
                       candidateOrder=[r['id'] for r in rows],target=count,selection='Deterministic metadata-only order; disjoint artists, titles, recording IDs and audio SHA256.',
                       pretrainingOverlapExcluded=False,correctorHoldout=True)
        seal=output/'selection.json'
        if seal.exists() and json.loads(seal.read_text())!=selection:raise ValueError('Holdout selection changed')
        write(seal,selection)
        public=output/'public';(public/'audio').mkdir(parents=True,exist_ok=True)
        state=lambda stage,**kw:write(output/'holdout-status.json',dict(stage=stage,pid=os.getpid(),updated=time.time(),**kw))
        try:
            accepted=[];failed=[];seen_hashes={r['audioSHA256'] for r in old};seen_artists=set();seen_titles=set()
            with ThreadPoolExecutor(max_workers=4) as pool:
                for offset in range(0,len(rows),4):
                    if (output/'STOP').exists():raise InterruptedError('STOP requested')
                    for result in pool.map(lambda r:fetch(r,public),rows[offset:offset+min(4,count-len(accepted))]):
                        if 'error' in result:failed.append(result);continue
                        artist,title=canonical(result['artist']),canonical(result['title'])
                        if result['audioSHA256'] in seen_hashes or artist in seen_artists or title in seen_titles:
                            failed.append(dict(id=result['id'],error='Duplicate recording, artist or work'));continue
                        seen_hashes.add(result['audioSHA256']);seen_artists.add(artist);seen_titles.add(title);accepted.append(result)
                    write(public/'manifest.json',dict(schema=1,tracks=accepted,failures=failed,selection=selection))
                    state('fetching',accepted=len(accepted),target=count,failures=len(failed))
                    print(json.dumps(dict(stage='fetching',accepted=len(accepted),target=count,failures=len(failed))),flush=True)
                    if len(accepted)==count:break
            if len(accepted)!=count:raise ValueError('Not enough new recordings: '+str(len(accepted)))
            analysis=output/'analysis';analysis.mkdir(exist_ok=True)
            manifest=dict(schema=1,tracks=accepted,selection=selection,correctorCandidateSHA256=sha(candidate),
                          scope='New held-out recordings and artists for this corrector. SongFormer pretraining overlap unknown.')
            target=analysis/'manifest.json'
            if target.exists() and json.loads(target.read_text())!=manifest:raise ValueError('Holdout manifest changed')
            write(target,manifest)
            command=[str(engine/'.venv-structure/bin/python'),str(Path(__file__).with_name('run_full_song_benchmark.py')),
                     '--manifest',str(target),'--output',str(analysis),'--engine',str(engine)]
            state('analyzing',songs=count,candidateSHA256=sha(candidate))
            with (analysis/'run.log').open('a') as log:
                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                write(analysis/'launch.json',dict(pid=process.pid,command=command,started=time.time()))
                if process.wait()!=0:raise RuntimeError('Holdout inference failed; see analysis/run.log')
            state('complete',songs=count,candidateSHA256=sha(candidate))
        except BaseException as error:
            state('paused' if isinstance(error,InterruptedError) else 'failed',error=type(error).__name__+': '+str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--count',type=int,default=24)
    a=p.parse_args();run(a.base.resolve(),a.output.resolve(),a.engine.resolve(),a.count)
