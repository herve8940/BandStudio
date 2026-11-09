"""Windows development host for BandStudio's shared, local-only interface."""
import copy
import csv
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import numpy as np
import soundfile as sf
from platform_tools import executable,python_for,creation_flags
from services import atomic,safe_name
from windows import project as model
from windows.audio import Audio,SR
from windows import recording

COMPONENTS={'generate':'creative','vocalsplit':'creative','separate':'stems','drumsep':'drumsep','structure':'structure','lyrics':'words','chords':'chords','drums':'drums','smartgrid':'rhythm'}
ENVIRONMENTS={'generate':'.venv-creative','vocalsplit':'.venv-creative','separate':'.venv-demucs','drumsep':'.venv-demucs','structure':'.venv-structure','lyrics':'.venv-words','chords':'.venv-chords','drums':'.venv-drums','smartgrid':'.venv-demucs'}

class Api:
    def __init__(self,engine,library=None):
        self._engine=Path(engine).resolve();self._library=Path(library or Path.home()/'Music/BandStudioDev');self._library.mkdir(parents=True,exist_ok=True)
        self._project=model.fresh();self._root=None;self._audio=Audio(self._engine);self._window=None;self._busy=False;self._job_name='';self._job=None;self._job_log=None;self._notice='';self._revision=0;self._history=[];self._future=[];self._last_export='';self._stop=threading.Event();self._lock=threading.RLock();self._record=None;self._components={};self._phone=None;self._bridge=None;self._transport_generation=0
        try:self._setlists=json.loads((self._library/'setlists.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):self._setlists=[]
    def _send(self,value):
        if self._window and not self._stop.is_set():
            try:self._window.evaluate_js('window.studioReceive && window.studioReceive('+json.dumps(value,ensure_ascii=True,allow_nan=False)+')')
            except Exception:pass
    def _list(self):
        return [dict(name=p.stem,path=str(p)) for p in sorted(self._library.glob('*.bandstudio')) if (p/'project.json').is_file()]
    def _ready_guides(self):
        return bool(self._root and self._project['guideKey']==model.guide_key(self._project) and all(model.relative_file(self._root,p).is_file() for p in self._project['guideFiles'].values()))
    def _state(self):
        self._send(dict(type='state',project=self._project,duration=model.duration(self._project),loaded=self._root is not None,library=self._list(),setlists=self._setlists,busy=self._busy,job=self._job_name,notice=self._notice,undo=bool(self._history),redo=bool(self._future),revision=self._revision,lastExport=self._last_export,guidesReady=self._ready_guides(),platform='windows',capture=recording.state(self),bridgeEnabled=self._bridge is not None,components={k:python_for(self._engine,v).is_file() for k,v in ENVIRONMENTS.items()}))
        self._transport()
    def _transport(self):
        a=self._audio
        self._send(dict(type='transport',position=self._record.elapsed if self._record and self._record.config['mode']=='live' else a.position,captureElapsed=self._record.elapsed if self._record else 0,meters=self._record.meters if self._record else [],playing=a.running,recording=self._record is not None,rate=a.rate,pitch=a.pitch,loop=a.loop,loopStart=a.loopStart,loopEnd=a.loopEnd,mode=a.mode,countRemaining=a.remaining() if a.project else 0))
    def _pulse(self):
        while not self._stop.wait(.1):
            with self._lock:
                if self._bridge:self._bridge.update(self)
                if self._record and (self._record.errors or self._record.elapsed>=43100 or (self._record.config['mode']=='punch' and self._audio.position>=self._record.config['punchEnd'])):
                    try:self._stop_record();self._state()
                    except Exception as e:self._notice=str(e)
            self._transport()
            if self._phone:self._phone.update(self)
            if self._audio.error:self._notice=self._audio.error;self._audio.error='';self._state()
            if self._audio.pending_rate and not self._busy:
                rate=self._audio.pending_rate;self._audio.pending_rate=None
                self._op('Préparation du prochain palier',lambda:self._set_rate(rate,self._audio.pitch,True))
            if self._job_log and self._busy:
                try:
                    with self._job_log.open('rb') as f:f.seek(0,2);f.seek(max(0,f.tell()-1500));detail=f.read().decode(errors='replace').strip().splitlines()
                    self._send(dict(type='job',detail=detail[-1] if detail else 'Préparation locale en cours…'))
                except OSError:pass
            for name,proc in list(self._components.items()):
                if proc.poll() is not None:
                    del self._components[name];self._notice='Installation terminée.' if proc.returncode==0 else 'L’installation a été interrompue ou a échoué. Consulte la fenêtre d’installation.';self._state()
    def _loaded(self):
        self._state()
        projects=self._list()
        example=self._engine.parent/'examples/Decouverte.bandstudio'
        if not projects and example.is_dir():
            target=self._library/'Decouverte.bandstudio'
            if not target.exists():shutil.copytree(example,target)
            projects=self._list()
        if projects and self._root is None:self._op('Ouverture du morceau',lambda:self._load(Path(projects[0]['path'])))
    def _op(self,title,work):
        with self._lock:
            if self._busy:raise ValueError('Un traitement est déjà en cours. Patiente ou annule-le.')
            self._busy=True;self._job_name=title;self._notice=''
        self._state()
        def run():
            before=copy.deepcopy(self._project);root=self._root
            try:work()
            except Exception as error:
                traceback.print_exc();self._notice=str(error)
                if self._root==root and self._project['id']==before['id']:
                    self._project=before
                    if root:
                        try:self._reload();model.save(before,root)
                        except Exception:pass
            finally:self._busy=False;self._job=None;self._job_name='';self._job_log=None;self._state()
        threading.Thread(target=run,daemon=True).start()
    def _prepared_transport(self,action):
        generation=self._transport_generation
        def ready():
            self._guides()
            with self._lock:
                if self._transport_generation==generation:action()
        return ready
    def _work(self,kind,input=None,arguments=()):
        if kind in ENVIRONMENTS and not python_for(self._engine,ENVIRONMENTS[kind]).is_file():raise ValueError('Installe le composant '+COMPONENTS[kind]+' dans Réglages → Analyses locales, puis relance ce traitement.')
        folder=(self._root or self._library/'.Imports')/'Analyses'/model.ident();folder.mkdir(parents=True)
        snapshot=folder/'project.json';atomic(snapshot,{**self._project,'_root':str(self._root or folder),'_mode':self._audio.mode})
        result=folder/'result.json';python=python_for(self._engine,ENVIRONMENTS.get(kind,'.venv'))
        arguments=list(arguments)
        if '--options' in arguments:
            index=arguments.index('--options');options=folder/'options.json';options.write_text(arguments[index+1],encoding='utf-8');arguments[index:index+2]=['--options-file',str(options)]
        args=[str(python),str(self._engine/'worker.py'),kind,'--engine',str(self._engine),'--project',str(snapshot),'--output',str(result),*map(str,arguments)]
        if input:args+=['--input',str(input)]
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',PATH=str(self._engine/'import-tools')+os.pathsep+env.get('PATH',''))
        self._job_log=folder/'traitement.log'
        with self._job_log.open('wb') as log:
            proc=subprocess.Popen(args,stdout=log,stderr=log,cwd=folder,env=env,creationflags=creation_flags());self._job=proc;status=proc.wait()
        self._job=None
        if status:
            lines=self._job_log.read_text(errors='replace').strip().splitlines();raise RuntimeError((lines[-1] if lines else 'Traitement annulé ou interrompu.')[-1500:])
        return result,json.loads(result.read_text(encoding='utf-8'))
    def _remember(self):self._history.append(copy.deepcopy(self._project));self._history=self._history[-80:];self._future=[]
    def _save(self):
        if self._root:model.save(self._project,self._root)
        self._revision+=1
    def _reload(self):
        pos,mode=self._audio.position,self._audio.mode;self._audio.load(self._project,self._root);self._audio.position=min(pos,model.duration(self._project));self._audio.mode=mode
    def _load(self,root):
        p=model.load(root);self._audio.loop=False;self._audio.load(p,root);self._project=p;self._root=root;self._history=[];self._future=[];self._last_export='';self._revision+=1;self._state()
        if model.duration(p)>0:self._guides()
    def _guides(self,force=False):
        if not force and self._ready_guides():return
        result,obj=self._work('guides');folder=self._root/'Guides'/model.ident();folder.mkdir(parents=True)
        mapping={}
        for key,value in obj['files'].items():
            file=Path(value).resolve()
            if not file.is_relative_to(result.parent.resolve()):raise ValueError('Guide audio hors du dossier de traitement.')
            target=folder/(model.ident()+'.wav');shutil.copy2(file,target);mapping[key]=target.relative_to(self._root).as_posix()
        self._project['tracks']=[t for t in self._project['tracks'] if not t['role'].startswith('guide_')]
        for key,name,role in [('click','Métronome','guide_click'),('calls','Appels de régions','guide_voice'),('counts','Décompte des régions','guide_count')]:self._project['tracks'].append(model.track(self._root/mapping[key],self._root,name,role))
        self._project['guideFiles']=mapping;self._project['guideKey']=model.guide_key(self._project);self._reload();self._save();self._notice='Appels, décomptes et métronome prêts.'
    def _decode(self,source,target):
        args=[str(executable(self._engine,'ffmpeg')),'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe,crypto,data','-i',str(source),'-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','pcm_f32le',str(target)]
        r=subprocess.run(args,capture_output=True,creationflags=creation_flags(),timeout=1800)
        if r.returncode:raise ValueError('Fichier audio illisible : '+r.stderr.decode(errors='replace')[-700:])
    def _import(self,files,new=True,title=None,url=''):
        if new:
            p=model.fresh(title or Path(files[0]).stem)
            try:p['settings'].update(json.loads((self._library/'defaults.json').read_text()))
            except (OSError,ValueError):pass
            p['sourceURL']=url;root=self._library/(safe_name(p['name'])+'.bandstudio')
            if root.exists():root=self._library/(safe_name(p['name'])+' '+p['id'][:6]+'.bandstudio')
        else:p=copy.deepcopy(self._project);root=self._root
        if root is None:raise ValueError('Importe d’abord un morceau.')
        (root/'Audio').mkdir(parents=True,exist_ok=True)
        for source in files:
            target=root/'Audio'/(model.ident()+'.wav');self._decode(source,target);name=Path(source).stem;role='source' if new else 'other'
            if not new:
                for candidate,words in [('drums',['drum','batterie']),('bass',['bass','basse']),('vocals',['vocal','chant']),('guitar',['guitar','guitare']),('piano',['piano','clavier'])]:
                    if any(w in name.lower() for w in words):role=candidate;break
            p['tracks'].append(model.track(target,root,'Original' if new else name,role))
        model.save(p,root);self._load(root);self._notice='Morceau importé. Tu peux lancer la lecture ou préparer les analyses.'
    def _import_rpp(self,path):
        result,obj=self._work('rpp',path);source=Path(obj['project']).resolve()
        if not source.is_relative_to(result.parent.resolve()):raise ValueError('Dossier d’import invalide.')
        p=model.load(source);target=self._library/(safe_name(p['name'])+' '+p['id'][:6]+'.bandstudio');shutil.move(str(source),target);self._load(target);self._notice='Projet REAPER importé. '+' '.join(obj.get('warnings',[]))
    def _analysis(self,kind,args):
        if kind=='grid' and self._project.get('gridLocked'):raise ValueError('Le calage est protégé. Déverrouille-le dans Guidage avant une nouvelle analyse.')
        desired={'lyrics':'vocals','drums':'drums','drumsep':'drums'}.get(kind,'source');source=next((t for t in self._project['tracks'] if t['role']==desired),None)
        if not source and kind not in ('drums','drumsep'):source=next((t for t in self._project['tracks'] if t['role']=='source'),None)
        if not source:raise ValueError('Il manque la piste '+desired+'. Importe un morceau ou sépare ses instruments.')
        offset=source['offset']
        result,obj=self._work(kind,model.relative_file(self._root,source['file']),['--model',args.get('model','htdemucs'),'--quality',args.get('quality','standard'),'--language',args.get('language','auto')]);self._remember()
        if kind=='grid':self._project['bpm']=obj.get('bpm',0);self._project['beats']=obj.get('beats',[])
        elif kind=='structure':model.apply_sections(self._project,obj['sections'])
        elif kind in ('separate','drumsep'):
            tracks=[];names={'drums':'Batterie','bass':'Basse','vocals':'Chant','guitar':'Guitare','piano':'Piano','other':'Autres instruments','drum_kick':'Grosse caisse','drum_snare':'Caisse claire','drum_toms':'Toms','drum_cymbals':'Cymbales et charleston'}
            for t in obj['tracks']:
                source=Path(t['path']).resolve()
                if not source.is_relative_to(result.parent.resolve()):raise ValueError('Piste hors du dossier de traitement.')
                target=self._root/'Audio'/(model.ident()+'.wav');shutil.copy2(source,target);tracks.append(model.track(target,self._root,names.get(t['role'],t['role']),t['role'],offset if kind=='drumsep' else 0))
            keep=[t for t in self._project['tracks'] if not t['role'].startswith('drum_')] if kind=='drumsep' else [t for t in self._project['tracks'] if t['role'] in ('source','take') or t['role'].startswith('guide_')]
            self._project['tracks']=keep+tracks;self._reload();self._audio.mode='mix'
        elif kind=='drums':
            pitches={'BD':36,'SD':38,'TT':45,'HH':42,'CY':49};self._project['drumHits']=sorted([dict(time=t,pitch=pitches[k],velocity=max(1,min(127,round(prob*127)))) for k,rows in obj['onsets'].items() for t,prob in rows if t<=model.duration(self._project)],key=lambda x:x['time'])
        elif kind in ('lyrics','chords'):
            entries=[];manual=[x for x in self._project[kind] if x.get('manual')]
            for row in obj['segments']:
                start=row.get('start',row.get('t',0));end=min(model.duration(self._project),row['end'])
                if end<=start or any(x['start']<end and x['end']>start for x in manual):continue
                entry=dict(id=model.ident(),start=start,end=end,text=row.get('text',row.get('label','')),manual=False)
                if kind=='lyrics':entry['words']=[dict(start=w['t'],end=w['end'],text=w['w']) for w in row.get('words',[]) if start<=w['t']<w['end']<=end+.1]
                entries.append(entry)
            self._project[kind]=sorted(manual+entries,key=lambda x:x['start'])
        self._save();self._notice='Analyse ajoutée. Vérifie et corrige les propositions dans l’atelier ou le prompteur.'
    def _set_rate(self,rate,pitch,resume=False):
        self._audio.pause();self._audio.rate=model.number(rate,.5,1.5);self._audio.pitch=model.number(pitch,-12,12);self._audio.prepare()
        if resume:self._audio.play()
    def _dialog(self,kind,**options):
        import webview
        return self._window.create_file_dialog(getattr(webview.FileDialog,kind),**options)
    def _reveal(self,path):
        if os.name=='nt':subprocess.Popen(['explorer.exe','/select,',str(Path(path))],creationflags=creation_flags())
    def _install(self,component):
        if component not in ('stems','structure','words','chords','drums','rhythm','drumsep','creative'):raise ValueError('Composant inconnu.')
        if component in self._components:raise ValueError('Cette installation est déjà ouverte.')
        env=os.environ.copy();env.update(PYTHONUTF8='1',REAPER_RESOURCE_PATH=str(self._engine/'worker-state'),UV_PYTHON_INSTALL_DIR=str(self._engine/'managed-python'),UV_CACHE_DIR=str(self._engine/'.uv_cache'),REACUE_WORDS_ENGINE='off',TORCH_HOME=str(self._engine/'torch-cache'))
        env['PATH']=str(self._engine/'tools')+os.pathsep+str(self._engine/'import-tools')+os.pathsep+env.get('PATH','')
        script=['-File',str(self._engine/'windows/install_extra.ps1'),'-Component',component] if component in ('rhythm','drumsep','creative') else ['-File',str(self._engine/'install'/('install_'+component+'_windows.ps1')),'-Lang','fr']
        proc=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-NoExit',*script],cwd=self._engine,env=env,creationflags=subprocess.CREATE_NEW_CONSOLE)
        self._components[component]=proc;self._notice='Une fenêtre d’installation est ouverte. Suis ses indications puis ferme-la quand elle a terminé.'
    def command(self,message):
        """The only method exposed to the local WebView; never accepts executable code."""
        with self._lock:
            before=copy.deepcopy(self._project);history=self._history.copy();future=self._future.copy()
            try:self._command(message)
            except Exception as error:
                self._history=history;self._future=future
                if self._project['id']==before['id'] and self._project!=before:
                    self._project=before
                    try:self._reload();self._save()
                    except Exception:pass
                self._notice=str(error);traceback.print_exc()
            self._state()
        return {'ok':True}
    def _command(self,m):
        if not isinstance(m,dict):raise ValueError('Commande invalide.')
        cmd=m.get('command');args=m.get('args') or {};a=self._audio;p=self._project
        if cmd=='ready':return
        if cmd=='cancel':
            self._transport_generation+=1
            if self._job:
                if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(self._job.pid),'/T','/F'],capture_output=True,creationflags=creation_flags())
                else:self._job.terminate()
            return
        if self._busy and cmd not in ('stop','play','studioControl'):raise ValueError('Un traitement est en cours. Patiente ou annule-le.')
        if self._record and cmd not in ('record','stop','studioControl'):raise ValueError('Arrête la prise avant cette action.')
        if cmd=='installComponent':self._install(args.get('component'));return
        if cmd=='audioSettings':os.startfile('ms-settings:sound');return
        if cmd=='bandpilot':raise ValueError('La connexion directe avec BandPilot n’est pas disponible dans cette préversion Windows.')
        if cmd in ('import','addTracks'):
            paths=self._dialog('OPEN',allow_multiple=cmd=='addTracks',file_types=('Audio et vidéos (*.*)',))
            if paths:a.pause();self._op('Import du morceau',lambda:self._import(paths,cmd=='import'))
            return
        if cmd in ('open','openRPP'):
            paths=self._dialog('FOLDER' if cmd=='open' else 'OPEN',file_types=('Projet REAPER (*.rpp)',) if cmd=='openRPP' else ())
            if paths:a.pause();self._op('Ouverture du projet',lambda:self._load(Path(paths[0])) if cmd=='open' else self._import_rpp(Path(paths[0])))
            return
        if cmd=='library':
            path=args['path']
            if path not in [x['path'] for x in self._list()]:raise ValueError('Morceau hors de la bibliothèque.')
            a.pause();self._op('Ouverture du morceau',lambda:self._load(Path(path)));return
        if cmd=='link':
            from services import checked_url
            url=checked_url(args.get('url',''))
            def linked():
                _,result=self._work('link',arguments=['--url',url]);self._import([result['audio']],True,result['title'],url)
            a.pause();self._op('Import du lien',linked);return
        if m.get('projectID')!=p['id']:raise ValueError('Le projet a changé. Recommence ton action.')
        if cmd=='newSession':recording.command(self,dict(action='new',name=args.get('name','Répétition')));return
        if cmd=='captureSettings':recording.command(self,dict(action='configure',settings=args));return
        if cmd=='studioControl':recording.command(self,args);return
        if cmd=='bridge':
            from windows.studio_bridge import Bridge
            if args.get('on') and not self._bridge:self._bridge=Bridge();self._bridge.update(self)
            elif not args.get('on') and self._bridge:self._bridge.close();self._bridge=None
            return
        if cmd=='setlist':
            name=args.get('name','').strip();paths=args.get('paths',[])
            if not name or any(x not in [s['path'] for s in self._list()] for x in paths):raise ValueError('Nom ou morceaux de setlist invalides.')
            ident=args.get('id') or model.ident();item=dict(id=ident,name=name[:120],paths=paths)
            self._setlists=[x for x in self._setlists if x['id']!=ident]+[item];atomic(self._library/'setlists.json',self._setlists);return
        if self._root is None:raise ValueError('Importe ou ouvre d’abord un morceau.')
        if cmd=='play':
            if a.running:a.pause()
            elif self._ready_guides():a.play()
            else:self._op('Préparation des appels et du décompte',self._prepared_transport(a.play))
            return
        if cmd=='stop':
            self._transport_generation+=1
            if self._record:self._stop_record()
            a.pause();a.position=a.loopStart if a.loop else 0;return
        if cmd=='seek':
            running=a.running;a.pause();a.position=model.number(args['time'],0,model.duration(p))
            if running:a.play(p['settings']['countOnSeek'])
            return
        if cmd in ('rate','pitch'):
            rate=model.number(args['value'],.5,1.5) if cmd=='rate' else a.rate;pitch=model.number(args['value'],-12,12) if cmd=='pitch' else a.pitch;running=a.running;a.pause()
            self._op('Préparation de la vitesse et de la tonalité',lambda:self._set_rate(rate,pitch,running));return
        if cmd=='mode':
            mode=args['value']
            if mode not in ('original','mix','minus','drums'):raise ValueError('Mode inconnu.')
            if mode in ('minus','drums') and not any(t['role']=='drums' or t['role'].startswith('drum_') for t in p['tracks']):raise ValueError('Sépare la batterie avant d’utiliser ce mode.')
            a.mode=mode;return
        if cmd=='loop':
            start=model.number(args['start'],0,model.duration(p));end=model.number(args['end'],0,model.duration(p));on=bool(args['on'])
            if on and end-start<.05:raise ValueError('Choisis une boucle d’au moins 50 ms.')
            running=a.running;a.pause();a.loop=on;a.loopStart=start;a.loopEnd=end
            if running:a.play()
            return
        if cmd in ('reveal','showExport'):
            self._reveal(self._last_export if cmd=='showExport' and self._last_export else self._root);return
        if cmd=='save':self._save();self._notice='Projet enregistré.';return
        if cmd=='saveDefaults':atomic(self._library/'defaults.json',p['settings']);self._notice='Réglages enregistrés pour les prochains imports.';return
        if cmd=='guides':a.pause();self._op('Préparation des guides',lambda:self._guides(force=True));return
        if cmd=='settings':
            value={**model.GUIDE_DEFAULTS,**args['value']};candidate={**p,'settings':value};model.validate(candidate,self._root)
            a.pause();self._remember()
            if any(value[k]!=p['settings'][k] for k in ('firstBeat','gridMode','beatsPerBar','manualBPM')):p['gridLocked']=True
            p['settings']=value;self._save();self._op('Préparation des guides',self._guides);return
        if cmd=='phone':
            from windows.phone_host import PhoneSession
            if args.get('on'):
                if self._root is None:raise ValueError('Ouvre d’abord un morceau.')
                if not self._phone:self._phone=PhoneSession(self._engine)
                self._phone.announced=False;self._phone.update(self)
            else:
                if self._phone:self._phone.close()
                self._phone=None;self._send(dict(type='phone',active=False))
            return
        if cmd=='creative':
            from windows.creative_host import creative_task
            if args.get('kind') not in ('generate','vocalsplit'):raise ValueError('Traitement créatif inconnu.')
            self._op('Création musicale locale',lambda:creative_task(self,args['kind'],args.get('options',{})));return
        if cmd=='musicSettings':
            self._remember()
            if 'capo' in args:
                value=model.number(args['capo'],0,12)
                if int(value)!=value:raise ValueError('Position de capo entière attendue.')
                p['capo']=int(value)
            if 'key' in args:
                import re
                if args['key'] and not re.fullmatch(r'[A-G](#|b)?m?',args['key']):raise ValueError('Tonalité invalide.')
                p['key']=args['key']
            if 'gridLocked' in args:p['gridLocked']=bool(args['gridLocked'])
            self._save();return
        if cmd=='studioTask':
            from windows.advanced_host import advanced_task
            kind=args.get('kind');options=args.get('options') or {}
            if kind not in ('smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet','reaperextension'):raise ValueError('Outil inconnu.')
            if kind=='smartgrid' and p.get('gridLocked'):raise ValueError('Le calage est protégé. Déverrouille-le dans Guidage avant une nouvelle analyse.')
            a.pause();self._op('Outil local : '+kind,lambda:advanced_task(self,kind,options));return
        if cmd=='analyze':
            kind=args.get('kind')
            if kind not in ('grid','structure','separate','drumsep','lyrics','chords','drums'):raise ValueError('Analyse inconnue.')
            self._op('Analyse locale : '+kind,lambda:self._analysis(kind,args));return
        if cmd in ('reaper','midi'):
            def exported():
                if cmd=='reaper':self._guides()
                _,obj=self._work(cmd);self._last_export=obj['path'];self._notice='Export terminé. Afficher l’export permet de le retrouver.'
            self._op('Création de l’export',exported);return
        if cmd=='export':
            paths=self._dialog('SAVE',save_filename=safe_name(p['name'])+' - mix.wav',file_types=('Audio WAV (*.wav)',))
            if paths:
                target=Path(paths[0] if isinstance(paths,(list,tuple)) else paths)
                def export_audio():
                    self._guides();temporary=target.with_name('.'+target.stem+'-'+model.ident()+'.wav')
                    try:
                        a.render(temporary,a.loopStart if a.loop else 0,a.loopEnd if a.loop else model.duration(p),p['settings']['exportCount']);os.replace(temporary,target)
                    finally:temporary.unlink(missing_ok=True)
                    self._last_export=str(target);self._notice='Mix WAV exporté.'
                a.pause();self._op('Export du mix',export_audio)
            return
        if cmd=='exportCues':
            paths=self._dialog('SAVE',save_filename=safe_name(p['name'])+' - repères.csv',file_types=('CSV (*.csv)',))
            if paths:
                target=Path(paths[0] if isinstance(paths,(list,tuple)) else paths)
                with target.open('w',encoding='utf-8-sig',newline='') as f:
                    writer=csv.writer(f);writer.writerow(['type','début','fin','nom']);writer.writerows([['section',s['start'],s['end'],s['name']] for s in p['sections']]+[['cue',c['time'],c['time'],c['name']] for c in p['cues']])
                self._last_export=str(target)
            return
        if cmd=='record':
            if self._record:self._stop_record()
            else:recording.command(self,dict(action='record'))
            return
        if cmd in ('undo','redo'):
            source,dest=(self._history,self._future) if cmd=='undo' else (self._future,self._history)
            if source:dest.append(copy.deepcopy(p));self._project=source.pop();self._reload();self._save()
            return
        self._remember()
        if cmd=='track':
            track=next(t for t in p['tracks'] if t['id']==args['id'])
            if track['role'].startswith('guide_'):raise ValueError('Utilise Guidage pour régler cette piste.')
            for k,low,high in [('gain',0,2),('pan',-1,1),('offset',-120,43200)]:
                if k in args:track[k]=model.number(args[k],low,high)
            for k in ('muted','solo'):
                if k in args:track[k]=bool(args[k])
            if args.get('name'):track['name']=str(args['name'])[:120]
            if args.get('role') in ('drums','drum_kick','drum_snare','drum_toms','drum_cymbals','bass','vocals','guitar','piano','other','take') and track['role']!='source':track['role']=args['role']
            model.validate(p,self._root)
            with a.lock:a.project=copy.deepcopy(p)
        elif cmd in ('section','cue'):
            name=str(args.get('name','')).strip()
            if not name:raise ValueError('Donne un nom au passage.')
            item=dict(id=args.get('id') or model.ident(),name=name[:160],callText=str(args.get('callText',''))[:240],announce=args.get('announce',True))
            if cmd=='section':
                start=model.number(args['start'],0,model.duration(p));end=model.number(args['end'],start+.000001,model.duration(p))
                if any(s['id']!=item['id'] and s['start']<end and s['end']>start for s in p['sections']):raise ValueError('Les sections se chevauchent.')
                item.update(start=start,end=end,locked=bool(args.get('locked',True)),origin='manual');key='sections';sort='start'
            else:item['time']=model.number(args['time'],0,model.duration(p));key='cues';sort='time'
            p[key]=sorted([s for s in p[key] if s['id']!=item['id']]+[item],key=lambda s:s[sort])
        elif cmd in ('deleteSection','deleteCue'):
            key='sections' if cmd=='deleteSection' else 'cues';p[key]=[s for s in p[key] if s['id']!=args['id']]
        elif cmd in ('splitSection','mergeSection'):
            index=next((i for i,x in enumerate(p['sections']) if x['id']==args.get('id')),None)
            if index is None:raise ValueError('Sélectionne une section.')
            section=p['sections'][index];section.update(locked=True,origin='manual')
            if cmd=='splitSection':
                at=model.number(args['time'],section['start']+.01,section['end']-.01);new={**section,'id':model.ident(),'start':at,'name':section['name']+' · suite'};section['end']=at;p['sections'].insert(index+1,new)
            else:
                if index+1>=len(p['sections']):raise ValueError('Aucune section suivante.')
                section['end']=p['sections'][index+1]['end'];p['sections'].pop(index+1)
        elif cmd=='notes':p['notes']=str(args.get('value',''))[:20000]
        elif cmd=='annotation':
            kind=args.get('kind')
            if kind not in ('lyrics','chords'):raise ValueError('Annotation inconnue.')
            ident=args.get('id') or model.ident();entries=[x for x in p[kind] if x['id']!=ident]
            if not args.get('delete'):
                start=model.number(args['start'],0,model.duration(p));end=model.number(args['end'],start+.000001,model.duration(p));text=str(args['text']).strip()
                if not text:raise ValueError('Saisis un texte.')
                words=[];previous=start
                if kind=='lyrics':
                    if len(args.get('words',[]))>300:raise ValueError('Trop de mots pour cette ligne.')
                    for w in args.get('words',[]):
                        a=model.number(w['start'],start,end);b=model.number(w['end'],start,end);word=str(w['text']).strip()
                        if a<previous or b<=a or not word or len(word)>120:raise ValueError('Horaires des mots invalides ou chevauchants.')
                        words.append(dict(start=a,end=b,text=word));previous=b
                entries.append(dict(id=ident,start=start,end=end,text=text[:1000],manual=True,words=words))
            p[kind]=sorted(entries,key=lambda x:x['start'])
        elif cmd=='drumHit':
            at=model.number(args['time'],0,model.duration(p));pitch=int(model.number(args['pitch'],0,127));tolerance=model.number(args['tolerance'],.001,1)
            p['drumHits']=[h for h in p['drumHits'] if not (h['pitch']==pitch and abs(h['time']-at)<tolerance)]
            if args.get('on'):p['drumHits'].append(dict(time=at,pitch=pitch,velocity=int(model.number(args['velocity'],1,127))))
            p['drumHits'].sort(key=lambda x:x['time'])
        elif cmd=='deleteTrack':
            tracks=[t for t in p['tracks'] if t['id']!=args['id']]
            if not any(not t['role'].startswith('guide_') for t in tracks):raise ValueError('Conserve au moins une piste audio.')
            p['tracks']=tracks;model.validate(p,self._root);self._reload()
        else:raise ValueError('Commande inconnue : '+str(cmd))
        self._save()
    def _start_record(self):recording.start(self)
    def _stop_record(self):recording.stop(self)
    def _closing(self):
        if self._record or self._busy:
            if not self._window.create_confirmation_dialog('BandStudio','Un traitement ou un enregistrement est en cours. L’arrêter et quitter ?'):return False
        if self._record:self._stop_record()
        if self._bridge:self._bridge.close();self._bridge=None
        if self._job:
            if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(self._job.pid),'/T','/F'],capture_output=True,creationflags=creation_flags())
            else:self._job.terminate()
        if self._phone:self._phone.close()
        self._stop.set();self._audio.close();return True
