"""Windows host integration for the shared local practice tools."""
import copy
import json
from windows import project as model
from windows.audio import Audio


def advanced_task(host, kind, options):
    p=host._project;root=host._root
    if root is None:raise ValueError('Ouvre d’abord un morceau.')
    audio=None;offset=0
    if kind in ('smartgrid','key'):
        source=next((t for t in p['tracks'] if t['role']=='source'),next((t for t in p['tracks'] if not t['role'].startswith('guide_')),None))
        if not source:raise ValueError('Aucune piste à analyser.')
        audio=model.relative_file(root,source['file']);offset=source['offset']
    if kind=='master':
        audio=root/'Analyses'/('mix-'+model.ident()+'.wav');audio.parent.mkdir(parents=True,exist_ok=True)
        music=copy.deepcopy(p);music['settings']['exportGuides']=False;music['settings']['exportCount']=False
        render=Audio(host._engine);render.rate=host._audio.rate;render.pitch=host._audio.pitch;render.load(music,root);render.mode=host._audio.mode
        render.render(audio,0,model.duration(p),False)
    _,obj=host._work(kind,audio,['--options',json.dumps(options,ensure_ascii=True)])
    if kind=='smartgrid':
        host._remember();length=model.duration(p)
        p['beats']=[t+offset for t in obj['beats'] if 0<=t+offset<length]
        p['downbeats']=[t+offset for t in obj['downbeats'] if 0<=t+offset<length]
        p['bpm']=obj['bpm'];p['settings']['gridMode']='detected'
        if obj.get('firstBeat') is not None and 2<=obj['beatsPerBar']<=12:
            p['settings']['firstBeat']=max(0,obj['firstBeat']+offset);p['settings']['beatsPerBar']=obj['beatsPerBar']
        p['analysisNote']=obj['gridStatus'];host._reload();host._save();host._notice=p['analysisNote']
    elif kind=='key':
        host._remember();p['key']=obj['key'];host._save();host._notice='Tonalité proposée : '+p['key']+'. Vérifie et corrige-la dans le prompteur.'
    elif kind=='lyricsimport':
        host._remember();entries=obj['entries']
        p['lyrics']=entries if options.get('replace') else p['lyrics']+[e for e in entries if not any(x['start']<e['end'] and x['end']>e['start'] for x in p['lyrics'])]
        p['lyrics'].sort(key=lambda x:x['start']);host._save();host._notice='Paroles synchronisées importées.'
    else:
        host._last_export=obj['path'];host._notice='Export terminé. Utilise Afficher l’export pour le retrouver.'
