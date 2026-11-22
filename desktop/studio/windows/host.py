"""Windows development host for BandStudio's shared, local-only interface."""
import copy
import csv
import json
import os
from pathlib import Path
import queue
import re
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
import diagnostics
import updater
import catalog
import artwork

COMPONENTS={'generate':'creative','vocalsplit':'creative','separate':'stems','drumsep':'drumsep','structure':'structure','lyrics':'words','lyricscorrect':'words','chords':'chords','drums':'drums','smartgrid':'rhythm'}
ENVIRONMENTS={'generate':'.venv-creative','vocalsplit':'.venv-creative','separate':'.venv-demucs','drumsep':'.venv-demucs','structure':'.venv-structure','lyrics':'.venv-words','lyricscorrect':'.venv-words','chords':'.venv','drums':'.venv-drums','smartgrid':'.venv-demucs'}

class Api:
    def __init__(self,engine,library=None):
        self._engine=Path(engine).resolve();self._library=Path(library or Path.home()/'Music/BandStudioDev');self._library.mkdir(parents=True,exist_ok=True)
        self._project=model.fresh();self._root=None;self._audio=Audio(self._engine);self._window=None;self._busy=False;self._job_name='';self._job=None;self._job_log=None;self._notice='';self._revision=0;self._history=[];self._future=[];self._last_export='';self._stop=threading.Event();self._lock=threading.RLock();self._record=None;self._components={};self._phone=None;self._bridge=None;self._transport_generation=0;self._checking_update=False
        self._cancelled=threading.Event();self._artwork_busy=False
        self._batch=None;self._batch_pulse=0.;self._batch_state=dict(type='batchQueue',items=[],enabled=False)
        try:self._setlists=json.loads((self._library/'setlists.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):self._setlists=[]
    def _send(self,value):
        if self._window and not self._stop.is_set():
            try:self._window.evaluate_js('window.studioReceive && window.studioReceive('+json.dumps(value,ensure_ascii=True,allow_nan=False)+')')
            except Exception:pass
    def _list(self):
        return catalog.entries(self._library)
    def _plan(self):
        available={k:python_for(self._engine,v).is_file() for k,v in ENVIRONMENTS.items()}
        available['smartgrid']=available['smartgrid'] and any((self._engine/'.venv-demucs').glob('**/site-packages/beat_this'))
        steps=[]
        if available['separate'] and not any(t['role'] in ('drums','bass','vocals','other','guitar','piano') for t in self._project['tracks']):steps.append('separate')
        roles={t['role'] for t in self._project['tracks']}
        if available['drumsep'] and (self._engine/'drumsep/49469ca8.th').is_file() and ('separate' in steps or 'drums' in roles):steps.append('drumsep')
        if available['vocalsplit'] and (self._engine/'creative/UVR_MDXNET_KARA_2.onnx').is_file() and ('separate' in steps or 'vocals' in roles):steps.append('vocalsplit')
        if not self._project.get('gridLocked'):steps.append('smartgrid' if available['smartgrid'] else 'grid')
        if available['structure']:steps.append('structure')
        if not self._project.get('key'):steps.append('key')
        if available['lyrics']:steps.append('lyricscorrect' if model.analysis_done(self._project,'lyrics') else 'lyrics')
        steps=[kind for kind in steps if not model.analysis_done(self._project,kind)]
        if 'source' in roles and (steps or (self._project.get('structureProposal') or {}).get('status')!='prepared'):steps.append('prepareReview')
        return steps+(['guides'] if steps or not self._ready_guides() else [])
    def _ready_guides(self):
        return bool(self._root and self._project['guideKey']==model.guide_key(self._project) and all(model.relative_file(self._root,p).is_file() for p in self._project['guideFiles'].values()))
    def _state(self):
        from chord_sources import public_catalog
        self._send(dict(type='state',project=self._project,duration=model.duration(self._project),loaded=self._root is not None,library=self._list(),trashAvailable=bool(catalog.trashed(self._library)),analysisPlan=self._plan(),setlists=self._setlists,busy=self._busy,job=self._job_name,jobTask=getattr(self,'_job_kind',''),jobID=str(self._job_log or ''),jobPlan=getattr(self,'_job_plan',[]),jobPlanIndex=getattr(self,'_job_plan_index',0),notice=self._notice,undo=bool(self._history),redo=bool(self._future),revision=self._revision,lastExport=self._last_export,guidesReady=self._ready_guides(),platform='windows',components={k:python_for(self._engine,v).is_file() for k,v in ENVIRONMENTS.items()},chordProviders=public_catalog()))
        self._transport()
    def _transport(self):
        a=self._audio
        self._send(dict(type='transport',position=self._record.elapsed if self._record and self._record.config['mode']=='live' else a.position,captureElapsed=self._record.elapsed if self._record else 0,meters=self._record.meters if self._record else [],playing=a.running,recording=self._record is not None,rate=a.rate,pitch=a.pitch,loop=a.loop,loopStart=a.loopStart,loopEnd=a.loopEnd,mode=a.mode,countRemaining=a.remaining() if a.project else 0))
    def _pulse(self):
        while not self._stop.wait(.1):
            with self._lock:
                if self._record and (self._record.errors or self._record.elapsed>=43100 or (self._record.config['mode']=='punch' and self._audio.position>=self._record.config['punchEnd'])):
                    try:self._stop_record();self._state()
                    except Exception as e:self._notice=str(e)
            self._transport()
            batch_client=self._batch
            if batch_client and time.monotonic()-self._batch_pulse>.5:
                self._batch_pulse=time.monotonic()
                try:batch_client.send(dict(action='heartbeat',ready=not self._busy and not self._audio.running and not self._record and not self._components))
                except (OSError,ValueError):
                    self._send(dict(type='batchQueue',items=self._batch_state.get('items',[]),enabled=False,status='File arrêtée',message='Clique sur Actualiser la file pour la reconnecter.'))
                    if self._batch is batch_client:self._batch=None
            if self._phone:self._phone.update(self)
            if self._audio.error:self._notice=self._audio.error;self._audio.error='';self._state()
            if self._audio.pending_rate and not self._busy:
                rate=self._audio.pending_rate;self._audio.pending_rate=None
                self._op('Préparation du prochain palier',lambda:self._set_rate(rate,self._audio.pitch,True))
            if self._job_log and self._busy:
                try:
                    with self._job_log.open('rb') as f:f.seek(0,2);f.seek(max(0,f.tell()-1500));detail=f.read().decode(errors='replace').strip().splitlines()
                    try:status=json.loads((self._job_log.parent/'progress.json').read_text(encoding='utf-8'))
                    except (OSError,ValueError):status={}
                    if not isinstance(status,dict):status={}
                    self._send({**status,'type':'job','task':getattr(self,'_job_kind',''),'jobID':str(self._job_log),'plan':getattr(self,'_job_plan',[]),'planIndex':getattr(self,'_job_plan_index',0),'detail':detail[-1] if detail else '', 'elapsed':max(0,time.monotonic()-self._job_started)})
                except OSError:pass
            for name,proc in list(self._components.items()):
                if proc.poll() is not None:
                    diagnostics.event('component.finish', component=name, exit=proc.returncode)
                    del self._components[name];self._notice='Installation terminée.' if proc.returncode==0 else 'L’installation a été interrompue ou a échoué. Consulte la fenêtre d’installation.';self._state()
    def _check_updates(self):
        if self._checking_update:return
        self._checking_update=True
        def check():
            self._send(dict(type="update",automatic=updater.enabled(),message="Vérification des mises à jour…"))
            try:result=updater.check(self._engine)
            except Exception as error:
                diagnostics.event("update.error",error=error);result={"message":"Mise à jour indisponible. La version installée reste utilisable."}
            finally:self._checking_update=False
            self._send(dict(type="update",automatic=updater.enabled(),**result))
        threading.Thread(target=check,daemon=True).start()
    def _loaded(self):
        self._state()
        try:self._batch_command(dict(action='refresh'))
        except Exception as error:self._send(dict(type='batchQueue',items=[],enabled=False,message=str(error)))
        self._send(dict(type="update",automatic=updater.enabled(),message=""))
        if updater.enabled():self._check_updates()
        projects=self._list()
        example=self._engine.parent/'examples/Decouverte.bandstudio'
        if not projects and example.is_dir():
            target=self._library/'Decouverte.bandstudio'
            if not target.exists():shutil.copytree(example,target)
            projects=self._list()
        if projects and self._root is None:self._op('Ouverture du morceau',lambda:self._load(Path(projects[0]['path'])))
    def _op(self,title,work,rollback=True):
        with self._lock:
            if self._busy:raise ValueError('Un traitement est déjà en cours. Patiente ou annule-le.')
            self._busy=True;self._job_name=title;self._notice='';self._cancelled.clear()
        self._state()
        def run():
            before=copy.deepcopy(self._project);root=self._root
            try:work()
            except Exception as error:
                diagnostics.event("job.error",operation=title,kind=type(error).__name__,error=error);traceback.print_exc();self._notice=str(error)
                if rollback and self._root==root and self._project['id']==before['id']:
                    self._project=before
                    if root:
                        try:self._reload();model.save(before,root)
                        except Exception:pass
            finally:self._busy=False;self._job=None;self._job_name='';self._job_log=None;self._job_plan=[];self._job_plan_index=0;self._state()
        threading.Thread(target=run,daemon=True).start()
    def _prepared_transport(self,action):
        generation=self._transport_generation
        def ready():
            self._guides()
            with self._lock:
                if self._transport_generation==generation:action()
        return ready
    def _work(self,kind,input=None,arguments=()):
        if self._cancelled.is_set():raise RuntimeError('Traitement annulé.')
        diagnostics.event('job.start', task=kind, environment=ENVIRONMENTS.get(kind,'.venv'))
        if kind in ENVIRONMENTS and self._components:raise ValueError('Termine l’installation des composants et ferme sa fenêtre avant de lancer une analyse.')
        if kind in ENVIRONMENTS and not python_for(self._engine,ENVIRONMENTS[kind]).is_file():raise ValueError('Installe le composant '+COMPONENTS[kind]+' dans Réglages → Analyses locales, puis relance ce traitement.')
        folder=(self._root or self._library/'.Imports')/'Analyses'/model.ident();folder.mkdir(parents=True)
        snapshot=folder/'project.json';atomic(snapshot,{**self._project,'_root':str(self._root or folder),'_library':str(self._library),'_mode':self._audio.mode,'_rate':self._audio.rate,'_pitch':self._audio.pitch})
        result=folder/'result.json';python=python_for(self._engine,ENVIRONMENTS.get(kind,'.venv'))
        arguments=list(arguments)
        if '--options' in arguments:
            index=arguments.index('--options');options=folder/'options.json';options.write_text(arguments[index+1],encoding='utf-8');arguments[index:index+2]=['--options-file',str(options)]
        args=[str(python),str(self._engine/'worker.py'),kind,'--engine',str(self._engine),'--project',str(snapshot),'--output',str(result),*map(str,arguments)]
        if input:args+=['--input',str(input)]
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',PATH=str(self._engine/'import-tools')+os.pathsep+env.get('PATH',''))
        self._job_kind=kind
        self._job_started=time.monotonic();self._job_log=folder/'traitement.log'
        self._state()
        with self._job_log.open('wb') as log:
            with self._lock:
                if self._cancelled.is_set():raise RuntimeError('Traitement annulé.')
                proc=subprocess.Popen(args,stdout=log,stderr=log,cwd=folder,env=env,creationflags=creation_flags());self._job=proc
            status=proc.wait()
        self._job=None
        self._send(dict(type='job',task=kind,jobID=str(self._job_log),finished=status==0 and not self._cancelled.is_set(),failed=status!=0 or self._cancelled.is_set(),progress=100 if status==0 and not self._cancelled.is_set() else 0))
        if self._cancelled.is_set():raise RuntimeError('Traitement annulé.')
        diagnostics.event('job.finish', task=kind, exit=status, elapsed=round(time.monotonic()-self._job_started,2))
        if status:
            lines=self._job_log.read_text(errors='replace').strip().splitlines()
            if any('numpy.core.multiarray failed to import' in line or '_ARRAY_API not found' in line for line in lines):
                component='Rythme avancé' if kind=='smartgrid' else COMPONENTS.get(kind,'concerné')
                raise RuntimeError('Incompatibilité NumPy dans le moteur d’analyse. Réinstalle '+component+' dans Réglages → Analyses locales, puis relance le traitement. Tes morceaux sont conservés.')
            raise RuntimeError((lines[-1] if lines else 'Traitement annulé ou interrompu.')[-1500:])
        return result,json.loads(result.read_text(encoding='utf-8'))
    def _remember(self):self._history.append(copy.deepcopy(self._project));self._history=self._history[-80:];self._future=[]
    def _save(self,invalidate=True):
        if invalidate:self._project.pop('structureProposal',None)
        if invalidate and self._project.get('preparation'):
            self._project['preparation'].pop('fingerprint',None);self._project['preparation'].pop('validatedAt',None)
        if self._root:model.save(self._project,self._root)
        self._revision+=1
    def _reload(self):
        pos,mode=self._audio.position,self._audio.mode;self._audio.load(self._project,self._root);self._audio.position=min(pos,model.duration(self._project));self._audio.mode=mode
    def _load(self,root,prepare_guides=True):
        p=model.load(root)
        from section_grid_rollback import rollback_section_grid
        rollback_section_grid(p,root)
        prep=p.get('preparation') or {}
        model.save(p,root) # Persist repaired legacy waveforms.
        self._audio.loop=False;self._audio.rate=prep.get('rate',1);self._audio.pitch=prep.get('pitch',0)
        self._audio.load(p,root)
        if prep:self._audio.mode=prep.get('mode','mix')
        self._project=p;self._root=root;self._history=[];self._future=[];self._last_export='';self._revision+=1;self._state()
        if prepare_guides and model.duration(p)>0:
            self._guides()
            if not model.analysis_done(p,'lyricscorrect') and python_for(self._engine,'.venv-words').is_file():
                self._analysis('lyricscorrect',{})
    def _guides(self,force=False):
        if not force and self._ready_guides():return
        result,obj=self._work('guides');folder=self._root/'Guides'/model.ident();folder.mkdir(parents=True)
        mapping={}
        for key,value in obj['files'].items():
            file=Path(value).resolve()
            if not file.is_relative_to(result.parent.resolve()):raise ValueError('Guide audio hors du dossier de traitement.')
            target=folder/(model.ident()+'.wav');shutil.copy2(file,target);mapping[key]=target.relative_to(self._root).as_posix()
        previous_guides=self._project['tracks']
        self._project['tracks']=[t for t in previous_guides if not t['role'].startswith('guide_')]
        for key,name,role in [('click','Métronome','guide_click'),('calls','Appels de régions','guide_voice'),('cues','Cues','guide_cue'),('counts','Décompte des régions','guide_count')]:self._project['tracks'].append(model.guide_track(self._root/mapping[key],self._root,name,role,previous_guides))
        self._project['guideFiles']=mapping;self._project['guideKey']=model.guide_key(self._project);self._reload();self._save(invalidate=False);self._notice='Appels, décomptes et métronome prêts.'
        if obj.get('guideWarnings'):
            self._notice=f"Guides prêts · {len(obj['guideWarnings'])} annonce(s) sans place avant l’entrée : raccourcis le texte ou le décompte."
    def _decode(self,source,target):
        args=[str(executable(self._engine,'ffmpeg')),'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe,crypto,data','-i',str(source),'-map','0:a:0','-vn','-ac','2','-ar','44100','-c:a','pcm_f32le',str(target)]
        r=subprocess.run(args,capture_output=True,creationflags=creation_flags(),timeout=1800)
        if r.returncode:raise ValueError('Fichier audio illisible : '+r.stderr.decode(errors='replace')[-700:])
    def _import(self,files,new=True,title=None,url='',artwork=None,metadata=None):
        if new:
            p=model.fresh(title or Path(files[0]).stem)
            try:p['settings'].update(json.loads((self._library/'defaults.json').read_text()))
            except (OSError,ValueError):pass
            from services import import_settings
            p['settings']=import_settings(p['settings'])
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
        if new:catalog.extract(artwork or files[0],root,self._engine)
        model.save(p,root)
        if new:
            from artwork import seed
            seed(root,files[0],self._engine,metadata)
        self._load(root,prepare_guides=not new)
        if new:
            from windows.advanced_host import advanced_task
            if 'smartgrid' in self._plan():advanced_task(self,'smartgrid',{})
            else:self._analysis('grid',{})
            self._guides();self._notice='Import terminé. '+self._project['analysisNote']
        else:self._notice='Pistes importées.'
    def _import_rpp(self,path):
        result,obj=self._work('rpp',path);source=Path(obj['project']).resolve()
        if not source.is_relative_to(result.parent.resolve()):raise ValueError('Dossier d’import invalide.')
        p=model.load(source);target=self._library/(safe_name(p['name'])+' '+p['id'][:6]+'.bandstudio');shutil.move(str(source),target);self._load(target);self._notice='Projet REAPER importé. '+' '.join(obj.get('warnings',[]))
    def _analysis(self,kind,args):
        reanalyze=args.get('reanalyze') is True
        if not reanalyze and model.analysis_done(self._project,kind):
            self._notice='Analyse déjà disponible et résultat protégé. Les corrections et validations sont conservées.';return
        if kind=='grid' and self._project.get('gridLocked'):raise ValueError('Le calage est protégé. Décoche « Protéger le calage » dans Click & cues avant de relancer.')
        vocal='vocal_lead' if any(t['role']=='vocal_lead' for t in self._project['tracks']) else 'vocals'
        desired={'lyrics':vocal,'lyricscorrect':vocal,'drums':'drums','drumsep':'drums'}.get(kind,'source');source=next((t for t in self._project['tracks'] if t['role']==desired),None)
        if not source and kind not in ('drums','drumsep'):source=next((t for t in self._project['tracks'] if t['role']=='source'),None)
        if not source:raise ValueError('Il manque la piste '+desired+'. Importe un morceau ou sépare ses instruments.')
        offset=source['offset']
        arguments=['--model',args.get('model','htdemucs'),'--quality',args.get('quality','standard'),'--language',args.get('language','auto')]
        if reanalyze:arguments.append('--reanalyze')
        if args.get('sourceURL'):
            if kind!='chords' or not any(s['url']==args['sourceURL'] for s in (self._project.get('chordReference') or {}).get('sources',[])):raise ValueError('Choisis une grille trouvée pour ce morceau.')
            arguments+=['--chord-source',args['sourceURL']]
        result,obj=self._work(kind,model.relative_file(self._root,source['file']),arguments);self._remember()
        if kind=='grid':
            model.apply_grid(self._project,obj,offset,reanalyze=reanalyze);self._reload()
        elif kind=='structure':model.apply_sections(self._project,obj['sections'])
        elif kind in ('separate','drumsep'):
            tracks=[];names={'drums':'Batterie','bass':'Basse','vocals':'Chant','guitar':'Guitare','piano':'Piano','other':'Autres instruments','drum_kick':'Grosse caisse','drum_snare':'Caisse claire','drum_toms':'Toms','drum_cymbals':'Cymbales et charleston'}
            for t in obj['tracks']:
                source=Path(t['path']).resolve()
                if not source.is_relative_to(result.parent.resolve()):raise ValueError('Piste hors du dossier de traitement.')
                target=self._root/'Audio'/(model.ident()+'.wav');shutil.copy2(source,target);tracks.append(model.track(target,self._root,names.get(t['role'],t['role']),t['role'],offset if kind=='drumsep' else 0))
                if kind=='drumsep':
                    parent=next(old for old in self._project['tracks'] if old['role']=='drums')
                    tracks[-1].update({k:parent[k] for k in ('gain','pan','muted')})
                    previous=next((old for old in self._project['tracks'] if old['role']==t['role']),None)
                    if previous:tracks[-1].update({k:previous[k] for k in ('id','gain','pan','muted','solo')})
            if kind=='drumsep' and {t['role'] for t in tracks}!={'drum_kick','drum_snare','drum_toms','drum_cymbals'}:raise ValueError('Séparation de batterie incomplète.')
            keep=[t for t in self._project['tracks'] if not t['role'].startswith('drum_')] if kind=='drumsep' else [t for t in self._project['tracks'] if t['role'] in ('source','take') or t['role'].startswith('guide_')]
            self._project['tracks']=keep+tracks;self._reload();self._audio.mode='mix'
        elif kind=='drums':
            pitches={'BD':36,'SD':38,'TT':45,'HH':42,'CY':49};self._project['drumHits']=sorted([dict(time=t,pitch=pitches[k],velocity=max(1,min(127,round(prob*127)))) for k,rows in obj['onsets'].items() for t,prob in rows if t<=model.duration(self._project)],key=lambda x:x['time'])
        elif kind=='chords':
            from chord_sources import apply
            apply(self._project,obj)
        elif kind in ('lyrics','lyricscorrect'):
            kind='lyrics'
            self._project['lyricsReference']=obj.get('lyricsReference')
            entries=[];manual=[x for x in self._project[kind] if x.get('manual')]
            for row in obj['segments']:
                start=row.get('start',row.get('t',0));end=min(model.duration(self._project),row['end'])
                if end<=start or any(x['start']<end and x['end']>start for x in manual):continue
                entry=dict(id=model.ident(),start=start,end=end,text=row.get('text',row.get('label','')),manual=False,sourceURL=row.get('sourceURL'),confidence=row.get('confidence'))
                if kind=='lyrics':entry['words']=[dict(start=w['t'],end=w['end'],text=w['w']) for w in row.get('words',[]) if start<=w['t']<w['end']<=end+.1]
                entries.append(entry)
            self._project[kind]=sorted(manual+entries,key=lambda x:x['start'])
        model.analysis_completed(self._project,kind)
        self._save();self._notice=obj['reference']['message'] if kind=='chords' else obj['lyricsReference']['message'] if kind=='lyrics' and obj.get('lyricsReference') else 'Analyse ajoutée. Vérifie et corrige les propositions dans l’atelier ou le prompteur.'
    def _set_rate(self,rate,pitch,resume=False):
        self._audio.pause();self._audio.rate=model.number(rate,.5,1.5);self._audio.pitch=model.number(pitch,-12,12);self._audio.prepare()
        if resume:self._audio.play()
    def _prepare_all(self,args,only=None):
        from windows.advanced_host import advanced_task
        steps=[kind for kind in self._plan() if only is None or kind in only];self._job_plan=steps
        for index,kind in enumerate(steps,1):
            self._job_plan_index=index-1
            before=copy.deepcopy(self._project)
            titles={'separate':'Séparation','drumsep':'Éléments de batterie','vocalsplit':'Chant et chœurs','grid':'Tempo','smartgrid':'Temps et mesures','structure':'Structure','key':'Tonalité','lyrics':'Paroles','lyricscorrect':'Correction des paroles','chords':'Accords','prepareReview':'Vérification finale des sections et accords','guides':'Click et annonces'}
            self._job_name=f'Tout préparer · {index}/{len(steps)} · '+titles[kind];self._state()
            try:
                if self._cancelled.is_set():raise RuntimeError('Traitement annulé.')
                if kind in ('smartgrid','key'):advanced_task(self,kind,{})
                elif kind=='vocalsplit':
                    from windows.creative_host import creative_task
                    creative_task(self,kind,{})
                elif kind=='prepareReview':
                    _,result=self._work(kind)
                    prepared=result['project'];model.validate(prepared,self._root)
                    if prepared['id']!=self._project['id']:raise ValueError('Préparation d’un autre morceau.')
                    self._remember();self._project=prepared;self._reload();self._save(invalidate=False)
                elif kind=='guides':self._guides()
                else:self._analysis(kind,args)
            except Exception as error:
                self._project=before;self._reload();self._save(invalidate=False)
                raise RuntimeError(f'Arrêt à l’étape {index}/{len(steps)} ({kind}). Les étapes terminées sont conservées. {error}') from error
        self._notice='Morceau préparé. Les améliorations sont visibles dans Pistes & structure ; écoute les passages signalés.'
    def _dialog(self,kind,**options):
        import webview
        return self._window.create_file_dialog(getattr(webview.FileDialog,kind),**options)
    def _reveal(self,path):
        if os.name=='nt':subprocess.Popen(['explorer.exe','/select,',str(Path(path))],creationflags=creation_flags())
    def _install(self,component):
        if component not in ('stems','structure','words','chords','drums','rhythm','drumsep','creative'):raise ValueError('Composant inconnu.')
        if self._components:raise ValueError('Une installation est déjà ouverte. Termine-la et ferme sa fenêtre avant d’en lancer une autre.')
        env=os.environ.copy();env.update(PYTHONUTF8='1',REAPER_RESOURCE_PATH=str(self._engine/'worker-state'),UV_PYTHON_INSTALL_DIR=str(self._engine/'managed-python'),UV_CACHE_DIR=str(self._engine/'.uv_cache'),REACUE_WORDS_ENGINE='off',TORCH_HOME=str(self._engine/'torch-cache'))
        env['PATH']=str(self._engine/'tools')+os.pathsep+str(self._engine/'import-tools')+os.pathsep+env.get('PATH','')
        script=['-File',str(self._engine/'windows/install_extra.ps1'),'-Component',component] if component in ('rhythm','drumsep','creative') else ['-File',str(self._engine/'install'/('install_'+component+'_windows.ps1')),'-Lang','fr']
        proc=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-NoExit',*script],cwd=self._engine,env=env,creationflags=subprocess.CREATE_NEW_CONSOLE)
        diagnostics.event('component.start', component=component)
        self._components[component]=proc;self._notice='Une fenêtre d’installation est ouverte. Suis ses indications puis ferme-la quand elle a terminé.'
    def command(self,message):
        """The only method exposed to the local WebView; never accepts executable code."""
        with self._lock:
            before=copy.deepcopy(self._project);history=self._history.copy();future=self._future.copy()
            ok=True
            if message.get("command") not in ("ready","diagnostic"):diagnostics.event("command",command=message.get("command"),playing=self._audio.running,position=self._audio.position,busy=self._busy)
            try:self._command(message)
            except Exception as error:
                self._history=history;self._future=future
                if self._project['id']==before['id'] and self._project!=before:
                    self._project=before
                    try:self._reload();self._save()
                    except Exception:pass
                ok=False;diagnostics.event("command.error",kind=type(error).__name__,error=error);self._notice=str(error);traceback.print_exc()
            self._state()
        return {'ok':ok}
    def _batch_command(self,args):
        from batch_queue import Client
        with self._lock:
            if not self._batch:
                def receive(value):
                    self._batch_state=value;self._send(value)
                    if value.get('libraryChanged'):self._state()
                self._batch=Client(self._engine,self._library,receive)
        action=args.get('action')
        if action=='files':
            paths=self._dialog('OPEN',allow_multiple=True,file_types=('Audio et vidéos (*.*)',))
            if paths:self._batch.send(dict(action='add',kind='file',sources=list(paths),options=args.get('options',{})))
        elif action=='refresh':self._send(self._batch_state)
        else:self._batch.send(args)
        self._batch.send(dict(action='heartbeat',ready=not self._busy and not self._audio.running and not self._record and not self._components))
    def _command(self,m):
        if not isinstance(m,dict):raise ValueError('Commande invalide.')
        cmd=m.get('command');args=m.get('args') or {};a=self._audio;p=self._project
        if cmd=='batchQueue':self._batch_command(args);return
        if cmd=='checkUpdates':self._check_updates();return
        if cmd=='automaticUpdates':
            updater.set_enabled(args.get('enabled',True));self._send(dict(type='update',automatic=updater.enabled(),message='Préférence enregistrée.'))
            if updater.enabled():self._check_updates()
            return
        if cmd=='artwork':
            if self._artwork_busy:
                self._send(dict(type='artworkResult',path=args.get('path'),message='Une recherche est déjà en cours.'));return
            self._artwork_busy=True
            def lookup():
                try:
                    result=artwork.run(self._library,self._engine,args)
                    catalog.member(self._library,args['path']);result['entry']=catalog.entry(args['path'])
                except Exception as error:
                    diagnostics.event('artwork.error',kind=type(error).__name__);result=dict(message='Ce morceau n’est plus disponible.')
                finally:self._artwork_busy=False
                self._send(dict(type='artworkResult',path=args.get('path'),**result))
            threading.Thread(target=lookup,daemon=True).start();return
        if cmd=='ready':return
        if cmd=='chordSourceOpen':
            import webbrowser
            from urllib.parse import urlsplit
            link=args.get('url','');url=urlsplit(link)
            if not any(s['url']==link for s in (self._project.get('chordReference') or {}).get('sources',[])) or url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Source d’accords invalide.')
            if not webbrowser.open(link):raise ValueError('Impossible d’ouvrir la grille.')
            return
        if cmd=='referenceSearch':
            import webbrowser
            from chord_sources import search_url
            kind=args.get('kind');query=str(args.get('query','')).strip()[:300]
            if not self._root or kind not in ('chords','lyrics') or not query:raise ValueError('Précise le titre du morceau.')
            url=search_url(query,kind,args.get('provider',''))
            if not webbrowser.open(url):raise ValueError('Impossible d’ouvrir le navigateur.')
            return
        if cmd=='supportInfo':self._send(diagnostics.support_info());return
        if cmd=='openCommunity':
            import webbrowser
            if not webbrowser.open(diagnostics.community_url(args.get('destination','invite'))):
                self._notice='Impossible d’ouvrir Discord. Réessaie depuis le lien du site BandStudio.'
            return
        if cmd=='copyDiscordReport':
            import webbrowser
            try:
                diagnostics.copy_report_windows(args.get('text'))
            except (ValueError,OSError,subprocess.SubprocessError):
                self._send(dict(type='supportCopied',request=args.get('request'),ok=False,message='Copie indisponible. Copie le texte sélectionné, puis ouvre le salon des bugs.'));return
            try:opened=webbrowser.open(diagnostics.community_url('bugs'))
            except OSError:opened=False
            message='Rapport copié. Colle-le dans #rapports-de-bugs et clique sur Envoyer dans Discord.' if opened else 'Rapport copié. Ouvre le salon des bugs avec le bouton ci-dessous, puis colle-le.'
            self._send(dict(type='supportCopied',request=args.get('request'),ok=True,message=message));return
        if cmd=='diagnostic':diagnostics.event('web.error',message=str(args.get('message',''))[:2000],line=args.get('line',0));return
        if cmd=='showLogs':self._reveal(diagnostics.directory()/'application.log');return
        if cmd=='reportBug':
            import webbrowser
            webbrowser.open(diagnostics.issue_url());return
        if cmd=='exportDiagnostics':
            paths=self._dialog('SAVE',save_filename='BandStudio-diagnostic.zip')
            if paths:
                target=paths if isinstance(paths,str) else paths[0]
                diagnostics.export_report(target);self._notice='Diagnostic exporté. Vérifie-le avant de le joindre au signalement.'
            return
        if cmd=='cancel':
            self._cancelled.set()
            self._transport_generation+=1
            if self._job:
                if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(self._job.pid),'/T','/F'],capture_output=True,creationflags=creation_flags())
                else:self._job.terminate()
            return
        if self._busy and cmd not in ('stop','play','studioControl'):raise ValueError('Un traitement est en cours. Patiente ou annule-le.')
        if self._record and cmd not in ('record','stop','studioControl'):raise ValueError('Arrête la prise avant cette action.')
        if cmd=='installComponent':self._install(args.get('component'));return
        if cmd=='audioSettings':os.startfile('ms-settings:sound');return
        if cmd=='voiceSettings':os.startfile('ms-settings:speech');return
        if cmd in ('bandpilot','bridge','studioControl','record','newSession','captureSettings'):
            raise ValueError('BandStudio prépare les morceaux. L’enregistrement se poursuit dans REAPER.')
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
        if cmd=='deleteProject':
            path=catalog.member(self._library,args['path']);active=self._root is not None and path==self._root.resolve()
            if active:a.close();a.data.clear()
            try:catalog.remove(self._library,path)
            except Exception:
                if active:self._reload()
                raise
            if active:
                self._audio=Audio(self._engine);self._project=model.fresh();self._root=None;self._history=[];self._future=[];self._last_export='';self._revision+=1
            self._notice='Morceau déplacé dans la corbeille BandStudio. Tu peux le restaurer depuis Mes morceaux.';return
        if cmd=='restoreProject':
            catalog.restore(self._library);self._notice='Morceau restauré dans la bibliothèque.';return
        if cmd=='projectArtwork':
            path=catalog.member(self._library,args['path'])
            files=self._dialog('OPEN',file_types=('Images (*.jpg;*.jpeg;*.png;*.webp)',))
            if files:
                def assign_artwork():
                    if not catalog.extract(files[0],path,self._engine):raise ValueError('Image illisible. Choisis une image JPG, PNG ou WebP.')
                    self._notice='Pochette enregistrée.'
                self._op('Ajout de la pochette',assign_artwork)
            return
        if m.get('projectID')!=p['id']:raise ValueError('Le projet a changé. Recommence ton action.')
        if cmd=='newSession':recording.command(self,dict(action='new',name=args.get('name','Répétition')));return
        if cmd=='captureSettings':recording.command(self,dict(action='configure',settings=args));return
        if cmd=='setlist':
            name=str(args.get('name') or '').strip();paths=args.get('paths') or []
            if not name:raise ValueError('Donne un nom à la setlist avant de l’enregistrer.')
            if not isinstance(paths,list):raise ValueError('Morceaux de setlist invalides.')
            # A song deleted from the library stays listed as « Fichier déplacé »; drop it instead
            # of rejecting every later edit (rename, reorder, add) of that setlist.
            known={s['path'] for s in self._list()};paths=[x for x in paths if x in known]
            ident=args.get('id') or model.ident();item=dict(id=ident,name=name[:120],paths=paths)
            self._setlists=[x for x in self._setlists if x['id']!=ident]+[item];atomic(self._library/'setlists.json',self._setlists);return
        if self._root is None:raise ValueError('Importe ou ouvre d’abord un morceau.')
        if cmd=='play':
            if a.running:a.pause()
            elif self._ready_guides():a.play()
            elif self._busy:self._notice='Préparation audio en cours. Patiente avant de relancer la lecture.'
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
            def change_playback():
                self._set_rate(rate,pitch,running)
                p['preparation']=dict(rate=rate,pitch=pitch,mode=a.mode);self._save()
            self._op('Préparation de la vitesse et de la tonalité',change_playback);return
        if cmd=='mode':
            mode=args['value']
            from listening import parse_mode,matches
            kind,instrument=parse_mode(mode)
            if instrument and not any(matches(t['role'],instrument) for t in p['tracks']):raise ValueError('Sépare cet instrument ou ajoute sa piste avant d’utiliser ce mode.')
            if kind=='original' and not any(t['role']=='source' for t in p['tracks']):raise ValueError('Ce projet ne contient pas de piste originale.')
            a.mode=mode;p['preparation']=dict(rate=a.rate,pitch=a.pitch,mode=mode);self._save();return
        if cmd=='loop':
            start=model.number(args['start'],0,model.duration(p));end=model.number(args['end'],0,model.duration(p));on=bool(args['on'])
            if on and end-start<.05:raise ValueError('Choisis une boucle d’au moins 50 ms.')
            running=a.running;a.pause();a.loop=on;a.loopStart=start;a.loopEnd=end
            if running:a.play()
            return
        if cmd in ('reveal','showExport'):
            self._reveal(self._last_export if cmd=='showExport' and self._last_export else self._root);return
        if cmd=='save':self._save(invalidate=False);self._notice='Projet enregistré.';return
        if cmd=='saveDefaults':atomic(self._library/'defaults.json',p['settings']);self._notice='Réglages enregistrés pour les prochains imports.';return
        if cmd=='guides':a.pause();self._op('Préparation des guides',lambda:self._guides(force=True));return
        if cmd=='guideMix':
            key=args.get('key')
            if key not in ('clickGain','callsGain','cuesGain','countGain'):raise ValueError('Volume inconnu.')
            gain=model.number(args['value'],0,1.5);self._remember();p['settings'][key]=gain
            if gain>0 and key!='countGain':p['settings'][{'clickGain':'clickEnabled','callsGain':'callsEnabled','cuesGain':'speakCues'}[key]]=True
            with a.lock:a.project=copy.deepcopy(p)
            self._save();return
        if cmd in ('moveMarker','reviewMarker'):
            a.pause();self._remember();model.edit_marker(p,args,review=cmd=='reviewMarker');self._save();return
        if cmd=='audition':
            start=model.number(args['start'],0,model.duration(p));end=model.number(args['end'],start+.05,model.duration(p))
            a.pause();a.loop=True;a.loopStart=start;a.loopEnd=end;a.position=start
            action=lambda:a.play(with_count=False)
            if self._ready_guides():action()
            else:self._op('Préparation de l’écoute',self._prepared_transport(action))
            return
        if cmd=='settings':
            value={**model.GUIDE_DEFAULTS,**args['value']};candidate={**p,'settings':value};model.validate(candidate,self._root)
            a.pause();self._remember()
            if any(value[k]!=p['settings'][k] for k in ('firstBeat','gridMode','beatsPerBar','manualBPM')) or (value['gridMode']=='fixed' and value.get('pulseUnit')!=p['settings'].get('pulseUnit')):p['gridLocked']=True
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
                if args['key'] and not re.fullmatch(r'[A-G](#|b)?m?',args['key']):raise ValueError('Tonalité invalide.')
                p['key']=args['key']
            if 'gridLocked' in args:p['gridLocked']=bool(args['gridLocked'])
            self._save();return
        if cmd=='studioTask':
            from windows.advanced_host import advanced_task
            kind=args.get('kind');options=args.get('options') or {}
            if kind not in ('smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet'):raise ValueError('Outil inconnu.')
            if options.get('reanalyze') is not True and model.analysis_done(p,kind):
                self._notice='Analyse déjà disponible et résultat protégé. Les corrections et validations sont conservées.';return
            a.pause();self._op('Outil local : '+kind,lambda:advanced_task(self,kind,options));return
        if cmd=='analyze':
            kind=args.get('kind')
            if kind not in ('grid','structure','separate','drumsep','lyrics','lyricscorrect','chords','drums'):raise ValueError('Analyse inconnue.')
            self._op('Analyse locale : '+kind,lambda:self._analysis(kind,args));return
        if cmd=='reviewStructure':
            if not self._root or not any(t['role']=='source' for t in p['tracks']):raise ValueError('Importe le morceau original avant la vérification.')
            def review_structure():
                _,memory=self._work('structureMemory')
                if memory.get('proposal'):
                    self._prepare_all(args,only={'separate'})
                    _,memory=self._work('structureMemory')
                    if not memory.get('proposal'):raise ValueError('Le morceau a changé pendant la préparation. Relance la vérification.')
                    self._project['structureProposal']=memory['proposal'];self._save(invalidate=False)
                    self._notice='Préparation du même enregistrement retrouvée. Valide la proposition pour la réutiliser.'
                    return
                self._prepare_all(args,only={'separate','grid','smartgrid','structure','chords'})
                _,proposal=self._work('structureReview')
                self._project['structureProposal']=proposal;self._save(invalidate=False)
                changed=proposal.get('changes') or proposal.get('chordUpdate') or proposal.get('memory') or proposal.get('restoredGrid')
                self._notice=('Proposition disponible dans Pistes & structure. Les sections actuelles sont conservées jusqu’à ta validation.'
                              if changed else 'Aucune amélioration proposée — préparation actuelle conservée.')
            a.pause();self._op('Vérification de la structure',review_structure,rollback=False);return
        if cmd=='dismissStructure':
            if not args.get('proposalID') or args.get('proposalID')!=(p.get('structureProposal') or {}).get('id'):raise ValueError('Cette proposition n’est plus disponible.')
            from structure_review import record_decision
            record_decision(self._root,p['structureProposal'],'kept_current')
            p.pop('structureProposal',None);self._save(invalidate=False);self._notice='Parcours actuel conservé.';return
        if cmd=='applyStructure':
            if args.get('reviewed') is not True or not args.get('proposalID') or args['proposalID']!=(p.get('structureProposal') or {}).get('id'):
                raise ValueError('Valide la proposition affichée dans Pistes & structure.')
            def apply_structure():
                _,result=self._work('structureApply')
                prepared=result['project']
                if prepared['id']!=self._project['id']:raise ValueError('La proposition appartient à un autre morceau.')
                model.validate(prepared,self._root)
                self._remember();self._project=prepared
                for key in ('_root','_library','_mode','_rate','_pitch'):self._project.pop(key,None)
                self._reload();self._save()
                self._notice='Proposition enregistrée dans le morceau. Annuler permet de retrouver les repères précédents.'
            a.pause();self._op('Application de la proposition',apply_structure);return
        if cmd=='exportStructure':
            if args.get('reviewed') is not True or not args.get('proposalID') or args['proposalID']!=(p.get('structureProposal') or {}).get('id'):
                raise ValueError('Valide la proposition affichée dans Pistes & structure.')
            def export_structure():
                _,result=self._work('structureExport')
                self._remember();self._project=result['project']
                for key in ('_root','_library','_mode','_rate','_pitch'):self._project.pop(key,None)
                self._reload();self._save(invalidate=False);self._last_export=result['path']
                self._notice='Proposition appliquée et projet REAPER exporté. Afficher l’export permet de le retrouver.'
            a.pause();self._op('Validation et export REAPER',export_structure);return
        if cmd=='prepareAll':
            if not any(t['role']=='source' for t in p['tracks']):raise ValueError('Importe le morceau original avant de lancer la préparation complète.')
            a.pause();self._op('Préparation complète',lambda:self._prepare_all(args),rollback=False);return
        if cmd=='validateProject':
            if args.get('reviewed') is not True:raise ValueError('Confirme l’écoute et les repères dans Valider & envoyer.')
            def validate_preparation():
                self._guides();_,obj=self._work('validate');p['preparation']=obj['preparation'];self._save(invalidate=False)
                self._notice='Morceau validé. Tu peux maintenant l’envoyer dans REAPER.'
            a.pause();self._op('Vérification du morceau et des médias',validate_preparation);return
        if cmd in ('reaper','midi'):
            def exported():
                if cmd=='reaper':self._guides()
                _,obj=self._work(cmd);self._last_export=obj['path'];self._notice='Export terminé. Afficher l’export permet de le retrouver.'
                if cmd=='reaper' and args.get('open'):
                    candidates=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'REAPER (x64)/reaper.exe',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'REAPER/reaper.exe',Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Programs/REAPER (x64)/reaper.exe']
                    app=next((x for x in candidates if x.is_file()),None)
                    if app:subprocess.Popen([str(app),'-newinst',str(self._last_export)],creationflags=creation_flags())
                    else:
                        try:os.startfile(str(self._last_export))
                        except OSError:self._notice='Projet exporté. Installe REAPER puis ouvre le fichier avec Afficher l’export.'
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
            if track['role'].startswith('guide_') and any(k not in ('id','muted','solo') for k in args):raise ValueError('Utilise Guidage pour régler le contenu de cette piste.')
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
            section=p['sections'][index];section.update(locked=True,origin='manual',reviewed=False)
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
                if kind=='chords' and args.get('replaceRange') is True:
                    tails=[]
                    for item in entries:
                        if item['start']>=end or item['end']<=start:
                            tails.append(item)
                            continue
                        if item['start']<start:tails.append(dict(item,end=start))
                        if item['end']>end:
                            tails.append(dict(item,start=end,id=model.ident() if item['start']<start else item['id']))
                    entries=tails
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
        # Stop UI updates first: WebView2 is disposed while the shutdown below runs, and
        # evaluate_js on it logs ObjectDisposedException in webview.log.
        self._stop.set()
        if self._record:self._stop_record()
        if self._bridge:self._bridge.close();self._bridge=None
        if self._job:
            if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(self._job.pid),'/T','/F'],capture_output=True,creationflags=creation_flags())
            else:self._job.terminate()
        if self._phone:self._phone.close()
        if self._batch:self._batch.close();self._batch=None
        updater.schedule_apply(self._engine)
        self._stop.set();self._audio.close();return True
