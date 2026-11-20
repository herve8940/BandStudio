"""Local, exact-recording recall. Acceptance is remembered, never training truth.

The digest covers decoded samples, rate and channels, not filenames or tags.
Different edits/encodings are deliberately not fuzzy-matched to a trusted map.
"""
import copy
import hashlib
import json
from pathlib import Path
import time
import uuid

from preparation import media_file
from services import atomic

GRID_KEYS=('gridMode','manualBPM','firstBeat','beatsPerBar','pulseUnit')


def recording(project):
    import soundfile as sf
    import numpy as np
    source=next((t for t in project['tracks'] if t['role']=='source'),None)
    if source is None:return None
    path=media_file(Path(project['_root']),source['file']);before=path.stat()
    digest=hashlib.sha256()
    with sf.SoundFile(path) as stream:
        digest.update(f'pcm-v1:{stream.samplerate}:{stream.channels}:{stream.frames}:'.encode())
        for block in stream.blocks(blocksize=262144,dtype='float32',always_2d=True):
            if not np.isfinite(block).all():raise ValueError('Audio non fini.')
            digest.update(block.astype('<f4',copy=False).tobytes())
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Audio modifié pendant la comparaison.')
    return dict(digest=digest.hexdigest(),offset=source.get('offset',0),duration=source['duration'])


def folder(project):
    root=Path(project['_root'])
    return Path(project.get('_library') or (root.parent if root.suffix=='.bandstudio' else root))/'.bandstudio-memory'


def grid(project):
    return dict(bpm=project.get('bpm',0),beats=project.get('beats',[]),downbeats=project.get('downbeats',[]),
                gridLocked=bool(project.get('gridLocked')),**{k:project['settings'].get(k) for k in GRID_KEYS})


def payload_digest(value):
    # IDs are workspace details, not musical disagreements between two saves.
    clean={k:value.get(k) for k in ('scope','grid','offset','sections','chords','chordReference')}
    for key in ('sections','chords'):
        clean[key]=[{k:v for k,v in row.items() if k!='id'} for row in clean[key]]
    return hashlib.sha256(json.dumps(clean,sort_keys=True,allow_nan=False).encode()).hexdigest()


def remember(project,*,accepted=False):
    from structure_review import confirmed
    sections=copy.deepcopy(project.get('sections',[]))
    chords=copy.deepcopy(project.get('chords',[]))
    if not accepted:
        sections=[s for s in sections if confirmed(s)]
        chords=[c for c in chords if c.get('manual')]
    if not sections and not chords:return None
    audio=recording(project)
    if audio is None:return None
    value=dict(schema=1,projectID=project['id'],name=project['name'],scope='accepted' if accepted else 'reviewed',
               audio=audio['digest'],offset=audio['offset'],duration=audio['duration'],createdAt=time.time(),
               sections=sections,chords=chords,chordReference=project.get('chordReference') if accepted else None,
               grid=grid(project) if accepted or project.get('gridLocked') else None,
               labelPolicy='Restore the same recording only. Batch acceptance is not marker/chord training truth.')
    value['contentDigest']=payload_digest(value)
    owner=hashlib.sha256(project['id'].encode()).hexdigest()[:24]
    path=folder(project)/audio['digest']/(owner+'.json')
    # Visiting a project must not downgrade an accepted full preparation to a
    # partial marker memory. Explicit new corrections supersede old acceptance.
    if not accepted and path.exists():
        try:
            old=json.loads(path.read_text())
            same=lambda key:all(any(all(x.get(k)==v for k,v in row.items() if k!='id') for x in old[key]) for row in value[key])
            if old.get('scope')=='accepted' and same('sections') and same('chords') and old.get('grid')==grid(project):return old
        except (OSError,ValueError,KeyError,TypeError):pass
    atomic(path,value);return value


def discover(project):
    """Index prior reviewed projects without requiring another user action.

    A short sample digest is only a cheap candidate filter. recall() still
    requires the full decoded-audio digest before proposing any restoration.
    """
    import soundfile as sf
    from preparation import fingerprint
    def candidate(p):
        source=next(t for t in p['tracks'] if t['role']=='source')
        path=media_file(Path(p['_root']),source['file']);digest=hashlib.sha256()
        with sf.SoundFile(path) as audio:
            digest.update(f'{audio.samplerate}:{audio.channels}:{audio.frames}'.encode())
            for position in (0,max(0,audio.frames//2-audio.samplerate//2),max(0,audio.frames-audio.samplerate)):
                audio.seek(position);digest.update(audio.read(audio.samplerate,dtype='float32',always_2d=True).astype('<f4',copy=False).tobytes())
        return digest.hexdigest()
    signature=candidate(project);library=folder(project).parent
    for path in sorted(library.glob('*.bandstudio/project.json'))[:1000]:
        try:
            if path.parent.resolve()==Path(project['_root']).resolve() or path.stat().st_size>10_000_000:continue
            saved=json.loads(path.read_text())
            if saved.get('id')==project['id']:continue
            from structure_review import confirmed
            approval=saved.get('preparation') or {}
            if not approval.get('validatedAt') and not any(confirmed(s) for s in saved.get('sections',[])) and not any(c.get('manual') for c in saved.get('chords',[])):continue
            saved.update(_root=str(path.parent),_library=str(library))
            if candidate(saved)!=signature:continue
            accepted=bool(approval.get('validatedAt') and approval.get('fingerprint')==fingerprint(saved))
            remember(saved,accepted=accepted)
        except (OSError,ValueError,KeyError,TypeError,StopIteration):continue


def recall(project):
    from structure_review import protected
    audio=recording(project)
    if not audio:return None,'missing_audio'
    matches=[]
    for path in sorted((folder(project)/audio['digest']).glob('*.json'))[:100]:
        try:
            if path.stat().st_size>5_000_000:continue
            value=json.loads(path.read_text())
            if any(not isinstance(value.get(k),list) or not all(isinstance(row,dict) for row in value[k]) for k in ('sections','chords')):continue
            if (value['schema']!=1 or value['audio']!=audio['digest'] or value['projectID']==project['id']
                    or value['contentDigest']!=payload_digest(value) or value['scope'] not in ('accepted','reviewed')):continue
            matches.append(value)
        except (OSError,ValueError,KeyError,TypeError):continue
    if not matches:return None,'not_found'
    # Multiple independently saved, different maps need a human decision.
    if len({m['contentDigest'] for m in matches})>1:return None,'conflict'
    memory=matches[0];result=copy.deepcopy(project);shift=audio['offset']-memory['offset']
    length=max(t['offset']+t['duration'] for t in project['tracks'])
    for field,protect in (('sections',protected),('chords',lambda c:c.get('manual'))):
        incoming=copy.deepcopy(memory[field]);current=project.get(field,[])
        for row in incoming:row.update(id=str(uuid.uuid4()),start=row['start']+shift,end=row['end']+shift)
        if any(row['start']<0 or row['end']>length+.01 for row in incoming):return None,'different_placement'
        kept=[s for s in current if protect(s)]
        for keep in kept:
            overlapping=[s for s in incoming if s['start']<keep['end'] and s['end']>keep['start']]
            if any((s['start'],s['end'],s.get('name',s.get('text')))!=(keep['start'],keep['end'],keep.get('name',keep.get('text'))) for s in overlapping):
                return None,'protected_conflict'
            incoming=[s for s in incoming if s not in overlapping]
        if memory['scope']=='reviewed':
            for row in current:
                if protect(row):continue
                spans=[(row['start'],row['end'])]
                for new in incoming:
                    next_spans=[]
                    for a,b in spans:
                        if b<=new['start'] or a>=new['end']:next_spans.append((a,b))
                        else:next_spans.extend(piece for piece in ((a,min(b,new['start'])),(max(a,new['end']),b)) if piece[1]-piece[0]>.001)
                    spans=next_spans
                for a,b in spans:
                    kept.append({**row,'id':str(uuid.uuid4()),'start':a,'end':b})
        result[field]=sorted(kept+incoming,key=lambda s:s['start'])
    saved=memory.get('grid')
    if saved and not project.get('gridLocked') and project['settings'].get('gridMode')!='fixed':
        result['bpm']=saved['bpm'];result['gridLocked']=saved['gridLocked']
        for key in ('beats','downbeats'):result[key]=[t+shift for t in saved[key] if 0<=t+shift<length]
        result['settings'].update({k:v for k,v in saved.items() if k in GRID_KEYS and v is not None})
        result['settings']['firstBeat']+=shift
    if memory['scope']=='accepted':result['chordReference']=memory.get('chordReference')
    return dict(project=result,name=memory['name'],scope=memory['scope'],sections=len(memory['sections']),chords=len(memory['chords'])), 'found'
