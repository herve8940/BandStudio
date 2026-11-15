"""Cache correctness: changed audio/models invalidate; project edits still apply."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import analysis_cache
import worker


def setup(tmp_path):
    engine=tmp_path/'engine';(engine/'structure').mkdir(parents=True)
    (engine/'structure/model.pt').write_bytes(b'model-one')
    (engine/'reacue_structure.py').write_text('# model adapter v1')
    audio=tmp_path/'source.wav';sf.write(audio,np.zeros(8*8000),8000)
    p=dict(_root=str(tmp_path),tracks=[dict(file='source.wav',offset=0,duration=8,role='source')],
           settings=dict(gridMode='detected',firstBeat=0,manualBPM=120,beatsPerBar=4),
           beats=[n*.5 for n in range(16)],sections=[])
    return engine,audio,p


def test_cache_checks_audio_contents_even_if_size_and_mtime_are_preserved(tmp_path):
    engine,audio,p=setup(tmp_path)
    first=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    first.store(dict(segments=[dict(start=0,end=8,label='intro')]))
    assert first.load()['segments'][0]['label']=='intro'
    stat=audio.stat();data=bytearray(audio.read_bytes());data[-1]=1;audio.write_bytes(data)
    os.utime(audio,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    changed=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    assert changed.key!=first.key and changed.load() is None


def test_models_settings_and_drum_stem_changes_invalidate_results(tmp_path):
    engine,audio,p=setup(tmp_path);drums=tmp_path/'drums.wav';drums.write_bytes(audio.read_bytes())
    create=lambda **kw:analysis_cache.AnalysisCache.create(p,'structure',audio,engine,**kw)
    first=create(options={'window':420},extra_audio=[drums]);first.store({'segments':[]})
    assert create(options={'window':120},extra_audio=[drums]).key!=first.key
    drums.write_bytes(b'different stem')
    changed_stem=create(options={'window':420},extra_audio=[drums])
    assert changed_stem.key!=first.key
    model=engine/'structure/model.pt';stat=model.stat();model.write_bytes(b'model-two');os.utime(model,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert create(options={'window':420},extra_audio=[drums]).key!=changed_stem.key


def test_windows_model_changes_are_detected_with_frozen_timestamps(tmp_path,monkeypatch):
    engine,audio,p=setup(tmp_path);model=engine/'structure/model.pt'
    original=model.stat();stat=Path.stat
    def frozen(path,*args,**kwargs):
        value=stat(path,*args,**kwargs)
        if path==model:
            return SimpleNamespace(st_mode=value.st_mode,st_size=value.st_size,
                                   st_mtime_ns=original.st_mtime_ns,st_ctime_ns=original.st_ctime_ns)
        return value
    # Simulate Windows creation-time semantics without changing pathlib's OS.
    monkeypatch.setattr(analysis_cache,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(Path,'stat',frozen)
    before=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    model.write_bytes(b'model-two')
    after=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    assert before.key!=after.key


def test_corrupt_or_partial_cache_recomputes_and_evidence_is_retained(tmp_path):
    engine,audio,p=setup(tmp_path);cache=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    evidence=tmp_path/'source.npz';np.savez(evidence,values=[1,2,3])
    cache.store({'segments':[]},evidence)
    out=tmp_path/'next/evidence.npz';assert cache.load(out)=={'segments':[]}
    assert out.read_bytes()==evidence.read_bytes()
    (cache.folder/'evidence.npz').write_bytes(b'interrupted write')
    assert cache.load() is None
    cache.store({'segments':[]},evidence)
    (cache.folder/'result.json').write_text('{')
    assert cache.load() is None


def test_audio_changed_during_analysis_is_not_saved(tmp_path):
    engine,audio,p=setup(tmp_path);cache=analysis_cache.AnalysisCache.create(p,'structure',audio,engine)
    audio.write_bytes(b'changed');cache.store({'segments':[]})
    assert cache.load() is None


def test_cached_structure_avoids_model_loading_without_rewriting_boundaries(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'path',sys.path.copy())
    for key in ('REACUE_STRUCTURE_DIR','REAPER_RESOURCE_PATH','HF_HUB_OFFLINE','REACUE_CPU_THREADS'):
        monkeypatch.setenv(key,os.environ.get(key,''))
    engine,audio,p=setup(tmp_path);calls=[]
    def analyze(app,audio,window,evidence_path=None):
        calls.append('inference')
        return [dict(start=0,end=4.12,label='intro'),dict(start=4.12,end=8,label='verse')]
    module=SimpleNamespace(load_app=lambda:calls.append('load') or SimpleNamespace(device='cpu'),
                           init_models=lambda app:None,segments_from_app=analyze,ram_gb=lambda:16)
    monkeypatch.setitem(sys.modules,'reacue_structure',module)
    snap=tmp_path/'project.json';snap.write_text(json.dumps(p));output=tmp_path/'job1/result.json'
    worker.analyze(str(audio),output,'structure',engine,snap)
    first=json.loads(output.read_text());assert not first['cacheHit'] and first['sections'][1]['start']==4.12
    p['settings']['firstBeat']=.5
    snap.write_text(json.dumps(p));second=tmp_path/'job2/result.json'
    worker.analyze(str(audio),second,'structure',engine,snap)
    result=json.loads(second.read_text())
    assert result['cacheHit'] and calls==['load','inference']
    assert result['sections'][1]['start']==4.12  # no stale alignment from the previous grid


def test_compilation_cache_is_shared_across_jobs(tmp_path,monkeypatch):
    for key in ('NUMBA_CACHE_DIR','MPLCONFIGDIR'):monkeypatch.delenv(key,raising=False)
    analysis_cache.runtime_caches(tmp_path/'engine',tmp_path/'job1')
    first=os.environ['NUMBA_CACHE_DIR']
    analysis_cache.runtime_caches(tmp_path/'engine',tmp_path/'job2')
    assert first==os.environ['NUMBA_CACHE_DIR']
    assert 'job' not in first


def test_structure_pipeline_aligns_new_intros_using_cached_analysis(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'path',sys.path.copy())
    for key in ('REACUE_STRUCTURE_DIR','REAPER_RESOURCE_PATH','HF_HUB_OFFLINE','REACUE_CPU_THREADS'):
        monkeypatch.setenv(key,os.environ.get(key,''))
    engine,audio,p=setup(tmp_path)
    sound=np.zeros(8*8000);sound[2000:]=.1;sf.write(audio,sound,8000)
    p['beats']=[.25+n*.5 for n in range(16)];p['settings']['firstBeat']=.25;p['bpm']=120
    cache=analysis_cache.AnalysisCache.create(p,'structure',audio,engine,dict(window=420))
    cache.store(dict(segments=[dict(start=0,end=2.12,label='intro'),dict(start=2.12,end=4.12,label='intro'),dict(start=4.12,end=8,label='verse')]))
    monkeypatch.setitem(sys.modules,'reacue_structure',SimpleNamespace(ram_gb=lambda:16,load_app=lambda:pytest.fail('Model rerun despite cached analysis')))
    snap=tmp_path/'project.json';snap.write_text(json.dumps(p));out=tmp_path/'job/result.json'
    worker.analyze(str(audio),out,'structure',engine,snap)
    result=json.loads(out.read_text());assert result['cacheHit'] is True
    assert [s['name'] for s in result['sections']]==['Avant départ','Intro','Intro','Couplet']
    assert [s['start'] for s in result['sections']]==[0,.25,2.25,4.12]
