from ui_language import ui_text
import json
from pathlib import Path
import shutil
from windows import project as model

def creative_task(host,kind,options):
    p=host._project;root=host._root
    if len(p['tracks'])+2>128:raise ValueError(ui_text('Le projet atteint sa limite de pistes.', 'This project has reached its track limit.'))
    source=next((t for t in p['tracks'] if t['role']=='vocals'),None) if kind=='vocalsplit' else None
    if kind=='vocalsplit' and source is None:raise ValueError(ui_text('Sépare d’abord le chant du morceau.', 'Separate the song’s vocals first.'))
    result,obj=host._work(kind,model.relative_file(root,source['file']) if source else None,['--options',json.dumps(options)])
    tracks=[]
    for item in obj['tracks']:
        path=Path(item['path']).resolve();role=item['role']
        if not path.is_relative_to(result.parent.resolve()) or role not in ('take','vocal_lead','vocal_backing'):raise ValueError(ui_text('Résultat créatif invalide.', 'Invalid generated result.'))
        target=root/'Audio'/(model.ident()+'-'+role+'.wav');shutil.copy2(path,target)
        t=model.track(target,root,ui_text('Accompagnement généré', 'Generated accompaniment') if kind=='generate' else {'vocal_lead':ui_text('Chant principal', 'Lead vocals'),'vocal_backing':ui_text('Chœurs', 'Backing vocals')}[role],role,source['offset'] if source else 0)
        t['gain']=source['gain'] if source else .8;t['pan']=source['pan'] if source else 0;t['muted']=source['muted'] if source else kind=='generate' and model.duration(p)>0
        previous=next((x for x in p['tracks'] if x['role']==role),None)
        if kind=='vocalsplit' and previous:t.update({k:previous[k] for k in ('id','gain','pan','muted','solo')})
        tracks.append(t)
    if not tracks:raise ValueError(ui_text('Aucune piste générée.', 'No track generated.'))
    if kind=='vocalsplit' and {t['role'] for t in tracks}!={'vocal_lead','vocal_backing'}:raise ValueError(ui_text('Séparation du chant incomplète.', 'Vocal separation incomplete.'))
    host._remember()
    if kind=='vocalsplit':p['tracks']=[t for t in p['tracks'] if not t['role'].startswith('vocal_')]
    p['tracks']+=tracks;host._save();host._reload();host._audio.mode='mix'
    host._notice=ui_text('Création terminée. Active le Solo de la nouvelle piste pour l’écouter.', 'Generation finished. Solo the new track to hear it.') if kind=='generate' else ui_text('Chant principal et chœurs proposés. Le chant complet reste disponible en Solo.', 'Lead and backing vocals are ready. Solo the full vocal track to compare.')
