import json
from pathlib import Path
import shutil
from windows import project as model

def creative_task(host,kind,options):
    p=host._project;root=host._root
    if len(p['tracks'])+2>128:raise ValueError('Le projet atteint sa limite de pistes.')
    source=next((t for t in p['tracks'] if t['role']=='vocals'),None) if kind=='vocalsplit' else None
    if kind=='vocalsplit' and source is None:raise ValueError('Sépare d’abord le chant du morceau.')
    result,obj=host._work(kind,model.relative_file(root,source['file']) if source else None,['--options',json.dumps(options)])
    tracks=[]
    for item in obj['tracks']:
        path=Path(item['path']).resolve();role=item['role']
        if not path.is_relative_to(result.parent.resolve()) or role not in ('take','vocal_lead','vocal_backing'):raise ValueError('Résultat créatif invalide.')
        target=root/'Audio'/(model.ident()+'-'+role+'.wav');shutil.copy2(path,target)
        t=model.track(target,root,'Accompagnement généré' if kind=='generate' else {'vocal_lead':'Chant principal','vocal_backing':'Chœurs'}[role],role,source['offset'] if source else 0)
        t['gain']=source['gain'] if source else .8;t['pan']=source['pan'] if source else 0;t['muted']=kind=='generate' and model.duration(p)>0;tracks.append(t)
    if not tracks:raise ValueError('Aucune piste générée.')
    host._remember()
    if kind=='vocalsplit':p['tracks']=[t for t in p['tracks'] if not t['role'].startswith('vocal_')]
    p['tracks']+=tracks;host._save();host._reload();host._audio.mode='mix'
    host._notice='Création terminée. Active le Solo de la nouvelle piste pour l’écouter.' if kind=='generate' else 'Chant principal et chœurs proposés. Le chant complet reste disponible en Solo.'
