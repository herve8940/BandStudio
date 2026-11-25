"""Portable concert media shared by Live, QLab and grandMA3."""
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid

import numpy as np
import soundfile as sf

from catalog import member
from musical_timing import tempo_envelope
from preparation import fingerprint, media_file, playback, review, transformed
from services import arrangement_items, atomic, count_plan, decode, guides, portable_project_stem, safe_name
from ui_language import ui_text
from windows.project import GUIDE_DEFAULTS, guide_key, guide_track

# The frame before the music is already running when the first light cue fires.
LOCK_IN = 2
RATE = 44100


def smpte(frames, fps):
    seconds, frame = divmod(frames, fps)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f'{hour:02}:{minute:02}:{second:02}:{frame:02}'


def time_addresses(db, songs):
    """Keep a title's address across all selections and setlists in the library."""
    changed = {}
    db.execute('BEGIN IMMEDIATE')
    db.execute('CREATE TABLE IF NOT EXISTS ranges (song TEXT PRIMARY KEY, start INTEGER, span INTEGER)')
    saved = {key: (start, span) for key, start, span in db.execute('SELECT song,start,span FROM ranges')}
    for song in songs:
        key = song['id']
        required = math.ceil(song['duration']) + LOCK_IN + 1
        previous = saved.get(key)
        end_of_ranges = max([3600] + [a+b for a,b in saved.values()])
        start = previous[0] if previous else end_of_ranges
        limit = min([86400] + [a for a,b in saved.values() if a > start])
        if previous and start + required > limit:
            start, limit = end_of_ranges, 86400
            changed[key] = previous[0]
        if start + required > limit:
            raise ValueError(ui_text('Les plages disponibles dépassent 24 heures de timecode.', 'The available timecode ranges exceed 24 hours.'))
        span = min(limit-start, max(previous[1] if previous else 0, math.ceil((required+30)/60)*60))
        saved[key] = start, span
        db.execute('INSERT OR REPLACE INTO ranges VALUES (?,?,?)', (key,start,span))
    return {key: start for key,(start, span) in saved.items()}, changed


def stage_project(p, work):
    """Regenerate missing/stale guides in a private directory during a batch export."""
    root = Path(p['_root'])
    settings = p['settings']
    required = settings['exportGuides'] or settings['exportCount']
    old_tracks = p['tracks']
    instruments = [t for t in old_tracks if not t['role'].startswith('guide_')]
    if not required:
        return dict(p, tracks=instruments, guideFiles={})
    files = p.get('guideFiles', {})
    key = p.get('guideKey') or ''
    approved = (p.get('preparation') or {}).get('fingerprint')
    fresh = (p.get('_guidesReady') is True or (key.startswith('windows-guides-') and key == guide_key(p))
             or (bool(key) and approved and approved == fingerprint(p)))
    if fresh and all(k in files for k in ('click','calls','counts','cues')):
        saved = list(files.values()) + [t['file'] for t in old_tracks if t['role'].startswith('guide_')]
        if all((root / path).is_file() for path in saved):
            for path in saved:
                media_file(root, path)
            return p
    project = dict(p, tracks=[], guideFiles={}, _root=str(work))
    for index, track in enumerate(old_tracks):
        if track['role'].startswith('guide_'):
            continue
        source = media_file(root, track['file'])
        filename = f'source-{index}{source.suffix}'
        try:
            os.link(source, work / filename)
        except OSError:
            shutil.copy2(source, work / filename)
        project['tracks'].append(dict(track, file=filename))
    snapshot, output = work / 'snapshot.json', work / 'guides.json'
    atomic(snapshot, project)
    include_announcements = settings['exportGuides'] and (settings['callsEnabled'] or settings['speakCues'])
    guides(snapshot, output, include_announcements=include_announcements)
    generated = json.loads(output.read_text(encoding='utf-8'))
    project['guideFiles'] = {key: Path(path).relative_to(work).as_posix() for key,path in generated['files'].items()}
    for key, name, role in [('click','Click','guide_click'), ('calls',ui_text('Annonces','Calls'),'guide_voice'),
                            ('cues',ui_text('Repères','Cues'),'guide_cue'), ('counts',ui_text('Décompte','Count-in'),'guide_count')]:
        path = work / project['guideFiles'][key]
        project['tracks'].append(guide_track(path, work, name, role, old_tracks))
    if not project.get('gridLocked') and generated.get('firstBeatCorrection') is not None:
        project['settings'] = dict(project['settings'], firstBeat=generated['firstBeatCorrection'])
    project['timingGrid'] = generated.get('timingGrid')
    return project


def project_list(current, options, library):
    paths = options.get('paths')
    if paths is None:
        paths = [current.get('_root')]
    if not isinstance(paths, list) or not paths or any(not isinstance(path,str) or not path for path in paths):
        raise ValueError(ui_text('Sélectionne au moins un morceau.', 'Select at least one song.'))
    projects = []
    for path in paths:
        root = Path(path).resolve()
        if current.get('_root') and root == Path(current['_root']).resolve():
            p = dict(current)
        else:
            root = member(library, path)
            p = json.loads((root / 'project.json').read_text(encoding='utf-8'))
        p['_root'] = str(root)
        p['settings'] = {**GUIDE_DEFAULTS, **p['settings']}
        p['_rate'], p['_pitch'], p['_mode'] = playback(p)
        projects.append(p)
    return projects


def cut_media(source, destination, skip, length, scratch, engine, concert):
    info = sf.info(source)
    if concert and (info.samplerate != RATE or info.channels not in (1,2)):
        converted = scratch / 'normalized.wav'
        decode(source, converted, engine)
        source = converted
    with sf.SoundFile(source) as audio:
        offset = min(len(audio), round(skip * audio.samplerate))
        remaining = min(len(audio) - offset, round(length * audio.samplerate))
        if remaining <= 0:
            return False
        audio.seek(offset)
        with sf.SoundFile(destination, 'w', audio.samplerate, audio.channels, subtype='FLOAT') as out:
            while remaining:
                block = audio.read(min(65536, remaining), dtype='float32', always_2d=True)
                if len(block) == 0:
                    raise ValueError(ui_text('Fin de fichier audio inattendue.', 'Unexpected end of audio file.'))
                out.write(block)
                remaining -= len(block)
    return True


def prepare_song(p, folder, work, engine, concert):
    for track in p['tracks']:
        if not track['role'].startswith('guide_'):
            media_file(Path(p['_root']), track['file'])
    signature = fingerprint(p)
    prepared = stage_project(p, work)
    review(prepared)
    scaled = transformed(prepared, work / 'transformed', engine)
    plan = count_plan(scaled)
    lead = plan['lead'] if scaled['settings']['exportCount'] else 0
    media = folder / ('audio' if concert else 'Samples/Imported')
    media.mkdir(parents=True)
    items = []
    for index, item in enumerate(arrangement_items(scaled, work, plan, lead), 1):
        filename = f'{index:03}-{safe_name(item["name"])[:45]}.wav'
        dest = media / filename
        if cut_media(item['path'], dest, item['skip'], item['length'], work, engine, concert):
            items.append({**{k:item[k] for k in ('name','role','position','gain','pan','muted')},
                          'file':dest.relative_to(folder).as_posix(), 'length':sf.info(dest).duration})
    markers = [dict(name=s['name'],time=s['start']+lead,kind='section') for s in scaled['sections']]
    markers.extend(dict(name=c['name'],time=c['time']+lead,kind='cue') for c in scaled['cues'])
    markers.sort(key=lambda m:m['time'])
    duration = max([lead + max((t['offset'] + t['duration'] for t in scaled['tracks']),default=0)] +
                   [i['position'] + i['length'] for i in items])
    if fingerprint(p) != signature:
        raise ValueError(ui_text('Média modifié pendant l’export.', 'Media changed during export.'))
    return dict(id=p['id'],name=p['name'],items=items,markers=markers,duration=duration,
                tempo=tempo_envelope(scaled,lead),lead=lead,lyrics=scaled.get('lyrics',[]),chords=scaled.get('chords',[]))


def stereo_gains(item):
    # Stereo balance: the centre leaves both channels at unity.
    pan = item['pan']
    return np.array([min(1,1-pan), min(1,1+pan)], dtype='float32') * item['gain']


def prepare_console_audio(folder, song, mode):
    """Print console stems with their mix settings, keeping monitor buses isolated."""
    front = []
    for item in song['items']:
        path = folder / item['file']
        gains = stereo_gains(item) * (.85 if not item['role'].startswith('guide_') else 1)
        with sf.SoundFile(path) as src, sf.SoundFile(path.with_suffix('.part.wav'), 'w', RATE, 2, subtype='FLOAT') as dst:
            for block in src.blocks(blocksize=65536, dtype='float32', always_2d=True):
                dst.write(block * gains)
        path.with_suffix('.part.wav').replace(path)
        if not item['role'].startswith('guide_') and not item['muted']:
            front.append(item)
    if mode == 'stems':
        return
    from contextlib import ExitStack
    with ExitStack() as stack:
        sources = [(round(i['position']*RATE), stack.enter_context(sf.SoundFile(folder/i['file']))) for i in front]
        length = math.ceil(song['duration']*RATE)
        with sf.SoundFile(folder/'audio'/'FOH.wav','w',RATE,2,subtype='FLOAT') as dst:
            for pos in range(0,length,65536):
                block = np.zeros((min(65536,length-pos),2),np.float32)
                for offset, audio in sources:
                    begin = max(pos, offset)
                    stop = min(pos+len(block),offset+len(audio))
                    if stop > begin:
                        block[begin-pos:stop-pos] += audio.read(stop-begin, dtype='float32', always_2d=True)
                dst.write(block)
    song['mix'] = 'audio/FOH.wav'
    if mode == 'mix':
        for item in song['items']:
            if not item['role'].startswith('guide_'):
                (folder/item['file']).unlink()
        song['items'] = [i for i in song['items'] if i['role'].startswith('guide_')]


def export_show(snapshot, output, engine, options):
    from live_set import write_live_set
    from show_control import write_control
    current = json.loads(Path(snapshot).read_text(encoding='utf-8'))
    library = Path(current['_library']).resolve()
    kind = options.get('kind')
    concert = kind == 'regie'
    fps = options.get('fps',25)
    sound, layout = options.get('sound','both'), options.get('layout','both')
    if kind not in ('live','regie') or fps not in (24,25,30) or sound not in ('stems','mix','both') or layout not in ('songs','concert','both'):
        raise ValueError(ui_text('Options d’export invalides.', 'Invalid export options.'))
    projects = project_list(current, options, library)
    destination = library/'Exports'
    destination.mkdir(exist_ok=True)
    name = safe_name(options.get('name') or projects[0]['name'])[:54]
    prefix = 'Regie' if concert else 'Live'
    target = destination / f'{prefix}-{name}-{uuid.uuid4().hex[:10]}'
    with tempfile.TemporaryDirectory(dir=destination, prefix='.stage-') as stage:
        stage = Path(stage)
        bundle = stage/'bundle'
        bundle.mkdir()
        songs, order = {}, []
        for number,p in enumerate(projects,1):
            key = p['id']
            order.append(key)
            if key in songs:
                if songs[key]['root'] != p['_root']:
                    raise ValueError(ui_text('Deux projets partagent le même identifiant.', 'Two projects have the same identifier.'))
                continue
            dirname = f'{number:02}-{safe_name(p["name"])[:42]}'
            folder = bundle/dirname if concert or len(projects)>1 else bundle
            with tempfile.TemporaryDirectory(dir=stage) as work:
                try:
                    song = prepare_song(p, folder, Path(work), engine, concert)
                except (ValueError,OSError,RuntimeError) as exc:
                    raise ValueError(f'{p["name"]} — {exc}') from exc
            song.update(directory=folder.relative_to(bundle).as_posix(),root=p['_root'])
            songs[key] = song
            if concert:
                prepare_console_audio(folder,song,sound)
            else:
                write_live_set(folder, portable_project_stem(p['name'])[:54].rstrip(' .')+'.als', song['items'],song['markers'],song['tempo'],song['duration'])
        if concert:
            with sqlite3.connect(library/'show-timecode.sqlite3',timeout=20) as db:
                addresses, changed = time_addresses(db,songs.values())
                write_control(bundle,name,songs,order,addresses,fps,layout,changed)
                bundle.rename(target)
        else:
            bundle.rename(target)
    atomic(output,dict(path=str(target),folder=str(target)))
