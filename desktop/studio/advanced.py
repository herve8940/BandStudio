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


def smart_grid(audio, engine, notify=lambda info: None, project=None):
    from analysis_cache import AnalysisCache
    cache=AnalysisCache.create(project,'rhythm',audio,engine)
    cached=cache.load() if cache else None
    if cached is not None:
        notify(dict(cacheHit=True))
        return {**cached,'cacheHit':True}
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
    from compute import run
    def inference(info):
        predictor = Audio2Beats(checkpoint_path=str(checkpoint), device=info['device'], dbn=False)
        with torch.inference_mode():
            return predictor(signal.mean(axis=1), sr)
    (beats, downbeats), _ = run(torch,'smartgrid',inference,notify=notify)
    result=musical_grid(beats, downbeats, len(signal) / sr)
    if cache:cache.store(result)
    return {**result,'cacheHit':False}


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


def practice_grid(p, options=None):
    """Read-only score layout, using the same beat origin as the editable song sheet."""
    import bisect
    from phone import transpose
    options = options or {}
    settings = p.get('settings') or {}
    meter = int(settings.get('beatsPerBar', 4))
    bpm = settings.get('manualBPM', 120) if settings.get('gridMode') == 'fixed' else p.get('bpm') or settings.get('manualBPM', 120)
    duration = max(p.get('sessionDuration', 0), max((t.get('offset', 0)+t['duration'] for t in p.get('tracks', []) if not t.get('role', '').startswith('guide_')), default=0))
    if duration <= 0:
        duration = max((x.get('end', 0) for kind in ('sections', 'lyrics', 'chords') for x in p.get(kind, [])), default=0)
    if not 1 <= meter <= 12 or not 20 <= bpm <= 400 or duration <= 0:
        raise ValueError('Le morceau doit avoir une durée, un tempo et une mesure valides.')
    beats = sorted({float(t) for t in p.get('beats', []) if math.isfinite(t) and 0 <= t <= duration})
    detected = settings.get('gridMode', 'detected') != 'fixed' and len(beats) > 1
    first = float(settings.get('firstBeat', 0))
    anchor = min(range(len(beats)), key=lambda i: abs(beats[i]-first)) if detected else 0
    anchor %= meter  # Match the editor and the metronome when a later downbeat was calibrated.
    origin = beats[anchor] if detected else first

    def at(value):
        if not detected:
            return origin+value*60/bpm
        index = value+anchor
        lower = max(0, min(len(beats)-2, math.floor(index)))
        return beats[lower]+(index-lower)*(beats[lower+1]-beats[lower])

    def coordinate(t):
        if not detected:
            return (t-origin)*bpm/60
        i = max(0, min(len(beats)-2, bisect.bisect_right(beats, t)-1))
        return i-anchor+(t-beats[i])/(beats[i+1]-beats[i])

    shift = int(finite(options.get('pitch', 0), -12, 12))
    capo = int(p.get('capo', 0))

    def chord_name(text):
        # Display musical symbols rather than the analysis model's colon notation.
        text = str(text).strip()
        if text.upper() in ('N', 'NC', 'N.C.', 'NO_CHORD'):
            return 'N.C.'
        text = re.sub(r':min(?=$|[^a-z])', 'm', text)
        text = re.sub(r':maj(?=$|/|\s)', '', text)
        text = re.sub(r':maj(?=\d)', 'maj', text)
        text = re.sub(r':(dim|aug|sus|add|\d)', r'\1', text)
        return transpose(text, shift-capo)

    bars = []
    if origin > 1e-7:
        bars.append(dict(number=0, start=0, end=min(origin, duration)))
    n = max(0, math.floor(coordinate(0)/meter))
    while at(n*meter) < duration-1e-7:
        start, end = max(0, at(n*meter)), min(duration, at((n+1)*meter))
        if end > start+1e-7:
            bars.append(dict(number=n+1, start=start, end=end))
        n += 1
        if len(bars) > 30000:
            raise ValueError('La grille contient trop de mesures.')

    groups, end = [], 0
    for s in sorted(p.get('sections', []), key=lambda x: x['start']):
        a, b = max(end, s['start'], 0), min(duration, s['end'])
        if a > end+1e-7:
            groups.append(dict(name='Sans section', start=end, end=a))
        if b > a+1e-7:
            groups.append(dict(name=s['name'], start=a, end=b))
            end = b
    if end < duration-1e-7:
        groups.append(dict(name='Sans section' if groups else 'Le morceau', start=end, end=duration))

    chords = sorted(p.get('chords', []), key=lambda x: x['start'])
    lyrics = []
    for line in p.get('lyrics', []):
        words = line.get('words') or []
        if words:
            lyrics.extend(dict(start=w['start'], text=w['text']) for w in words)
        elif line.get('text'):
            # Without word timings, keep the complete line at its known start.
            lyrics.append(dict(start=line['start'], text=line['text']))
    lyrics.sort(key=lambda x: x['start'])
    for group in groups:
        cells = []
        for bar in bars:
            a, b = max(bar['start'], group['start']), min(bar['end'], group['end'])
            if b <= a+1e-7:
                continue
            names = []
            for chord in chords:
                if chord['start'] < b-1e-7 and chord['end'] > a+1e-7:
                    name = chord_name(chord['text'])
                    if name and (not names or names[-1] != name):
                        names.append(name)
            # A word belongs to its starting measure, so a held word is never printed twice.
            text = ' '.join(x['text'] for x in lyrics if a <= x['start'] < b)
            text = re.sub(r'\s+([,.;!?])', r'\1', text)
            cues = [c.get('callText') or c.get('name', '') for c in p.get('cues', []) if a <= c['time'] < b]
            cells.append(dict(number=bar['number'], start=a, end=b, chords=names, lyrics=text,
                              cues=cues, partial=a > bar['start']+1e-7 or b < bar['end']-1e-7,
                              continuation=a > bar['start']+1e-7))
        group['cells'] = cells
    return dict(groups=groups, bpm=bpm, meter=meter, key=transpose(p.get('key') or '?', shift),
                capo=capo, shift=shift, has_lyrics=bool(lyrics), duration=duration)


def practice_sheet(p, target, options):
    """An album-led rehearsal chart, with numbered measures and editable song data."""
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Flowable
    data = practice_grid(p, options)
    fonts = Path(reportlab.__file__).parent/'fonts'
    pdfmetrics.registerFont(TTFont('Studio', str(fonts/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('StudioBold', str(fonts/'VeraBd.ttf')))
    width = A4[0]-76-12  # The document frame includes 6 pt padding on each side.
    ink = colors.HexColor('#223D31')
    line = colors.HexColor('#A6B4A1')
    quiet = colors.HexColor('#7B8676')
    peach = colors.HexColor('#FCF4EA')
    red = '#A14D3E'
    muted = colors.HexColor('#E6E9E1')
    # Album metadata stays with the song. No network access is needed to export.
    from artwork import guesses, read as read_artwork
    title, artist = guesses(p.get('name', 'Morceau'))[0]
    album, cover_image = '', None
    root = Path(p['_root']) if p.get('_root') else None
    if root:
        art = read_artwork(root)
        if art.get('title') and art['title'] != p.get('name'):
            title = str(art['title'])
        artist = str(art.get('artist') or artist)
        album = str(art.get('album') or '')
        cover_path = root/'Artwork.jpg'
        try:
            if cover_path.is_file() and not cover_path.is_symlink() and cover_path.stat().st_size <= 512_000:
                cover_image = ImageReader(str(cover_path))
                cover_image.getRGBData()  # Decode now, so a damaged cover falls back cleanly.
        except (OSError, ValueError):
            cover_image = None
    styles = {
        'title': ParagraphStyle('GridTitle', fontName='StudioBold', fontSize=30, leading=33, textColor=ink),
        'meta': ParagraphStyle('GridMeta', fontName='Studio', fontSize=9, leading=13),
        'key': ParagraphStyle('GridKey', fontName='Studio', fontSize=13, leading=17, alignment=1, spaceBefore=8, spaceAfter=14),
        'section': ParagraphStyle('GridSection', fontName='StudioBold', fontSize=10, leading=14, textColor=ink, keepWithNext=True),
        'chord': ParagraphStyle('GridChord', fontName='StudioBold', fontSize=10, leading=12, textColor=ink, alignment=1),
        'body': ParagraphStyle('GridBody', fontName='Studio', fontSize=8.5, leading=11, alignment=1, splitLongWords=True),
        'notes': ParagraphStyle('GridNotes', fontName='Studio', fontSize=9, leading=13),
    }
    def escaped(text):
        return html.escape(str(text)).replace('\n', '<br/>')
    def para(text, style):
        return Paragraph(escaped(text), styles[style])

    class SheetHeader(Flowable):
        def __init__(self):
            Flowable.__init__(self)
            self.width = width
            self.title = para(title, 'title')
            self.artist = Paragraph(escaped(artist), ParagraphStyle('GridArtist', fontName='Studio', fontSize=11,
                                                                                leading=15, textColor=quiet))
            self.album = Paragraph(escaped(album or 'Fiche de répétition'), ParagraphStyle('GridAlbum', fontName='Studio',
                                                         fontSize=8, leading=11, textColor=quiet))
            self.text_width = width-148
            self.title_height = self.title.wrap(self.text_width, 10000)[1]
            self.artist_height = self.artist.wrap(self.text_width, 10000)[1]
            self.album_height = self.album.wrap(self.text_width, 10000)[1]
            self.hero_height = max(128, 28+self.artist_height+self.title_height+self.album_height+18)
            self.height = self.hero_height+61

        def wrap(self, avail_width, avail_height):
            return width, self.height

        def draw(self):
            c = self.canv
            c.setFillColor(quiet);c.setFont('StudioBold', 6.5)
            c.drawString(0, self.height-8, 'B A N D S T U D I O   /   F I C H E   M O R C E A U')
            y = self.height-28
            self.artist.drawOn(c, 0, y-self.artist_height);y -= self.artist_height+6
            self.title.drawOn(c, 0, y-self.title_height);y -= self.title_height+11
            self.album.drawOn(c, 0, y-self.album_height)
            size = 120;x = width-size;cover_y = self.height-124
            if cover_image:
                c.setFillColor(colors.HexColor('#E4E6DB'));c.rect(x+3,cover_y-3,size,size,fill=1,stroke=0)
                c.drawImage(cover_image,x,cover_y,width=size,height=size,preserveAspectRatio=True,anchor='c',mask='auto')
            else:
                c.setFillColor(ink);c.rect(x,cover_y,size,size,fill=1,stroke=0)
                c.setStrokeColor(colors.HexColor('#51664D'))
                for r in range(16,57,5):c.circle(x+60,cover_y+60,r,stroke=1,fill=0)
                c.setFillColor(colors.HexColor('#D9BE7C'));c.circle(x+60,cover_y+60,10,fill=1,stroke=0)
            c.setStrokeColor(line);c.setLineWidth(.5);c.line(0,53,width,53)
            duration = f'{int(data["duration"])//60}:{int(data["duration"])%60:02}'
            key = data['key']+(f' / capo {data["capo"]}' if data['capo'] else '')
            for i,(label,value) in enumerate([('TEMPO',f'{data["bpm"]:g} BPM'),('TONALITÉ',key),('MESURE',f'{data["meter"]}/4'),('DURÉE',duration)]):
                x=i*width/4
                c.setFillColor(quiet);c.setFont('Studio',6);c.drawString(x,40,label)
                c.setFillColor(ink);c.setFont('StudioBold',12);c.drawString(x,23,value)
            if data['shift']:
                c.setFont('Studio',6);c.setFillColor(quiet);c.drawRightString(width,8,f'Transposition : {data["shift"]:+d} demi-tons')
            c.setStrokeColor(line);c.line(0,11,width,11)

    class BarRow(Flowable):
        def __init__(self, cells, continued=False, bodies=None):
            Flowable.__init__(self)
            self.cells, self.continued = cells, continued
            self.width = width
            self.cell_width = width/4
            self.chords, self.bodies = [], []
            for i, cell in enumerate(cells):
                names = cell['chords'] or ['']
                # Dense detected harmony remains readable without discarding any change.
                labels = names if len(names) <= 4 else [' / '.join(names)]
                if any(pdfmetrics.stringWidth(name, 'StudioBold', 7.5) > self.cell_width/len(labels)-8 for name in labels):
                    labels = [' / '.join(names)]
                chord_style = styles['chord']
                if len(labels)>1:
                    font_size = min(10, min((self.cell_width/len(labels)-8)/max(1,pdfmetrics.stringWidth(name,'StudioBold',1)) for name in labels))
                    chord_style = ParagraphStyle('GridChordFit', parent=chord_style, fontSize=font_size, leading=font_size+2, splitLongWords=False)
                self.chords.append([Paragraph(escaped(name), chord_style) for name in labels])
                if bodies is not None:
                    self.bodies.append(bodies[i])
                else:
                    parts = []
                    if cell['lyrics']:
                        parts.append('<font color="'+red+'">'+escaped(cell['lyrics'])+'</font>')
                    if cell['cues']:
                        parts.append('<font size="7.5" color="#444444">'+escaped(' / '.join(cell['cues']))+'</font>')
                    self.bodies.append(Paragraph('<br/>'.join(parts), styles['body']) if parts else None)
            self.header_height = max((q.wrap(self.cell_width/len(chords)-8, 10000)[1] for chords in self.chords for q in chords), default=12)+12
            self.body_heights = [q.wrap(self.cell_width-10, 10000)[1] if q else 0 for q in self.bodies]
            self.height = max(24, self.header_height+max(self.body_heights, default=0)+5+(7 if continued else 0))

        def wrap(self, avail_width, avail_height):
            return self.width, self.height

        def split(self, avail_width, avail_height):
            room = avail_height-self.header_height-16
            if room < styles['body'].leading*2:
                return []
            first, rest = [], []
            for q in self.bodies:
                if not q:
                    first.append(None);rest.append(None);continue
                pieces = q.split(self.cell_width-10, room)
                if not pieces:
                    return []
                first.append(pieces[0]);rest.append(pieces[1] if len(pieces)>1 else None)
            if not any(rest):
                return []
            return [BarRow(self.cells, self.continued, first), BarRow(self.cells, True, rest)]

        def draw(self):
            canvas = self.canv
            for i, cell in enumerate(self.cells):
                x = i*self.cell_width
                fill = peach if cell['lyrics'] else muted if any('mute' in c.lower() for c in cell['chords']) else colors.white
                canvas.setFillColor(fill);canvas.setStrokeColor(line);canvas.setLineWidth(.55)
                canvas.rect(x, 0, self.cell_width, self.height, stroke=1, fill=1)
                number = 'LEVÉE' if not cell['number'] else f'M. {cell["number"]}'
                if cell['partial']:
                    number += ' - suite' if cell['continuation'] else ' - début'
                canvas.setFont('Studio',5.8);canvas.setFillColor(quiet)
                canvas.drawString(x+5,self.height-8,number)
                chords = self.chords[i];part = self.cell_width/len(chords)
                for j, q in enumerate(chords):
                    _, h = q.wrap(part-8, 10000)
                    q.drawOn(canvas, x+j*part+4, self.height-10-h)
                    if j:
                        # With lyrics, the text spans the complete measure below the chords.
                        floor = self.height-self.header_height if self.bodies[i] else 4
                        canvas.saveState();canvas.setLineWidth(.3);canvas.setDash(1.5,2)
                        canvas.line(x+j*part, floor, x+j*part, self.height-9);canvas.restoreState()
                q = self.bodies[i]
                if q:
                    q.drawOn(canvas, x+5, self.height-self.header_height-self.body_heights[i])
                if self.continued:
                    canvas.setFont('Studio', 6);canvas.setFillColor(colors.HexColor('#777777'))
                    canvas.drawRightString(x+self.cell_width-4, 2, 'suite')

    class SectionBlock(Flowable):
        def __init__(self, name, position, rows, continued=False, number=1):
            Flowable.__init__(self)
            self.name, self.position, self.rows, self.continued = name, position, rows, continued
            self.number = number
            label = escaped(name)+(' (suite)' if continued else '')
            self.heading = Paragraph(label+' <font name="Studio" size="7" color="#7B8676">'+escaped(position)+'</font>', styles['section'])
            self.heading_height = self.heading.wrap(width-29, 10000)[1]
            self.width = width
            self.height = self.heading_height+sum(row.height for row in rows)+20

        def wrap(self, avail_width, avail_height):
            return self.width, self.height

        def split(self, avail_width, avail_height):
            # A normal section stays together. Oversized sections repeat their label on each page.
            if self.height <= A4[1]-42-44-12:
                return []
            room = avail_height-self.heading_height-20
            first, rest = [], list(self.rows)
            while rest and rest[0].height <= room:
                row = rest.pop(0);first.append(row);room -= row.height
            if not first and rest:
                parts = rest[0].split(avail_width, room)
                if parts:
                    first.append(parts[0]);rest = parts[1:]+rest[1:]
            if not first:
                return []
            return [SectionBlock(self.name, self.position, first, self.continued, self.number),
                    SectionBlock(self.name, self.position, rest, True, self.number)]

        def draw(self):
            y = self.height-10-self.heading_height
            self.canv.setFillColor(ink);self.canv.roundRect(0,y-1,21,17,3,fill=1,stroke=0)
            self.canv.setFillColor(colors.white);self.canv.setFont('StudioBold',7)
            self.canv.drawCentredString(10.5,y+4,str(self.number).zfill(2))
            self.heading.drawOn(self.canv, 29, y)
            y -= 9
            for row in self.rows:
                y -= row.height;row.drawOn(self.canv, 0, y)

    body = [SheetHeader()]
    for group_number, group in enumerate(data['groups'],1):
        cells = group['cells']
        if not cells:
            continue
        first, last = cells[0]['number'], cells[-1]['number']
        position = 'levée' if first == last == 0 else ('levée puis ' if first == 0 else '')+f'mes. {max(1, first)}-{last}'
        if cells[0]['partial'] or cells[-1]['partial']:
            position += ' / mesure partagée'
        rows = [BarRow(cells[i:i+4]) for i in range(0, len(cells), 4)]
        body.append(SectionBlock(group['name'], position, rows, number=group_number))
    if p.get('notes'):
        body.extend([para('Notes de jeu', 'section'), para(p['notes'], 'notes')])
    def footer(canvas, doc):
        canvas.saveState();canvas.setFont('Studio',6);canvas.setFillColor(quiet)
        canvas.setStrokeColor(line);canvas.setLineWidth(.4);canvas.line(44,34,A4[0]-44,34)
        canvas.drawString(44,22,'BANDSTUDIO / GRILLE DE RÉPÉTITION')
        canvas.drawRightString(A4[0]-44,22,str(doc.page).zfill(2))
        if doc.page>1:
            canvas.setFont('StudioBold',7);canvas.setFillColor(ink)
            short=title if len(title)<=55 else title[:52]+'...'
            canvas.drawString(44,A4[1]-27,short)
            canvas.setFont('Studio',6);canvas.setFillColor(quiet)
            canvas.drawRightString(A4[0]-44,A4[1]-27,f'{data["bpm"]:g} BPM / {data["key"]} / {data["meter"]}/4')
        canvas.restoreState()
    SimpleDocTemplate(str(target), pagesize=A4, leftMargin=38, rightMargin=38, topMargin=42, bottomMargin=44,
                      title=p['name'], author='BandStudio').build(body, onFirstPage=footer, onLaterPages=footer)


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
        result = smart_grid(audio, engine, project=p, notify=lambda info:atomic(Path(output).parent/'progress.json',dict(stage='smartgrid',**info)))
    elif kind == 'key':
        result = detect_key(audio)
    elif kind == 'lyricsimport':
        result = dict(entries=parse_lyrics(options.get('text',''), length))
    else:
        folder = root / 'Exports' / (kind+'-'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        name = safe_name(p['name'])
        if kind == 'lyricsexport':
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
