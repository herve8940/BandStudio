"""Version-1 BandStudio documents, compatible with the native Mac application."""
import copy
import hashlib
import json
import math
from pathlib import Path
import uuid
import numpy as np
import soundfile as sf

GUIDE_DEFAULTS=dict(clickEnabled=False,clickGain=.45,clickPan=0,subdivision=1,beatsPerBar=4,firstBeat=0,gridMode='detected',manualBPM=120,countBars=2,countClick=True,countVoice=True,countGain=.8,countPan=0,countEveryLoop=False,countOnSeek=True,callsEnabled=True,callsGain=.9,callsPan=0,leadBeats=8,voice='Système',language='fr',speechRate=210,speakCues=True,regionCountEnabled=True,regionCountBeats=4,exportGuides=True,exportCount=True,loopStep=0,loopEvery=4,loopMaxRate=1)

def ident():return str(uuid.uuid4())

def fresh(name='Nouveau morceau'):
    return dict(version=1,id=ident(),name=name,tracks=[],sections=[],cues=[],bpm=0,beats=[],notes='',settings=GUIDE_DEFAULTS.copy(),guideFiles={},guideKey='',lyrics=[],chords=[],drumHits=[],key='',sourceURL='',capo=0,gridLocked=False,downbeats=[],analysisNote='')

def duration(p):return max(p.get('sessionDuration',0),max((t['offset']+t['duration'] for t in p['tracks'] if not t['role'].startswith('guide_')),default=0))

def relative_file(root,relative):
    root=Path(root).resolve();value=Path(relative)
    if value.is_absolute() or '..' in value.parts:raise ValueError('Fichier hors du projet.')
    path=(root/value).resolve()
    if not path.is_relative_to(root):raise ValueError('Fichier hors du projet.')
    return path

def number(value,low,high):
    value=float(value)
    if not math.isfinite(value) or not low<=value<=high:raise ValueError('Une valeur est hors limites.')
    return value

def validate(p,root=None):
    if p.get('version')!=1 or len(p['tracks'])>128:raise ValueError('Format de projet non pris en charge.')
    if len({t['id'] for t in p['tracks']})!=len(p['tracks']):raise ValueError('Identifiants de piste dupliqués.')
    number(p.get('sessionDuration',0),0,43200)
    if p.get('preparation'):
        prep=p['preparation'];number(prep['rate'],.5,1.5);number(prep['pitch'],-12,12)
        from listening import parse_mode
        parse_mode(prep['mode'])
    if 'capture' in p:
        from windows.recording import settings
        settings(p['capture'])
    length=duration(p)
    if int(p.get('capo',0))!=number(p.get('capo',0),0,12):raise ValueError('Position de capo entière attendue.')
    for value in p.get('downbeats',[]):number(value,0,length+.1)
    for t in p['tracks']:
        number(t['duration'],.00001,43200);number(t['offset'],-120,43200);number(t['gain'],0,2);number(t['pan'],-1,1)
        if root:
            f=relative_file(root,t['file'])
            if not f.is_file():raise ValueError('Média introuvable : '+t['name'])
    for s in p['sections']:
        number(s['start'],0,length);number(s['end'],s['start']+.000001,length+.1)
    for c in p['cues']:number(c['time'],0,length)
    for x in p['lyrics']+p['chords']:number(x['start'],0,length);number(x['end'],x['start']+.000001,length+.1)
    for x in p['drumHits']:number(x['time'],0,length);number(x['pitch'],0,127);number(x['velocity'],1,127)
    for v in p['beats']:number(v,0,length+.1)
    s=p['settings']
    for key,low,high in [('clickGain',0,1.5),('callsGain',0,1.5),('countGain',0,1.5),('clickPan',-1,1),('callsPan',-1,1),('countPan',-1,1),('firstBeat',-30,43200),('manualBPM',20,400),('loopStep',0,.25),('loopMaxRate',.5,1.5)]:number(s[key],low,high)
    for key,low,high in [('subdivision',1,4),('beatsPerBar',1,12),('countBars',0,8),('regionCountBeats',1,12),('leadBeats',0,32),('speechRate',100,360),('loopEvery',1,32)]:
        if int(s[key])!=number(s[key],low,high):raise ValueError('Nombre entier attendu : '+key)
    if s['gridMode'] not in ('detected','fixed') or s['language'] not in ('fr','en'):raise ValueError('Réglages de guidage invalides.')
    if root:
        for path in p['guideFiles'].values():relative_file(root,path)

def load(root):
    p=json.loads((Path(root)/'project.json').read_text(encoding='utf-8'));defaults=fresh()
    p.setdefault('gridLocked',bool(p.get('beats')))
    for k,v in defaults.items():p.setdefault(k,v)
    p['settings']={**GUIDE_DEFAULTS,**p['settings']};validate(p,root)
    for t in p['tracks']:
        info=sf.info(relative_file(root,t['file']))
        if abs(info.duration-t['duration'])>.1:raise ValueError('La durée d’un média a changé : '+t['name'])
    return p

def save(p,root):
    from services import atomic
    validate(p,root);atomic(Path(root)/'project.json',p)

def track(path,root,name,role,offset=0):
    path=Path(path);info=sf.info(path);peaks=np.zeros(720,dtype=np.float32);at=0
    for data in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):
        bins=np.minimum(719,(np.arange(len(data))+at)*720//info.frames);np.maximum.at(peaks,bins,np.abs(data).max(axis=1));at+=len(data)
    return dict(id=ident(),name=name,file=path.relative_to(root).as_posix(),role=role,duration=info.duration,offset=offset,gain=.8,pan=0,muted=False,solo=False,peaks=peaks.tolist())

def guide_key(p):
    value={k:p[k] for k in ['settings','bpm','beats','sections','cues']};value['duration']=duration(p)
    # Platform names prevent accidentally reusing Mac voice assets after editing on Windows.
    return 'windows-guides-2:'+hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()

def period(p,at):
    import bisect
    beats=p['beats'];s=p['settings']
    if s['gridMode']=='detected' and len(beats)>1:
        i=max(1,min(len(beats)-1,bisect.bisect_right(beats,at)));delta=beats[i]-beats[i-1]
        if .1<delta<3:return delta
    return 60/(s['manualBPM'] if s['gridMode']=='fixed' else p['bpm'] or s['manualBPM'])

def apply_sections(p,suggestions):
    protected=[s for s in p['sections'] if s.get('locked') or s.get('origin')=='manual'];result=copy.deepcopy(protected)
    for section in suggestions:
        ranges=[(max(0,section['start']),min(duration(p),section['end']))]
        for keep in protected:
            next_ranges=[]
            for a,b in ranges:
                if keep['end']<=a or keep['start']>=b:next_ranges.append((a,b))
                else:next_ranges += [(a,min(b,keep['start'])),(max(a,keep['end']),b)]
            ranges=[(a,b) for a,b in next_ranges if b-a>.01]
        result += [{**section,'id':ident(),'start':a,'end':b} for a,b in ranges if b-a>.01]
    p['sections']=sorted(result,key=lambda x:x['start'])
