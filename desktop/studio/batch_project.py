"""Prepare private queue projects with the same workers and document format as Studio."""
from ui_language import ui_text
import json
import shutil
from pathlib import Path

from platform_tools import python_for
from services import atomic, import_settings, calibrate_grid
from windows import project as model

ENVIRONMENTS = {'separate': '.venv-demucs', 'smartgrid': '.venv-demucs',
                'structure': '.venv-structure', 'lyrics': '.venv-words', 'chords': '.venv',
                'drumsep': '.venv-demucs','vocalsplit': '.venv-creative'}
LABELS = {'import': 'Import', 'separate': ui_text('Séparation des instruments', 'Instrument separation'), 'grid': 'Tempo',
          'smartgrid': ui_text('Temps et mesures', 'Beats and bars'), 'structure': 'Structure', 'key': ui_text('Tonalité', 'Key'),
          'lyrics': ui_text('Paroles', 'Lyrics'), 'chords': ui_text('Accords', 'Chords'), 'guides': ui_text('Click et annonces', 'Click and announcements'),
          'drumsep':ui_text('Éléments de batterie', 'Drum kit pieces'),'vocalsplit':ui_text('Chant et chœurs', 'Lead and backing vocals'),'prepareReview':ui_text('Vérification finale des sections et accords', 'Final check of sections and chords')}


def plan(engine):
    engine = Path(engine)
    if not python_for(engine, '.venv-demucs').is_file():
        raise ValueError(ui_text('Installe Séparer les stems dans Réglages → Analyses locales, puis réessaie.', 'Install Separate stems in Settings → Local analysis, then try again.'))
    smart = any((engine / '.venv-demucs').glob('**/site-packages/beat_this'))
    extra=[]
    if (engine/'drumsep/49469ca8.th').is_file():extra.append('drumsep')
    if python_for(engine,'.venv-creative').is_file() and (engine/'creative/UVR_MDXNET_KARA_2.onnx').is_file():extra.append('vocalsplit')
    return ['import', 'separate', *extra, 'smartgrid' if smart else 'grid'] + [
        k for k in ('structure', 'key', 'lyrics')
        if k=='key' or python_for(engine, ENVIRONMENTS[k]).is_file()] + ['prepareReview','guides']


def snapshot(root, library, title):
    root = Path(root)
    if (root / 'project.json').exists():
        return model.load(root)
    p = model.fresh(title)
    try:
        p['settings'].update(json.loads((Path(library) / 'defaults.json').read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    p['settings'] = import_settings(p['settings'])
    # Native Mac voices have names; "Système" is the portable Windows default.
    import sys
    if sys.platform == 'darwin' and p['settings']['voice'] == 'Système':
        p['settings']['voice'] = 'Thomas' if p['settings']['language'] == 'fr' else 'Samantha'
    return p


def request(item, stage, root, folder, engine, library):
    p = snapshot(root, library, item['title'])
    source = None
    command = stage
    args = []
    if stage == 'import':
        command = 'decode'
        source = item['source']
        if item.get('kind') != 'file' or not Path(source).is_file():
            raise ValueError(ui_text('Fichier source introuvable. Remets-le à son emplacement puis réessaie.', 'Source file not found. Put it back in its original location and try again.'))
    elif stage not in ('guides','prepareReview'):
        role = ('vocal_lead' if any(t['role']=='vocal_lead' for t in p['tracks']) else 'vocals') if stage=='lyrics' else 'vocals' if stage=='vocalsplit' else 'drums' if stage=='drumsep' else 'source'
        track = next((t for t in p['tracks'] if t['role'] == role), None)
        if not track:
            raise ValueError(ui_text('Piste nécessaire absente : ', 'Required track missing: ') + role)
        source = str(model.relative_file(root, track['file']))
    snap = folder / 'snapshot.json'
    atomic(snap, {**p, '_root': str(root)})
    options = item['options']
    args = [str(python_for(engine, ENVIRONMENTS.get(stage, '.venv'))),
            str(Path(engine) / 'worker.py'), command, '--engine', str(engine),
            '--project', str(snap), '--output', str(folder / 'result.json'),
            '--model', options['model'], '--quality', options['quality'],
            '--language', options['language'], *args]
    if source:
        args += ['--input', source]
    return args


def apply(item, stage, root, folder, library):
    """Commit a step and its checkpoint together; partial files are never a completed step."""
    root, folder = Path(root), Path(folder)
    p = snapshot(root, library, item['title'])
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))

    def copy_media(path, category, name):
        source = Path(path).resolve()
        if not source.is_relative_to(folder.resolve()) or not source.is_file():
            raise ValueError(ui_text('Résultat audio hors du dossier de traitement.', 'Audio result is outside the processing folder.'))
        target = root / category / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    if stage == 'import':
        target = copy_media(result['audio'], 'Audio', 'original.wav')
        p['name'] = str(result.get('title') or item['title'])[:200]
        p['sourceURL'] = ''
        p['tracks'] = [model.track(target, root, 'Original', 'source')]
        if result.get('artwork'):
            copy_media(result['artwork'], '.', 'Artwork.jpg')
        atomic(root / 'Artwork.json', {**(result.get('musicMetadata') or {}), 'title': p['name']})
    elif stage == 'separate':
        names = {'vocals': ui_text('Chant', 'Vocals'), 'bass': ui_text('Basse', 'Bass'), 'drums': ui_text('Batterie', 'Drums'),
                 'guitar': ui_text('Guitare', 'Guitar'), 'piano': 'Piano', 'other': ui_text('Autres instruments', 'Other instruments')}
        tracks = []
        for row in result['tracks']:
            role = row['role']
            if role not in names:
                raise ValueError(ui_text('Instrument séparé inconnu.', 'Unknown separated instrument.'))
            target = copy_media(row['path'], 'Audio', role + '.wav')
            tracks.append(model.track(target, root, names[role], role))
        if not tracks:
            raise ValueError(ui_text('La séparation n’a produit aucune piste.', 'Separation produced no tracks.'))
        p['tracks'] = [t for t in p['tracks'] if t['role'] == 'source'] + tracks
        p['preparation'] = dict(rate=1, pitch=0, mode='mix')
    elif stage in ('drumsep','vocalsplit'):
        names={'drum_kick':ui_text('Grosse caisse', 'Kick'),'drum_snare':ui_text('Caisse claire', 'Snare'),'drum_toms':'Toms','drum_cymbals':ui_text('Cymbales / charleston', 'Cymbals / hi-hat')} if stage=='drumsep' else {'vocal_lead':ui_text('Chant principal', 'Lead vocals'),'vocal_backing':ui_text('Chœurs', 'Backing vocals')}
        parent=next(t for t in p['tracks'] if t['role']==('drums' if stage=='drumsep' else 'vocals'))
        tracks=[]
        for row in result['tracks']:
            role=row['role']
            if role not in names:raise ValueError(ui_text('Sous-piste inconnue.', 'Unknown subtrack.'))
            target=copy_media(row['path'],'Audio',role+'.wav')
            track=model.track(target,root,names[role],role,parent['offset']);track.update({k:parent[k] for k in ('gain','pan','muted')})
            previous=next((t for t in p['tracks'] if t['role']==role),None)
            if previous:track.update({k:previous[k] for k in ('id','gain','pan','muted','solo')})
            tracks.append(track)
        if {t['role'] for t in tracks}!=set(names):raise ValueError(ui_text('Séparation incomplète.', 'Separation incomplete.'))
        p['tracks']=[t for t in p['tracks'] if t['role'] not in names]+tracks
    elif stage=='prepareReview':
        prepared=result['project']
        if prepared['id']!=p['id']:raise ValueError(ui_text('Préparation d’un autre morceau.', 'This preparation belongs to another song.'))
        model.validate(prepared,root);p=prepared
    elif stage in ('grid', 'smartgrid'):
        if not model.analysis_done(p, stage):
            model.apply_grid(p, calibrate_grid(result))
    elif stage == 'structure':
        model.apply_sections(p, result['sections'])
    elif stage == 'key':
        p['key'] = result['key']
    elif stage=='chords':
        from chord_sources import apply as apply_chord_reference
        apply_chord_reference(p,result)
    elif stage=='lyrics':
        model.apply_lyrics(p,result)
    elif stage == 'guides':
        p['timingGrid'] = result.get('timingGrid')
        if not p.get('gridLocked') and result.get('firstBeatCorrection') is not None:p['settings']['firstBeat']=result['firstBeatCorrection']
        previous_guides = p['tracks']
        p['tracks'] = [t for t in p['tracks'] if not t['role'].startswith('guide_')]
        # Count-ins also need the individual spoken numbers and section-call assets.
        p['guideFiles'] = {
            key: copy_media(path, 'Guides', f'{index:03}.wav').relative_to(root).as_posix()
            for index, (key, path) in enumerate(result['files'].items())}
        for key, name, role in [('click', ui_text('Métronome', 'Metronome'), 'guide_click'),
                                ('calls', ui_text('Appels de régions', 'Region announcements'), 'guide_voice'),
                                ('cues', 'Cues', 'guide_cue'),
                                ('counts', ui_text('Décomptes', 'Count-ins'), 'guide_count')]:
            if key not in p['guideFiles']:continue
            target = root / p['guideFiles'][key]
            p['tracks'].append(model.guide_track(target, root, name, role, previous_guides))
        p['guideKey'] = model.guide_key(p) if 'cues' in p['guideFiles'] else ''
    if stage in ('grid','smartgrid','structure','lyrics','chords','drums','key','separate','drumsep','vocalsplit','prepareReview'):model.analysis_completed(p,stage)
    p['_queueID'] = item['id']
    p['_queueCompleted'] = list(dict.fromkeys([*p.get('_queueCompleted', []), stage]))
    model.save(p, root)
    return p
