import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'desktop/studio'),str(ROOT/'tools')]
import cue_corrector as core
import cue_corrector_runtime as runtime
from run_cue_holdout import novel_candidates


def sections():
    return [dict(id=str(i),name=name,start=start,end=end,origin='analysis',locked=False)
            for i,(name,start,end) in enumerate([('Intro',0.,30.),('Couplet',30.,90.),('Refrain',90.,150.)])]


def approved_bundle(tmp_path):
    engine=tmp_path/'engine';(engine/'structure').mkdir(parents=True)
    weight=engine/'structure/test.bin';weight.write_bytes(b'weights')
    (engine/'reacue_structure.py').write_text('# frozen structure wrapper')
    bundle=engine/'cue-corrector';bundle.mkdir()
    n=len(core.FEATURES)
    model=dict(schema=1,version='cue-corrector-v2',features=list(core.FEATURES),mean=[0.]*n,scale=[1.]*n,
               timingWeights=[.15]+[0.]*n,maximumShiftSeconds=.25,deleteThreshold=0.,approved=True,
               uncertaintyGuard=dict(kind='ensemble_abstention',maximumDisagreementSeconds=.15,
                                     alternativeWeights=[[.15]+[0.]*n,[.15]+[0.]*n]))
    (bundle/'model.json').write_text(json.dumps(model))
    approval=dict(schema=1,approved=True,enabled=True,windowSeconds=60,
                  correctorSourceSHA256=runtime.digest(core.__file__),runtimeSourceSHA256=runtime.digest(runtime.__file__),
                  structureWrapperSHA256=runtime.digest(engine/'reacue_structure.py'),modelSHA256=runtime.digest(bundle/'model.json'),
                  structureFiles={'structure/test.bin':dict(sha256=runtime.digest(weight),stamp=runtime.stamp(weight))})
    (bundle/'approval.json').write_text(json.dumps(approval))
    return engine,model


def mock_features(monkeypatch):
    monkeypatch.setattr(core,'audio_features',lambda path:dict(duration=150.))
    monkeypatch.setattr(core,'boundary_features',lambda s,a,d:np.zeros((len(s),len(core.FEATURES))))


def test_unapproved_or_wrong_window_bundle_cannot_change_sections(tmp_path,monkeypatch):
    engine,model=approved_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'unchanged audio');mock_features(monkeypatch)
    original=sections()
    result,meta=runtime.adapt(audio,original,engine,150.,60)
    assert result[1]['start']==30.15 and meta['applied'] is True
    result,meta=runtime.adapt(audio,original,engine,150.,30)
    assert result==original and meta['reason']=='different-analysis-window'
    approval=engine/'cue-corrector/approval.json';r=json.loads(approval.read_text());r['approved']=False;approval.write_text(json.dumps(r))
    assert runtime.adapt(audio,original,engine,150.,60)[0]==original


def test_manual_project_or_gaps_are_preserved_even_with_approved_model(tmp_path,monkeypatch):
    engine,model=approved_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'a');mock_features(monkeypatch)
    original=sections()
    project=dict(sections=[dict(start=30,reviewed=True)])
    result,meta=runtime.adapt(audio,original,engine,150.,60,project)
    assert result==original and meta['reason']=='protected-project-sections'
    original[0]['end']=29.
    assert runtime.adapt(audio,original,engine,150.,60)[0]==original
    assert runtime.apply_model(original,np.zeros((3,len(core.FEATURES))),model,150.)==(original,[])


def test_context_or_weights_changes_disable_correction(tmp_path,monkeypatch):
    engine,model=approved_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'a');mock_features(monkeypatch)
    original=sections()
    (engine/'structure/test.bin').write_bytes(b'changed weights')
    result,meta=runtime.adapt(audio,original,engine,150.,60)
    assert result==original and meta['reason']=='different-structure-weights'
    engine2,model2=approved_bundle(tmp_path/'second')
    (engine2/'cue-corrector/model.json').write_text('{}')
    result,meta=runtime.adapt(audio,original,engine2,150.,60)
    assert result==original and meta['reason']=='changed-corrector-weights'


def test_outer_edge_is_preserved_and_audio_mutations_abort(tmp_path,monkeypatch):
    engine,model=approved_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'a');mock_features(monkeypatch)
    original=sections();original[-1]['end']=149.8
    result,meta=runtime.adapt(audio,original,engine,150.,60)
    assert result[-1]['end']==149.8
    def changing_features(path):
        path.write_bytes(b'changed');return dict(duration=150.)
    monkeypatch.setattr(core,'audio_features',changing_features)
    result,meta=runtime.adapt(audio,original,engine,150.,60)
    assert result==original and meta['reason']=='audio-changed'


def test_cached_model_is_corrected_once_per_analysis_without_cache_pollution(tmp_path,monkeypatch):
    import soundfile as sf
    import worker
    from analysis_cache import AnalysisCache
    from windows.project import fresh
    engine,model=approved_bundle(tmp_path)
    audio=tmp_path/'audio.wav';sf.write(audio,np.zeros(8000*150),8000)
    project=fresh();project['_root']=str(tmp_path);project['tracks']=[dict(role='source',file='audio.wav',duration=150,offset=0)]
    snapshot=tmp_path/'project.json';snapshot.write_text(json.dumps(project))
    raw=[dict(start=0.,end=30.,label='intro'),dict(start=30.,end=90.,label='verse'),dict(start=90.,end=150.,label='chorus')]
    cache=AnalysisCache.create(project,'structure',audio,engine,dict(window=60));cache.store(dict(segments=raw))
    monkeypatch.setattr(sys,'path',sys.path.copy())
    monkeypatch.setitem(sys.modules,'reacue_structure',SimpleNamespace(choose_window=lambda:60,load_app=lambda:pytest.fail('Cached model was rerun')))
    for key in ('REACUE_STRUCTURE_DIR','REAPER_RESOURCE_PATH','HF_HUB_OFFLINE','REACUE_CPU_THREADS'):monkeypatch.setenv(key,'')
    mock_features(monkeypatch)
    for i in range(2):
        out=tmp_path/f'job-{i}/result.json';worker.analyze(audio,out,'structure',engine,snapshot)
        r=json.loads(out.read_text());assert r['cacheHit'] and r['sections'][1]['start']==30.15
        assert r['cueCorrection']['applied'] is True
    assert cache.load()['segments']==raw


def test_holdout_excludes_known_artists_works_and_ids_without_scores():
    old=[dict(id='a',artist='Artist A',title='My Song')]
    rows=[dict(id='a',artist='New One',title='First'),dict(id='b',artist='ARTIST A',title='Second'),
          dict(id='c',artist='New Two',title='My song'),dict(id='d',artist='New Three',title='A New Song')]
    assert [r['id'] for r in novel_candidates(old,rows)]==['d']


def test_fresh_holdout_checks_and_paired_bootstrap():
    from validate_cue_release import independent_rows,confidence_interval
    old=[dict(id='old',artist='old artist',title='old work',audioSHA256='old hash')]
    rows=[dict(id=str(i),artist='artist '+str(i),title='work '+str(i),audioSHA256='hash '+str(i)) for i in range(24)]
    independent_rows(old,rows)
    rows[0]['artist']='OLD ARTIST'
    with pytest.raises(ValueError,match='artist overlap'):independent_rows(old,rows)
    records=[dict(scores=[dict(before={'0.5':dict(f1=.5)},after={'0.5':dict(f1=.55)}) for _ in range(2)]) for i in range(24)]
    interval=confidence_interval(records)
    assert interval['lower']==pytest.approx(.05) and interval['upper']==pytest.approx(.05)
    assert interval==confidence_interval(records)


def test_rejected_release_cannot_reach_installer(tmp_path):
    from install_cue_corrector import install
    (tmp_path/'fresh-report.json').write_text(json.dumps(dict(passed=False,decision='rejected_keep_current_engine')))
    with pytest.raises(ValueError,match='rejected'):install(tmp_path,dict(sources={},inputs={}))


def test_failed_installed_worker_smoke_rolls_back_engine_and_bundle(tmp_path,monkeypatch):
    import install_cue_corrector as installer
    import subprocess
    output=tmp_path/'experiment';output.mkdir();(output/'stage').mkdir();(output/'analysis').mkdir()
    engine=tmp_path/'engine';engine.mkdir();(engine/'structure').mkdir();library=tmp_path/'library';library.mkdir()
    (engine/'worker.py').write_text('old worker')
    (engine/'reacue_structure.py').write_text('structure wrapper')
    (engine/'cue-corrector').mkdir();(engine/'cue-corrector/approval.json').write_text('old bundle')
    names=['cue_corrector.py','cue_corrector_runtime.py','worker.py']
    for name in names:(output/'stage'/name).write_text('new '+name)
    weights={}
    for i in range(3):
        name=f'structure/weight-{i}.pt';(engine/name).write_bytes(bytes([i]));weights[name]=runtime.digest(engine/name)
    (output/'analysis/protocol.json').write_text(json.dumps(dict(structureWrapperSHA256=runtime.digest(engine/'reacue_structure.py'),checkpointSHA256=weights)))
    (output/'candidate.json').write_text(json.dumps(dict(model=dict(version='cue-corrector-v2',approved=False))))
    plan=dict(sources={},inputs={},engine=str(engine),library=str(library),
              engineBefore={name:runtime.digest(engine/name) if (engine/name).exists() else None for name in names},
              stageSHA256={name:runtime.digest(output/'stage'/name) for name in names})
    (output/'release-plan.json').write_text(json.dumps(plan))
    report=dict(passed=True,decision='eligible_for_installation',releasePlanSHA256=runtime.digest(output/'release-plan.json'),candidateSHA256=runtime.digest(output/'candidate.json'))
    (output/'fresh-report.json').write_text(json.dumps(report))
    def failure(*a,**kw):raise subprocess.CalledProcessError(1,'smoke')
    monkeypatch.setattr(installer.subprocess,'run',failure)
    with pytest.raises(subprocess.CalledProcessError):installer.install(output,plan)
    assert (engine/'worker.py').read_text()=='old worker'
    assert not (engine/'cue_corrector.py').exists() and not (engine/'cue_corrector_runtime.py').exists()
    assert (engine/'cue-corrector/approval.json').read_text()=='old bundle'
    assert not (output/'installation.json').exists()
