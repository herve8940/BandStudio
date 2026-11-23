"""Intro boundaries and count-ins on the saved musical grid; no model inference."""
import bisect
import copy
import math
import statistics
import uuid
from functools import lru_cache


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


def timing_basis(project, duration=None):
    s=project.get('settings',{})
    if duration is None:
        duration=max(project.get('sessionDuration',0),max((t.get('offset',0)+t.get('duration',0)
                     for t in project.get('tracks',[]) if not t.get('role','').startswith('guide_')),default=0))
        if not duration:duration=max(project.get('beats',[0]) or [0])+60/pulse_bpm(project)
    return dict(beats=project.get('beats',[]),downbeats=project.get('downbeats',[]),
                bpm=pulse_bpm(project),first=s.get('firstBeat',0),meter=s.get('beatsPerBar',4),
                mode=s.get('gridMode','detected'),locked=bool(project.get('gridLocked')),duration=duration)


@lru_cache(maxsize=64)
def _completed_clock(raw, downbeats, bpm, first, meter, mode, locked, duration):
    fallback=60/bpm
    observed=sorted(set(t for t in raw if math.isfinite(t) and 0<=t<duration))
    if mode=='fixed' or len(observed)<2:
        start=math.ceil(-first/fallback-1e-9);stop=math.ceil((duration-first)/fallback-1e-9)
        beats=[max(0.,first+i*fallback) for i in range(start,stop)]
        return tuple(beats),0,fallback,fallback,0,0.,False
    spans=[b-a for a,b in zip(observed,observed[1:])]
    def local(values):
        usable=[d for d in values if .15<=d<=max(3.,4*fallback)]
        # Reject missing pulses when choosing the interpolation/extrapolation tempo.
        center=statistics.median(usable) if usable else fallback
        close=[d for d in usable if .65*center<=d<=1.5*center]
        return statistics.median(close) if close else fallback
    head=local(spans[:16]);tail=local(spans[-16:])
    # Sparse end detections must not slow the clock by several multiples.
    for side in ('head','tail'):
        window=spans[:16] if side=='head' else spans[-16:]
        if sum(.65*fallback<=d<=1.5*fallback for d in window)>=4:
            value=local([d for d in window if .65*fallback<=d<=1.5*fallback])
            if side=='head':head=value
            else:tail=value
    beats=[observed[0]];filled=0
    for i,span in enumerate(spans):
        period=local(spans[max(0,i-8):i]+spans[i+1:i+9])
        count=max(1,round(span/period)) if span>1.65*period else 1
        # Keep every observed pulse at its exact timestamp. Fill gaps locally;
        # never replace expressive timing by the global BPM estimate.
        beats.extend(observed[i]+span*j/count for j in range(1,count))
        beats.append(observed[i+1]);filled+=count-1
    start=math.ceil(-beats[0]/head-1e-9)
    before=[max(0.,beats[0]+i*head) for i in range(start,0)]
    end=math.ceil((duration-beats[-1])/tail-1e-9)
    after=[beats[-1]+i*tail for i in range(1,end)]
    beats=before+beats+after
    nearest=min(range(len(beats)),key=lambda i:abs(beats[i]-first));anchor=nearest%meter
    confidence=0.
    if (not locked and len(downbeats)>=4 and all(math.isfinite(t) for t in downbeats)
            and all(b>a for a,b in zip(downbeats,downbeats[1:]))):
        indices=[]
        for t in downbeats:
            i=bisect.bisect_left(beats,t)
            choices=[j for j in (i-1,i) if 0<=j<len(beats)]
            if not choices:continue
            j=min(choices,key=lambda j:abs(beats[j]-t))
            if abs(beats[j]-t)<=.15*fallback:indices.append(j)
        indices=sorted(set(indices))
        if len(indices)>=4:
            votes=[sum(i%meter==phase for i in indices) for phase in range(meter)]
            phase=max(range(meter),key=lambda phase:votes[phase])
            adjacent=sum(b-a==meter for a,b in zip(indices,indices[1:]))
            confidence=votes[phase]/len(indices) if adjacent>=3 else 0.
            if confidence>=.85 and adjacent>=3:anchor=phase
    return tuple(beats),anchor,head,tail,filled+len(before)+len(after),confidence,True


class BeatClock:
    """Shared musical coordinates for guides, counts, sheets and exported tempo."""
    def __init__(self,project,duration=None):
        self.basis=timing_basis(project,duration);b=self.basis
        values=_completed_clock(tuple(b['beats']),tuple(b['downbeats']),b['bpm'],b['first'],
                                b['meter'],b['mode'],b['locked'],b['duration'])
        self.beats,self.anchor,self.head,self.tail,self.filled,self.confidence,self.detected=values
        self.meter=b['meter'];self.first=b['first'];self.period=60/b['bpm']

    def at(self,value):
        if not self.detected:return self.first+value*self.period
        index=value+self.anchor
        if index<0:return self.beats[0]+index*self.head
        if index>=len(self.beats)-1:return self.beats[-1]+(index-len(self.beats)+1)*self.tail
        i=math.floor(index)
        return self.beats[i]+(index-i)*(self.beats[i+1]-self.beats[i])

    def coordinate(self,time):
        if not self.detected:return (time-self.first)/self.period
        if time<self.beats[0]:return (time-self.beats[0])/self.head-self.anchor
        if time>=self.beats[-1]:return len(self.beats)-1+(time-self.beats[-1])/self.tail-self.anchor
        i=bisect.bisect_right(self.beats,time)-1
        return i+(time-self.beats[i])/(self.beats[i+1]-self.beats[i])-self.anchor

    def period_at(self,time):
        i=math.floor(self.coordinate(time)+1e-9)
        return self.at(i+1)-self.at(i)

    def payload(self):
        return dict(version=1,basis=self.basis,beats=list(self.beats),anchor=self.anchor,
                    head=self.head,tail=self.tail,filled=self.filled,phaseConfidence=self.confidence,detected=self.detected)


def prepare_clock(project):
    """Resolve automatic bar phase once before saving a review or rendering its guides."""
    clock = BeatClock(project)
    correction = None
    if clock.detected and not project.get('gridLocked') and clock.confidence >= .85:
        if round(clock.coordinate(project['settings']['firstBeat'])) % clock.meter:
            correction = clock.at(0)
            project['settings']['firstBeat'] = correction
            clock = BeatClock(project)
    return clock, correction


def metronome_grid(project, duration):
    return list(BeatClock(project,duration).beats)


def grid(project):
    clock=BeatClock(project)
    return (lambda i:clock.at(i-clock.anchor),
            lambda t:math.ceil(clock.coordinate(t)-1e-7)+clock.anchor,clock.anchor)


def count_plan(project,position=0):
    s=project['settings'];meter=s['beatsPerBar'];n=s['countBars']*meter
    if not n:return dict(lead=0,end=0,target=position,events=[])
    clock=BeatClock(project);at=clock.at
    target=(math.ceil(clock.coordinate(0)/meter-1e-9)*meter if position<=0 else
            math.ceil(clock.coordinate(position)-1e-9))
    anchor=0
    # Count every beat through an opening pickup, including the final "four".
    # The music keeps its pickup; the generated click takes over on the "one".
    lead=max(0,position-at(target-n))
    events=[dict(time=at(i)-position+lead,end=at(i+1)-position+lead,
                 number=(i-anchor)%meter+1,spoken=i>=target-meter)
            for i in range(target-n,target)]
    return dict(lead=lead,end=at(target)-position+lead,target=at(target),events=events)


def tempo_envelope(project,preroll=0):
    """REAPER square tempo points: one pulse between consecutive clock beats.

    Without a count-in, the leading partial measure gets its own short time
    signature. This preserves the audio positions and all later bar accents.
    """
    clock=BeatClock(project);scale=pulse_scale(project['settings']);meter=clock.meter
    coordinate=clock.coordinate(-preroll);index=math.floor(coordinate+1e-9)
    exact=abs(clock.at(index)+preroll)<1e-7
    pickup=(-index)%meter if exact else 0
    denominator=8 if scale==1.5 else 4
    def point(time,i,pulses=0,partial=False):
        return dict(time=max(0.,time),bpm=60*scale/(clock.at(i+1)-clock.at(i)),
                    numerator=pulses*(3 if scale==1.5 else 1),denominator=denominator,
                    flags=(5 if partial else 1) if pulses else 0)
    points=[point(0,index,pickup or meter)]
    limit=clock.basis['duration']+preroll
    for i in range(index+1,math.ceil(clock.coordinate(clock.basis['duration']))+1):
        time=clock.at(i)+preroll
        if time>=limit-1e-9:break
        if not exact:
            pickup=(-i)%meter
            item=point(time,i,pickup or meter,True);exact=True
        elif pickup and i%meter==0:
            item=point(time,i,meter);pickup=0
        else:item=point(time,i)
        # Keep every tempo change, without redundant points on a fixed grid.
        if item['flags'] or abs(item['bpm']-points[-1]['bpm'])>1e-8:points.append(item)
    return points


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
    at,_,anchor=grid(p);meter=p['settings']['beatsPerBar'];beats=list(BeatClock(p).beats)
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


if __name__ == '__main__':
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('--clock', action='store_true', required=True)
    parser.parse_args()
    json.dump(BeatClock(json.load(sys.stdin)).payload(), sys.stdout, allow_nan=False)
