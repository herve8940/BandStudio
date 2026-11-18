import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'desktop/studio')]
import cue_corrector as corrector
import train_cue_corrector as training


def sections():
    return [dict(id=str(i), start=float(t), end=float(end), name=name, origin='analysis')
            for i, (t, end, name) in enumerate([(0, 10, 'Intro'), (10, 30, 'Couplet'), (30, 40, 'Refrain')])]


def model(shift=.3):
    n = len(corrector.FEATURES)
    return dict(schema=1, features=list(corrector.FEATURES), mean=[0.] * n, scale=[1.] * n,
                timingWeights=[shift] + [0.] * n, maximumShiftSeconds=1., deleteThreshold=0.,
                presenceWeights=[0.] * (n+1), approved=False)


def test_correction_preserves_manual_markers_and_adjacent_ends():
    original = sections(); features = np.zeros((3, len(corrector.FEATURES)))
    for key, value in [('reviewed', True), ('locked', True), ('origin', 'manual')]:
        protected = copy.deepcopy(original); protected[1][key] = value
        assert corrector.correct(protected, features, model(), 40) == (protected, [])
    fresh, changes = corrector.correct(original, features, model(), 40)
    assert fresh[0]['start'] == 0 and fresh[1]['start'] == pytest.approx(10.3)
    assert fresh[0]['end'] == fresh[1]['start'] and fresh[-1]['end'] == 40
    assert len(changes) == 2 and original == sections()


def test_moves_cannot_cross_and_missing_provenance_vetoes_correction():
    original = sections(); original[1]['end'] = original[2]['start'] = 10.05
    features = np.zeros((3, len(corrector.FEATURES)))
    changed, _ = corrector.correct(original, features, model(20), 40)
    assert changed[1]['start'] < changed[2]['start']
    assert abs(changed[1]['start'] - original[1]['start']) <= 1
    original[0].pop('origin')
    assert corrector.correct(original, features, model(), 40) == (original, [])
    unsafe = model(); unsafe['maximumShiftSeconds'] = 10
    with pytest.raises(ValueError, match='Unsafe'):
        corrector.correct(sections(), features, unsafe, 40)


def test_ensemble_abstains_before_clipping_and_bounds_every_accepted_move():
    m=model(.518);m['maximumShiftSeconds']=.25
    n=len(corrector.FEATURES)
    m['uncertaintyGuard']=dict(kind='ensemble_abstention',maximumDisagreementSeconds=.15,
                               alternativeWeights=[[.295]+[0.]*n,[.408]+[0.]*n])
    original=sections();x=np.zeros((3,n))
    unchanged,edits=corrector.correct(original,x,m,40)
    assert unchanged==original and edits==[]
    m['timingWeights'][0]=.35
    moved,edits=corrector.correct(original,x,m,40)
    assert moved[1]['start']==10.25 and all(abs(e['after']-e['before'])<=.25 for e in edits)
    m['maximumShiftSeconds']=.5
    with pytest.raises(ValueError,match='conservative'):corrector.correct(original,x,m,40)


def test_removal_is_limited_to_short_fragments_and_keeps_contiguous_timeline():
    m = model(0); m['presenceWeights'][0] = -30; m['deleteThreshold'] = .05
    original = sections(); changed, edits = corrector.correct(original, np.zeros((3, len(corrector.FEATURES))), m, 40)
    assert [s['id'] for s in changed] == ['0', '1']  # 20-second verse retained
    assert changed[-1]['end'] == 40 and edits == [dict(id='2', kind='remove', before=30., presenceScore=pytest.approx(0., abs=1e-10))]


def test_group_split_unions_artist_work_and_duplicate_audio_without_scores():
    rows = [dict(id=str(i), artist='Artist '+str(i), title='Work '+str(i), audioSHA256='audio'+str(i)) for i in range(30)]
    rows[1]['artist'] = rows[0]['artist'].upper()
    rows[2]['title'] = rows[1]['title']
    rows[3]['audioSHA256'] = rows[2]['audioSHA256']
    split = training.split_groups(rows)
    assert len({split['assignment'][str(i)]['group'] for i in range(4)}) == 1
    assert len({split['assignment'][str(i)]['split'] for i in range(4)}) == 1
    assert split == training.split_groups(list(reversed(rows)))
    assert set(split['counts']) == {'train', 'validation', 'test'}


def test_ready_requires_successful_complete_report_and_every_prediction(tmp_path):
    rows = [dict(id='one')]
    def write(name, obj): (tmp_path / name).write_text(json.dumps(obj))
    write('status.json', dict(stage='analyzing', total=1, completed=0))
    assert training.ready(tmp_path, rows)[0] is False
    write('status.json', dict(stage='complete', total=1, completed=1))
    write('report.json', dict(complete=True, completed=1, total=1, results=[dict(id='one')]))
    with pytest.raises(ValueError, match='missing'):
        training.ready(tmp_path, rows)
    (tmp_path / 'one').mkdir()
    (tmp_path / 'one/prediction.json').write_text('{}'); (tmp_path / 'one/scores.json').write_text('{}')
    assert training.ready(tmp_path, rows)[0] is True
    write('status.json', dict(stage='failed', total=1, completed=0, error='inference failed'))
    with pytest.raises(RuntimeError, match='failed'):
        training.ready(tmp_path, rows)


def test_waiter_starts_only_after_success_and_respects_stop(tmp_path, monkeypatch):
    import os
    import time
    analysis=tmp_path/'analysis';analysis.mkdir()
    output=tmp_path/'training';output.mkdir()
    rows=[dict(id='one')];folder=analysis/'one';folder.mkdir()
    for name in ('prediction.json','scores.json'):(folder/name).write_text('{}')
    training.write(analysis/'status.json',dict(stage='analyzing',total=1,completed=0,pid=os.getpid(),updated=time.time()))
    sleeps=[]
    def advance(seconds):
        sleeps.append(seconds)
        training.write(analysis/'status.json',dict(stage='complete',total=1,completed=1))
        training.write(analysis/'report.json',dict(complete=True,total=1,completed=1,results=[dict(id='one')]))
    monkeypatch.setattr(training.time,'sleep',advance)
    training.await_analysis(analysis,output,rows,True)
    assert sleeps==[20]
    assert json.loads((output/'status.json').read_text())['trainingStarted'] is False
    (output/'STOP').touch()
    with pytest.raises(InterruptedError):training.await_analysis(analysis,output,rows,True)


def test_interval_objective_respects_human_uncertainty_and_gradient():
    design = np.array([[1., .5], [1., -.2]])
    low, high, weights = np.array([.2, -.5]), np.array([.4, -.2]), np.array([.5, .5])
    beta = np.array([.1, .7])
    loss, grad = training.interval_loss(beta, design, low, high, weights, .1)
    epsilon = 1e-6
    finite = [(training.interval_loss(beta + np.eye(2)[i]*epsilon, design, low, high, weights, .1)[0]
              - training.interval_loss(beta - np.eye(2)[i]*epsilon, design, low, high, weights, .1)[0])/(2*epsilon) for i in range(2)]
    assert grad == pytest.approx(finite, abs=1e-7)
    assert training.interval_loss(np.array([.3]), np.ones((1,1)), np.array([.2]), np.array([.4]), np.ones(1), 0.)[0] == 0


def synthetic_training_data(count=16):
    result = []
    for i in range(count):
        s = sections()
        s.insert(2, dict(id='extra', start=20., end=30., name='Pont', origin='analysis'))
        s[1]['end'] = 20.
        examples = [dict(kind='move_boundary', prediction=s[j], reference=dict(earliest=s[j]['start']+.25,
                    latest=s[j]['start']+.35, labels=['verse'])) for j in (1,3)]
        examples += [dict(kind='extra_boundary', prediction=s[2], reference=dict(labels=['verse']))]
        result.append(dict(row=dict(id=str(i), duration=40), sections=s,
                           x=np.full((4, len(corrector.FEATURES)), float(i)/100), examples=examples))
    return result


def test_fitting_learns_a_real_offset_and_unknown_examples_are_not_negatives(monkeypatch):
    monkeypatch.setitem(training.CONFIG, 'minimumTrainingPairs', 20)
    data = synthetic_training_data()
    models, fitted = training.fit_heads(data)
    assert fitted['trainingPairs'] == 32 and fitted['negativeCases'] == 16
    assert fitted['presenceTrained'] is False
    assert all(.24 < m['timingWeights'][0] < .36 for m in models)
    # Missing transitions have no prediction features and cannot become negatives.
    data[0]['examples'].append(dict(kind='missing_boundary', prediction=None, reference=dict(earliest=35, latest=35.1)))
    again, details = training.fit_heads(data)
    assert again == models and details == fitted


def test_presence_head_is_actually_fitted_and_json_serializable():
    data = synthetic_training_data(count=40)
    # Give negatives a learnable audio descriptor, without supplying labels to inference.
    for row in data:
        row['x'][2, 20] = -3.
        row['x'][1, 20] = row['x'][3, 20] = 3.
    models, fitted = training.fit_heads(data)
    assert fitted['presenceTrained'] is True and fitted['negativeCases'] == 40
    assert len(models) == 6 and models[0]['presenceWeights'][21] > 0
    json.dumps(dict(models=models, fitting=fitted), allow_nan=False)


def test_deleted_true_boundary_counts_as_error_not_an_improved_mae():
    s = sections(); ref = dict(annotator=1, duration=40, segments=[
        dict(start=0, end=10, labels=['intro']), dict(start=10,end=30,labels=['verse']), dict(start=30,end=40,labels=['chorus'])])
    data = [dict(row=dict(id='x', artist='artist', duration=40, references=[ref, {**ref, 'annotator':2}]),
                 sections=s, x=np.zeros((3,len(corrector.FEATURES))), examples=[
                     dict(kind='keep_boundary', prediction=s[2], reference=dict(earliest=30.,latest=30.1))])]
    m = model(0); m['presenceWeights'][0] = -30; m['deleteThreshold'] = .05
    report = training.evaluate(data, m)
    assert report['summary']['before']['intervalMAESeconds'] == 0
    assert report['summary']['after']['intervalMAESeconds'] == 3
    assert report['summary']['brokenGood'] == 1
    assert training.gate(report['summary'])['passed'] is False


def test_audio_features_use_real_audio_and_are_finite(tmp_path):
    import soundfile as sf
    rate = 8000; times = np.arange(rate*5)/rate
    audio = np.sin(2*np.pi*220*times) * np.where(times < 2.5, .05, .5)
    path = tmp_path/'audio.wav'; sf.write(path, audio, rate)
    descriptors = corrector.audio_features(path)
    s = [dict(start=0.,end=2.5,name='Intro'),dict(start=2.5,end=5.,name='Couplet')]
    x = corrector.boundary_features(s, descriptors, 5.)
    assert x.shape == (2,len(corrector.FEATURES)) and np.isfinite(x).all()
    assert descriptors['duration'] == 5.
    assert x[1, corrector.FEATURES.index('energy@0.6')] > x[1,corrector.FEATURES.index('energy@-0.6')]


def test_mp3_header_estimate_is_not_a_changed_recording_but_truncation_is_rejected(monkeypatch):
    import soundfile as sf
    from types import SimpleNamespace
    row=dict(id='salami_1166',audio='unchanged.mp3',duration=246.96571428571428,
             references=[dict(duration=246.674852607),dict(duration=246.6892517)])
    info=SimpleNamespace(duration=row['duration'],samplerate=44100,format='MP3')
    monkeypatch.setattr(sf,'info',lambda path:info)
    result=training.validate_decoded_duration(row,246.59591836734694)
    assert result['mp3HeaderEstimateAccepted'] is True
    assert result['shiftedAudio'] is result['shiftedLabels'] is False
    with pytest.raises(ValueError,match='mismatch'):
        training.validate_decoded_duration(row,240.)
    info.duration+=.2
    with pytest.raises(ValueError,match='header changed'):
        training.validate_decoded_duration(row,246.59591836734694)
    info.duration=row['duration'];info.format='WAV'
    with pytest.raises(ValueError,match='mismatch'):
        training.validate_decoded_duration(row,246.59591836734694)


def test_selection_only_uses_validation_and_test_sees_frozen_model(tmp_path, monkeypatch):
    (tmp_path/'dataset.json').write_text('{}')
    (tmp_path/'feature-manifest.json').write_text('{}')
    data = [dict(split=s, row=dict(id=s)) for s in ('train','validation','test')]
    good = model(.3); good['name']='validation_choice'
    bad = model(.6); bad['name']='test_would_prefer_this'
    calls=[]
    def fake_fit(rows):
        assert [r['row']['id'] for r in rows] == ['train']
        return [good,bad], dict(trainingSongs=1)
    def fake_evaluate(rows, m):
        split=rows[0]['split']; calls.append((split,m['name']))
        if split=='test':
            assert json.loads((tmp_path/'frozen-model.json').read_text())['model']['name']=='validation_choice'
        chosen=(m['name']=='validation_choice') == (split=='validation')
        before=dict(f1HalfSecond=.6,f1ThreeSeconds=.8,labelF1HalfSecond=.5,intervalMAESeconds=.3)
        after=dict(f1HalfSecond=.7 if chosen else .61,f1ThreeSeconds=.8,labelF1HalfSecond=.6,intervalMAESeconds=.2)
        return dict(summary=dict(songs=10,matchedConsensusPairs=20,before=before,after=after,
                    changes=10,brokenGoodFraction=0,severeRegressions=[]),records=[])
    monkeypatch.setattr(training,'fit_heads',fake_fit)
    monkeypatch.setattr(training,'evaluate',fake_evaluate)
    report=training.fit_and_evaluate(data,tmp_path)
    assert calls==[('validation','validation_choice'),('validation','test_would_prefer_this'),('test','validation_choice')]
    assert report['modelInstalled'] is False
    assert json.loads((tmp_path/'cue-corrector-candidate.json').read_text())['approved'] is False


@pytest.mark.skipif(sys.platform == "win32", reason="Training launcher uses POSIX locking; inference is portable")
def test_full_training_pipeline_exports_real_weights_and_resumes_completed_run(tmp_path, monkeypatch):
    import soundfile as sf
    analysis=tmp_path/'analysis'; analysis.mkdir()
    output=tmp_path/'training'; rows=[]
    rate=8000; t=np.arange(rate*40)/rate
    for i in range(40):
        path=tmp_path/f'audio-{i}.wav'
        signal=.1*np.sin(2*np.pi*(110+i)*t)*np.where(t<10.3,.5,np.where(t<30.3,1.,.7))
        sf.write(path,signal,rate)
        ref=dict(duration=40.,segments=[dict(start=0.,end=10.3,labels=['intro']),
             dict(start=10.3,end=30.3,labels=['verse']),dict(start=30.3,end=40.,labels=['chorus'])])
        row=dict(id=f'track-{i}',artist=f'Artist {i}',title=f'Composition {i}',duration=40.,
                 audio=str(path),audioSHA256=training.sha(path),references=[dict(**ref,annotator=n,sha256=f'reference-{i}-{n}') for n in (1,2)])
        rows.append(row); folder=analysis/row['id'];folder.mkdir()
        training.write(folder/'prediction.json',dict(audioSHA256=row['audioSHA256'],provenance={},sections=sections()))
        training.write(folder/'scores.json',{})
    manifest=tmp_path/'manifest.json';training.write(manifest,dict(tracks=rows))
    training.write(analysis/'protocol.json',{})
    training.write(analysis/'status.json',dict(stage='complete',total=40,completed=40))
    training.write(analysis/'report.json',dict(complete=True,total=40,completed=40,results=[dict(id=r['id']) for r in rows]))
    monkeypatch.setattr(training.os,'nice',lambda amount:0)
    report=training.run(manifest,analysis,output)
    assert report['trainingCompleted'] is True and report['modelInstalled'] is False
    assert report['fitting']['trainingPairs'] >= 40
    assert report['decision']=='rejected_keep_current_engine'  # no half-second F1 gain on this already-correct fixture
    frozen=json.loads((output/'frozen-model.json').read_text())
    assert .24 < frozen['model']['timingWeights'][0] < .36
    before=(output/'frozen-model.json').stat().st_mtime_ns
    assert training.run(manifest,analysis,output)==report
    assert before==(output/'frozen-model.json').stat().st_mtime_ns
