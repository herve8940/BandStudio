"""Offline analysis workers for the standalone studio. No DAW or bridge required."""
from __future__ import annotations
from ui_language import ui_text
import argparse
import json
import os
from pathlib import Path
import sys
import uuid


def write(path, value):
    from analysis_progress import replace_file
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    replace_file(tmp, path)


def progress(output, stage, **values):
    """UI status is separate from diagnostic stdout/stderr (including warnings)."""
    from analysis_progress import emit, _active, write_status
    if _active is not None:emit(stage=stage, **values)
    else:write_status(Path(output).parent / 'progress.json',
                      json.dumps(dict(stage=stage, **values), ensure_ascii=False, allow_nan=False))


def sections(raw, duration):
    """Group adjacent phrases of the same function into one announced section.

    Model phrase boundaries are finer than the rehearsal sections. Keep every
    change of function (including very short breaks), gap and exact outer edge.
    This only processes raw proposals; hosts preserve manual sections separately.
    """
    labels = {'intro': 'Intro', 'verse': ui_text('Couplet', 'Verse'), 'chorus': ui_text('Refrain', 'Chorus'),
              'pre-chorus': ui_text('Pré-refrain', 'Pre-chorus'), 'bridge': ui_text('Pont', 'Bridge'), 'inst': 'Instrumental',
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
        label=str(item['label']).strip()
        name=labels.get(label.casefold(), label)
        if result and result[-1]['name']==name and abs(start-result[-1]['end'])<1e-6:
            result[-1]['end']=end
            continue
        result.append(dict(id=str(uuid.uuid4()), start=start, end=end,
                           name=name, locked=False,
                           origin='analysis'))
    return result


def grid(audio):
    from analysis_progress import emit
    emit(progress=0,progressLabel=ui_text('Lecture audio · étape 1 sur 3', 'Reading audio · step 1 of 3'),progressBasis='steps',indeterminate=True)
    import numpy as np
    import librosa
    y, sr = librosa.load(audio, sr=22050, mono=True)
    duration = len(y) / sr
    if duration < 1 or np.max(np.abs(y), initial=0) < 1e-7:
        return dict(duration=duration, bpm=0, beats=[], downbeats=[], cues=[])
    # Beat positions are estimates, not a fabricated fixed tempo map.
    emit(progress=100/3,progressLabel=ui_text('Recherche des attaques · étape 2 sur 3', 'Finding onsets · step 2 of 3'),indeterminate=True)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    emit(progress=200/3,progressLabel=ui_text('Calage des temps · étape 3 sur 3', 'Aligning beats · step 3 of 3'),indeterminate=True)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=256)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=256).tolist()
    return dict(duration=duration, bpm=float(np.asarray(tempo).reshape(-1)[0]),
                beats=beats, downbeats=[], cues=[], gridStatus='estimated')


def separate(audio, output, model, engine, quality='standard'):
    from analysis_progress import emit, PassProgress
    import demucs.apply as demucs_apply
    emit(progressLabel=ui_text('Chargement des modèles…', 'Loading models…'), indeterminate=True)
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
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!='aefaa8543c9b9c75e22f5f32b53ab86dfe416457849af1383ff1aef83401423f':raise ValueError(ui_text('Modèle DrumSep modifié ou incomplet.', 'DrumSep model modified or incomplete.'))
        # Only this exact, verified upstream checkpoint may deserialize its model class.
        net=load_model(torch.load(checkpoint,map_location='cpu',weights_only=False))
    else:
        net=get_model(model)
    # Keep the complete song and output on the CPU; only model chunks use CUDA.
    x, sr = sf.read(audio, dtype='float32', always_2d=True)
    x = convert_audio(torch.from_numpy(x.T), sr, net.samplerate, net.audio_channels)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std()
    if not torch.isfinite(std) or std < 1e-8:
        sources = torch.zeros((len(net.sources), *x.shape))
    else:
        x = (x - mean) / std
        shifts,overlap={'fast':(0,.1),'standard':(1,.25),'careful':(2,.5)}[quality]
        from compute import run, demucs_segment
        def inference(info):
            segment=demucs_segment(info)
            if segment is not None:segment=min(segment,float(getattr(net,'max_allowed_segment',getattr(net,'segment',segment))))
            counter=PassProgress(len(getattr(net,'models',[net])) * max(1,shifts))
            with torch.inference_mode(), counter.track(demucs_apply):
                return apply_model(net, x[None], device=info['device'], shifts=shifts,
                    split=True, overlap=overlap, progress=True, num_workers=0, segment=segment)[0].cpu()
        sources,compute=run(torch,'drumsep' if model=='49469ca8' else 'separate',inference,
            cleanup=lambda:net.to('cpu'),notify=lambda info:progress(output,'separation',**info))
        sources = sources * std + mean
    emit(progress=99,progressLabel=ui_text('Enregistrement des pistes…', 'Saving tracks…'),indeterminate=True)
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


def analyze(audio, output, mode, engine, project_file=None, *, reanalyze=False):
    from analysis_cache import AnalysisCache
    project=json.loads(Path(project_file).read_text()) if project_file else None
    if mode == 'grid':
        cache=AnalysisCache.create(project,'grid',audio,engine)
        result=cache.load() if cache and not reanalyze else None
        hit=result is not None
        if not hit:
            result=grid(audio)
            if cache:cache.store(result)
        from services import calibrate_grid
        write(output, calibrate_grid({**result,'cacheHit':hit}))
        return
    sys.path.insert(0, str(engine))
    os.environ['REACUE_STRUCTURE_DIR'] = str(engine / 'structure')
    os.environ['REAPER_RESOURCE_PATH'] = str(Path(output).parent / 'worker-state')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['REACUE_CPU_THREADS'] = '4'
    progress(output, 'structure-loading',progressLabel=ui_text('Chargement des modèles…', 'Loading models…'),indeterminate=True)
    import reacue_structure as structure
    window=structure.choose_window()
    cache=AnalysisCache.create(project,'structure',audio,engine,dict(window=window))
    cached=cache.load() if cache and not reanalyze else None
    if cached is not None:
        raw=cached['segments']
        progress(output,'analysis-reuse')
    else:
        app=structure.load_app()
        notify=lambda info:progress(output,**info)
        structure.init_models(app,notify=notify)
        progress(output,'structure-analysis',device=str(app.device))
        from analysis_progress import track_structure
        with track_structure(app,audio,window):
            raw=structure.segments_from_app(app,audio,window,notify=notify)
        if cache:cache.store(dict(segments=raw))
    progress(output, 'structure-saving',progress=99,progressLabel=ui_text('Enregistrement des sections…', 'Saving sections…'),indeterminate=True)
    import soundfile as sf
    info = sf.info(audio)
    proposed=sections(raw, info.duration)
    from cue_corrector_runtime import adapt
    proposed,correction=adapt(audio,proposed,engine,info.duration,window,project)
    if project and project.get('beats'):
        from musical_timing import align_intro_sections,cached_audio_entry
        proposed=align_intro_sections({**project,'sections':proposed},cached_audio_entry(audio,project,engine))['sections']
    if project and (project.get('beats') or project.get('settings',{}).get('gridMode')=='fixed'):
        from section_evidence import align_bar_arrivals
        proposed,_=align_bar_arrivals({**project,'sections':proposed})
    write(output, dict(sections=proposed, engine='SongFormer',cacheHit=cached is not None,cueCorrection=correction))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['showExport','prepareReview','structureMemory','structureReview','structureApply','structureExport','validate','generate','vocalsplit','grid', 'structure', 'separate','drumsep','guides','decode','reaper','rpp','lyrics','lyricscorrect','chords','drums','midi','smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet'])
    p.add_argument('--options',default='{}')
    p.add_argument('--options-file')
    p.add_argument('--input', default='')
    p.add_argument('--project')
    p.add_argument('--language',default='auto')
    p.add_argument('--quality',choices=['fast','standard','careful'],default='standard')
    p.add_argument('--reanalyze',action='store_true',help='Recompute explicitly instead of reusing a previous result')
    p.add_argument('--preflight',action='store_true',help='Check the current media and timeline before a local REAPER export')
    p.add_argument('--chord-source',default='',help='Use a matching saved web chart for local chord alignment')
    p.add_argument('--output', required=True)
    p.add_argument('--engine', required=True)
    p.add_argument('--model', choices=['htdemucs', 'htdemucs_6s', 'htdemucs_ft'], default='htdemucs')
    a = p.parse_args()
    from analysis_progress import reporting
    with reporting(a.output,a.command):
        execute(a)


def execute(a):
    engine = Path(a.engine).resolve()
    a.input = str(Path(a.input).resolve())
    a.output = str(Path(a.output).resolve())
    os.environ['TORCH_HOME'] = str(engine / 'torch-cache')
    from analysis_cache import runtime_caches
    runtime_caches(engine,Path(a.output).parent)
    os.environ['OMP_NUM_THREADS'] = '4'
    os.environ['REAPER_RESOURCE_PATH'] = str(Path(a.output).parent / 'worker-state')
    os.environ['REACUE_CPU_THREADS']='4'
    os.environ['HF_HUB_OFFLINE']='1'
    sys.path.insert(0,str(engine))
    from compute import versions
    versions(a.command)
    progress(a.output, a.command)
    from analysis_progress import emit, legacy_status
    from services import guides,decode,export_reaper,export_midi,import_reaper
    if a.command == 'showExport':
        from show_export import export_show
        options = json.loads(Path(a.options_file).read_text(encoding='utf-8') if a.options_file else a.options)
        export_show(a.project, a.output, engine, options)
        return
    if a.command in ('generate','vocalsplit'):
        from creative import run
        run(a.command,a.input,a.output,engine,json.loads(Path(a.options_file).read_text() if a.options_file else a.options));return
    if a.command=='drumsep':
        if not (engine/'drumsep/49469ca8.th').is_file():raise ValueError(ui_text('Le modèle DrumSep n’est pas installé.', 'The DrumSep model is not installed.'))
        separate(a.input,a.output,'49469ca8',engine,a.quality)
        return
    if a.command in ('smartgrid','key','lyricsimport','lyricsexport','stemsexport','master','report','portable','sheet'):
        from advanced import run
        run(a.command,a.project,a.output,engine,json.loads(Path(a.options_file).read_text() if a.options_file else a.options),a.input)
        if a.command=='smartgrid':
            from services import calibrate_grid
            write(a.output,calibrate_grid(json.loads(Path(a.output).read_text())))
        return
    if a.command=='prepareReview':
        from structure_review import finish_preparation
        finish_preparation(a.project,a.output,engine)
        return
    if a.command in ('structureMemory','structureReview','structureApply','structureExport'):
        from structure_review import propose, export_proposal,memory_proposal,save_proposal
        if a.command=='structureMemory':write(a.output,dict(proposal=memory_proposal(json.loads(Path(a.project).read_text()))));return
        if a.command=='structureApply':save_proposal(a.project,a.output);return
        if a.command=='structureReview':write(a.output,propose(json.loads(Path(a.project).read_text())))
        else:export_proposal(a.project,a.output,engine)
        return
    if a.command=='guides':guides(a.project,a.output);return
    if a.command=='decode':
        target=Path(a.output).parent/'import.wav';decode(a.input,target,engine);write(a.output,dict(audio=str(target)));return
    if a.command in ('validate','reaper'):
        from preparation import validate_project, export_validated
        if a.command=='validate':
            validate_project(a.project,a.output)
            from song_memory import remember
            try:remember(json.loads(Path(a.project).read_text()),accepted=True)
            except (OSError,ValueError):pass
        else:export_validated(a.project,a.output,engine,preflight=getattr(a,'preflight',False))
        return
    if a.command=='rpp':import_reaper(a.input,a.output,engine,a.project);return
    if a.command in ('lyrics','lyricscorrect'):
        from lyrics_reference import correct, existing_transcription, correction_audio
        project=json.loads(Path(a.project).read_text())
        if a.command=='lyricscorrect' and project.get('_root'):
            original=Path(project['_root'])/'project.json'
            backup=original.parent/'Backups/lyrics-alignment-v1/project.json'
            if original.is_file() and not backup.exists():
                backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(original.read_bytes())
        track=next((t for role in ('vocal_lead','vocals','source') for t in project['tracks'] if t['role']==role),{})
        offset=track.get('offset',0)
        if a.command=='lyrics' or not project.get('lyrics'):
            print(ui_text('Transcription locale du chant et alignement des mots…', 'Transcribing vocals and aligning words locally…'),flush=True)
            import reacue_transcribe
            with legacy_status(reacue_transcribe, phases=3):
                if reacue_transcribe.transcribe(a.input,a.output,lang=a.language,model_name=reacue_transcribe.selected_model())!=0:raise RuntimeError(ui_text('La transcription des paroles a échoué.', 'Lyric transcription failed.'))
            transcription=json.loads(Path(a.output).read_text())
            for row in transcription.get('segments',[]):
                row['manual']=any(x.get('manual') and x['start']<row['end']+offset and x['end']>row['t']+offset for x in project.get('lyrics',[]))
        else:transcription=existing_transcription(project,offset,a.language)
        reference_audio,reference_offset=correction_audio(project,a.input,offset)
        # ASR may use the lead stem; full vocals retain the backing responses.
        # Translate anchors to that stem's clock before forced alignment.
        shift=offset-reference_offset
        for row in transcription.get('segments',[]):
            row['t']=row.get('t',row.get('start',0))+shift;row['end']+=shift
            for word in row.get('words',[]):word['t']+=shift;word['end']+=shift
        offset=reference_offset
        print(ui_text('Comparaison des références Internet et recalage sur le chant…', 'Comparing online references and aligning them to the vocals…'),flush=True)
        result=correct(project,transcription,reference_audio,Path(a.output).parent)
        for row in result.get('segments',[]):
            row['t']=row.get('t',row.get('start',0))+offset;row['end']+=offset
            for word in row.get('words',[]):word['t']+=offset;word['end']+=offset
        write(a.output,result)
        return
    if a.command=='chords':
        print(ui_text('Recherche d’une grille Internet à partir du titre et de l’artiste…', 'Finding an online chart from the song title and artist…'),flush=True)
        from chord_sources import analyze as analyze_chord_reference
        project=json.loads(Path(a.project).read_text())
        write(a.output,analyze_chord_reference(project,a.input,reanalyze=a.reanalyze,source_url=getattr(a,'chord_source','')))
        return
    if a.command=='drums':
        print(ui_text('Détection des frappes sur la piste batterie…', 'Detecting hits on the drum track…'),flush=True)
        import reacue_drums
        with legacy_status(reacue_drums):
            if reacue_drums.analyze(a.input,a.output)!=0:raise RuntimeError(ui_text('La transcription batterie a échoué.', 'Drum transcription failed.'))
        return
    if a.command=='midi':
        target=Path(a.output).parent/'batterie.mid';export_midi(json.loads(Path(a.project).read_text()),target)
        write(a.output,dict(path=str(target)));return
    if a.command == 'separate':
        separate(a.input, a.output, a.model, engine,a.quality)
    else:
        analyze(a.input, a.output, a.command, engine,a.project,reanalyze=a.reanalyze)


if __name__ == '__main__':
    main()
