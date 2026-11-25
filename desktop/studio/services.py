"""Portable project services: audible guides, media decoding and REAPER exchange."""
from __future__ import annotations
from ui_language import ui_text, using_english
from listening import included, guide_audible
import bisect
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from collections import Counter
from contextlib import ExitStack
from platform_tools import executable, creation_flags
from musical_timing import BeatClock, count_plan, pulse_bpm, pulse_scale, metronome_grid, prepare_clock, tempo_envelope


def import_settings(settings):
    """Keep listening preferences, but never inherit another song's rhythm."""
    return {**settings, 'firstBeat': 0, 'gridMode': 'detected',
            'manualBPM': 120, 'beatsPerBar': 4, 'pulseUnit': None, 'referenceBPM': None}


def calibrate_grid(result):
    """Check saved beat/downbeat evidence without running or changing a model."""
    beats = result.get('beats', [])
    first, meter, agreement = (beats[0] if beats else 0), 4, 0.
    valid = len(beats) > 1 and all(math.isfinite(t) and t >= 0 and
             (not i or t > beats[i-1]) for i, t in enumerate(beats))
    evidence = {}
    downbeats = result.get('downbeats', [])
    strengths = result.get('downbeatStrengths', [])
    if len(strengths) != len(downbeats) or not all(math.isfinite(w) and w > 0 for w in strengths):
        strengths = [1.] * len(downbeats)
    if valid:
        for t, weight in zip(downbeats, strengths):
            if not math.isfinite(t) or not beats[0] <= t <= beats[-1]:continue
            right = bisect.bisect_left(beats, t)
            i = min((i for i in (right-1, right) if 0 <= i < len(beats)), key=lambda i:abs(beats[i]-t))
            span = beats[min(i+1, len(beats)-1)]-beats[max(0, i-1)]
            if 0 < i < len(beats)-1:span /= 2
            if abs(beats[i]-t) <= .2*span:evidence[i] = max(evidence.get(i, 0), weight)
    indices = sorted(evidence)
    phase_confidence = 0.
    if len(indices) >= 4:
        intervals = [b-a for a,b in zip(indices, indices[1:])]
        meters = Counter(n for n in intervals if 2 <= n <= 12)
        if meters:
            meter, count = meters.most_common(1)[0]
            phases = [sum(evidence[i] for i in indices if i % meter == phase) for phase in range(meter)]
            phase = max(range(meter), key=lambda p:phases[p])
            phase_confidence = phases[phase] / sum(evidence.values())
            # Missing bar accents are not changes of meter. Off-phase detections
            # still reduce confidence; several actual one-bar intervals must agree.
            consistent = sum(n % meter == 0 and n <= 4*meter for n in intervals)/len(intervals)
            agreement = min(consistent, phase_confidence, sum(evidence.values())/max(1.,sum(strengths)))
            if count/len(intervals) < .6:agreement = min(agreement, .84)
            if phase_confidence >= .75:first = beats[phase]
    automatic = agreement >= .85 and not result.get('learnedReviewRequired', False) and not result.get('timingReviewRequired',False)
    proposal=result.get('learnedBarProposal')
    proposal_applied=False
    if isinstance(proposal,dict) and result.get('learnedReviewRequired'):
        # Keep the learned proposal when worker/host calibrates the same result
        # again. Invalidate it if anyone changed the underlying beat list.
        from rhythm_adapter import fingerprint
        if (proposal.get('meter') in range(2,13) and proposal.get('firstBeat') in beats
                and proposal.get('beatsSHA256')==fingerprint(beats)):
            meter,first=proposal['meter'],proposal['firstBeat']
            automatic=False
            proposal_applied=True
    if proposal and not proposal_applied:
        result={k:v for k,v in result.items() if k not in ('learnedBarProposal','barAdaptation')}
    status = ui_text('« 1 » calé automatiquement sur les mesures détectées', 'Beat 1 aligned automatically to the detected bars') if automatic else ui_text('« 1 » à vérifier à l’écoute · mesures non confirmées', 'Check beat 1 by ear · bars unconfirmed')
    if result.get('learnedReviewRequired'):
        status = ui_text('Temps et mesures à vérifier à l’écoute · calage incertain', 'Check beats and bars by ear · uncertain timing')
        if proposal_applied:status=ui_text('Premier temps et mesure proposés par apprentissage · à vérifier à l’écoute', 'Suggested downbeat and meter from the learned model · check by ear')
    if result.get('tempoNote'):status += ' · ' + result['tempoNote']
    if beats and beats[0] > 2:status += (f' · grid from {beats[0]:.2f} s' if using_english() else f' · grille à partir de {beats[0]:.2f} s')
    return {**result, 'firstBeat': first, 'beatsPerBar': meter,
            'agreement': agreement, 'phaseConfidence': phase_confidence,
            'gridReviewRequired': not automatic, 'gridStatus': status}


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
    os.replace(temp,path)


def run(argv,timeout=1800):
    """Argument vectors only; terminate the child when the job is cancelled."""
    proc=subprocess.Popen([str(x) for x in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt',creationflags=creation_flags())
    def stop(sig,frame):
        try:
            if os.name=='nt':proc.terminate()
            else:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        raise SystemExit(130)
    prior=signal.signal(signal.SIGTERM,stop)
    try:
        out,err=proc.communicate(timeout=timeout)
        if proc.returncode:raise RuntimeError(err.decode(errors='replace')[-1800:] or ui_text('Le traitement média a échoué.', 'Media processing failed.'))
        return out
    finally:
        if proc.poll() is None:
            try:
                if os.name=='nt':proc.terminate()
                else:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            proc.wait(timeout=10)
        signal.signal(signal.SIGTERM,prior)


def decode(source,target,engine,*,start=None,duration=None,channels=2):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    command=[executable(engine,'ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y']
    if start is not None:command+=['-ss',str(start)]
    command+=['-protocol_whitelist','file,pipe,crypto,data','-i',source]
    if duration is not None:command+=['-t',str(duration)]
    command+=['-map','0:a:0','-vn','-ac',str(channels),'-ar','44100','-c:a','pcm_f32le',target]
    run(command)


def beat_grid(project):
    clock=BeatClock(project)
    return list(clock.beats),clock.basis['duration']


def local_pulse(beats,index,fallback=.5):
    """Robust nearby pulse length, excluding an isolated detection gap."""
    spans=[b-a for a,b in zip(beats[max(0,index-4):index+4],beats[max(0,index-4)+1:index+5]) if b>a]
    spans.sort()
    return spans[len(spans)//2] if spans else fallback


def pulse_gap(beats,index):
    return (0<=index<len(beats)-1 and
            beats[index+1]-beats[index]>2.5*local_pulse(beats,index))


def before_beat(target,amount,beats,bpm):
    if not amount:return target
    if len(beats)>1:
        if target>beats[-1]+(beats[-1]-beats[-2])*.5:
            # A cue in a free outro must not jump back to the final detected
            # bar. Without a nearby pulse, retain its time-based anticipation.
            return target-amount*60/max(20,bpm)
        right=bisect.bisect_left(beats,target)
        i=min((i for i in (right-1,right) if 0<=i<len(beats)),key=lambda i:(abs(beats[i]-target),i))
        span=local_pulse(beats,i,60/max(20,bpm))
        if (abs(beats[i]-target)>.6*span or
                any(pulse_gap(beats,j) for j in range(max(0,i-amount),i))):
            return target-amount*span
        if i>=amount:return beats[i-amount]
        return beats[0]-(amount-i)*(beats[1]-beats[0])
    return target-amount*60/max(20,bpm)


def announcement_before(limit,beats,bpm):
    """Move a long announcement earlier by whole pulses to clear a count-in."""
    if len(beats)>1:
        i=bisect.bisect_right(beats,limit+1e-7)-1
        if i>=0:return beats[i]
        span=beats[1]-beats[0]
        return beats[0]+math.floor((limit-beats[0])/span+1e-7)*span
    span=60/max(20,bpm)
    return math.floor(limit/span+1e-7)*span


def region_count_beats(target,amount,beats):
    """Place spoken numbers on existing clicks, never on an offset copy of the grid."""
    # Use the closest click as the passage's musical entry without moving its region.
    # Otherwise a region 100 ms after a beat would speak "four" on that entry beat.
    if not beats:return []
    right=bisect.bisect_left(beats,target)
    candidates=[i for i in (right-1,right) if 0<=i<len(beats)]
    stop=min(candidates,key=lambda i:(abs(beats[i]-target),i))
    if not stop:return []
    if abs(beats[stop]-target)>.6*local_pulse(beats,stop):return []
    if target>beats[-1]:
        span=beats[-1]-beats[-2] if len(beats)>1 else 0
        # Do not invent a countdown in a tail where beat detection has stopped.
        if span<=0 or target-beats[-1]>span*1.25:return []
    first=max(0,stop-amount)
    # Retain only the available beats after a silence, with their final count
    # numbers (e.g. "three, four"). Never stretch a spoken beat across a gap.
    for index in range(first,stop):
        if pulse_gap(beats,index):first=index+1
    return [dict(number=amount-(stop-index)+1,time=beats[index],
                 end=min(target,beats[index+1]))
            for index in range(first,stop)]


def plan_announcements(entries,count_plans,beats,bpm,settings):
    """Keep complete announcements intelligible and in target order.

    A spoken countdown owns its pulse windows. Anticipated calls move earlier
    by whole beats to clear those windows and later announcements. Unavoidable
    lack of room is reported, never hidden by mixing two speaking voices.
    """
    reserved=[(e['time'],e['end']) for plan in count_plans.values() for e in plan
              if settings['regionCountEnabled'] and settings['countVoice']]
    scheduled=[];warnings=[];next_start=math.inf
    for entry in sorted(entries,key=lambda e:(e['target'],e['id']),reverse=True):
        at=entry['requested'];length=entry['duration']
        # The section containing the playback start is spoken by the native
        # initial count-in. Its sound file is still kept in guideFiles.
        initial_call=(entry['kind']=='section' and
            (settings.get('countBars',0)>1 or (settings.get('countBars',0)>0 and not settings['countVoice'])) and
            entry['target']<=settings.get('firstBeat',0)<entry.get('sectionEnd',math.inf))
        if at<0 and (entry['target']<=0 or initial_call):continue
        if at<0 and entry['target']>=length+.05:at=0.
        limit=next_start-length-.05
        if settings['leadBeats']>0:limit=min(limit,entry['target']-length-.05)
        own_count=count_plans.get(entry['id'],[]) if entry['kind']=='section' else []
        if own_count and settings['regionCountEnabled'] and settings['countVoice']:
            limit=min(limit,own_count[0]['time']-length-.05)
        if at>limit+1e-7:at=announcement_before(limit,beats,bpm)
        while at>=0:
            conflict=next(((a,b) for a,b in reserved if at<b-1e-7 and at+length+.05>a+1e-7),None)
            if conflict is None:break
            at=announcement_before(conflict[0]-length-.05,beats,bpm)
        if at<0:
            warnings.append(dict(id=entry['id'],target=entry['target'],reason='noRoomBeforeEntry',
                message=ui_text('Annonce sans place disponible avant l’entrée et son décompte.', 'No room for the announcement before the entry and its count-in.')))
            continue
        scheduled.append({**entry,'time':at,'end':at+length,'moved':abs(at-entry['requested'])>1e-6})
        next_start=at
    return sorted(scheduled,key=lambda e:(e['target'],e['id'])),warnings


def voice_key(text,settings):
    return hashlib.sha256(json.dumps(['speech-v4',os.name,settings['language'],settings['voice'],
                                      settings['speechRate'],str(text).strip()[:240]],ensure_ascii=False).encode()).hexdigest()[:24]


def reusable_voice(text,folder,settings,project_root=None):
    """Reuse identical speech between jobs; exports still receive private files."""
    import numpy as np
    import soundfile as sf
    stored=None;key=voice_key(text,settings)
    try:
        if project_root:
            base=Path(project_root).resolve();candidate=base/'Cache/guide-voices'
            if candidate.resolve().is_relative_to(base):stored=candidate/(key+'.wav')
        if stored and stored.is_file() and not stored.is_symlink():
            info=sf.info(stored)
            if info.samplerate==44100 and info.channels==2 and 0<info.frames<=44100*120:
                samples,_=sf.read(stored,dtype='float32',always_2d=True)
                if len(samples)==info.frames and np.isfinite(samples).all() and np.max(np.abs(samples))>1e-6:
                    target=folder/(key+'.wav');shutil.copy2(stored,target);return target
    except (OSError,RuntimeError,ValueError):pass
    result=voice_wav(text,folder,settings)
    if stored and result:
        temporary=None
        try:
            stored.parent.mkdir(parents=True,exist_ok=True)
            temporary=stored.with_name(key+'.'+uuid.uuid4().hex+'.tmp')
            shutil.copy2(result,temporary);os.replace(temporary,stored)
        except OSError:pass  # A read-only cache must never prevent guide creation.
        finally:
            if temporary:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass
    return result


def voice_wav(text,folder,settings):
    import numpy as np
    import soundfile as sf
    import scipy.signal
    text=str(text).strip()[:240]
    if not text:return None
    digest=voice_key(text,settings)
    target=folder/(digest+'.wav')
    if target.exists():return target
    raw=folder/(digest+('.speech.wav' if os.name=='nt' else '.aiff'))
    if os.name=='nt':
        request=folder/(digest+'.speech.json')
        atomic(request,dict(text=text,voice=settings['voice'],language=settings['language'],rate=settings['speechRate'],output=str(raw.resolve())))
        voice_info=run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',Path(__file__).parent/'windows/speak.ps1','-RequestFile',request],timeout=60)
        print(voice_info.decode('utf-8',errors='replace').strip(),flush=True)
        request.unlink(missing_ok=True)
    else:run(['/usr/bin/say','-v',settings['voice'],'-r',str(settings['speechRate']),'-o',raw,'--',text],timeout=60)
    x,sr=sf.read(raw,dtype='float32',always_2d=True)
    if not len(x) or float(np.max(np.abs(x)))<1e-6:raise RuntimeError(ui_text('La voix choisie ne produit aucun son. Choisis une voix installée.', 'The selected voice produced no sound. Choose an installed voice.'))
    # Preserve quiet consonants/nasal onsets; only trim actual synthesis silence.
    # A 3 ms margin at 1.8% of peak clipped the beginning of ‘Introduction’.
    active=np.flatnonzero(np.max(np.abs(x),axis=1)>np.max(np.abs(x))*.001)
    x=x[max(0,int(active[0])-round(sr*.03)):min(len(x),int(active[-1])+1+round(sr*.06))]
    g=math.gcd(sr,44100);x=scipy.signal.resample_poly(x,44100//g,sr//g,axis=0)
    if x.shape[1]==1:x=np.repeat(x,2,axis=1)
    x=x[:,:2];x*=.9/max(float(np.max(np.abs(x))),1e-6)
    fade=min(220,len(x)//2);ramp=np.linspace(0,1,fade,dtype='float32')[:,None]
    x[:fade]*=ramp;x[-fade:]*=ramp[::-1]
    sf.write(target,x,44100,subtype='FLOAT');raw.unlink(missing_ok=True)
    return target


def announcement_text(item, language):
    if item.get('callText'):return item['callText']
    name=item['name']
    # Translate standard section names, while preserving custom names and cues.
    pairs={'couplet':'verse','refrain':'chorus','pré-refrain':'pre-chorus','pont':'bridge','silence':'break','introduction':'intro','fin':'ending'}
    mapping=pairs if language=='en' else {v:k for k,v in pairs.items()}
    match=re.fullmatch(r'(.+?)(\s+\d+)?',name.strip())
    if match and match[1].casefold() in mapping:return mapping[match[1].casefold()]+(match[2] or '')
    return name


def guides(project_file,output,*,include_announcements=True):
    with ExitStack() as scratch:
        _render_guides(project_file, output, include_announcements, scratch)


def _render_guides(project_file, output, include_announcements, scratch):
    from analysis_progress import phase_items
    import numpy as np
    import soundfile as sf
    p=json.loads(Path(project_file).read_text());s=p['settings']
    root=Path(output).parent;cache=root/'voice';cache.mkdir(parents=True,exist_ok=True)
    clock,correction=prepare_clock(p)
    duration=clock.basis['duration'];beats=list(clock.beats);sr=44100
    # Memory-mapped timelines avoid allocating two whole stereo songs in RAM.
    shape=(max(1,math.ceil(duration*sr)),2)
    def timeline():
        file = scratch.enter_context(tempfile.TemporaryFile(dir=root))
        file.truncate(math.prod(shape) * np.dtype('float32').itemsize)
        mapping = scratch.enter_context(mmap.mmap(file.fileno(), 0))
        samples = np.ndarray(shape, dtype='float32', buffer=mapping)
        samples.fill(0)
        return samples

    click, calls, cues, counts = (timeline() for _ in range(4))
    def place(dest,data,at):
        start=round(at*sr)
        if start<0:data=data[-start:];start=0
        n=min(len(data),len(dest)-start)
        if n>0:dest[start:start+n]+=data[:n]
    click_beats=([clock.at(clock.coordinate(beats[0])-1)]+beats if beats and s['subdivision']>1 else beats)
    for beat in phase_items(click_beats,0,5,ui_text("Création du click", 'Creating click')):
        index=round(clock.coordinate(beat));span=clock.at(index+1)-clock.at(index)
        for sub in range(s['subdivision']):
            at=beat+sub*span/s['subdivision']
            if at < -1e-9 or at>=duration:continue
            accented=sub==0 and index%s['beatsPerBar']==0
            n=int(sr*.035);t=np.arange(n)/sr
            sound=np.sin(2*np.pi*(1760 if accented else 1100)*t)*np.exp(-t*130)*(0.8 if sub==0 else 0.35)
            place(click,np.repeat(sound[:,None],2,axis=1),max(0.,at))
    file_map={};events=[];count_events=[];announcements=[]
    count_plans={item['id']:region_count_beats(item['start'],s['regionCountBeats'],beats)
                 for item in p.get('sections',[]) if item.get('announce') is not False}
    previous_start=0.
    # Close transitions may have fewer than four available beats. Do not count
    # for the next section over the previous section's own entry/countdown.
    for item in sorted(p.get('sections',[]),key=lambda x:(x['start'],x['id'])):
        if item['id'] in count_plans:
            count_plans[item['id']]=[e for e in count_plans[item['id']] if e['time']>=previous_start]
        previous_start=max(previous_start,item['start'])
    announcement_items = p.get('sections', []) + p.get('cues', []) if include_announcements else []
    for item in phase_items(announcement_items,1,5,ui_text('Annonces des passages', 'Announcing passages')):
        if item.get('announce') is False:continue
        text=announcement_text(item,s['language']);target=item.get('start',item.get('time',0))
        path=reusable_voice(text,cache,s,p.get('_root'))
        if path:
            file_map['call:'+item['id']]=str(path)
            x,_=sf.read(path,dtype='float32',always_2d=True)
            at=before_beat(target,s['leadBeats'],beats,pulse_bpm(p))
            announcements.append(dict(id=item['id'],kind='section' if 'start' in item else 'cue',
                requested=at,target=target,sectionEnd=item.get('end'),duration=len(x)/sr,text=text,file=str(path)))
    scheduled,warnings=plan_announcements(announcements,count_plans,beats,pulse_bpm(p),s)
    for event in scheduled:
        x,_=sf.read(event['file'],dtype='float32',always_2d=True)
        place(calls if event['kind']=='section' else cues,x,event['time'])
        events.append(event)
    words={'fr':['un','deux','trois','quatre','cinq','six','sept','huit','neuf','dix','onze','douze'],
           'en':['one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve']}
    if s['countVoice']:
        for i,text in enumerate(phase_items(words[s['language']][:max(s['beatsPerBar'],s['regionCountBeats'])],2,5,ui_text('Voix du décompte', 'Count-in voice'))):file_map['number:'+str(i+1)]=str(reusable_voice(text,cache,s,p.get('_root')))
    for item in phase_items(p.get('sections',[]),3,5,ui_text('Placement des décomptes', 'Placing count-ins')):
        if item.get('announce') is False:continue
        for event in count_plans[item['id']]:
            number,at,end=event['number'],event['time'],event['end']
            count_events.append(dict(section=item['id'],target=item['start'],number=number,time=at,end=end))
            if s['countVoice']:
                x,_=sf.read(file_map['number:'+str(number)],dtype='float32',always_2d=True)
                place(counts,x[:max(0,int((end-at)*sr*.92))],at)
            if s['countClick']:
                # A pickup can start on any beat. Counting "one" must not
                # introduce a competing bar accent over the main metronome.
                accented=round(clock.coordinate(at))%s['beatsPerBar']==0
                t=np.arange(int(sr*.035))/sr;wave=.65*np.sin(2*np.pi*(1760 if accented else 1100)*t)*np.exp(-t*130)
                place(counts,np.repeat(wave[:,None],2,axis=1),at)
    for name,data in phase_items([('click',click),('calls',calls),('cues',cues),('counts',counts)],4,5,ui_text('Enregistrement des guides', 'Saving guides')):
        path=root/(name+'.wav')
        with sf.SoundFile(path,'w',samplerate=sr,channels=2,subtype='FLOAT') as writer:
            for a in range(0,len(data),65536):writer.write(np.clip(data[a:a+65536],-1,1))
        file_map[name]=str(path)
    atomic(output,dict(files=file_map,events=events,countEvents=count_events,guideWarnings=warnings,
                       beats=beats,duration=duration,generatorVersion=8,timingGrid=clock.payload(),firstBeatCorrection=correction))


def quote(value):
    # REAPER string tokens cannot contain literal line breaks or quotation marks.
    return '"'+str(value).replace('"',"'").replace('\r',' ').replace('\n',' ')+'"'


def portable_project_stem(name):
    stem = safe_name(name)
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)',stem,re.I):
        stem = ui_text('Morceau-', 'Song-')+stem
    return stem


def reaper_filename(name, folder):
    """Leave room for Windows media, waveform caches and REAPER backups."""
    def units(value):return len(str(value).encode('utf-16-le'))//2
    budget=240-units(folder)-1
    # Audio/<UUID>.wav.reapeaks is longer than our metadata filenames.
    if budget<len('Audio/00000000-0000-0000-0000-000000000000.wav.reapeaks'):
        raise ValueError(ui_text('Chemin d’export trop long pour REAPER. Place le morceau dans un dossier plus court, puis relance l’export.', 'REAPER export path is too long. Move the song to a shorter path and export again.'))
    stem=portable_project_stem(name)
    while units(stem)>min(60,budget-len('.rpp-bak')):stem=stem[:-1]
    return (stem.rstrip(' .') or ui_text('Morceau', 'Song'))+'.rpp'


def arrangement_items(p, media, plan, preroll):
    """Media positions and mix decisions shared by every concert export."""
    root = Path(p['_root'])
    s = p['settings']

    def item(path, name, role, position, skip, length, gain, pan, muted):
        return dict(path=path, name=name, role=role, position=position, skip=skip,
                    length=length, gain=gain, pan=pan, muted=muted)

    has_stems=any(t['role'] not in ('source','take') and not t['role'].startswith('guide_') for t in p['tracks'])
    mode=p.get('_mode','mix')
    has_solo=any(t['solo'] for t in p['tracks'] if t['role']!='source')
    guide_solo=any(t['solo'] for t in p['tracks'] if t['role'].startswith('guide_'))
    for t in p['tracks']:
        if t['role'].startswith('guide_') and not s['exportGuides']:
            continue
        original = (root / t['file']).resolve()
        if not original.is_relative_to(root.resolve()):
            raise ValueError(ui_text('Fichier hors du projet.', 'File outside the project.'))
        audible=not t['muted'] and (not has_solo or t['solo'])
        if mode=='original':audible=t['role']=='source' and not t['muted'] and not guide_solo
        elif t['role']=='source':audible=mode=='mix' and not has_stems and not t['muted'] and not has_solo
        else:audible=audible and included(t['role'],mode)
        if t['role']=='vocals' and any(x['role'].startswith('vocal_') for x in p['tracks']) and not t['solo']:audible=False
        if t['role']=='drums' and any(x['role'].startswith('drum_') for x in p['tracks']) and not t['solo']:audible=False
        muted=not audible
        gain=t['gain'];pan=t['pan']
        if t['role']=='guide_click':muted=not (s['clickEnabled'] and guide_audible(p,t['role']));gain=s['clickGain'];pan=s['clickPan']
        if t['role']=='guide_voice':muted=not (s['callsEnabled'] and guide_audible(p,t['role']));gain=s['callsGain'];pan=s['callsPan']
        if t['role']=='guide_cue':muted=not (s['speakCues'] and guide_audible(p,t['role']));gain=s.get('cuesGain',s['callsGain']);pan=s['callsPan']
        if t['role']=='guide_count':muted=not (s['regionCountEnabled'] and guide_audible(p,t['role']));gain=s['countGain'];pan=s['countPan']
        offset=t['offset']+preroll;skip=max(0,-offset)
        if s['exportCount'] and plan['events'] and (t['role']=='guide_count' or (t['role']=='guide_click' and s['countClick'])):
            skip=max(skip,plan['target']-t['offset']);offset=t['offset']+skip+preroll
        yield item(original, t['name'], t['role'], max(0,offset), skip,
                   max(0,t['duration']-skip), gain, pan, muted) | {'id': t['id']}
    if s['exportCount'] and plan['events']:
        count = render_count(p, root, plan, media / 'count-in.wav')
        yield item(count, ui_text('Décompte', 'Count-in'), 'guide_count', 0, 0, plan['end'],
                   s['countGain'], s['countPan'], not guide_audible(p,'guide_count'))
        if s['exportGuides'] and s['callsEnabled'] and (s['countBars']>1 or not s['countVoice']):
            first=next((x for x in p['sections'] if x['start']<=plan['target']+.1 and x['end']>plan['target'] and x.get('announce') is not False),None)
            relative=p.get('guideFiles',{}).get('call:'+first['id']) if first else None
            if relative:
                import soundfile as sf
                initial=media/'initial-call.wav';shutil.copy2(root/relative,initial)
                available=next((e['time'] for e in plan['events'] if e['spoken']),plan['end']) if s['countVoice'] else plan['end']
                length=min(sf.info(initial).duration,max(0,available-.05))
                yield item(initial, ui_text('Annonce de départ', 'Start announcement'), 'guide_voice',
                           0, 0, length, s['callsGain'], s['callsPan'], not guide_audible(p,'guide_voice'))


def export_reaper(project_file,output,*,final_folder=None):
    p=json.loads(Path(project_file).read_text());root=Path(project_file).parent
    # Snapshots carry the real root explicitly; it is supplied by the native host.
    root=Path(p.get('_root',root));s=p['settings'];target=Path(output).parent/'REAPER'
    filename=reaper_filename(p['name'],final_folder or target);target.mkdir(parents=True,exist_ok=True)
    media=target/'Audio';media.mkdir(exist_ok=True)
    _,duration=beat_grid(p)
    bpm=pulse_bpm(p);scale=pulse_scale(s);period=60/bpm
    numerator,denominator=(s['beatsPerBar']*3,8) if scale==1.5 else (s['beatsPerBar'],4)
    plan=count_plan(p);preroll=plan['lead'] if s['exportCount'] else 0
    lines=['<REAPER_PROJECT 0.1 7.0 1','  SAMPLERATE 44100',f'  TEMPO {bpm*scale:g} {numerator} {denominator}', '  MASTER_VOLUME 0.85']
    points=tempo_envelope(p,preroll)
    lines+=['  TIMELOCKMODE 0','  <TEMPOENVEX','    ACT 1 -1','    DEFSHAPE 1 -1 -1']
    for point in points:
        signature=point['numerator']+(point['denominator']<<16)
        suffix=f' {signature} 0 {point["flags"]}' if point['flags'] else ''
        lines.append(f'    PT {point["time"]:.12f} {point["bpm"]:.12f} 1'+suffix)
    lines+=['  >']
    for i,section in enumerate(p['sections'],1):
        lines += [f'  MARKER {i} {section["start"]+preroll:.9f} {quote(section["name"])} 1',f'  MARKER {i} {section["end"]+preroll:.9f} "" 1']
    for i,cue in enumerate(p['cues'],len(p['sections'])+1):lines.append(f'  MARKER {i} {cue["time"]+preroll:.9f} {quote(cue["name"])} 0')
    for item in arrangement_items(dict(p, _root=str(root)), media, plan, preroll):
        original = item['path']
        if 'id' in item:
            name = str(uuid.uuid5(uuid.NAMESPACE_OID,item['id'])) + '.wav'
            dest = media / name
            if not dest.exists():
                if original.suffix.lower() == '.wav':
                    shutil.copy2(original, dest)
                else:
                    decode(original, dest, Path(__file__).resolve().parent)
        else:
            name = original.name
        lines += ['  <TRACK','    NAME '+quote(item['name']),
                  f'    VOLPAN {item["gain"]:.8f} {item["pan"]:.8f}',f'    MUTESOLO {int(item["muted"])} 0 0',
                  '    <ITEM','      BEAT 0',f'      POSITION {item["position"]:.9f}',
                  f'      SOFFS {item["skip"]:.9f}',f'      LENGTH {item["length"]:.9f}',
                  '      VOLPAN 1 0 1 -1','      NAME '+quote(item['name']),'      <SOURCE WAVE',
                  '        FILE '+quote('Audio/'+name),'      >','    >','  >']
    if p.get('_exportChordTrack') and p.get('chords'):
        # Empty, muted items make the reviewed harmony readable in REAPER.
        # The original annotation metadata remains available for round trips.
        lines+=['  <TRACK',ui_text('    NAME "Accords"', '    NAME "Chords"'),'    MUTESOLO 1 0 0']
        for chord in p['chords']:
            caption=chord['text']+(ui_text(' · à vérifier', ' · needs review') if not chord.get('manual') and chord.get('confidence',0)<.5 else '')
            lines+=['    <ITEM',f'      POSITION {chord["start"]+preroll:.9f}',
                    f'      LENGTH {chord["end"]-chord["start"]:.9f}',
                    '      NAME '+quote(caption),'      IMGRESOURCEFLAGS 2',
                    '      <NOTES','        |'+caption.replace('\r',' ').replace('\n',' '),'      >','    >']
        lines+=['  >']
    lines+=['>'];rpp=target/filename;rpp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Bind detailed annotations to this exact export, including optional chord items.
    metadata={key:p.get(key) for key in ['name','settings','notes','lyrics','lyricsReference','chords','drumHits','key','sourceURL','capo','downbeats','gridLocked','analysisNote']}
    clock=BeatClock(p)
    metadata.update(beats=list(clock.beats),bpm=p.get('bpm',0),timingVersion=1)
    metadata['settings']={**s,'firstBeat':clock.at(0)}
    metadata.update(exportPreroll=preroll,rppSHA256=hashlib.sha256(rpp.read_bytes()).hexdigest(),trackRoles={str(uuid.uuid5(uuid.NAMESPACE_OID,t['id']))+'.wav':t['role'] for t in p['tracks']})
    atomic(target/'bandstudio-project.json',metadata)
    atomic(output,dict(path=str(rpp),folder=str(target),preroll=preroll))


def render_count(p,root,plan,target):
    import numpy as np
    import soundfile as sf
    s=p['settings'];sr=44100;y=np.zeros((math.ceil(plan['end']*sr),2),dtype='float32')
    for event in plan['events']:
        at=round(event['time']*sr);period=event['end']-event['time']
        if s['countClick']:
            t=np.arange(int(sr*.035))/sr;wave=.65*np.sin(2*np.pi*(1760 if event['number']==1 else 1100)*t)*np.exp(-t*130)
            n=min(len(wave),len(y)-at);y[at:at+n]+=wave[:n,None]
        if s['countVoice'] and event['spoken']:
            path=p.get('guideFiles',{}).get('number:'+str(event['number']))
            if path:
                x,_=sf.read(root/path,dtype='float32',always_2d=True);n=min(len(x),int(period*sr*.92),len(y)-at);y[at:at+n]+=x[:n]
    sf.write(target,np.clip(y,-1,1),sr,subtype='FLOAT');return target


def safe_name(name):return re.sub(r'[\x00-\x1f/\\:*?"<>|]','-',str(name))[:100].strip(' .') or ui_text('Morceau', 'Song')


def export_midi(p,output):
    """Standard MIDI type 0, absolute seconds represented with a fixed 120 BPM clock."""
    import struct
    def var(n):
        b=[n&127];n>>=7
        while n:b.insert(0,(n&127)|128);n>>=7
        return bytes(b)
    events=[]
    for hit in p.get('drumHits',[]):
        tick=round(hit['time']*960)
        events += [(tick,bytes([0x99,hit['pitch'],hit['velocity']])),(tick+72,bytes([0x89,hit['pitch'],0]))]
    data=bytearray(b'\x00\xff\x51\x03\x07\xa1\x20');last=0
    for tick,msg in sorted(events,key=lambda x:x[0]):data+=var(tick-last)+msg;last=tick
    data+=b'\x00\xff\x2f\x00'
    Path(output).write_bytes(b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(data))+data)


def read_rpp(path):
    """Parse chunk boundaries; plugin state is data, never executable instructions."""
    import shlex
    stack=[];root=None
    for line in Path(path).read_text(encoding='utf-8-sig',errors='replace').splitlines():
        line=line.strip()
        if not line:continue
        if line=='>':
            if stack:stack.pop()
            continue
        if line.startswith('<'):
            chunk=dict(kind=line[1:].split()[0],lines=[],children=[])
            if stack:stack[-1]['children'].append(chunk)
            elif root is None:root=chunk
            stack.append(chunk)
        elif stack:
            try:tokens=shlex.split(line)
            except ValueError:continue
            if tokens:stack[-1]['lines'].append(tokens)
    if root is None or root['kind']!='REAPER_PROJECT':raise ValueError(ui_text('Ce fichier ne contient pas de projet REAPER.', 'This file does not contain a REAPER project.'))
    return root


def import_reaper(path,output,engine,snapshot):
    import numpy as np
    import soundfile as sf
    source=Path(path).resolve();tree=read_rpp(source);folder=Path(output).parent/'Imported.bandstudio';media=folder/'Audio';media.mkdir(parents=True,exist_ok=True)
    roles_by_file={}
    metadata=source.parent/'bandstudio-project.json'
    if metadata.is_file():
        saved=json.loads(metadata.read_text())
        if saved.get('rppSHA256')==hashlib.sha256(source.read_bytes()).hexdigest():roles_by_file=saved.get('trackRoles',{})
    p=json.loads(Path(snapshot).read_text());settings=import_settings(p['settings']);settings['countBars']=0
    p=dict(version=1,id=str(uuid.uuid4()),name=source.stem,tracks=[],sections=[],cues=[],bpm=120,beats=[],notes='',settings=settings,guideFiles={},guideKey='',lyrics=[],chords=[],drumHits=[],key='',sourceURL='')
    warnings=[]
    def field(chunk,name,default):return next((r[1:] for r in chunk['lines'] if r[0]==name),default)
    def num(values,index,default=0):
        try:
            value=float(values[index]);return value if math.isfinite(value) else default
        except (ValueError,IndexError,TypeError):return default
    tempo=field(tree,'TEMPO',['120','4']);p['bpm']=max(20,min(400,num(tempo,0,120)));settings['beatsPerBar']=max(1,min(12,int(num(tempo,1,4))));settings['manualBPM']=p['bpm']
    compound=int(num(tempo,2,4))==8 and int(num(tempo,1,4)) in (6,9,12)
    settings['pulseUnit']='dottedQuarter' if compound else 'quarter'
    if compound:settings['beatsPerBar']=int(num(tempo,1,4))//3;p['bpm']/=1.5
    guide_names={'click','voice','cues','métronome','appels de régions','décompte des régions','décompte','annonce de départ'}
    for track in [c for c in tree['children'] if c['kind']=='TRACK']:
        name=' '.join(field(track,'NAME',[ui_text('Piste', 'Track')]))
        if name.lower().strip() in guide_names:continue # Rebuilt from the editable imported regions.
        if any(c['kind']=='FXCHAIN' for c in track['children']):warnings.append(ui_text('Les effets REAPER restent dans le RPP et ne sont pas reproduits ici.', 'REAPER effects remain in the RPP. This player does not reproduce them.'))
        vp=field(track,'VOLPAN',['1','0']);ms=field(track,'MUTESOLO',['0','0']);items=[c for c in track['children'] if c['kind']=='ITEM']
        for index,item in enumerate(items):
            sources=[c for c in item['children'] if c['kind']=='SOURCE'];src=sources[0] if sources else {}
            filename=field(src,'FILE',[]) if src else []
            if not filename:
                warnings.append(ui_text('Une source MIDI, générée ou composée a été ignorée.', 'Skipped a MIDI, generated or composite source.'));continue
            audio=Path(filename[0]);audio=audio if audio.is_absolute() else source.parent/audio
            if not audio.is_file():raise FileNotFoundError(ui_text('Média REAPER introuvable : ', 'REAPER media not found: ')+str(audio))
            length=num(field(item,'LENGTH',['0']),0);offset=num(field(item,'POSITION',['0']),0);skip=max(0,num(field(item,'SOFFS',['0']),0))
            if length<=0 or length>43200 or offset<0:raise ValueError(ui_text('Durée ou position non prise en charge dans le projet REAPER.', 'Unsupported duration or position in the REAPER project.'))
            rate_values=field(item,'PLAYRATE',['1','1','0']);rate=max(.1,min(8,num(rate_values,0,1)));preserve=num(rate_values,1,1)!=0;pitch=max(-36,min(36,num(rate_values,2,0)))
            factor=2**(pitch/12)*(1 if preserve else rate)
            filters=['aresample=44100']
            if abs(factor-1)>1e-7:filters += ['asetrate='+str(44100*factor),'aresample=44100']
            speed=rate/factor
            while speed>2:filters.append('atempo=2');speed/=2
            while speed<.5:filters.append('atempo=0.5');speed/=.5
            if abs(speed-1)>1e-7:filters.append('atempo='+str(speed))
            ident=str(uuid.uuid4());target=media/(ident+'.wav')
            command=[executable(engine,'ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y']
            if num(field(item,'LOOP',['0']),0)!=0:command+=['-stream_loop','-1']
            command+=['-ss',str(skip),'-protocol_whitelist','file,pipe,crypto,data','-i',audio,'-t',str(length),'-map','0:a:0','-vn','-af',','.join(filters),'-ac','2','-ar','44100','-c:a','pcm_f32le',target]
            run(command)
            info=sf.info(target);peaks=np.zeros(720,dtype=np.float32);at=0
            for block in sf.blocks(target,blocksize=65536,dtype='float32',always_2d=True):
                bins=np.minimum(719,(np.arange(len(block))+at)*720//info.frames);np.maximum.at(peaks,bins,np.abs(block).max(axis=1));at+=len(block)
            role='other';lower=name.lower()
            for candidate,words in [('source',['original','source']),('drums',['drum','batterie']),('bass',['bass','basse']),('vocals',['vocal','chant']),('guitar',['guitar','guitare']),('piano',['piano','clavier']),('take',['prise'])]:
                if any(w in lower for w in words):role=candidate;break
            restored_role=roles_by_file.get(Path(filename[0]).name)
            if restored_role in ('source','drums','drum_kick','drum_snare','drum_toms','drum_cymbals','vocal_lead','vocal_backing','bass','vocals','guitar','piano','other','take'):role=restored_role
            itemvp=field(item,'VOLPAN',['1','0']);gain=max(0,min(2,num(vp,0,1)*num(itemvp,0,1)));pan=max(-1,min(1,num(vp,1)+num(itemvp,1)))
            p['tracks'].append(dict(id=ident,name=name+(f' · {index+1}' if len(items)>1 else ''),file='Audio/'+target.name,role=role,duration=info.duration,offset=offset,gain=gain,pan=pan,muted=num(ms,0)!=0 or num(field(item,'MUTE',['0']),0)!=0,solo=num(ms,1)!=0,peaks=peaks.tolist()))
    if not p['tracks']:raise ValueError(ui_text('Aucune piste audio à importer. Dans REAPER, rends les instruments MIDI en audio avant l’import.', 'No audio tracks to import. Render MIDI instruments to audio in REAPER first.'))
    if len(p['tracks'])>125:raise ValueError(ui_text('Le projet contient trop de clips audio. Consolide les pistes dans REAPER avant l’import.', 'Too many audio clips. Consolidate tracks in REAPER before importing.'))
    duration=max(t['offset']+t['duration'] for t in p['tracks']);starts={}
    for row in tree['lines']:
        if row[0]!='MARKER' or len(row)<4:continue
        ident=row[1];at=float(row[2]);name=row[3];is_region=len(row)>4 and row[4]=='1'
        if not math.isfinite(at) or at<0:continue
        if is_region:
            if ident in starts:
                begin,title=starts.pop(ident);end=min(duration,at)
                if end>begin:p['sections'].append(dict(id=str(uuid.uuid4()),start=begin,end=end,name=title or 'Section',locked=True,origin='manual'))
            else:starts[ident]=(at,name)
        elif at<=duration:p['cues'].append(dict(id=str(uuid.uuid4()),time=at,name=name or 'Repère'))
    p['sections'].sort(key=lambda s:s['start']);p['cues'].sort(key=lambda s:s['time'])
    points=[(0.,p['bpm'])]
    for env in [c for c in tree['children'] if c['kind']=='TEMPOENVEX']:
        for row in env['lines']:
            if row[0]=='PT' and len(row)>2:
                at,bpm=float(row[1]),float(row[2])
                if 0<=at<duration and 20<=bpm<=400:points.append((at,bpm/pulse_scale(settings)))
    points=sorted(dict(points).items())
    for i,(start,bpm) in enumerate(points):
        end=points[i+1][0] if i+1<len(points) else duration
        p['beats'] += [start+j*60/bpm for j in range(math.ceil((end-start)*bpm/60)) if start+j*60/bpm<end-1e-6]
    metadata=source.parent/'bandstudio-project.json'
    if metadata.is_file():
        saved=json.loads(metadata.read_text())
        if saved.get('rppSHA256')==hashlib.sha256(source.read_bytes()).hexdigest():
            shift=saved.get('exportPreroll',0)
            if isinstance(saved.get('name'),str) and saved['name'].strip():p['name']=saved['name']
            for kind in ['lyrics','chords']:
                for item in saved.get(kind) or []:
                    entry={**item,'start':item['start']+shift,'end':item['end']+shift}
                    if item.get('words'):entry['words']=[{**w,'start':w['start']+shift,'end':w['end']+shift} for w in item['words']]
                    p[kind].append(entry)
            p['drumHits']=[{**h,'time':h['time']+shift} for h in saved.get('drumHits') or []]
            p['key']=saved.get('key') or '';p['sourceURL']=saved.get('sourceURL') or ''
            p['lyricsReference']=saved.get('lyricsReference');p['capo']=saved.get('capo') or 0;p['gridLocked']=saved.get('gridLocked',True);p['analysisNote']=saved.get('analysisNote') or ''
            p['downbeats']=[t+shift for t in saved.get('downbeats') or []]
            if saved.get('settings'):
                p['settings']={**saved['settings'],'countBars':0,
                               'firstBeat':saved['settings'].get('firstBeat',0)+shift}
            if saved.get('timingVersion')==1:
                p['beats']=[t+shift for t in saved.get('beats') or []]
                p['bpm']=saved.get('bpm',p['bpm'])
        else:warnings.append(ui_text('Le RPP a été modifié : les anciennes annotations de paroles et d’accords doivent être resynchronisées.', 'The RPP has changed. Resync the old lyrics and chord annotations.'))
    p['notes']=ui_text('Import audio du projet REAPER. Les régions et repères gardent leurs temps d’origine.\n', 'Audio imported from the REAPER project. Regions and markers keep their original times.\n')+'\n'.join(dict.fromkeys(warnings))
    atomic(folder/'project.json',p);atomic(output,dict(project=str(folder),warnings=list(dict.fromkeys(warnings))))
