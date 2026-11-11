"""Selected-input capture, persistent plans and explicit transport commands."""
import copy
import json
import os
from pathlib import Path
import queue
import shutil
import threading
import time
import numpy as np
import soundfile as sf
from services import atomic, safe_name
from windows import project as model

DEFAULTS=dict(deviceUID='',channels=[],mode='overdub',latencyMS=0.,punchStart=0.,punchEnd=0.,preRoll=2.)

def settings(value):
    s=copy.deepcopy({**DEFAULTS,**value})
    if s['mode'] not in ('live','overdub','punch') or not isinstance(s['deviceUID'],str) or len(s['deviceUID'])>512:raise ValueError('Configuration de prise invalide.')
    for key,low,high in [('latencyMS',-2000,2000),('punchStart',0,43200),('punchEnd',0,43200),('preRoll',0,30)]:s[key]=model.number(s[key],low,high)
    channels=s['channels']
    if not isinstance(channels,list) or len(channels)>32:raise ValueError('Au maximum 32 entrées armées.')
    used=set()
    for c in channels:
        n=model.number(c['input'],1,32)
        if n!=int(n) or n in used or not isinstance(c['name'],str) or not c['name'].strip() or len(c['name'])>120:raise ValueError('Entrée ou nom de piste invalide.')
        used.add(n);c['input']=int(n)
    return s

def devices():
    try:
        import sounddevice as sd
        result=[]
        for i,d in enumerate(sd.query_devices()):
            if d['max_input_channels']:
                host=sd.query_hostapis(d['hostapi'])['name']
                result.append(dict(uid=host+'::'+d['name'],name=d['name']+' · '+host,channels=int(d['max_input_channels']),rate=d['default_samplerate'],index=i))
        return result
    except Exception:return []

def state(host):
    rec=host._record
    return dict(settings=settings(host._project.get('capture',{})),devices=[{k:v for k,v in d.items() if k!='index'} for d in devices()],elapsed=rec.elapsed if rec else 0,meters=rec.meters if rec else [],pending=False)

class Capture:
    def __init__(self,host):
        import sounddevice as sd
        self.config=settings(host._project.get('capture',{}));s=self.config
        selected=s['channels']
        if not selected:raise ValueError('Arme au moins une entrée dans Prises.')
        device=next((d for d in devices() if d['uid']==s['deviceUID']),None)
        if not device or max(c['input'] for c in selected)>device['channels']:raise ValueError('L’interface choisie est absente ou ne propose pas toutes les entrées armées.')
        if shutil.disk_usage(host._root).free<100_000_000:raise ValueError('Moins de 100 Mo disponibles pour enregistrer.')
        self.rate=int(device['rate']);self.frames=0;self.meters=[];self.errors=[];self.first_time=None
        self.path=host._root/'Audio'/('capture-'+model.ident()+'.wav');self.q=queue.Queue(maxsize=64)
        self.source_channels=[c['input']-1 for c in selected]
        self.file=sf.SoundFile(self.path,'w',samplerate=self.rate,channels=len(selected),subtype='PCM_24')
        def writer():
            try:
                with self.file:
                    while True:
                        data=self.q.get()
                        if data is None:break
                        if not self.errors:
                            try:self.file.write(data)
                            except Exception as e:self.errors.append('Écriture interrompue : '+str(e))
            except Exception as e:self.errors.append(str(e))
        def callback(data,frames,t,status):
            if status:self.errors.append('Interruption de capture : '+str(status));return
            if self.errors:return
            if self.first_time is None:self.first_time=time.perf_counter()+t.inputBufferAdcTime-t.currentTime
            block=data[:,self.source_channels].copy();self.meters=np.abs(block).max(axis=0).tolist()
            try:self.q.put_nowait(block);self.frames+=frames
            except queue.Full:self.errors.append('Le disque ne suit pas. Capture arrêtée, fichiers conservés.')
        self.thread=threading.Thread(target=writer,daemon=True);self.thread.start()
        try:
            self.stream=sd.InputStream(device=device['index'],samplerate=self.rate,channels=max(self.source_channels)+1,dtype='float32',callback=callback)
            self.stream.start()
        except Exception:
            self.q.put(None);self.thread.join();raise
    @property
    def elapsed(self):return self.frames/self.rate
    def stop(self):
        self.stream.stop();self.stream.close();self.q.put(None);self.thread.join()

def start(host):
    a=host._audio;p=host._project;s=settings(p.get('capture',{}))
    if host._record:return
    if a.rate!=1 or a.pitch!=0 or a.loop:raise ValueError('Enregistre à 100 %, sans transposition et sans boucle.')
    if len(p['tracks'])+len(s['channels'])>128:raise ValueError('Le projet dépasserait 128 pistes.')
    if s['mode']!='live' and model.duration(p)<=0:raise ValueError('Ouvre un morceau pour enregistrer par-dessus.')
    if s['mode']=='punch' and not 0<=s['punchStart']<s['punchEnd']<=model.duration(p):raise ValueError('Plage de punch invalide.')
    if s['mode']=='live':a.pause();a.position=0
    elif s['mode']=='punch':a.pause();a.position=max(0,s['punchStart']-s['preRoll'])
    rec=Capture(host)
    try:
        if s['mode']!='live' and not a.running:a.play(with_count=s['mode']!='punch')
    except Exception:rec.stop();raise
    host._record=rec;host._notice='Capture WAV 24 bits en cours. Retour d’écoute sur la console.'

def stop(host):
    rec=host._record
    if not rec:return
    rec.stop();host._record=None;a=host._audio;a.pause();s=rec.config
    anchor=getattr(a,'output_anchor',None)
    offset=0 if s['mode']=='live' else (anchor[1]+(rec.first_time-anchor[0]) if anchor and rec.first_time is not None else a.position-rec.elapsed)-s['latencyMS']/1000
    additions=[];info=sf.info(rec.path)
    first=0;last=info.frames
    if s['mode']=='punch':first=max(0,round((s['punchStart']-offset)*rec.rate));last=min(last,round((s['punchEnd']-offset)*rec.rate))
    if last>first:
        for i,c in enumerate(s['channels']):
            target=host._root/'Audio'/('prise-'+model.ident()+'.wav')
            with sf.SoundFile(rec.path) as src,sf.SoundFile(target,'w',samplerate=rec.rate,channels=1,subtype='PCM_24') as dst:
                src.seek(first);remaining=last-first
                while remaining:
                    data=src.read(min(65536,remaining),always_2d=True,dtype='float32')
                    if not len(data):break
                    dst.write(data[:,i]);remaining-=len(data)
            track=model.track(target,host._root,c['name']+' · prise','take',offset+first/rec.rate);track['gain']=1;additions.append(track)
    host._remember();host._project['tracks']+=additions;host._project['sessionDuration']=max(model.duration(host._project),host._project.get('sessionDuration',0))
    host._save();host._reload();a.mode='mix';host._notice=rec.errors[0] if rec.errors else f'{len(additions)} pistes enregistrées. Capture complète conservée dans Audio.'

def command(host,args):
    action=args.get('action');p=host._project;a=host._audio
    if action=='stop':host._transport_generation+=1;stop(host);a.pause();return
    if action=='record' and host._record:return
    if action=='marker':
        if host._busy:raise ValueError('Termine le traitement en cours.')
        if host._root is None:raise ValueError('Ouvre un projet.')
        at=host._record.elapsed if host._record and settings(p.get('capture',{}))['mode']=='live' else a.position
        if host._record:p['sessionDuration']=max(p.get('sessionDuration',0),at)
        host._remember();p['cues'].append(dict(id=model.ident(),time=at,name=str(args.get('name','Repère '+str(len(p['cues'])+1)))[:120]));p['cues'].sort(key=lambda c:c['time']);host._save();return
    if host._record or host._busy:raise ValueError('Termine la prise ou le traitement en cours.')
    if action=='new':
        name=safe_name(str(args.get('name','Répétition')));root=host._library/(name+'-'+model.ident()[:8]+'.bandstudio');(root/'Audio').mkdir(parents=True)
        p=model.fresh(name);p['capture']=settings(dict(mode='live'));p['settings']['countBars']=0;model.save(p,root);host._load(root);return
    if host._root is None:raise ValueError('Crée une session ou ouvre un morceau.')
    if action=='configure':
        config=settings(args['settings'])
        if config['mode']=='punch' and not 0<=config['punchStart']<config['punchEnd']<=model.duration(p):raise ValueError('Plage de punch invalide.')
        host._remember();p['capture']=config;host._save();return
    if action=='record':
        if settings(p.get('capture',{}))['mode']=='live':start(host)
        else:host._op('Préparation de la prise',host._prepared_transport(lambda:start(host)))
        return
    if action=='play':
        if not a.running:host._command(dict(command='play',projectID=p['id']))
        return
    if action=='pause':a.pause();return
    points=sorted(set([0,model.duration(p)]+[s['start'] for s in p['sections']]+[c['time'] for c in p['cues']]))
    value={'start':0,'end':model.duration(p),'back':max(0,a.position-model.period(p,a.position)*p['settings']['beatsPerBar']),'forward':min(model.duration(p),a.position+model.period(p,a.position)*p['settings']['beatsPerBar']),'previous':max((t for t in points if t<a.position-.05),default=0),'next':min((t for t in points if t>a.position+.05),default=model.duration(p))}.get(action)
    if action=='seek':value=model.number(args['time'],0,model.duration(p))
    if value is not None:host._command(dict(command='seek',args=dict(time=value),projectID=p['id']));return
    if action=='loop':host._command(dict(command='loop',args=args,projectID=p['id']));return
    raise ValueError('Commande de lecteur inconnue.')
