"""Windows host integration for the shared local practice tools."""
from ui_language import ui_text
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
from windows import project as model
from windows.audio import Audio


def advanced_task(host, kind, options):
    reanalyze=options.get('reanalyze') is True
    if not reanalyze and model.analysis_done(host._project,kind):
        host._notice=ui_text('Analyse déjà disponible et résultat protégé. Les corrections et validations sont conservées.', 'Analysis already exists and is protected. Your corrections and approvals have been kept.');return
    p=host._project;root=host._root
    if root is None:raise ValueError(ui_text('Ouvre d’abord un morceau.', 'Open a song first.'))
    if kind=='smartgrid' and p.get('gridLocked'):
        raise ValueError(ui_text('Le calage est protégé. Décoche « Protéger le calage » dans Click & cues avant de relancer.', 'Timing is locked. Clear Protect timing in the metronome settings before running detection again.'))
    audio=None;offset=0
    if kind in ('smartgrid','key'):
        source=next((t for t in p['tracks'] if t['role']=='source'),next((t for t in p['tracks'] if not t['role'].startswith('guide_')),None))
        if not source:raise ValueError(ui_text('Aucune piste à analyser.', 'No track to analyze.'))
        audio=model.relative_file(root,source['file']);offset=source['offset']
    if kind=='master':
        audio=root/'Analyses'/('mix-'+model.ident()+'.wav');audio.parent.mkdir(parents=True,exist_ok=True)
        music=copy.deepcopy(p);music['settings']['exportGuides']=False;music['settings']['exportCount']=False
        render=Audio(host._engine);render.rate=host._audio.rate;render.pitch=host._audio.pitch;render.load(music,root);render.mode=host._audio.mode
        render.render(audio,0,model.duration(p),False)
    _,obj=host._work(kind,audio,['--options',json.dumps(options,ensure_ascii=True)])
    if kind=='smartgrid':
        host._remember();model.apply_grid(p,obj,offset,reanalyze=reanalyze)
        model.analysis_completed(p,kind);host._reload();host._save();host._notice=p['analysisNote']
    elif kind=='key':
        host._remember();p['key']=obj['key'];model.analysis_completed(p,kind);host._save();host._notice=ui_text('Tonalité proposée : ', 'Suggested key: ')+p['key']+ui_text('. Vérifie et corrige-la dans le prompteur.', '. Check or change it in the teleprompter.')
    elif kind=='lyricsimport':
        host._remember();entries=obj['entries']
        p['lyrics']=entries if options.get('replace') else p['lyrics']+[e for e in entries if not any(x['start']<e['end'] and x['end']>e['start'] for x in p['lyrics'])]
        p['lyrics'].sort(key=lambda x:x['start']);host._save();host._notice=ui_text('Paroles synchronisées importées.', 'Synced lyrics imported.')
    else:
        host._last_export=obj['path'];host._notice=ui_text('Export terminé. Utilise Afficher l’export pour le retrouver.', 'Export complete. Choose Show export to find it.')
        if kind=='sheet' and host._window is not None:
            source=Path(host._last_export).resolve()
            if not source.is_relative_to((root/'Exports').resolve()) or source.suffix.lower()!='.pdf' or not source.is_file():raise ValueError(ui_text('La fiche PDF est introuvable.', 'PDF song sheet not found.'))
            paths=host._dialog('SAVE',save_filename=source.name,file_types=(ui_text('Fiche PDF (*.pdf)', 'PDF song sheet (*.pdf)'),))
            if not paths:
                host._notice=ui_text('Enregistrement ailleurs annulé. Le PDF reste dans le dossier du morceau.', 'Save canceled. The PDF is still in the song folder.');return
            target=Path(paths[0] if isinstance(paths,(list,tuple)) else paths)
            if target.suffix.lower()!='.pdf':
                host._notice=ui_text('Choisis un nom se terminant par .pdf. Le PDF reste dans le dossier du morceau.', 'Choose a name ending in .pdf. The PDF is still in the song folder.');return
            temp=None
            try:
                if target.resolve()!=source:
                    with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.bandstudio-',suffix='.pdf',delete=False) as f:temp=Path(f.name)
                    shutil.copyfile(source,temp);os.replace(temp,target)
                host._last_export=str(target)
            except OSError as error:
                host._notice=ui_text('Impossible d’enregistrer cette copie : ', 'Could not save this copy: ')+str(error)+ui_text('. Le PDF original reste dans le dossier du morceau.', '. The original PDF is still in the song folder.');return
            finally:
                if temp is not None:temp.unlink(missing_ok=True)
            try:
                os.startfile(str(target));host._notice=ui_text('PDF enregistré et ouvert.', 'PDF saved and opened.')
            except OSError:
                host._notice=ui_text('PDF enregistré. L’ouverture automatique a échoué ; utilise Afficher l’export pour le retrouver.', 'PDF saved. Choose Show export to open it manually.')
