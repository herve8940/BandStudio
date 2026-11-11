"""Portable project services: audible guides, media decoding and REAPER exchange."""
from __future__ import annotations
from listening import included
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from urllib.parse import urlsplit
import uuid
from platform_tools import executable, python_for, creation_flags


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
        if proc.returncode:raise RuntimeError(err.decode(errors='replace')[-1800:] or 'Le traitement média a échoué.')
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


def checked_url(value):
    if not isinstance(value,str) or len(value)>4096:raise ValueError('Lien invalide.')
    u=urlsplit(value.strip())
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:
        raise ValueError('Utilise un lien public HTTP ou HTTPS.')
    if '\n' in value or '\r' in value:raise ValueError('Lien invalide.')
    # The user explicitly chooses the URL. Never inherit browser cookies or account credentials.
    return value.strip()


def import_link(url,output,engine):
    url=checked_url(url);folder=Path(output).parent;folder.mkdir(parents=True,exist_ok=True)
    args=[python_for(engine,'.venv-import'),'-m','yt_dlp','--ignore-config','--no-plugin-dirs',
          '--no-playlist','--no-cookies','--no-cookies-from-browser','--no-remote-components',
          '--no-js-runtimes','--js-runtimes','deno:'+str(executable(engine,'deno')),
          '--socket-timeout','25','--retries','2','--max-filesize','1G',
          '--match-filter','!is_live & duration <= 10800','--ffmpeg-location',engine/'import-tools',
          '--write-info-json','--write-thumbnail','--no-progress','-f','bestaudio/best','-o',folder/'source.%(ext)s','--',url]
    run(args,timeout=3600)
    metadata=next(folder.glob('source.info.json'),None)
    info=json.loads(metadata.read_text()) if metadata else {}
    files=[p for p in folder.glob('source.*') if p.suffix not in ('.json','.part','.ytdl','.jpg','.jpeg','.png','.webp','.avif')]
    if len(files)!=1:raise RuntimeError('Aucun fichier audio unique reçu. Choisis un lien vers un morceau ou une vidéo.')
    target=folder/'import.wav';decode(files[0],target,engine)
    from catalog import extract
    picture=next((p for p in folder.glob('source.*') if p.suffix in ('.jpg','.jpeg','.png','.webp','.avif')),files[0])
    artwork=str(folder/'Artwork.jpg') if extract(picture,folder,engine) else None
    atomic(output,dict(audio=str(target),title=str(info.get('title') or 'Morceau importé'),sourceURL=url,artwork=artwork))


def beat_grid(project):
    settings=project['settings'];duration=max(t['offset']+t['duration'] for t in project['tracks'] if not t['role'].startswith('guide_'))
    beats=sorted({float(x) for x in project.get('beats',[]) if math.isfinite(x) and 0<=x<=duration})
    bpm=settings['manualBPM'] if settings['gridMode']=='fixed' else project.get('bpm') or settings['manualBPM']
    if settings['gridMode']=='fixed' or len(beats)<2:
        dt=60/bpm;first=settings['firstBeat']
        while first<0:first+=dt
        beats=[first+i*dt for i in range(max(0,int((duration-first)/dt)+1))]
    return beats,duration


def before_beat(target,amount,beats,bpm):
    if not amount:return target
    if len(beats)>1:
        i=max(0,min(len(beats)-1,bisect.bisect_right(beats,target+0.02)-1))
        frac=target-beats[i]
        if i>=amount:return beats[i-amount]+frac
        return beats[0]+frac-(amount-i)*(beats[1]-beats[0])
    return target-amount*60/max(20,bpm)


def region_count_beats(target,amount,beats):
    """Place spoken numbers on existing clicks, never on an offset copy of the grid."""
    # Use the closest click as the passage's musical entry without moving its region.
    # Otherwise a region 100 ms after a beat would speak "four" on that entry beat.
    if not beats:return []
    right=bisect.bisect_left(beats,target)
    candidates=[i for i in (right-1,right) if 0<=i<len(beats)]
    stop=min(candidates,key=lambda i:(abs(beats[i]-target),i))
    if not stop:return []
    if target>beats[-1]:
        span=beats[-1]-beats[-2] if len(beats)>1 else 0
        # Do not invent a countdown in a tail where beat detection has stopped.
        if span<=0 or target-beats[-1]>span*1.25:return []
    first=max(0,stop-amount)
    return [dict(number=amount-(stop-index)+1,time=beats[index],
                 end=beats[index+1])
            for index in range(first,stop)]


def voice_wav(text,folder,settings):
    import numpy as np
    import soundfile as sf
    import scipy.signal
    text=str(text).strip()[:240]
    if not text:return None
    digest=hashlib.sha256(('speech-v3:'+str(os.name)+settings['language']+settings['voice']+str(settings['speechRate'])+text).encode()).hexdigest()[:24]
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
    if not len(x) or float(np.max(np.abs(x)))<1e-6:raise RuntimeError('La voix choisie ne produit aucun son. Choisis une voix installée.')
    active=np.flatnonzero(np.max(np.abs(x),axis=1)>np.max(np.abs(x))*0.018)
    x=x[max(0,int(active[0]) - int(sr*.003)):min(len(x),int(active[-1])+int(sr*.03))]
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


def guides(project_file,output):
    import numpy as np
    import soundfile as sf
    p=json.loads(Path(project_file).read_text());s=p['settings']
    root=Path(output).parent;cache=root/'voice';cache.mkdir(parents=True,exist_ok=True)
    beats,duration=beat_grid(p);sr=44100
    # Memory-mapped timelines avoid allocating two whole stereo songs in RAM.
    shape=(max(1,math.ceil(duration*sr)),2)
    click=np.memmap(root/'click.raw',dtype='float32',mode='w+',shape=shape);click[:]=0
    calls=np.memmap(root/'calls.raw',dtype='float32',mode='w+',shape=shape);calls[:]=0
    counts=np.memmap(root/'counts.raw',dtype='float32',mode='w+',shape=shape);counts[:]=0
    def place(dest,data,at):
        start=round(at*sr)
        if start<0:data=data[-start:];start=0
        n=min(len(data),len(dest)-start)
        if n>0:dest[start:start+n]+=data[:n]
    first=min(range(len(beats)),key=lambda i:abs(beats[i]-s['firstBeat'])) if beats else 0
    for i,beat in enumerate(beats):
        span=beats[i+1]-beat if i+1<len(beats) else (beats[-1]-beats[-2] if len(beats)>1 else 60/s['manualBPM'])
        for sub in range(s['subdivision']):
            accented=sub==0 and (i-first)%s['beatsPerBar']==0
            n=int(sr*.035);t=np.arange(n)/sr
            sound=np.sin(2*np.pi*(1760 if accented else 1100)*t)*np.exp(-t*130)*(0.8 if sub==0 else 0.35)
            place(click,np.repeat(sound[:,None],2,axis=1),beat+sub*span/s['subdivision'])
    file_map={};events=[];count_events=[]
    count_plans={item['id']:region_count_beats(item['start'],s['regionCountBeats'],beats)
                 for item in p.get('sections',[])}
    for item in p.get('sections',[])+ (p.get('cues',[]) if s['speakCues'] else []):
        if item.get('announce') is False or not s['callsEnabled']:continue
        text=announcement_text(item,s['language']);target=item.get('start',item.get('time',0))
        path=voice_wav(text,cache,s)
        if path:
            file_map['call:'+item['id']]=str(path)
            x,_=sf.read(path,dtype='float32',always_2d=True)
            at=before_beat(target,s['leadBeats'],beats,p.get('bpm') or s['manualBPM'])
            # Calls before time zero are played during the initial count-in by the native engine.
            # Reserve the final spoken beats for the region count, avoiding two voices at once.
            if 'start' in item and s['regionCountEnabled'] and s['countVoice']:
                plan=count_plans[item['id']]
                if plan:at=min(at,plan[0]['time']-len(x)/sr-.05)
            if at>=0:place(calls,x,at);events.append(dict(time=at,target=target,text=text,file=str(path)))
    words={'fr':['un','deux','trois','quatre','cinq','six','sept','huit','neuf','dix','onze','douze'],
           'en':['one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve']}
    if s['countVoice']:
        for i,text in enumerate(words[s['language']][:max(s['beatsPerBar'],s['regionCountBeats'])]):file_map['number:'+str(i+1)]=str(voice_wav(text,cache,s))
    for item in p.get('sections',[]):
        if item.get('announce') is False:continue
        for event in count_plans[item['id']]:
            number,at,end=event['number'],event['time'],event['end']
            count_events.append(dict(section=item['id'],target=item['start'],number=number,time=at,end=end))
            if s['countVoice']:
                x,_=sf.read(file_map['number:'+str(number)],dtype='float32',always_2d=True)
                place(counts,x[:max(0,int((end-at)*sr*.92))],at)
            if s['countClick']:
                t=np.arange(int(sr*.035))/sr;wave=.65*np.sin(2*np.pi*(1760 if number==1 else 1100)*t)*np.exp(-t*130)
                place(counts,np.repeat(wave[:,None],2,axis=1),at)
    for name,data in [('click',click),('calls',calls),('counts',counts)]:
        path=root/(name+'.wav')
        with sf.SoundFile(path,'w',samplerate=sr,channels=2,subtype='FLOAT') as writer:
            for a in range(0,len(data),65536):writer.write(np.clip(data[a:a+65536],-1,1))
        file_map[name]=str(path)
    # The loop variable also holds the final mmap; release it before unlinking on Windows.
    del data,click,calls,counts
    for name in ['click','calls','counts']:(root/(name+'.raw')).unlink()
    atomic(output,dict(files=file_map,events=events,countEvents=count_events,beats=beats,duration=duration))


def quote(value):
    # REAPER string tokens cannot contain literal line breaks or quotation marks.
    return '"'+str(value).replace('"',"'").replace('\r',' ').replace('\n',' ')+'"'


def export_reaper(project_file,output):
    p=json.loads(Path(project_file).read_text());root=Path(project_file).parent
    # Snapshots carry the real root explicitly; it is supplied by the native host.
    root=Path(p.get('_root',root));s=p['settings'];target=Path(output).parent/'REAPER';target.mkdir(parents=True,exist_ok=True)
    media=target/'Audio';media.mkdir(exist_ok=True)
    beats,duration=beat_grid(p)
    bpm=s['manualBPM'] if s['gridMode']=='fixed' else p.get('bpm') or s['manualBPM'];period=(beats[1]-beats[0]) if len(beats)>1 else 60/bpm
    preroll=s['countBars']*s['beatsPerBar']*period if s['exportCount'] else 0
    lines=['<REAPER_PROJECT 0.1 7.0 1','  SAMPLERATE 44100','  TEMPO '+str(bpm)+' '+str(s['beatsPerBar'])+' 4', '  MASTER_VOLUME 0.85']
    if beats and s['gridMode']=='detected':
        lines+=['  <TEMPOENVEX','    ACT 1 -1','    VIS 1 0 0','    ARM 1','    DEFSHAPE 1 -1 -1']
        for i,b in enumerate(beats[:-1]):
            dt=beats[i+1]-b
            if dt>0.1:lines.append(f'    PT {b+preroll:.9f} {60/dt:.9f} 1')
        lines+=['  >']
    for i,section in enumerate(p['sections'],1):
        lines += [f'  MARKER {i} {section["start"]+preroll:.9f} {quote(section["name"])} 1',f'  MARKER {i} {section["end"]+preroll:.9f} "" 1']
    for i,cue in enumerate(p['cues'],len(p['sections'])+1):lines.append(f'  MARKER {i} {cue["time"]+preroll:.9f} {quote(cue["name"])} 0')
    has_stems=any(t['role'] not in ('source','take') and not t['role'].startswith('guide_') for t in p['tracks'])
    mode=p.get('_mode','mix')
    has_solo=any(t['solo'] for t in p['tracks'] if t['role']!='source' and not t['role'].startswith('guide_'))
    for t in p['tracks']:
        if t['role'].startswith('guide_') and not s['exportGuides']:continue
        original=(root/t['file']).resolve()
        if not original.is_relative_to(root.resolve()):raise ValueError('Fichier hors du projet.')
        name=str(uuid.uuid5(uuid.NAMESPACE_OID,t['id']))+'.wav';dest=media/name
        if not dest.exists():
            if original.suffix.lower()=='.wav':shutil.copy2(original,dest)
            else:decode(original,dest,Path(__file__).resolve().parent)
        audible=not t['muted'] and (not has_solo or t['solo'])
        if mode=='original':audible=t['role']=='source' and not t['muted']
        elif t['role']=='source':audible=mode=='mix' and not has_stems and not t['muted'] and not has_solo
        else:audible=audible and included(t['role'],mode)
        if t['role']=='vocals' and any(x['role'].startswith('vocal_') for x in p['tracks']) and not t['solo']:audible=False
        if t['role']=='drums' and any(x['role'].startswith('drum_') for x in p['tracks']) and not t['solo']:audible=False
        muted=not audible
        gain=t['gain'];pan=t['pan']
        if t['role']=='guide_click':muted=not s['clickEnabled'];gain=s['clickGain'];pan=s['clickPan']
        if t['role']=='guide_voice':muted=not s['callsEnabled'];gain=s['callsGain'];pan=s['callsPan']
        if t['role']=='guide_count':muted=not s['regionCountEnabled'];gain=s['countGain'];pan=s['countPan']
        offset=t['offset']+preroll;skip=max(0,-offset)
        lines += ['  <TRACK','    NAME '+quote(t['name']),f'    VOLPAN {gain:.8f} {pan:.8f}',f'    MUTESOLO {int(muted)} 0 0',
                  '    <ITEM','      BEAT 0',f'      POSITION {max(0,offset):.9f}',f'      SOFFS {skip:.9f}',f'      LENGTH {max(0,t["duration"]-skip):.9f}',
                  '      VOLPAN 1 0 1 -1','      NAME '+quote(t['name']),'      <SOURCE WAVE','        FILE '+quote('Audio/'+name),'      >','    >','  >']
    if preroll>0:
        count=render_count(p,root,period,preroll,media/'count-in.wav')
        lines+=['  <TRACK','    NAME "Décompte"',f'    VOLPAN {s["countGain"]} {s["countPan"]}','    <ITEM','      POSITION 0',f'      LENGTH {preroll:.9f}','      <SOURCE WAVE','        FILE "Audio/count-in.wav"','      >','    >','  >']
        if s['exportGuides'] and s['callsEnabled'] and (s['countBars']>1 or not s['countVoice']):
            first=next((x for x in p['sections'] if x['start']<=.1 and x.get('announce') is not False),None)
            relative=p.get('guideFiles',{}).get('call:'+first['id']) if first else None
            if relative:
                import soundfile as sf
                initial=media/'initial-call.wav';shutil.copy2(root/relative,initial)
                length=min(sf.info(initial).duration,preroll-(s['beatsPerBar']*period if s['countVoice'] else 0))
                lines+=['  <TRACK','    NAME "Annonce de départ"',f'    VOLPAN {s["callsGain"]} {s["callsPan"]}','    <ITEM','      POSITION 0',f'      LENGTH {length:.9f}','      <SOURCE WAVE','        FILE "Audio/initial-call.wav"','      >','    >','  >']
    lines+=['>'];rpp=target/(safe_name(p['name'])+'.rpp');rpp.write_text('\n'.join(lines)+'\n')
    # Annotations have no native RPP representation. Bind their timing to this exact export.
    metadata={key:p.get(key) for key in ['settings','notes','lyrics','chords','drumHits','key','sourceURL','capo','downbeats','gridLocked','analysisNote']}
    metadata.update(exportPreroll=preroll,rppSHA256=hashlib.sha256(rpp.read_bytes()).hexdigest(),trackRoles={str(uuid.uuid5(uuid.NAMESPACE_OID,t['id']))+'.wav':t['role'] for t in p['tracks']})
    atomic(target/'bandstudio-project.json',metadata)
    atomic(output,dict(path=str(rpp),folder=str(target),preroll=preroll))


def render_count(p,root,period,duration,target):
    import numpy as np
    import soundfile as sf
    s=p['settings'];sr=44100;y=np.zeros((math.ceil(duration*sr),2),dtype='float32')
    for beat in range(s['countBars']*s['beatsPerBar']):
        at=round(beat*period*sr)
        if s['countClick']:
            t=np.arange(int(sr*.035))/sr;wave=.65*np.sin(2*np.pi*(1760 if beat%s['beatsPerBar']==0 else 1100)*t)*np.exp(-t*130)
            n=min(len(wave),len(y)-at);y[at:at+n]+=wave[:n,None]
        if s['countVoice'] and beat>=(s['countBars']-1)*s['beatsPerBar']:
            path=p.get('guideFiles',{}).get('number:'+str(beat%s['beatsPerBar']+1))
            if path:
                x,_=sf.read(root/path,dtype='float32',always_2d=True);n=min(len(x),int(period*sr*.92),len(y)-at);y[at:at+n]+=x[:n]
    sf.write(target,np.clip(y,-1,1),sr,subtype='FLOAT');return target


def safe_name(name):return re.sub(r'[\x00-\x1f/\\:*?"<>|]','-',str(name))[:100].strip(' .') or 'Morceau'


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
    for line in Path(path).read_text(errors='replace').splitlines():
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
    if root is None or root['kind']!='REAPER_PROJECT':raise ValueError('Ce fichier ne contient pas de projet REAPER.')
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
    p=json.loads(Path(snapshot).read_text());settings=p['settings'].copy();settings['countBars']=0
    p=dict(version=1,id=str(uuid.uuid4()),name=source.stem,tracks=[],sections=[],cues=[],bpm=120,beats=[],notes='',settings=settings,guideFiles={},guideKey='',lyrics=[],chords=[],drumHits=[],key='',sourceURL='')
    warnings=[]
    def field(chunk,name,default):return next((r[1:] for r in chunk['lines'] if r[0]==name),default)
    def num(values,index,default=0):
        try:
            value=float(values[index]);return value if math.isfinite(value) else default
        except (ValueError,IndexError,TypeError):return default
    tempo=field(tree,'TEMPO',['120','4']);p['bpm']=max(20,min(400,num(tempo,0,120)));settings['beatsPerBar']=max(1,min(12,int(num(tempo,1,4))));settings['manualBPM']=p['bpm']
    guide_names={'click','voice','cues','métronome','appels de régions','décompte des régions','décompte','annonce de départ'}
    for track in [c for c in tree['children'] if c['kind']=='TRACK']:
        name=' '.join(field(track,'NAME',['Piste']))
        if name.lower().strip() in guide_names:continue # Rebuilt from the editable imported regions.
        if any(c['kind']=='FXCHAIN' for c in track['children']):warnings.append('Les effets REAPER restent dans le RPP et ne sont pas reproduits ici.')
        vp=field(track,'VOLPAN',['1','0']);ms=field(track,'MUTESOLO',['0','0']);items=[c for c in track['children'] if c['kind']=='ITEM']
        for index,item in enumerate(items):
            sources=[c for c in item['children'] if c['kind']=='SOURCE'];src=sources[0] if sources else {}
            filename=field(src,'FILE',[]) if src else []
            if not filename:
                warnings.append('Une source MIDI, générée ou composée a été ignorée.');continue
            audio=Path(filename[0]);audio=audio if audio.is_absolute() else source.parent/audio
            if not audio.is_file():raise FileNotFoundError('Média REAPER introuvable : '+str(audio))
            length=num(field(item,'LENGTH',['0']),0);offset=num(field(item,'POSITION',['0']),0);skip=max(0,num(field(item,'SOFFS',['0']),0))
            if length<=0 or length>43200 or offset<0:raise ValueError('Durée ou position non prise en charge dans le projet REAPER.')
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
    if not p['tracks']:raise ValueError('Aucune piste audio à importer. Dans REAPER, rends les instruments MIDI en audio avant l’import.')
    if len(p['tracks'])>125:raise ValueError('Le projet contient trop de clips audio. Consolide les pistes dans REAPER avant l’import.')
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
                if 0<=at<duration and 20<=bpm<=400:points.append((at,bpm))
    points=sorted(dict(points).items())
    for i,(start,bpm) in enumerate(points):
        end=points[i+1][0] if i+1<len(points) else duration
        p['beats'] += [start+j*60/bpm for j in range(math.ceil((end-start)*bpm/60)) if start+j*60/bpm<end-1e-6]
    metadata=source.parent/'bandstudio-project.json'
    if metadata.is_file():
        saved=json.loads(metadata.read_text())
        if saved.get('rppSHA256')==hashlib.sha256(source.read_bytes()).hexdigest():
            shift=saved.get('exportPreroll',0)
            for kind in ['lyrics','chords']:
                for item in saved.get(kind) or []:
                    entry={**item,'start':item['start']+shift,'end':item['end']+shift}
                    if item.get('words'):entry['words']=[{**w,'start':w['start']+shift,'end':w['end']+shift} for w in item['words']]
                    p[kind].append(entry)
            p['drumHits']=[{**h,'time':h['time']+shift} for h in saved.get('drumHits') or []]
            p['key']=saved.get('key') or '';p['sourceURL']=saved.get('sourceURL') or ''
            p['capo']=saved.get('capo') or 0;p['gridLocked']=saved.get('gridLocked',True);p['analysisNote']=saved.get('analysisNote') or ''
            p['downbeats']=[t+shift for t in saved.get('downbeats') or []]
            if saved.get('settings'):p['settings']={**saved['settings'],'countBars':0}
        else:warnings.append('Le RPP a été modifié : les anciennes annotations de paroles et d’accords doivent être resynchronisées.')
    p['notes']='Import audio du projet REAPER. Les régions et repères gardent leurs temps d’origine.\n'+'\n'.join(dict.fromkeys(warnings))
    atomic(folder/'project.json',p);atomic(output,dict(project=str(folder),warnings=list(dict.fromkeys(warnings))))
