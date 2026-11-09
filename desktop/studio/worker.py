"""Offline analysis workers for the standalone studio. No DAW or bridge required."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import uuid


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    os.replace(tmp, path)


def sections(raw, duration):
    """Keep precise boundaries and short breaks; never coerce four-bar phrases."""
    labels = {'intro': 'Intro', 'verse': 'Couplet', 'chorus': 'Refrain',
              'pre-chorus': 'Pré-refrain', 'bridge': 'Pont', 'inst': 'Instrumental',
              'outro': 'Outro', 'silence': 'Silence', 'solo': 'Solo'}
    result = []
    for item in sorted(raw, key=lambda s: float(s['start'])):
        start, end = max(0., float(item['start'])), min(duration, float(item['end']))
        if not (start < end):
            continue
        if result:
            start = max(start, result[-1]['end'])
        if start >= end:
            continue
        result.append(dict(id=str(uuid.uuid4()), start=start, end=end,
                           name=labels.get(item['label'], item['label']), locked=False,
                           origin='analysis'))
    return result


def grid(audio):
    import numpy as np
    import librosa
    y, sr = librosa.load(audio, sr=22050, mono=True)
    duration = len(y) / sr
    if duration < 1 or np.max(np.abs(y), initial=0) < 1e-7:
        return dict(duration=duration, bpm=0, beats=[], downbeats=[], cues=[])
    # Beat positions are estimates, not a fabricated fixed tempo map.
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=256)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=256).tolist()
    return dict(duration=duration, bpm=float(np.asarray(tempo).reshape(-1)[0]),
                beats=beats, downbeats=[], cues=[], gridStatus='estimated')


def separate(audio, output, model, engine, quality='standard'):
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from demucs.audio import convert_audio
    import numpy as np
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    if model == '49469ca8':
        import hashlib
        from demucs.states import load_model
        checkpoint=Path(engine)/'drumsep/49469ca8.th'
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!='aefaa8543c9b9c75e22f5f32b53ab86dfe416457849af1383ff1aef83401423f':raise ValueError('Modèle DrumSep modifié ou incomplet.')
        # Only this exact, verified upstream checkpoint may deserialize its model class.
        net=load_model(torch.load(checkpoint,map_location='cpu',weights_only=False))
    else:
        net=get_model(model)
    # Bounded CPU operation is portable on Intel and does not interrupt playback.
    x, sr = sf.read(audio, dtype='float32', always_2d=True)
    x = convert_audio(torch.from_numpy(x.T), sr, net.samplerate, net.audio_channels)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std()
    if not torch.isfinite(std) or std < 1e-8:
        sources = torch.zeros((len(net.sources), *x.shape))
    else:
        x = (x - mean) / std
        shifts,overlap={'fast':(0,.1),'standard':(1,.25),'careful':(2,.5)}[quality]
        sources = apply_model(net, x[None], device='cpu', shifts=shifts,
                              split=True, overlap=overlap, progress=True, num_workers=0)[0]
        sources = sources * std + mean
    # Preserve relative stem levels; never normalize each stem independently.
    folder = Path(output).parent / 'stems'
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for name, data in zip(net.sources, sources):
        path = folder / (name + '.wav')
        sf.write(path, data.cpu().numpy().T, net.samplerate, subtype='FLOAT')
        role={'bombo':'kick','redoblante':'snare','platillos':'cymbals','toms':'toms'}.get(name,name)
        files.append(dict(role=('drum_'+role if model == '49469ca8' else name), path=str(path)))
    write(output, dict(tracks=files, model=model,quality=quality))


def analyze(audio, output, mode, engine):
    if mode == 'grid':
        write(output, grid(audio))
        return
    sys.path.insert(0, str(engine))
    os.environ['REACUE_STRUCTURE_DIR'] = str(engine / 'structure')
    os.environ['REAPER_RESOURCE_PATH'] = str(Path(output).parent / 'worker-state')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['REACUE_CPU_THREADS'] = '4'
    import reacue_structure as structure
    app = structure.load_app()
    structure.init_models(app)
    raw = structure.segments_from_app(app, audio, 420 if structure.ram_gb() >= 15 else 120)
    import soundfile as sf
    info = sf.info(audio)
    write(output, dict(sections=sections(raw, info.duration), engine='SongFormer'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['generate','vocalsplit','grid', 'structure', 'separate','drumsep','guides','link','decode','reaper','rpp','lyrics','chords','drums','midi','smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet','reaperextension'])
    p.add_argument('--options',default='{}')
    p.add_argument('--options-file')
    p.add_argument('--input', default='')
    p.add_argument('--project')
    p.add_argument('--url')
    p.add_argument('--language',default='auto')
    p.add_argument('--quality',choices=['fast','standard','careful'],default='standard')
    p.add_argument('--output', required=True)
    p.add_argument('--engine', required=True)
    p.add_argument('--model', choices=['htdemucs', 'htdemucs_6s', 'htdemucs_ft'], default='htdemucs')
    a = p.parse_args()
    engine = Path(a.engine).resolve()
    a.input = str(Path(a.input).resolve())
    a.output = str(Path(a.output).resolve())
    os.environ['TORCH_HOME'] = str(engine / 'torch-cache')
    os.environ['NUMBA_CACHE_DIR'] = str(Path(a.output).parent / 'numba')
    os.environ['OMP_NUM_THREADS'] = '4'
    os.environ['MPLCONFIGDIR'] = str(Path(a.output).parent / 'matplotlib')
    os.environ['REAPER_RESOURCE_PATH'] = str(Path(a.output).parent / 'worker-state')
    os.environ['REACUE_CPU_THREADS']='4'
    os.environ['HF_HUB_OFFLINE']='1'
    sys.path.insert(0,str(engine))
    from services import guides,import_link,decode,export_reaper,export_midi,import_reaper
    if a.command in ('generate','vocalsplit'):
        from creative import run
        run(a.command,a.input,a.output,engine,json.loads(Path(a.options_file).read_text() if a.options_file else a.options));return
    if a.command=='drumsep':
        if not (engine/'drumsep/49469ca8.th').is_file():raise ValueError('Le modèle DrumSep n’est pas installé.')
        separate(a.input,a.output,'49469ca8',engine,a.quality)
        return
    if a.command in ('smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet','reaperextension'):
        from advanced import run
        run(a.command,a.project,a.output,engine,json.loads(Path(a.options_file).read_text() if a.options_file else a.options),a.input)
        return
    if a.command=='guides':guides(a.project,a.output);return
    if a.command=='link':import_link(a.url,a.output,engine);return
    if a.command=='decode':
        target=Path(a.output).parent/'import.wav';decode(a.input,target,engine);write(a.output,dict(audio=str(target)));return
    if a.command=='reaper':export_reaper(a.project,a.output);return
    if a.command=='rpp':import_reaper(a.input,a.output,engine,a.project);return
    if a.command=='lyrics':
        print('Transcription locale du chant et alignement des mots…',flush=True)
        import reacue_transcribe
        if reacue_transcribe.transcribe(a.input,a.output,lang=a.language)!=0:raise RuntimeError('La transcription des paroles a échoué.')
        return
    if a.command=='chords':
        print('Écoute harmonique et détection des changements d’accords…',flush=True)
        import reacue_chords
        if reacue_chords.analyze(a.input,a.output)!=0:raise RuntimeError('La détection des accords a échoué.')
        return
    if a.command=='drums':
        print('Détection des frappes sur la piste batterie…',flush=True)
        import reacue_drums
        if reacue_drums.analyze(a.input,a.output)!=0:raise RuntimeError('La transcription batterie a échoué.')
        return
    if a.command=='midi':
        target=Path(a.output).parent/'batterie.mid';export_midi(json.loads(Path(a.project).read_text()),target)
        write(a.output,dict(path=str(target)));return
    if a.command == 'separate':
        separate(a.input, a.output, a.model, engine,a.quality)
    else:
        analyze(a.input, a.output, a.command, engine)


if __name__ == '__main__':
    main()
