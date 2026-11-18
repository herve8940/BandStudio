"""Local, auditable correction history. A saved prediction is never a label.

The journal includes edits, explicit reviews and undo. Consumers must compare
an event with the current document before using it; an orphaned event from a
failed save, a deleted marker or a revoked review is not a training example.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import time
import uuid

SETTINGS = ('gridMode','firstBeat','beatsPerBar','manualBPM','pulseUnit',
            'leadBeats','regionCountBeats','regionCountEnabled','countBars',
            'callsEnabled','speakCues','voice','speechRate','language')
MARKER = ('id','name','start','end','time','reviewed','origin','locked','announce','callText')
TRACK = ('id','file','role','offset','duration')


def selected(value,keys):
    return {k:copy.deepcopy(value[k]) for k in keys if k in value}


def snapshot(project):
    return dict(projectID=project['id'],
        tracks=[selected(t,TRACK) for t in project.get('tracks',[]) if not t['role'].startswith('guide_')],
        settings=selected(project.get('settings',{}),SETTINGS),
        bpm=project.get('bpm',0),beats=project.get('beats',[]),downbeats=project.get('downbeats',[]),
        gridLocked=project.get('gridLocked',False),
        sections=[selected(x,MARKER) for x in project.get('sections',[])],
        cues=[selected(x,MARKER) for x in project.get('cues',[])])


def record(root,project):
    """Write before project replacement; failed saves leave unusable events."""
    from services import atomic
    root=Path(root);path=root/'project.json'
    previous=json.loads(path.read_text()) if path.exists() else None
    before=snapshot(previous) if previous and previous.get('id')==project['id'] else None
    after=snapshot(project)
    if before==after or (before is None and not after['sections'] and not after['cues']):return
    event=dict(schema=1,id=str(uuid.uuid4()),created=time.time(),before=before,after=after,
               labelPolicy='Only currently reviewed markers are references; model predictions are not labels.')
    atomic(root/'Learning/events'/(event['id']+'.json'),event)


def references(project,events=()):
    """Export reviewed positions only, retaining unknown original proposals.

    Reviewing a section does NOT validate every beat or the whole song. Missing
    reviewed markers therefore cannot be counted as false-positive predictions.
    """
    current=snapshot(project)
    context=lambda s:{k:v for k,v in s.items() if k not in ('sections','cues')}
    history=sorted((e for e in events if e.get('schema')==1 and
                    e.get('after',{}).get('projectID')==project['id']),key=lambda e:(e['created'],e['id']))
    result=[]
    for field in ('sections','cues'):
        for marker in current[field]:
            if marker.get('reviewed') is not True:continue
            original=None;review_event=None
            for event in history:
                before=event.get('before')
                after=event['after']
                old=next((m for m in (before or {}).get(field,[]) if m['id']==marker['id']),None)
                new=next((m for m in after[field] if m['id']==marker['id']),None)
                if (original is None and old is not None and old.get('reviewed') is not True
                        and context(before)==context(current)):
                    original=old
                if new==marker and context(after)==context(current):review_event=event['id']
            # Legacy reviewed documents remain useful references, but no
            # historical before/after or beat-ground-truth is invented.
            result.append(dict(kind='section' if field=='sections' else 'cue',marker=marker,
                original=original if review_event else None,eventID=review_event,
                provenance='explicit_marker_review' if review_event else 'existing_reviewed_marker',
                beatReference=False))
    return result
