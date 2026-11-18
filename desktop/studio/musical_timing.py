"""Intro boundaries and count-ins on the saved musical grid; no model inference."""
import bisect
import copy
import math
import statistics
import uuid


def pulse_scale(settings):
    """Quarter notes per saved pulse; the audio grid always stores pulses."""
    return 1.5 if settings.get('pulseUnit') == 'dottedQuarter' else 1.


def pulse_bpm(project):
    s=project.get('settings',{})
    fallback=s.get('manualBPM',120)/pulse_scale(s)
    return fallback if s.get('gridMode')=='fixed' else project.get('bpm') or fallback


def tempo_info(project):
    s=project.get('settings',{});pulse=pulse_bpm(project)
    estimated=pulse*pulse_scale(s)
    reference=s.get('referenceBPM') if s.get('gridMode')!='fixed' else None
    return dict(bpm=reference or estimated,estimatedBPM=estimated,pulseBPM=pulse,
                source='manual' if s.get('gridMode')=='fixed' else 'reference' if reference else 'estimated')


def grid(project):
    s=project['settings'];meter=s['beatsPerBar']
    beats=sorted(set(t for t in project.get('beats',[]) if math.isfinite(t) and t>=0))
    period=60/pulse_bpm(project)
    if s['gridMode']=='detected' and len(beats)>1:
        anchor=min(range(len(beats)),key=lambda i:abs(beats[i]-s['firstBeat']))%meter
        head=statistics.median([b-a for a,b in zip(beats,beats[1:])][:8])
        tail=statistics.median([b-a for a,b in zip(beats,beats[1:])][-8:])
        def at(i):
            if i<0:return beats[0]+i*head
            if i>=len(beats):return beats[-1]+(i-len(beats)+1)*tail
            return beats[i]
        def following(t):
            if t<=beats[0]+1e-7:return anchor
            if t>beats[-1]:return len(beats)-1+math.ceil((t-beats[-1])/tail-1e-7)
            return bisect.bisect_left(beats,t-1e-7)
        return at,following,anchor
    first=s['firstBeat']
    return lambda i:first+i*period,lambda t:math.ceil((t-first)/period-1e-7),0


def count_plan(project,position=0):
    s=project['settings'];meter=s['beatsPerBar'];n=s['countBars']*meter
    if not n:return dict(lead=0,end=0,target=position,events=[])
    at,following,anchor=grid(project);target=following(position)
    # Count every beat through an opening pickup, including the final "four".
    # The music keeps its pickup; the generated click takes over on the "one".
    lead=max(0,position-at(target-n))
    events=[dict(time=at(i)-position+lead,end=at(i+1)-position+lead,
                 number=(i-anchor)%meter+1,spoken=i>=target-meter)
            for i in range(target-n,target)]
    return dict(lead=lead,end=at(target)-position+lead,target=at(target),events=events)


def audio_entry(audio):
    """Locate sustained sound, including quiet pickups; never crop the audio."""
    import numpy as np
    import soundfile as sf
    with sf.SoundFile(audio) as f:
        sr=f.samplerate;x=f.read(min(f.frames,60*sr),dtype='float32',always_2d=True)
    hop=max(1,round(sr*.005));n=len(x)//hop
    if not n:return None
    rms=np.sqrt(np.mean(x[:n*hop].reshape(n,hop,-1)**2,axis=(1,2)))
    threshold=max(1e-5,float(np.percentile(rms,95))*.025)
    active=rms>threshold
    sustained=np.convolve(active.astype(int),np.ones(4,dtype=int),'valid')>=3
    indices=np.flatnonzero(sustained)
    return float(indices[0]*hop/sr) if len(indices) else None


def cached_audio_entry(audio,project,engine):
    from analysis_cache import AnalysisCache
    cache=AnalysisCache.create(project,'intro',audio,engine)
    saved=cache.load() if cache else None
    if saved is not None:return saved['entry']
    entry=audio_entry(audio)
    if cache:cache.store(dict(entry=entry))
    return entry


def align_intro_sections(project,entry,force=False):
    """Only touch opening intro boundaries; preserve the first verse and all later edits."""
    p=copy.deepcopy(project);rows=p.get('sections',[])
    def intro(s):return s['name'].strip().casefold().split(' ')[0] in ('intro','introduction')
    def silence(s):return s['name'].strip().casefold() in ('silence','avant départ','levée')
    def editable(s):return force or not (s.get('locked') or s.get('reviewed') or s.get('origin')=='manual')
    if entry is None or not rows or not p.get('beats'):return p
    prefix=[]
    for i,s in enumerate(rows):
        if intro(s) or silence(s):prefix.append(i)
        else:break
    intros=[i for i in prefix if intro(rows[i])]
    if not intros or not all(editable(rows[i]) for i in prefix):return p
    at,_,anchor=grid(p);meter=p['settings']['beatsPerBar'];beats=p['beats']
    first=next((i for i in prefix if rows[i]['name'].strip().casefold()=='levée'),intros[0])
    if not 0<=entry<rows[first]['end']:return p
    nearest=min(beats,key=lambda t:abs(t-entry));period=60/pulse_bpm(p)
    start=nearest if abs(nearest-entry)<=min(.08,period*.15) else entry
    changes=[]
    if abs(rows[first]['start']-start)>.001:
        rows[first]['start']=start;changes.append(first)
        if first:rows[first-1]['end']=start;changes.append(first-1)
    downbeats=[at(i) for i in range(anchor,len(beats),meter)]
    for i in (i for i in intros if i>first):
        old=rows[i]['start'];target=min(downbeats,key=lambda t:abs(t-old))
        if abs(target-old)<=period*.6 and rows[i-1]['start']+.01<target<rows[i]['end']-.01:
            if abs(target-old)>.001:
                rows[i-1]['end']=target;rows[i]['start']=target;changes.extend([i-1,i])
    # A short pickup before the main intro is not a second full intro.
    if first==intros[0] and len(intros)>1 and rows[first]['end']-rows[first]['start']<period*.75:
        rows[first]['name']='Levée';rows[first]['announce']=False;changes.append(first)
    for i in set(changes):rows[i].update(reviewed=False,origin='intro-calibration',locked=False)
    for i in prefix:
        if silence(rows[i]):rows[i]['announce']=False
    if first==0 and start>.01:
        rows.insert(0,dict(id=str(uuid.uuid4()),name='Avant départ',start=0,end=start,
                          origin='intro-calibration',locked=False,reviewed=False,announce=False))
    return p
