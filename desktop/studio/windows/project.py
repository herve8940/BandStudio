"""Version-1 BandStudio documents, compatible with the native Mac application."""
import copy
import hashlib
import json
import math
from pathlib import Path
import uuid
import numpy as np
import soundfile as sf

GUIDE_DEFAULTS=dict(clickEnabled=False,clickGain=.45,clickPan=0,subdivision=1,beatsPerBar=4,firstBeat=0,gridMode='detected',manualBPM=120,countBars=2,countClick=True,countVoice=True,countGain=.8,countPan=0,countEveryLoop=False,countOnSeek=True,callsEnabled=True,callsGain=.9,cuesGain=.9,callsPan=0,leadBeats=8,voice='Système',language='fr',speechRate=180,speakCues=True,regionCountEnabled=True,regionCountBeats=4,exportGuides=True,exportCount=True,loopStep=0,loopEvery=4,loopMaxRate=1)
GUIDE_DEFAULTS.update(pulseUnit=None,referenceBPM=None)

def ident():return str(uuid.uuid4())

def fresh(name='Nouveau morceau'):
    return dict(version=1,sectionGridVersion=2,id=ident(),name=name,tracks=[],sections=[],cues=[],bpm=0,beats=[],notes='',settings=GUIDE_DEFAULTS.copy(),guideFiles={},guideKey='',lyrics=[],chords=[],drumHits=[],key='',sourceURL='',capo=0,analysesCompleted=[],gridLocked=False,downbeats=[],analysisNote='')

def duration(p):return max(p.get('sessionDuration',0),max((t['offset']+t['duration'] for t in p['tracks'] if not t['role'].startswith('guide_')),default=0))


def apply_lyrics(p,result):
    """Apply the same protected lyrics and word timing in the editor and batch queue."""
    manual=[line for line in p.get('lyrics',[]) if line.get('manual')]
    entries=list(manual)
    limit=duration(p)
    for row in result['segments']:
        start=row.get('start',row.get('t',0));end=min(limit,row['end'])
        if not 0<=start<end or any(line['start']<end and line['end']>start for line in manual):continue
        words=[]
        for w in row.get('words',[]):
            if start<=w['t']<w['end']<=end+.1:
                word=dict(start=w['t'],end=w['end'],text=w['w'])
                if w.get('timingReview') is True:word['timingReview']=True
                words.append(word)
        line=dict(id=ident(),start=start,end=end,text=row.get('text',row.get('label','')),manual=False,
                  words=words,sourceURL=row.get('sourceURL'),confidence=row.get('confidence'))
        if isinstance(row.get('timingReview'),bool):line['timingReview']=row['timingReview']
        entries.append(line)
    p['lyrics']=sorted(entries,key=lambda x:x['start'])
    p['lyricsReference']=result.get('lyricsReference')

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
    s={**GUIDE_DEFAULTS,**p['settings']}
    if s.get('pulseUnit') not in (None,'quarter','dottedQuarter'):raise ValueError('Unité de pulsation invalide.')
    if s.get('referenceBPM') is not None:number(s['referenceBPM'],20,400)
    for key,low,high in [('clickGain',0,1.5),('callsGain',0,1.5),('cuesGain',0,1.5),('countGain',0,1.5),('clickPan',-1,1),('callsPan',-1,1),('countPan',-1,1),('firstBeat',-30,43200),('manualBPM',20,400),('loopStep',0,.25),('loopMaxRate',.5,1.5)]:number(s[key],low,high)
    for key,low,high in [('subdivision',1,4),('beatsPerBar',1,12),('countBars',0,8),('regionCountBeats',1,12),('leadBeats',0,32),('speechRate',100,360),('loopEvery',1,32)]:
        if int(s[key])!=number(s[key],low,high):raise ValueError('Nombre entier attendu : '+key)
    if s['gridMode'] not in ('detected','fixed') or s['language'] not in ('fr','en'):raise ValueError('Réglages de guidage invalides.')
    if root:
        for path in p['guideFiles'].values():relative_file(root,path)

def load(root):
    p=json.loads((Path(root)/'project.json').read_text(encoding='utf-8'));defaults=fresh()
    p.setdefault('gridLocked',bool(p.get('beats')))
    for k,v in defaults.items():
        if k!='sectionGridVersion':p.setdefault(k,v)
    p['settings']={**GUIDE_DEFAULTS,**p['settings']};validate(p,root)
    for t in p['tracks']:
        info=sf.info(relative_file(root,t['file']))
        if abs(info.duration-t['duration'])>.1:raise ValueError('La durée d’un média a changé : '+t['name'])
        # Old Windows builds used int32 indices: multiplying by 720 overflowed
        # after 67 seconds at 44.1 kHz. Repair the cached display, never the audio.
        if t.get('peaksVersion',0)<2:
            t['peaks']=waveform(relative_file(root,t['file']));t['peaksVersion']=2
    return p

def save(p,root):
    from services import atomic
    from cue_feedback import record
    validate(p,root);record(root,p);atomic(Path(root)/'project.json',p)

def waveform(path):
    path=Path(path);info=sf.info(path);peaks=np.zeros(720,dtype=np.float32);at=0
    for data in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):
        bins=np.minimum(719,(np.arange(len(data),dtype=np.int64)+at)*720//info.frames);np.maximum.at(peaks,bins,np.abs(data).max(axis=1));at+=len(data)
    return peaks.tolist()

def track(path,root,name,role,offset=0):
    path=Path(path);info=sf.info(path)
    return dict(id=ident(),name=name,file=path.relative_to(root).as_posix(),role=role,duration=info.duration,offset=offset,gain=.8,pan=0,muted=False,solo=False,peaks=waveform(path),peaksVersion=2)

def guide_key(p):
    value={k:p[k] for k in ['settings','bpm','beats','sections','cues']};value['duration']=duration(p);value['downbeats']=p.get('downbeats',[]);value['gridLocked']=p.get('gridLocked',False)
    value=copy.deepcopy(value)
    value['settings'].pop('referenceBPM',None)
    if value['settings']['gridMode']=='detected':value['settings'].pop('pulseUnit',None)
    for key in ('clickGain','callsGain','cuesGain','countGain'):value['settings'][key]=1
    for key in ('clickPan','callsPan','countPan'):value['settings'][key]=0
    for key in ('clickEnabled','callsEnabled','speakCues'):value['settings'][key]=True
    for item in value['sections']+value['cues']:
        for key in ('reviewed','locked','origin'):item.pop(key,None)
    # Platform names prevent accidentally reusing Mac voice assets after editing on Windows.
    return 'windows-guides-9:'+hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()

def period(p,at):
    from musical_timing import BeatClock
    return BeatClock(p).period_at(at)

def apply_sections(p,suggestions):
    protected=[s for s in p['sections'] if s.get('locked') or s.get('reviewed') or s.get('origin')=='manual'];result=copy.deepcopy(protected)
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


def analysis_done(p,kind):
    """Existing musical decisions take priority over a preparation request."""
    if kind=='chords':
        chords=p.get('chords',[])
        return bool((p.get('preparation') or {}).get('fingerprint') or any(c.get('manual') for c in chords)
                    or ((p.get('chordReference') or {}).get('sources') and any(c.get('sourceURL') for c in chords)))
    if kind in ('grid','smartgrid'):
        return bool(p.get('gridLocked') or (p.get('preparation') or {}).get('fingerprint') or (p.get('settings') or {}).get('gridMode')=='fixed' or p.get('beats') or any(k in p.get('analysesCompleted',[]) for k in ('grid','smartgrid')))
    if kind in ('structure','lyrics','drums','key'):
        field={'structure':'sections','drums':'drumHits'}.get(kind,kind)
        return bool(p.get(field) or kind in p.get('analysesCompleted',[]) or (p.get('preparation') or {}).get('fingerprint'))
    roles=[t['role'] for t in p.get('tracks',[])]
    if kind=='separate':return any(r in ('drums','bass','vocals','other','guitar','piano') for r in roles)
    if kind=='drumsep':return all(r in roles for r in ('drum_kick','drum_snare','drum_toms','drum_cymbals'))
    if kind=='vocalsplit':return all(r in roles for r in ('vocal_lead','vocal_backing'))
    if kind=='lyricscorrect':return (p.get('lyricsReference') or {}).get('alignmentVersion',0)>=1 or not any(not x.get('manual') for x in p.get('lyrics',[]))
    return False


def analysis_completed(p,kind):
    p['analysesCompleted']=list(dict.fromkeys([*p.get('analysesCompleted',[]),kind]))


def apply_grid(p,result,offset=0,*,reanalyze=False):
    if p.get('gridLocked') or (not reanalyze and analysis_done(p,'smartgrid')):return
    from services import calibrate_grid
    result=calibrate_grid(result)
    length=duration(p)
    p['beats']=[t+offset for t in result['beats'] if 0<=t+offset<length]
    p['downbeats']=[t+offset for t in result.get('downbeats',[]) if 0<=t+offset<length]
    p['bpm']=result.get('bpm',0)
    p['settings'].update(gridMode='detected', firstBeat=result['firstBeat']+offset,
                         beatsPerBar=result['beatsPerBar'],pulseUnit=result.get('pulseUnit','quarter'))
    p['analysisNote']=result['gridStatus']


def edit_marker(p,args,review=False):
    kind=args.get('kind')
    if kind not in ('section','cue'):raise ValueError('Repère inconnu.')
    rows=p['sections' if kind=='section' else 'cues']
    item=next((v for v in rows if v['id']==args.get('id')),None)
    if item is None:raise ValueError('Ce repère n’existe plus.')
    if review:
        item['reviewed']=True
        if kind=='section':item['locked']=True
        return
    at=number(args['time'],0,duration(p))
    if kind=='cue':item['time']=at;rows.sort(key=lambda x:x['time'])
    else:
        rows.sort(key=lambda x:x['start']);index=rows.index(item)
        previous=rows[index-1] if index else None
        if at>=item['end']-.01 or (previous and at<=previous['start']+.01):
            raise ValueError('Le début doit rester entre les sections voisines.')
        if previous:
            if abs(previous['end']-item['start'])<.001:
                previous['end']=at;previous['locked']=True;previous['origin']='manual';previous['reviewed']=False
            elif at<previous['end']:raise ValueError('Cette position chevauche la section précédente.')
        item['start']=at;item['locked']=True;item['origin']='manual'
    item['reviewed']=False


def guide_track(path, root, name, role, previous):
    result = track(path, root, name, role)
    old = next((t for t in previous if t['role'] == role), {})
    result.update({key: old[key] for key in ('id', 'muted', 'solo') if key in old})
    return result
