"""Portable audio timeline: the same block mixer is used offline and by PortAudio."""
import copy
import hashlib
import math
from pathlib import Path
import subprocess
import threading
import time
import warnings
import numpy as np
import soundfile as sf
from scipy.io import wavfile
from platform_tools import executable,creation_flags
from windows.project import duration,period,relative_file

SR=44100

def pcm(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');rate,data=wavfile.read(path,mmap=True)
    if rate!=SR or data.dtype!=np.float32:raise ValueError('Le média doit être converti en WAV flottant 44,1 kHz.')
    if data.ndim==1:data=data[:,None]
    if data.shape[1]!=2:raise ValueError('Le lecteur attend un média stéréo.')
    return data

def converted(source,cache,engine,rate=1,pitch=0):
    info=sf.info(source)
    if abs(rate-1)<1e-8 and abs(pitch)<1e-8 and info.format=='WAV' and info.subtype=='FLOAT' and info.samplerate==SR and info.channels==2:return source
    stamp=f'{Path(source).resolve()}:{Path(source).stat().st_size}:{Path(source).stat().st_mtime_ns}:{rate}:{pitch}'
    dest=cache/(hashlib.sha256(stamp.encode()).hexdigest()+'.wav')
    if dest.exists():return dest
    cache.mkdir(parents=True,exist_ok=True)
    factor=2**(pitch/12);filters=[]
    if abs(factor-1)>1e-8:filters=['asetrate='+str(SR*factor),'aresample='+str(SR)]
    speed=rate/factor
    while speed>2:filters.append('atempo=2');speed/=2
    while speed<.5:filters.append('atempo=0.5');speed/=.5
    if abs(speed-1)>1e-8:filters.append('atempo='+str(speed))
    temp=dest.with_suffix('.tmp.wav')
    args=[str(executable(engine,'ffmpeg')),'-hide_banner','-nostdin','-loglevel','error','-y','-i',str(source),'-af',','.join(filters) or 'anull','-ac','2','-ar',str(SR),'-c:a','pcm_f32le',str(temp)]
    r=subprocess.run(args,capture_output=True,creationflags=creation_flags(),timeout=1800)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-1000:])
    temp.replace(dest);return dest

def pan_gain(gain,pan):return np.array([gain*(1-max(0,pan)),gain*(1+min(0,pan))],dtype=np.float32)

class Audio:
    def __init__(self,engine):
        self.engine=Path(engine);self.lock=threading.RLock();self.stream=None;self.running=False;self.position=0.;self.rate=1.;self.pitch=0.;self.mode='mix';self.loop=False;self.loopStart=0.;self.loopEnd=0.;self.project=None;self.root=None;self.data={};self.count=np.zeros((0,2),np.float32);self.loop_count=self.count;self.count_at=0;self.laps=0;self.pending_rate=None;self.error='';self.output_anchor=None
    def close(self):
        self.pause()
        if self.stream:self.stream.close();self.stream=None
    def load(self,p,root):
        self.close();self.project=copy.deepcopy(p);self.root=Path(root);self.position=0
        self.mode='original' if any(t['role']=='source' for t in p['tracks']) else 'mix'
        self.prepare()
    def prepare(self):
        self.data={}
        for t in self.project['tracks']:
            file=relative_file(self.root,t['file']);pitch=0 if t['role'].startswith('guide_') else self.pitch
            self.data[t['id']]=pcm(converted(file,self.root/'Cache/audio',self.engine,self.rate,pitch))
    def mix(self,start,frames,include_guides=True):
        p=self.project;s=p['settings'];out=np.zeros((frames,2),np.float32)
        has_stems=any(t['role'] not in ('source','take') and not t['role'].startswith('guide_') for t in p['tracks'])
        solo=any(t['solo'] for t in p['tracks'] if t['role']!='source' and not t['role'].startswith('guide_'))
        for t in p['tracks']:
            role=t['role'];gain=t['gain'];pan=t['pan'];on=not t['muted'] and (not solo or t['solo'])
            if role.startswith('guide_'):
                key={'guide_click':'click','guide_voice':'calls','guide_count':'count'}[role]
                on=include_guides and s['regionCountEnabled' if role=='guide_count' else key+'Enabled'];gain=s[key+'Gain'];pan=s[key+'Pan']
            elif self.mode=='original':on=role=='source' and not t['muted']
            elif role=='source':on=self.mode=='mix' and not has_stems and not t['muted'] and not solo
            elif self.mode=='minus':on=on and role!='drums' and not role.startswith('drum_')
            elif self.mode=='drums':on=on and (role=='drums' or role.startswith('drum_'))
            if role=='vocals' and any(x['role'].startswith('vocal_') for x in p['tracks']) and not t['solo']:on=False
            if role=='drums' and any(x['role'].startswith('drum_') for x in p['tracks']) and not t['solo']:on=False
            if not on:continue
            data=self.data[t['id']];offset=round((start-t['offset'])/self.rate*SR);begin=max(0,-offset);source=max(0,offset);n=min(frames-begin,len(data)-source)
            if n>0:out[begin:begin+n]+=data[source:source+n]*pan_gain(gain,pan)
        return out
    def make_count(self,at,include_call=True):
        p=self.project;s=p['settings'];beat=period(p,at)/self.rate;bars=s['countBars'];length=round(bars*s['beatsPerBar']*beat*SR);out=np.zeros((length,2),np.float32)
        def place(x,offset,gain,pan):
            a=round(offset*SR);n=min(len(x),length-a)
            if n>0:out[a:a+n]+=x[:n]*pan_gain(gain,pan)
        for i in range(bars*s['beatsPerBar']):
            if s['countClick']:
                t=np.arange(int(SR*.035/self.rate))/SR;x=.65*np.sin(2*np.pi*(1760 if i%s['beatsPerBar']==0 else 1100)*t)*np.exp(-t*130*self.rate);place(np.column_stack((x,x)),i*beat,s['countGain'],s['countPan'])
            key='number:'+str(i%s['beatsPerBar']+1)
            if s['countVoice'] and i>=(bars-1)*s['beatsPerBar'] and key in p['guideFiles']:
                x=pcm(converted(relative_file(self.root,p['guideFiles'][key]),self.root/'Cache/audio',self.engine,self.rate,0));place(x[:int(beat*SR*.92)],i*beat,s['countGain'],s['countPan'])
        if length and include_call and s['callsEnabled'] and (bars>1 or not s['countVoice']):
            section=next((x for x in p['sections'] if x['start']<=at+.1 and x['end']>at and x.get('announce') is not False),None)
            key='call:'+section['id'] if section else ''
            if key in p['guideFiles']:
                x=pcm(converted(relative_file(self.root,p['guideFiles'][key]),self.root/'Cache/audio',self.engine,self.rate,0));limit=length-(round(s['beatsPerBar']*beat*SR) if s['countVoice'] else 0);place(x[:limit],0,s['callsGain'],s['callsPan'])
        return out
    def play(self,with_count=True,hardware=True):
        if self.running:return
        if self.position>=duration(self.project)-.001:self.position=0
        if self.loop and not self.loopStart<=self.position<self.loopEnd:self.position=self.loopStart
        self.count=self.make_count(self.position) if with_count else np.zeros((0,2),np.float32);self.count_at=0
        self.loop_count=self.make_count(self.loopStart) if self.project['settings']['countEveryLoop'] and self.loop else np.zeros((0,2),np.float32)
        self.laps=0;self.running=True;self.output_anchor=None
        anchor_position=self.position-len(self.count)/SR*self.rate
        if hardware:
            import sounddevice as sd
            def callback(out,frames,t,status):
                if self.output_anchor is None:self.output_anchor=(time.perf_counter()+t.outputBufferDacTime-t.currentTime,anchor_position)
                try:out[:]=self.block(frames)
                except Exception as e:self.error=str(e);self.running=False;out.fill(0)
            try:
                if self.stream is None:self.stream=sd.OutputStream(samplerate=SR,channels=2,dtype='float32',callback=callback,latency='high')
                self.stream.start()
            except Exception:self.running=False;raise
    def pause(self):
        self.running=False
        if self.stream:self.stream.stop()
    def remaining(self):return max(0,math.ceil((len(self.count)-self.count_at)/SR/(period(self.project,self.position)/self.rate))) if self.running else 0
    def block(self,frames,include_guides=True):
        with self.lock:
            out=np.zeros((frames,2),np.float32);written=0
            while written<frames and self.running:
                if self.count_at<len(self.count):
                    n=min(frames-written,len(self.count)-self.count_at);out[written:written+n]=self.count[self.count_at:self.count_at+n];self.count_at+=n;written+=n;continue
                end=self.loopEnd if self.loop else duration(self.project)
                n=min(frames-written,max(0,round((end-self.position)/self.rate*SR)))
                if n:
                    out[written:written+n]=self.mix(self.position,n,include_guides);self.position+=n/SR*self.rate;written+=n
                if n==0 or self.position>=end-.5/SR*self.rate:
                    if not self.loop:self.position=end;self.running=False;break
                    self.position=self.loopStart;self.count=self.loop_count;self.count_at=0;self.laps+=1;s=self.project['settings']
                    if s['loopStep']>0 and self.rate<s['loopMaxRate'] and self.laps%s['loopEvery']==0:
                        self.pending_rate=min(s['loopMaxRate'],self.rate+s['loopStep']);self.running=False;break
            return out*.85
    def render(self,target,start,end,include_count=True):
        other=Audio(self.engine);other.rate=self.rate;other.pitch=self.pitch;other.load(self.project,self.root);other.mode=self.mode;other.position=start
        other.project=copy.deepcopy(other.project)
        # An artificial endpoint lets the exact same block scheduler render a selected passage.
        other.loop=True;other.loopStart=start;other.loopEnd=end;other.project['settings']['loopStep']=0
        other.count=other.make_count(start,other.project['settings']['exportGuides']) if include_count else np.zeros((0,2),np.float32);other.count_at=0;other.running=True
        total=round((end-start)/self.rate*SR)+len(other.count);left=total
        with sf.SoundFile(target,'w',samplerate=SR,channels=2,subtype='FLOAT') as f:
            while left:
                n=min(left,4096);f.write(other.block(n,other.project['settings']['exportGuides']));left-=n
        other.close()
