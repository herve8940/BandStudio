"""Turn complete-song diagnostics into explicit supervised correction cases.

Uncertain annotations stay unlabelled. An unmatched model boundary is negative
only inside a stable span agreed by BOTH annotators, far from either one's
boundaries. This script prepares examples; it does not fit or install weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from cue_benchmark import consensus_references,label,match,sha,write


def classify(row,predictions):
    refs=row['references'];consensus=consensus_references(refs)
    anchors=consensus['anchors'];pred=[p for p in predictions if .25<p['start']<row['duration']-.25]
    middle=lambda a:(a['earliest']+a['latest'])/2
    pairs=match([middle(a) for a in anchors],[p['start'] for p in pred],3.)
    paired={j:i for i,j in pairs};examples=[];uncertain=[]
    for j,p in enumerate(pred):
        if j in paired:
            a=anchors[paired[j]]
            distance=max(a['earliest']-p['start'],0,p['start']-a['latest'])
            kind='keep_boundary' if distance<=.25 else 'move_boundary'
            examples.append(dict(kind=kind,prediction=p,reference=a,
                labelCorrect=label(p['name']) in a['labels'],timingErrorLowerBoundSeconds=distance))
            continue
        stable=[]
        for ref in refs:
            # Any annotator's nearby boundary, even one with an unknown label,
            # prevents claiming this prediction is a false alarm.
            if any(abs(s['start']-p['start'])<=3 for s in ref['segments']):break
            segment=next((s for s in ref['segments'] if s['start']<p['start']<s['end']),None)
            if segment is None or set(segment['labels'])&{'unknown','silence'}:break
            stable.append(set(segment['labels']))
        if len(stable)==2 and stable[0]&stable[1]:
            examples.append(dict(kind='extra_boundary',prediction=p,
                                 reference=dict(labels=sorted(stable[0]&stable[1]),annotators=2)))
        else:uncertain.append(p)
    for i,a in enumerate(anchors):
        if i not in {i for i,j in pairs}:examples.append(dict(kind='missing_boundary',prediction=None,reference=a))
    return dict(examples=examples,unlabelledPredictions=uncertain)


def build(manifest,analysis,output):
    from collections import Counter
    rows=json.loads(manifest.read_text())['tracks'];results=[];counts=Counter()
    for row in rows:
        path=analysis/row['id']/'prediction.json'
        if not path.exists():continue
        p=json.loads(path.read_text())
        if p['audioSHA256']!=row['audioSHA256']:raise ValueError('Prediction belongs to another recording')
        cases=classify(row,p['sections']);counts.update(e['kind'] for e in cases['examples'])
        results.append(dict(id=row['id'],artist=row['artist'],title=row['title'],genre=row.get('genre'),
            audio=row['audio'],audioSHA256=row['audioSHA256'],predictionSHA256=sha(path),
            annotationSHA256=[r['sha256'] for r in row['references']],
            artistGroup=hashlib.sha256(row['artist'].strip().casefold().encode()).hexdigest(),**cases))
    result=dict(schema=1,created=time.time(),manifestSHA256=sha(manifest),builderSHA256=sha(__file__),
                scope='Human-consensus structural correction examples, development only. No beat labels. No fitted model.',
                completedSongs=len(results),totalSongs=len(rows),counts=dict(counts),
                unlabelledPredictions=sum(len(r['unlabelledPredictions']) for r in results),tracks=results)
    write(output,result);return result


def follow(manifest,analysis,output):
    seen=None
    while True:
        count=len(list(analysis.glob('*/prediction.json')))
        status=json.loads((analysis/'status.json').read_text()) if (analysis/'status.json').exists() else {}
        if count!=seen or status.get('stage') in ('complete','failed','paused'):
            r=build(manifest,analysis,output);seen=count
            print(json.dumps(dict(songs=r['completedSongs'],counts=r['counts'],stage=status.get('stage'))),flush=True)
        if status.get('stage') in ('complete','failed','paused'):return
        if (analysis/'STOP').exists():return
        if status.get('pid'):
            try:os.kill(status['pid'],0)
            except ProcessLookupError:
                print('Inference process exited; restart the follower after resuming the benchmark.',flush=True);return
        time.sleep(30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--follow',action='store_true');a=p.parse_args()
    (follow if a.follow else build)(a.manifest.resolve(),a.analysis.resolve(),a.output.resolve())
