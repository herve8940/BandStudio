"""Create a rehearsal arrangement in a new project or align an excerpt to bars."""
import copy
import shutil
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from musical_timing import BeatClock
from services import atomic
from ui_language import ui_text
from windows.project import duration, relative_file, waveform


def identity():
    return str(uuid.uuid4())


def bounds(project, options):
    a, b = float(options['start']), float(options['end'])
    if not (0 <= a < b <= duration(project) and b-a >= .05):
        raise ValueError(ui_text('Passage A–B invalide.', 'Invalid A–B range.'))
    return a, b


def align(project, options):
    a, b = bounds(project, options)
    bars, meter = options['bars'], options['meter']
    if not (isinstance(bars, int) and 1 <= bars <= 256 and isinstance(meter, int) and 1 <= meter <= 12):
        raise ValueError(ui_text('Nombre de mesures ou de temps invalide.', 'Invalid number of bars or beats.'))
    step = (b-a)/(bars*meter)
    if not .15 <= step <= 3:
        raise ValueError(ui_text('Ajuste la plage ou le nombre de mesures (20 à 400 pulsations/min).',
                                 'Adjust the range or bar count (20 to 400 beats/min).'))
    clock = BeatClock(project)
    # Keep the full clock outside the edit, including inferred beats at either end.
    beats = [t for t in clock.beats if t < a-.001 or t > b+.001]
    beats.extend(a+i*step for i in range(bars*meter))
    if b < duration(project): beats.append(b)
    after_meter = clock.bar_phase(b)[1]
    changes = [m for m in project.get('meterChanges') or [] if m['time'] < a or m['time'] > b]
    changes.append(dict(time=a, meter=meter))
    if b < duration(project): changes.append(dict(time=b, meter=after_meter))
    downbeats = [t for t in project.get('downbeats', []) if t < a or t > b]
    downbeats.extend(a+i*step*meter for i in range(bars+1))
    return dict(beats=sorted(set(beats)), downbeats=sorted(set(downbeats)), meterChanges=sorted(changes, key=lambda m:m['time']))


def spans(rows, segments, words=False):
    result = []
    for start, end, offset in segments:
        for row in rows:
            a, b = max(start,row['start']), min(end,row['end'])
            if b-a < .000001: continue
            item = dict(row, id=identity(), start=offset+(a-start), end=offset+(b-start))
            if words and row.get('words'):
                item['words'] = [dict(w,start=offset+(max(w['start'],a)-start),end=offset+(min(w['end'],b)-start))
                                 for w in row['words'] if w['end']>a and w['start']<b]
                if len(item['words']) != len(row['words']):
                    item['text'] = ' '.join(w['text'] for w in item['words']) or row['text']
                    item['timingReview'] = True
            result.append(item)
    return result


def points(rows, segments, duration):
    return [dict(row,time=offset+(row['time']-a)) for a,b,offset in segments for row in rows
            if a <= row['time'] < b or (row['time']==duration==b)]


def write_track(source, target, offset, segments):
    with sf.SoundFile(source) as src, sf.SoundFile(target, 'w', samplerate=src.samplerate, channels=src.channels,
                                                   subtype='FLOAT', format='WAVEX') as dest:
        sr = src.samplerate
        zeros = np.zeros((65536,src.channels),dtype='float32')
        for a,b,start in segments:
            frames = round((start+(b-a))*sr) - round(start*sr)
            cursor = round((a-offset)*sr)
            while frames > 0:
                size = min(frames,len(zeros))
                if cursor < 0:
                    size = min(size,-cursor)
                    data = zeros[:size]
                elif cursor >= len(src):
                    data = zeros[:size]
                else:
                    size = min(size,len(src)-cursor)
                    src.seek(cursor)
                    data = src.read(size,dtype='float32',always_2d=True)
                    if len(data)!=size: raise IOError('Incomplete audio track')
                dest.write(data)
                cursor += size
                frames -= size


def variant(project, options, folder):
    a,b = bounds(project,options)
    total = duration(project)
    if options['edit']=='cut':
        ranges = [(0,a),(b,total)]
        join = a
    elif options['edit']=='repeat':
        ranges = [(0,b),(a,b),(b,total)]
        join = b
    else:
        raise ValueError(ui_text('Choisis une coupe ou une répétition.', 'Choose a cut or repeat.'))
    segments=[]; length=0.
    for x,y in ranges:
        if y>x:
            segments.append((x,y,length))
            length += y-x
    if not .05 <= length <= 43200:
        raise ValueError(ui_text('Durée de variante invalide.', 'Invalid arrangement duration.'))
    p = copy.deepcopy({k:v for k,v in project.items() if not k.startswith('_')})
    p.update(id=identity(),name=p['name']+' · '+ui_text('Variante','Variant'),sessionDuration=length,
             guideFiles={},guideKey='',sectionGridVersion=2,structureProposal=None,timingGrid=None)
    p['preparation']=dict(rate=project.get('_rate',1),pitch=project.get('_pitch',0),mode=project.get('_mode','mix'))
    p['sections']=spans(p.get('sections',[]),segments)
    for key in ('lyrics','chords'):p[key]=spans(p.get(key,[]),segments,words=True)
    p['cues']=[dict(c,id=identity()) for c in points(p.get('cues',[]),segments,total)]
    p['drumHits']=points(p.get('drumHits',[]),segments,total)
    clock=BeatClock(project)
    p['beats']=[offset+(t-x) for x,y,offset in segments for t in clock.beats if x<=t<y]
    downbeats=[t for t in clock.beats if clock.bar_phase(t)[0]==0]
    p['downbeats']=[offset+(t-x) for x,y,offset in segments for t in downbeats if x<=t<y]
    changes=points(project.get('meterChanges') or [],segments,total)
    for x,y,offset in segments:
        first=next((t for t in downbeats if x<=t<y),None)
        if first is not None:
            changes.append(dict(time=offset+(first-x),meter=clock.bar_phase(first)[1]))
    p['meterChanges']=sorted({round(c['time'],8):c for c in changes}.values(),key=lambda c:c['time'])
    if len(p['beats'])>=2:
        p['settings']['gridMode']='detected'
        p['bpm']=clock.basis['bpm']
        p['settings']['firstBeat']=p['downbeats'][0] if p['downbeats'] else p['beats'][0]
        p['gridLocked']=True
    root=Path(project['_root'])
    folder=Path(folder)
    folder.mkdir()
    try:
        (folder/'Audio').mkdir()
        p['tracks']=[]
        for tr in project['tracks']:
            if tr['role'].startswith('guide_'):continue
            path=folder/'Audio'/(identity()+'.wav')
            write_track(relative_file(root,tr['file']),path,tr['offset'],segments)
            p['tracks'].append(dict(tr,id=identity(),file=path.relative_to(folder).as_posix(),offset=0.,
                                    duration=sf.info(path).duration,peaks=waveform(path),peaksVersion=2))
        atomic(folder/'project.json',p)
    except BaseException:
        shutil.rmtree(folder)
        raise
    return dict(join=min(join,length))
