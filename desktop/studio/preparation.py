"""Reviewed, portable handoff from the preparation workshop to REAPER."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import uuid

import soundfile as sf

from musical_timing import tempo_info
from platform_tools import executable
from services import atomic, export_reaper, reaper_filename, run


def media_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Média absent ou hors du projet : ' + str(relative))
    return path


def playback(p):
    saved = p.get('preparation') or {}
    rate = float(p.get('_rate', saved.get('rate', 1)))
    pitch = float(p.get('_pitch', saved.get('pitch', 0)))
    mode = p.get('_mode', saved.get('mode', 'mix'))
    if not math.isfinite(rate) or not .5 <= rate <= 1.5 or not math.isfinite(pitch) or not -12 <= pitch <= 12:
        raise ValueError('Vitesse ou transposition invalide.')
    from listening import parse_mode
    parse_mode(mode)
    return rate, pitch, mode


def fingerprint(p):
    root = Path(p['_root'])
    content = {k: p.get(k) for k in ('id', 'name', 'sections', 'cues', 'bpm', 'beats', 'settings',
                                    'lyrics', 'chords', 'drumHits', 'key', 'capo', 'notes', 'downbeats', 'gridLocked')}
    content['timingVersion']=1
    content['playback'] = playback(p)
    guide_mix = sorted((t['role'], bool(t.get('muted')), bool(t.get('solo'))) for t in p['tracks']
                       if t['role'].startswith('guide_') and (t.get('muted') or t.get('solo')))
    if guide_mix:content['guideMix'] = guide_mix
    content['tracks'] = []
    for track in p['tracks']:
        if track['role'].startswith('guide_'):
            continue
        stat = media_file(root, track['file']).stat()
        content['tracks'].append({**{k: v for k, v in track.items() if k != 'peaks'},
                                  'bytes': stat.st_size, 'modified': stat.st_mtime_ns})
    return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()


def review(p):
    """Technical checks accompany, but never replace, the musician's approval."""
    root = Path(p['_root'])
    rate, pitch, mode = playback(p)
    tracks = [t for t in p['tracks'] if not t['role'].startswith('guide_')]
    if not tracks:
        raise ValueError('Importe au moins une piste avant de valider le morceau.')
    for track in tracks:
        info = sf.info(media_file(root, track['file']))
        if info.frames <= 0 or abs(info.duration - track['duration']) > .1:
            raise ValueError('Le média a changé : ' + track['name'])
    duration = max(t['offset'] + t['duration'] for t in tracks)
    settings = p['settings']
    beats = p.get('beats', [])
    if settings['gridMode'] != 'fixed':
        if len(beats) < 2 or any(not math.isfinite(b) for b in beats) or any(b <= a for a, b in zip(beats, beats[1:])):
            raise ValueError('Détecte les temps ou choisis un tempo fixe dans Click & cues avant de valider.')
    bpm=tempo_info(p)['estimatedBPM']
    if not math.isfinite(bpm) or not 20 <= bpm <= 400:
        raise ValueError('Vérifie le tempo du morceau dans Click & cues.')
    end = 0
    for section in sorted(p.get('sections', []), key=lambda x: x['start']):
        if section['start'] < end - .000001 or section['end'] <= section['start'] or section['end'] > duration + .1:
            raise ValueError('Corrige les sections qui se chevauchent ou dépassent le morceau.')
        end = section['end']
    if any(not 0 <= c['time'] <= duration for c in p.get('cues', [])):
        raise ValueError('Un repère dépasse la durée du morceau.')
    if settings['exportGuides']:
        for name in ('click', 'calls', 'cues', 'counts'):
            relative = p.get('guideFiles', {}).get(name)
            if not relative:
                raise ValueError('Actualise les guides avant de valider le morceau.')
            media_file(root, relative)
    return dict(rate=rate, pitch=pitch, mode=mode, tracks=len(tracks), sections=len(p.get('sections', [])),
                cues=len(p.get('cues', [])), duration=duration / rate, bpm=bpm * rate)


def validate_project(snapshot, output):
    p = json.loads(Path(snapshot).read_text())
    summary = review(p)
    rate, pitch, mode = playback(p)
    approval = dict(rate=rate, pitch=pitch, mode=mode, fingerprint=fingerprint(p),
                    validatedAt=datetime.now(timezone.utc).isoformat())
    atomic(output, dict(preparation=approval, summary=summary))


def transpose(text, pitch):
    import re
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    semis = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
    def change(m):
        value = semis[m[2]] + {'#': 1, 'b': -1, '': 0}[m[3]] + round(pitch)
        return m[1] + names[value % 12]
    return re.sub(r'(^|/)([A-G])([#b]?)', change, text)


def transformed(p, folder, engine):
    """Render the chosen preparation once. All timeline coordinates use the same scale."""
    result = copy.deepcopy(p)
    root = Path(p['_root'])
    rate, pitch, _ = playback(p)
    # Imported media are already PCM WAV. Let the exporter copy them once,
    # byte for byte, instead of making an identical intermediate audio tree.
    media=[t['file'] for t in p['tracks']]+list(p.get('guideFiles',{}).values())
    if rate==1 and pitch==0 and all(Path(path).suffix.lower()=='.wav' for path in media):
        return result
    folder.mkdir(parents=True, exist_ok=True)
    converted = {}
    available = run([str(executable(engine, 'ffmpeg')), '-hide_banner', '-filters'])
    rubberband = b' rubberband ' in available
    def audio(relative, guide=False):
        key = (relative, guide)
        if key in converted:
            return converted[key]
        source = media_file(root, relative)
        name = str(uuid.uuid4()) + '.wav'
        target = folder / name
        semitones = 0 if guide else pitch
        if rate == 1 and semitones == 0 and source.suffix.lower() == '.wav':
            shutil.copy2(source, target)
        else:
            factor = 2 ** (semitones / 12)
            filters = []
            if rubberband:
                filters = [f'rubberband=tempo={rate:.12g}:pitch={factor:.12g}']
            else:
                # Some Windows FFmpeg distributions omit Rubber Band. This is also
                # the fallback used by the Windows preview, preserving pitch/time.
                if semitones:
                    filters = [f'asetrate={44100*factor:.12g}', 'aresample=44100']
                speed = rate / factor
                while speed > 2:
                    filters.append('atempo=2'); speed /= 2
                while speed < .5:
                    filters.append('atempo=0.5'); speed /= .5
                filters.append(f'atempo={speed:.12g}')
            run([str(executable(engine, 'ffmpeg')), '-nostdin', '-v', 'error', '-y', '-i', str(source),
                 '-af', ','.join(filters),
                 '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(target)])
        converted[key] = name
        return name
    for track in result['tracks']:
        track['file'] = audio(track['file'], track['role'].startswith('guide_'))
        track['duration'] = sf.info(folder / track['file']).duration
        track['offset'] /= rate
    result['guideFiles'] = {key: audio(value, True) for key, value in p.get('guideFiles', {}).items()}
    for collection in ('sections', 'lyrics', 'chords'):
        for item in result.get(collection, []):
            item['start'] /= rate
            item['end'] /= rate
            for word in item.get('words') or []:
                word['start'] /= rate
                word['end'] /= rate
            if collection == 'chords':
                item['text'] = transpose(item['text'], pitch)
    for collection in ('cues', 'drumHits'):
        for item in result.get(collection, []):
            item['time'] /= rate
    for key in ('beats', 'downbeats'):
        result[key] = [b / rate for b in result.get(key, [])]
    result['bpm'] *= rate
    result['settings']['manualBPM'] *= rate
    if result['settings'].get('referenceBPM'):result['settings']['referenceBPM'] *= rate
    result['settings']['firstBeat'] /= rate
    if result.get('sessionDuration'):result['sessionDuration']/=rate
    result.pop('timingGrid',None)
    result['key'] = transpose(result.get('key', ''), pitch)
    result['_root'] = str(folder)
    return result


def export_destination(root, name):
    """Do not repeat a long song title in every level of the export path."""
    unique=uuid.uuid4().hex
    dated='REAPER-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+unique[:6]
    for exports in (root/'Exports',root.parent/'Exports'):
        for folder in (dated,'R-'+unique[:10]):
            target=exports/folder
            try:return target,reaper_filename(name,target)
            except ValueError:continue
    raise ValueError('Chemin d’export trop long pour REAPER. Place le morceau dans un dossier plus court, puis relance l’export.')


def export_validated(snapshot, output, engine, *, preflight=False):
    p = json.loads(Path(snapshot).read_text())
    approval = p.get('preparation') or {}
    signature = fingerprint(p)
    if preflight:
        rate,pitch,mode=playback(p)
        # This is a technical check, never a claim of human listening approval.
        approval=dict(rate=rate,pitch=pitch,mode=mode,fingerprint=signature,
                      validatedAt=datetime.now(timezone.utc).isoformat(),kind='technical')
    if not approval.get('validatedAt') or approval.get('fingerprint') != signature:
        raise ValueError('Le morceau a changé ou n’a pas été validé. Ouvre Valider & envoyer avant l’export.')
    summary = review(p)
    target, filename = export_destination(Path(p['_root']),p['name'])
    target.parent.mkdir(exist_ok=True)
    # Keep intermediate audio paths short too, on the destination volume so
    # publishing the complete folder is atomic even for an external drive.
    with tempfile.TemporaryDirectory(prefix='.export-',dir=target.parent) as scratch:
        work = Path(scratch)
        scaled = transformed(p, work / 'PreparedAudio', engine)
        prepared = work / 'prepared.json'
        atomic(prepared, scaled)
        temporary = work / 'export-result.json'
        export_reaper(prepared, temporary, final_folder=target)
        info = json.loads(temporary.read_text())
        staged = Path(info['folder'])
        if fingerprint(p) != signature:
            raise ValueError('Un média a changé pendant l’export. Valide à nouveau le morceau.')
        atomic(staged / 'validation.json', dict(version=1, approval=approval, summary=summary))
        exported = Path(info['path'])
        if exported.name != filename:exported.rename(staged/filename)
        staged.rename(target)
    atomic(output, dict(path=str(target / filename), folder=str(target), summary=summary))
