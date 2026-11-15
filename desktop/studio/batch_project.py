"""Prepare private queue projects with the same workers and document format as Studio."""
import json
import shutil
from pathlib import Path

from platform_tools import python_for
from services import atomic
from windows import project as model

ENVIRONMENTS = {'separate': '.venv-demucs', 'smartgrid': '.venv-demucs',
                'structure': '.venv-structure', 'lyrics': '.venv-words', 'chords': '.venv-chords'}
LABELS = {'import': 'Import', 'separate': 'Séparation des instruments', 'grid': 'Tempo',
          'smartgrid': 'Temps et mesures', 'structure': 'Structure', 'key': 'Tonalité',
          'lyrics': 'Paroles', 'chords': 'Accords', 'guides': 'Click et annonces'}


def plan(engine):
    engine = Path(engine)
    if not python_for(engine, '.venv-demucs').is_file():
        raise ValueError('Installe Séparer les stems dans Réglages → Analyses locales, puis réessaie.')
    smart = any((engine / '.venv-demucs').glob('**/site-packages/beat_this'))
    return ['import', 'separate', 'smartgrid' if smart else 'grid'] + [
        k for k in ('structure', 'key', 'lyrics', 'chords')
        if k == 'key' or python_for(engine, ENVIRONMENTS[k]).is_file()] + ['guides']


def snapshot(root, library, title):
    root = Path(root)
    if (root / 'project.json').exists():
        return model.load(root)
    p = model.fresh(title)
    try:
        p['settings'].update(json.loads((Path(library) / 'defaults.json').read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
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
            raise ValueError('Fichier source introuvable. Remets-le à son emplacement puis réessaie.')
    elif stage != 'guides':
        role = 'vocals' if stage == 'lyrics' else 'source'
        track = next((t for t in p['tracks'] if t['role'] == role), None)
        if not track:
            raise ValueError('Piste nécessaire absente : ' + role)
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
            raise ValueError('Résultat audio hors du dossier de traitement.')
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
        names = {'vocals': 'Chant', 'bass': 'Basse', 'drums': 'Batterie',
                 'guitar': 'Guitare', 'piano': 'Piano', 'other': 'Autres instruments'}
        tracks = []
        for row in result['tracks']:
            role = row['role']
            if role not in names:
                raise ValueError('Instrument séparé inconnu.')
            target = copy_media(row['path'], 'Audio', role + '.wav')
            tracks.append(model.track(target, root, names[role], role))
        if not tracks:
            raise ValueError('La séparation n’a produit aucune piste.')
        p['tracks'] = [t for t in p['tracks'] if t['role'] == 'source'] + tracks
        p['preparation'] = dict(rate=1, pitch=0, mode='mix')
    elif stage in ('grid', 'smartgrid'):
        p['beats'], p['bpm'] = result['beats'], result['bpm']
        p['downbeats'] = result.get('downbeats', [])
        p['settings']['gridMode'] = 'detected'
        if stage == 'smartgrid' and result.get('firstBeat') is not None:
            p['settings'].update(firstBeat=result['firstBeat'], beatsPerBar=result['beatsPerBar'])
        p['analysisNote'] = result.get('gridStatus', '')
    elif stage == 'structure':
        model.apply_sections(p, result['sections'])
    elif stage == 'key':
        p['key'] = result['key']
    elif stage in ('lyrics', 'chords'):
        entries = []
        for row in result['segments']:
            start, end = row.get('start', row.get('t', 0)), min(model.duration(p), row['end'])
            if end <= start:
                continue
            entry = dict(id=model.ident(), start=start, end=end,
                         text=row.get('text', row.get('label', '')), manual=False)
            if stage == 'lyrics':
                entry['words'] = [dict(start=w['t'], end=w['end'], text=w['w'])
                                  for w in row.get('words', []) if start <= w['t'] < w['end'] <= end + .1]
            entries.append(entry)
        p[stage] = sorted(entries, key=lambda x: x['start'])
    elif stage == 'guides':
        p['tracks'] = [t for t in p['tracks'] if not t['role'].startswith('guide_')]
        # Count-ins also need the individual spoken numbers and section-call assets.
        p['guideFiles'] = {
            key: copy_media(path, 'Guides', f'{index:03}.wav').relative_to(root).as_posix()
            for index, (key, path) in enumerate(result['files'].items())}
        for key, name, role in [('click', 'Métronome', 'guide_click'),
                                ('calls', 'Appels de régions', 'guide_voice'),
                                ('counts', 'Décomptes', 'guide_count')]:
            target = root / p['guideFiles'][key]
            p['tracks'].append(model.track(target, root, name, role))
        p['guideKey'] = model.guide_key(p)
    p['_queueID'] = item['id']
    p['_queueCompleted'] = list(dict.fromkeys([*p.get('_queueCompleted', []), stage]))
    model.save(p, root)
    return p
