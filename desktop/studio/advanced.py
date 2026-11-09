"""Local practice, delivery and analysis tools. Never uploads the user's audio."""
from __future__ import annotations
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import zipfile

from platform_tools import executable, creation_flags
from services import atomic, safe_name


def finite(value, low, high):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Valeur hors limites.')
    return value


def media_path(root, relative):
    root = Path(root).resolve()
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Chemin de média invalide.')
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Média manquant ou hors du projet.')
    return path


def musical_grid(beats, downbeats, duration):
    """Accept a bar phase only when several consecutive bars agree."""
    import numpy as np
    beats = np.unique(np.asarray(beats, dtype=float))
    beats = beats[np.isfinite(beats) & (beats >= 0) & (beats < duration)]
    downbeats = np.asarray(downbeats, dtype=float)
    downbeats = downbeats[np.isfinite(downbeats) & (downbeats >= 0) & (downbeats < duration)]
    indices = sorted(set(int(np.argmin(abs(beats - t))) for t in downbeats)) if len(beats) else []
    intervals = np.diff(indices)
    meter, agreement, first = 0, 0., None
    if len(intervals) >= 3:
        valid = intervals[(intervals >= 2) & (intervals <= 12)]
        if len(valid):
            meter = int(np.bincount(valid).argmax())
            phases = np.bincount(np.asarray(indices) % meter, minlength=meter)
            phase = int(phases.argmax())
            agreement = min(float(np.mean(intervals == meter)), float(phases[phase] / len(indices)))
            if agreement >= .85:
                first = float(beats[phase])
    delta = np.diff(beats)
    delta = delta[(delta > .15) & (delta < 3)]
    status='Mesures repérées · à vérifier à l’écoute' if first is not None else 'Pulsations repérées · premier temps ou signature à régler manuellement'
    if len(beats) and beats[0]>2:status+=f' · détection à partir de {beats[0]:.2f} s'
    return dict(beats=beats.tolist(), downbeats=beats[indices].tolist(),
                bpm=float(60 / np.median(delta)) if len(delta) else 0,
                beatsPerBar=meter, firstBeat=first, agreement=agreement,
                gridStatus=status)


def smart_grid(audio, engine):
    import soundfile as sf
    import torch
    from beat_this.inference import Audio2Beats
    checkpoint = Path(engine) / 'rhythm/final0.ckpt'
    if not checkpoint.is_file():
        raise ValueError('Le modèle Beat This n’est pas installé. Installe le composant Rythme avancé.')
    import hashlib
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331':
        raise ValueError('Modèle Beat This modifié ou incomplet.')
    torch.set_num_threads(4)
    if sf.info(audio).duration > 1800:
        raise ValueError('L’analyse rythmique avancée accepte un morceau de 30 minutes maximum.')
    signal, sr = sf.read(audio, dtype='float32', always_2d=True)
    predictor = Audio2Beats(checkpoint_path=str(checkpoint), device='cpu', dbn=False)
    with torch.inference_mode():
        beats, downbeats = predictor(signal.mean(axis=1), sr)
    return musical_grid(beats, downbeats, len(signal) / sr)


def detect_key(audio):
    import numpy as np
    import librosa
    import soundfile as sf
    # Sample across the complete song, bounding memory and the analysis cost.
    info = sf.info(audio)
    moments = np.linspace(0, max(0, info.duration - 20), min(12, max(1, math.ceil(info.duration / 20))))
    chroma = np.zeros(12)
    for start in moments:
        y, sr = librosa.load(audio, sr=22050, mono=True, offset=float(start), duration=20)
        if not len(y) or np.max(abs(y)) < 1e-7:
            continue
        harmonic = librosa.effects.harmonic(y)
        c = librosa.feature.chroma_stft(y=harmonic, sr=sr, n_fft=4096, hop_length=1024, tuning=None)
        chroma += c.sum(axis=1)
    if chroma.max() < 1e-7:
        raise ValueError('Pas assez de contenu harmonique pour proposer une tonalité.')
    profiles = [('major', [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]),
                ('minor', [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])]
    names = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
    scores = []
    for mode, profile in profiles:
        for tonic in range(12):
            score = float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1])
            scores.append(dict(key=names[tonic] + ('m' if mode == 'minor' else ''), score=score))
    scores.sort(key=lambda x: x['score'], reverse=True)
    return dict(key=scores[0]['key'], alternatives=scores[:3],
                note='Estimation harmonique globale ; vérifier les modulations et la tonalité relative.')


def parse_lyrics(text, duration):
    if len(text) > 2_000_000:
        raise ValueError('Le fichier de paroles est trop volumineux.')
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    def stamp(s):
        parts = s.replace(',', '.').split(':')
        return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))
    entries = []
    if '-->' in text:
        for block in re.split(r'\n\s*\n', text):
            rows = block.strip().splitlines()
            match = next((i for i, row in enumerate(rows) if '-->' in row), None)
            if match is None:
                continue
            a, b = rows[match].split('-->', 1)
            entries.append((stamp(a.strip()), stamp(b.strip().split()[0]), '\n'.join(rows[match+1:]).strip()))
    else:
        offset = re.search(r'\[offset:([+-]?\d+)\]', text, re.I)
        offset = int(offset[1]) / 1000 if offset else 0
        lines = []
        for row in text.splitlines():
            times = re.findall(r'\[(\d+:\d+(?:\.\d+)?)\]', row)
            content = re.sub(r'\[[^\]]*\]', '', row).strip()
            for t in times:
                if content:
                    lines.append((max(0, stamp(t) + offset), content))
        lines.sort()
        entries = [(a, lines[i+1][0] if i+1 < len(lines) else duration, content) for i, (a, content) in enumerate(lines)]
    result = []
    for a, b, content in entries:
        a, b = max(0, a), min(duration, b)
        if content and math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= duration:
            result.append(dict(id=str(uuid.uuid4()), start=a, end=b, text=content[:1000], manual=True))
    if not result:
        raise ValueError('Aucune ligne synchronisée valide. Utilise un fichier LRC ou SRT avec ses horaires.')
    return sorted(result, key=lambda x: x['start'])


def lyric_file(project, target, fmt):
    entries = sorted(project.get('lyrics', []), key=lambda x: x['start'])
    if not entries:
        raise ValueError('Le projet ne contient pas encore de paroles.')
    def srt_stamp(t):
        ms = round(t * 1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    if fmt == 'srt':
        text = '\n\n'.join(f'{i+1}\n{srt_stamp(x["start"])} --> {srt_stamp(x["end"])}\n{x["text"]}' for i, x in enumerate(entries)) + '\n'
    elif fmt == 'lrc':
        text = '\n'.join(f'[{int(round(x["start"]*100))//6000:02}:{int(round(x["start"]*100))//100%60:02}.{int(round(x["start"]*100))%100:02}]'+x['text'].replace('\n', ' ') for x in entries) + '\n'
    else:
        raise ValueError('Format de paroles inconnu.')
    target.write_text(text, encoding='utf-8')


def ffmpeg(engine, arguments):
    result = subprocess.run([str(executable(engine, 'ffmpeg')), '-nostdin', '-hide_banner', '-y', *map(str, arguments)],
                            capture_output=True, creationflags=creation_flags(), timeout=3600)
    if result.returncode:
        raise ValueError('Traitement audio impossible : ' + result.stderr.decode(errors='replace')[-1200:])
    return result.stderr.decode(errors='replace')


def encode_audio(source, target, engine, fmt):
    codecs = {'wav':['-c:a','pcm_s24le'], 'flac':['-c:a','flac'], 'mp3':['-c:a','libmp3lame','-b:a','320k'], 'm4a':['-c:a','aac','-b:a','256k']}
    if fmt not in codecs:
        raise ValueError('Format audio inconnu.')
    ffmpeg(engine, ['-v','error','-i',source,*codecs[fmt],target])


def loudness(audio, engine, level=-16, peak=-1, spread=11):
    log = ffmpeg(engine, ['-i',audio,'-af',f'loudnorm=I={level}:TP={peak}:LRA={spread}:print_format=json','-f','null','-'])
    match = re.search(r'\{\s*"input_i".*?\}', log, re.S)
    if not match:
        raise ValueError('Impossible de mesurer le niveau sonore.')
    result = json.loads(match[0])
    if not all(math.isfinite(float(result[k])) for k in ('input_i','input_tp','input_lra','input_thresh')):
        raise ValueError('Audio silencieux ou trop court pour mesurer son niveau sonore.')
    return result


def mastering_filters(options):
    low=finite(options.get('lowDB',0),-12,12)
    mid=finite(options.get('midDB',0),-12,12)
    high=finite(options.get('highDB',0),-12,12)
    width=finite(options.get('width',1),0,1.5)
    threshold=finite(options.get('compressDB',-18),-40,-3)
    ratio=finite(options.get('ratio',1),1,6)
    attack=finite(options.get('attackMS',20),1,100)
    release=finite(options.get('releaseMS',150),20,1000)
    filters=[]
    if low:filters.append(f'bass=g={low}:f=120:t=q:w=.707')
    if mid:filters.append(f'equalizer=f=1500:t=q:w=.7:g={mid}')
    if high:filters.append(f'treble=g={high}:f=6000:t=q:w=.707')
    if ratio>1:filters.append(f'acompressor=threshold={10**(threshold/20)}:ratio={ratio}:attack={attack}:release={release}:makeup=1:knee=2.828:link=maximum:detection=rms')
    if width!=1:
        # Mid/side width: 0 mono, 1 original; normalization follows this stage.
        a,b=(1+width)/2,(1-width)/2
        filters.append(f'pan=stereo|c0={a}*c0+{b}*c1|c1={b}*c0+{a}*c1')
    return filters,dict(lowDB=low,midDB=mid,highDB=high,width=width,compressDB=threshold,ratio=ratio,attackMS=attack,releaseMS=release)


def master(audio, target, engine, options):
    level=finite(options.get('lufs',-16),-24,-9)
    peak=finite(options.get('peak',-1),-3,-.3)
    spread=finite(options.get('lra',11),5,20)
    filters,chain=mastering_filters(options)
    before=loudness(audio,engine,level,peak,spread)
    processed=Path(target).with_name('.master-processing-'+uuid.uuid4().hex+'.wav')
    try:
        source=audio
        if filters:
            ffmpeg(engine,['-i',audio,'-af',','.join(filters),'-c:a','pcm_f32le',processed]);source=processed
        measured=loudness(source,engine,level,peak,spread)
        filt=f'loudnorm=I={level}:TP={peak}:LRA={spread}:measured_I={measured["input_i"]}:measured_TP={measured["input_tp"]}:measured_LRA={measured["input_lra"]}:measured_thresh={measured["input_thresh"]}:offset={measured["target_offset"]}:linear=true:print_format=json'
        ffmpeg(engine,['-i',source,'-af',filt,'-ar','48000','-c:a','pcm_s24le',target])
        after=loudness(target,engine)
        return dict(before=before,after=after,targetLUFS=level,ceilingDBTP=peak,chain=chain,afterProcessing=measured)
    finally:
        processed.unlink(missing_ok=True)


def practice_sheet(p, target, options):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from phone import transpose
    font=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
    pdfmetrics.registerFont(TTFont('Studio',str(font)))
    styles=getSampleStyleSheet()
    for style in styles.byName.values():style.fontName='Studio'
    styles.add(ParagraphStyle('cell',fontName='Studio',fontSize=9,leading=13))
    def para(text,style='cell'):return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[style])
    def stamp(t):return f'{int(t)//60}:{t%60:05.2f}'
    body=[para('BANDSTUDIO · FICHE DE RÉPÉTITION','Heading3'),para(p['name'],'Title')]
    shift=int(finite(options.get('pitch',0),-12,12));capo=p.get('capo',0)
    body+=[para(f'Tempo source : {p.get("bpm",0):.1f} BPM · Tonalité entendue : {transpose(p.get("key", "—"),shift)} · Capo : {capo}'),
           para('Les accords ci-dessous tiennent compte de la transposition et du capo. Les horaires restent ceux du morceau original.'),Spacer(1,15)]
    def table(title,headers,rows,widths):
        if not rows:return
        body.append(para(title,'Heading2'))
        grid=Table([[para(x) for x in headers]]+[[para(x) for x in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        grid.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8ecf4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#ccd4df'))]))
        body.extend([grid,Spacer(1,12)])
    table('Structure',['Début','Fin','Passage'],[(stamp(s['start']),stamp(s['end']),s['name']) for s in p.get('sections',[])],[65,65,377])
    table('Repères de jeu',['Position','Consigne'],[(stamp(c['time']),c.get('callText') or c['name']) for c in p.get('cues',[])],[80,427])
    table('Accords',['Début','Fin','Accord affiché'],[(stamp(c['start']),stamp(c['end']),transpose(c['text'],shift-capo)) for c in p.get('chords',[])],[65,65,377])
    table('Paroles',['Début','Texte'],[(stamp(l['start']),l['text']) for l in p.get('lyrics',[])],[65,442])
    if p.get('notes'):body.extend([para('Notes','Heading2'),para(p['notes'])])
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Studio',8);canvas.drawString(44,26,'BandStudio · '+p['name'][:65]);canvas.drawRightString(A4[0]-44,26,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=44,bottomMargin=45,title=p['name'],author='BandStudio').build(body,onFirstPage=footer,onLaterPages=footer)


def audio_report(audio):
    import numpy as np
    import soundfile as sf
    peak, square, clipped, count, total = 0., 0., 0, 0, 0.
    for block in sf.blocks(audio, blocksize=65536, dtype='float32', always_2d=True):
        if not np.isfinite(block).all():
            raise ValueError('Le fichier contient des échantillons audio non valides.')
        peak = max(peak, float(np.max(abs(block), initial=0)))
        square += float(np.square(block.astype('float64')).sum())
        total += float(block.sum(dtype='float64'))
        clipped += int(np.count_nonzero(abs(block) >= .999))
        count += block.size
    db = lambda x: round(20 * math.log10(max(x, 1e-10)), 2)
    rms = math.sqrt(square / max(count, 1))
    return dict(duration=sf.info(audio).duration, peakDBFS=db(peak), rmsDBFS=db(rms),
                crestDB=round(db(peak)-db(rms), 2), nearFullScalePercent=round(clipped/max(count,1)*100, 4),
                dcOffset=round(total/max(count,1), 6))


def portable_project(p, root, target):
    data = {k:v for k,v in p.items() if not k.startswith('_')}
    files = {t['file'] for t in p['tracks']} | set(p.get('guideFiles', {}).values())
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        prefix = safe_name(p['name']) + '.bandstudio/'
        archive.writestr(prefix+'project.json', json.dumps(data, ensure_ascii=False, indent=2))
        for relative in sorted(files):
            archive.write(media_path(root, relative), prefix+Path(relative).as_posix())
        archive.writestr('LIRE-MOI.txt', 'Décompresse le dossier .bandstudio, puis ouvre-le dans BandStudio.\nLes médias et les réglages sont inclus.\n')


def run(kind, project_file, output, engine, options, audio=''):
    p = json.loads(Path(project_file).read_text())
    root = Path(p['_root']).resolve()
    length = max((t['duration']+t['offset'] for t in p['tracks'] if not t['role'].startswith('guide_')), default=0)
    if kind == 'smartgrid':
        result = smart_grid(audio, engine)
    elif kind == 'key':
        result = detect_key(audio)
    elif kind == 'lyricsimport':
        result = dict(entries=parse_lyrics(options.get('text',''), length))
    else:
        folder = root / 'Exports' / (kind+'-'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        name = safe_name(p['name'])
        if kind == 'reaperextension':
            target=folder/'BandStudio_Remote.lua';shutil.copy2(Path(engine)/'BandStudio_Remote.lua',target)
            (folder/'LIRE-MOI.txt').write_text('Dans REAPER : Actions > Nouvelle action > Charger un ReaScript, choisir BandStudio_Remote.lua. Ouvrir BandStudio > Prises > Relier BandPilot. La télécommande pilote BandStudio ; elle ne synchronise pas les horloges audio et ne modifie pas les pistes REAPER. Ce composant est un ReaScript, pas un VST/AU.\n',encoding='utf-8')
        elif kind == 'lyricsexport':
            fmt = options.get('format','srt')
            target = folder / (name+'.'+ ('lrc' if fmt == 'lrc' else 'srt'))
            lyric_file(p, target, fmt)
        elif kind == 'stemsexport':
            fmt = options.get('format','wav')
            if fmt not in ('wav','flac','mp3','m4a'):
                raise ValueError('Format inconnu.')
            tracks = [t for t in p['tracks'] if not t['role'].startswith('guide_') and t['role'] != 'source']
            if not tracks:
                raise ValueError('Sépare les instruments avant d’exporter les stems.')
            manifest = []
            for i, t in enumerate(tracks):
                dest = folder / (f'{i+1:02}-'+safe_name(t['name'])+'.'+fmt)
                encode_audio(media_path(root,t['file']), dest, engine, fmt)
                manifest.append(dict(file=dest.name, name=t['name'], role=t['role'], offset=t['offset'], gain=t['gain'], pan=t['pan']))
            atomic(folder/'pistes.json', dict(tracks=manifest, bpm=p['bpm'], note='Audio brut, tempo et hauteur d’origine. Les départs sont indiqués dans offset.'))
            target = folder
        elif kind == 'master':
            # The host supplies an offline render of the music mix, without spoken guides.
            target = folder/(name+' - niveau final.wav')
            report = master(audio, target, engine, options)
            atomic(folder/'mesures.json', report)
        elif kind == 'report':
            rows = []
            for t in p['tracks']:
                if t['role'].startswith('guide_') or (options.get('trackID') and t['id'] != options['trackID']):
                    continue
                rows.append(dict(id=t['id'], name=t['name'], role=t['role'], **audio_report(media_path(root,t['file']))))
            if not rows:
                raise ValueError('Aucune piste à analyser.')
            atomic(folder/'analyse.json', dict(schema='bandstudio.audio-analysis.v1', project=p['name'], tracks=rows))
            target = folder/(name+' - analyse.html')
            body = ''.join('<tr><td>'+html.escape(r['name'])+'</td>'+''.join('<td>'+str(r[k])+'</td>' for k in ('peakDBFS','rmsDBFS','crestDB','nearFullScalePercent'))+'</tr>' for r in rows)
            target.write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Analyse audio</title><style>body{font:16px system-ui;max-width:1000px;margin:50px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ccc;text-align:left}</style><h1>'+html.escape(p['name'])+'</h1><h2>Analyse des niveaux</h2><table><tr><th>Piste</th><th>Crête dBFS</th><th>RMS dBFS</th><th>Dynamique crête/RMS</th><th>Échantillons proches de 0 dBFS (%)</th></tr>'+body+'</table><p>Une crête proche de 0 dBFS invite à vérifier le gain d’entrée. Elle ne prouve pas à elle seule une saturation. Le RMS dépend du contenu et ne remplace pas les LUFS.</p><p>Ce rapport ne règle pas la console XR. Écoute les prises avant toute correction de gain, d’égalisation ou de compression.</p></html>', encoding='utf-8')
        elif kind == 'portable':
            target = folder/(name+'.zip')
            portable_project(p, root, target)
        elif kind == 'sheet':
            target = folder/(name+' - fiche.pdf')
            practice_sheet(p,target,options)
        else:
            raise ValueError('Outil inconnu.')
        result = dict(path=str(target))
    atomic(output, result)
