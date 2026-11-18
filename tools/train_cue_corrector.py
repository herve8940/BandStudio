"""Wait for the sealed full-song benchmark, then fit and evaluate a corrector.

No production files or user projects are written. Artist/work/audio connected
groups are split before training. Validation selects a model; the frozen model
is evaluated once on the held-out development split, never tuned against it.
SALAMI overlap with SongFormer pretraining is unknown: this is not a blind
external test, nor a test of beats or spoken cue anticipation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import unicodedata

# Set before importing NumPy/SciPy, including when launched manually.
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '2'

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))
from cue_corrector import FEATURES, SCHEMA, audio_features, boundary_features, correct
from build_cue_examples import build
from cue_benchmark import sha, structure_score, write

CONFIG = dict(
    version='cue-corrector-v1', seed='bandstudio-cue-20261118-v1',
    fractions=dict(train=.60, validation=.20, test=.20),
    timingModels=['constant', 'ridge_0.1', 'ridge_1.0'],
    deletionThresholds=[0., .05], presenceL2=.1,
    maximumShiftSeconds=1., huberSeconds=.5,
    minimumTrainingPairs=40, minimumTrainingSongs=12,
    minimumEvaluationPairs=10, minimumEvaluationSongs=8,
    gates=dict(minimumF1Gain=.01, minimumIntervalMAEGain=.02,
               maximumLooseF1Loss=.005, maximumLabelF1Loss=.005,
               maximumBrokenGoodFraction=.02, maximumSongF1Loss=.10),
)


def canonical(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold()) if c.isalnum())


def split_groups(rows):
    """Union artist, known title, and byte-identical audio before splitting."""
    rows = sorted(rows, key=lambda r: r['id'])
    parent = {r['id']: r['id'] for r in rows}
    def root(key):
        while key != parent[key]:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    seen = {}
    for row in rows:
        artist, title = canonical(row['artist']), canonical(row['title'])
        if not artist or artist in ('unknown', 'variousartists'):
            raise ValueError('An identified artist is required for splitting')
        keys = [('artist', artist), ('audio', row['audioSHA256'])]
        # Generic track labels are not evidence of a shared composition.
        if len(title) >= 4 and title not in ('unknown', 'untitled', 'intro', 'outro', 'introduction'):
            keys.append(('work', title))
        for key in keys:
            if key in seen:
                parent[root(row['id'])] = root(seen[key])
            seen[key] = row['id']
    groups = {}
    for row in rows:
        groups.setdefault(root(row['id']), []).append(row['id'])
    def digest(ids):
        return hashlib.sha256((CONFIG['seed'] + '|' + '|'.join(sorted(ids))).encode()).hexdigest()
    ordered = sorted(groups.values(), key=lambda ids: (-len(ids), digest(ids)))
    counts = Counter(); assignment = {}; connected = []
    for ids in ordered:
        # A deterministic grouped allocation uses metadata only, never scores.
        split = min(CONFIG['fractions'], key=lambda k: (counts[k] / (len(rows) * CONFIG['fractions'][k]), k))
        counts[split] += len(ids)
        group = digest(ids)
        connected.append(dict(group=group, ids=sorted(ids), split=split))
        for key in ids:
            assignment[key] = dict(split=split, group=group)
    return dict(schema=1, seed=CONFIG['seed'], counts=dict(counts), assignment=assignment, groups=connected,
                limitation='Metadata grouping cannot exclude unrecognised covers or SongFormer pretraining overlap.')


def emit(output, stage, **extra):
    state = dict(stage=stage, pid=os.getpid(), updated=time.time(), modelInstalled=False, **extra)
    write(output / 'status.json', state)
    print(json.dumps(state, ensure_ascii=False), flush=True)


def prepare(manifest, analysis, output):
    import scipy
    import soundfile
    rows = json.loads(manifest.read_text())['tracks']
    ids = [r['id'] for r in rows]
    if not rows or len(set(ids)) != len(ids):
        raise ValueError('Empty manifest or duplicate track IDs')
    split = split_groups(rows)
    files = [Path(__file__), Path(__file__).with_name('cue_benchmark.py'),
             Path(__file__).with_name('launch_cue_corrector.py'),
             Path(__file__).with_name('build_cue_examples.py'), ROOT / 'desktop/studio/cue_corrector.py',
             ROOT / 'desktop/studio/cue_feedback.py']
    protocol = dict(schema=1, manifestSHA256=sha(manifest), analysisProtocolSHA256=sha(analysis / 'protocol.json'),
                    sources={f.name: sha(f) for f in files}, config=CONFIG, split=split,
                    dependencies=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                                      soundfile=soundfile.__version__, libsndfile=soundfile.__libsndfile_version__),
                    scope='Supervised structural timing and conservative short-fragment removal; no beat labels, no insertion or section relabelling.',
                    externalBlindTest=False, productionInstall=False)
    path = output / 'protocol.json'
    if path.exists() and json.loads(path.read_text()) != protocol:
        raise ValueError('Protocol/code/data changed: use a new experiment directory')
    if not path.exists():
        (output / 'source').mkdir(parents=True, exist_ok=True)
        for source in files:
            shutil.copy2(source, output / 'source' / source.name)
        write(output / 'split.json', split)
        write(path, protocol)
    return rows, split, protocol


def ready(analysis, rows):
    status = json.loads((analysis / 'status.json').read_text())
    if status['stage'] in ('failed', 'paused'):
        raise RuntimeError('Source analysis is ' + status['stage'] + ': ' + status.get('error', ''))
    total = len(rows)
    if status.get('total') != total:
        raise ValueError('Analysis total does not match manifest')
    if status['stage'] != 'complete':
        return False, status
    report = json.loads((analysis / 'report.json').read_text())
    reported = [r['id'] for r in report['results']]
    if status.get('completed') != total or report.get('complete') is not True or report.get('completed') != total or report.get('total') != total or sorted(reported) != sorted(r['id'] for r in rows):
        raise ValueError('Analysis says complete but its report is incomplete')
    for row in rows:
        if not (analysis / row['id'] / 'prediction.json').is_file() or not (analysis / row['id'] / 'scores.json').is_file():
            raise ValueError('Completed analysis is missing a prediction or score')
    return True, status


def await_analysis(analysis, output, rows, wait):
    started = time.time(); last = None
    while True:
        if (output / 'STOP').exists() or (analysis / 'STOP').exists():
            raise InterruptedError('STOP requested')
        complete, state = ready(analysis, rows)
        if complete:
            return
        if not wait:
            raise RuntimeError('Analysis is incomplete; use --wait-for-analysis')
        completed = state.get('completed', 0)
        if completed != last:
            emit(output, 'waiting_for_analysis', completedAnalyses=completed, totalAnalyses=len(rows), trainingStarted=False)
            last = completed
        # Signal 0 probes existence on POSIX, but sends CTRL_C_EVENT on Windows.
        # Windows monitoring relies on the progress heartbeat below.
        if state.get('pid') and sys.platform != 'win32':
            try:
                os.kill(state['pid'], 0)
            except ProcessLookupError:
                raise RuntimeError('Analysis process exited before completing')
            except PermissionError:
                pass
        progress = analysis / str(state.get('current', '')) / 'progress.json'
        latest = max(state.get('updated', 0), progress.stat().st_mtime if progress.exists() else 0)
        if time.time() - latest > 3600:
            raise RuntimeError('Analysis has not reported progress for one hour')
        if time.time() - started > 48 * 3600:
            raise RuntimeError('Waiting limit of 48 hours exceeded')
        time.sleep(20)


def dataset_snapshot(manifest, analysis, output, rows, protocol):
    # Rebuild after completion; do not depend on a separate follower's timing.
    examples = build(manifest, analysis, output / 'examples.json')
    if examples['completedSongs'] != len(rows):
        raise ValueError('Incomplete supervised examples')
    provenance = json.loads((analysis / 'protocol.json').read_text())
    inputs = {}
    for row in rows:
        prediction = analysis / row['id'] / 'prediction.json'
        p = json.loads(prediction.read_text())
        if p['audioSHA256'] != row['audioSHA256'] or p['provenance'] != provenance:
            raise ValueError('Prediction provenance mismatch: ' + row['id'])
        inputs[row['id']] = dict(audioSHA256=row['audioSHA256'], predictionSHA256=sha(prediction))
    snapshot = dict(protocolSHA256=sha(output / 'protocol.json'), inputs=inputs)
    seal = output / 'dataset.json'
    if seal.exists() and json.loads(seal.read_text()) != snapshot:
        raise ValueError('Dataset changed after training was sealed')
    write(seal, snapshot)
    return {r['id']: r for r in examples['tracks']}, snapshot


def validate_decoded_duration(row, decoded_seconds):
    """Distinguish unchanged MP3 header estimates from changed/truncated audio.

    Audio identity is checked separately, before and after extraction. Some VBR
    headers overestimate EOF, including with the same decoder as SongFormer.
    Allow only a small MP3 discrepancy still consistent with BOTH annotation
    endpoints, using the corpus's existing 1.5-second alignment bound. Never
    shift audio or labels, and preserve the manifest's original time coordinate.
    """
    import soundfile as sf
    info = sf.info(row['audio'])
    if abs(info.duration - row['duration']) > 1. / info.samplerate:
        raise ValueError('Audio header changed: ' + row['id'])
    delta = decoded_seconds - info.duration
    verified_mp3_estimate = (info.format == 'MP3' and abs(delta) < 1.5
                            and len(row['references']) == 2
                            and all(abs(decoded_seconds - ref['duration']) < 1.5 for ref in row['references']))
    if abs(delta) > .1 and not verified_mp3_estimate:
        raise ValueError(f"Decoded audio duration mismatch: {row['id']}, header={info.duration:.6f}, decoded={decoded_seconds:.6f}")
    return dict(headerSeconds=info.duration, decodedSeconds=decoded_seconds, differenceSeconds=delta,
                mp3HeaderEstimateAccepted=abs(delta) > .1, shiftedAudio=False, shiftedLabels=False)


def load_data(rows, analysis, output, split, examples, snapshot):
    cache = output / 'features'; cache.mkdir(exist_ok=True)
    data = []
    for n, row in enumerate(rows):
        if (output / 'STOP').exists():
            raise InterruptedError('STOP requested')
        emit(output, 'extracting_features', completedSongs=n, totalSongs=len(rows), current=row['id'], trainingStarted=False)
        if sha(row['audio']) != row['audioSHA256']:
            raise ValueError('Audio changed: ' + row['id'])
        path = analysis / row['id'] / 'prediction.json'
        if sha(path) != snapshot['inputs'][row['id']]['predictionSHA256']:
            raise ValueError('Prediction changed: ' + row['id'])
        sections = json.loads(path.read_text())['sections']
        evidence = dict(audioSHA256=row['audioSHA256'], predictionSHA256=sha(path),
                        protocolSHA256=sha(output / 'protocol.json'))
        feature_path = cache / (row['id'] + '.json')
        if feature_path.exists():
            saved = json.loads(feature_path.read_text())
            if saved['evidence'] != evidence:
                raise ValueError('Stale acoustic feature cache')
            x = np.asarray(saved['features'], dtype=float)
        else:
            audio = audio_features(row['audio'])
            duration_check = validate_decoded_duration(row, audio['duration'])
            x = boundary_features(sections, audio, row['duration'])
            if sha(row['audio']) != row['audioSHA256']:
                raise ValueError('Audio changed during feature extraction')
            write(feature_path, dict(evidence=evidence, durationCheck=duration_check, features=x.tolist()))
        if x.shape != (len(sections), len(FEATURES)) or not np.isfinite(x).all():
            raise ValueError('Invalid cached features')
        data.append(dict(row=row, sections=sections, x=x, examples=examples[row['id']]['examples'],
                         split=split['assignment'][row['id']]['split']))
    feature_seal = {row['id']: sha(cache / (row['id'] + '.json')) for row in rows}
    seal_path = output / 'feature-manifest.json'
    if seal_path.exists() and json.loads(seal_path.read_text()) != feature_seal:
        raise ValueError('Extracted features changed after being sealed')
    write(seal_path, feature_seal)
    return data


def supervised_arrays(data):
    paired, presence = [], []
    for item in data:
        index = {s['id']: i for i, s in enumerate(item['sections'])}
        pairs = [e for e in item['examples'] if e['kind'] in ('keep_boundary', 'move_boundary')]
        known = [e for e in item['examples'] if e['kind'] != 'missing_boundary']
        for e in known:
            i = index[e['prediction']['id']]
            if i == 0:
                continue  # inference intentionally preserves the first section
            x = item['x'][i]
            presence.append((x, float(e['kind'] != 'extra_boundary'), 1. / max(1, len(known))))
            if e['kind'] in ('keep_boundary', 'move_boundary'):
                t = e['prediction']['start']; ref = e['reference']
                paired.append((x, ref['earliest'] - t, ref['latest'] - t, 1. / max(1, len(pairs))))
    if len(paired) < CONFIG['minimumTrainingPairs'] or len({r['row']['id'] for r in data if any(e['kind'] in ('keep_boundary', 'move_boundary') for e in r['examples'])}) < CONFIG['minimumTrainingSongs']:
        raise ValueError('Insufficient independent supervised training examples')
    return paired, presence


def interval_loss(beta, design, low, high, weight, l2):
    prediction = design @ beta
    residual = prediction - np.clip(prediction, low, high)
    delta = CONFIG['huberSeconds']; absolute = np.abs(residual)
    loss = np.where(absolute <= delta, .5 * residual ** 2, delta * (absolute - .5 * delta))
    gradient = design.T @ (weight * np.clip(residual, -delta, delta))
    gradient[1:] += l2 * beta[1:]
    return float(weight @ loss + .5 * l2 * (beta[1:] @ beta[1:])), gradient


def fit_heads(train):
    from scipy.optimize import minimize
    from scipy.special import expit
    paired, presence = supervised_arrays(train)
    px = np.asarray([e[0] for e in paired]); qx = np.asarray([e[0] for e in presence])
    # Fit normalization strictly on TRAIN, never on held-out songs.
    mean = qx.mean(axis=0); scale = np.maximum(qx.std(axis=0), .05)
    design = np.c_[np.ones(len(px)), np.clip((px - mean) / scale, -5., 5.)]
    low, high = np.asarray([e[1] for e in paired]), np.asarray([e[2] for e in paired])
    weights = np.asarray([e[3] for e in paired]); weights /= weights.sum()
    heads = {}
    for name in CONFIG['timingModels']:
        constant = name == 'constant'
        x = design[:, :1] if constant else design
        l2 = 0. if constant else float(name.split('_')[1])
        result = minimize(interval_loss, np.zeros(x.shape[1]), args=(x, low, high, weights, l2),
                          jac=True, method='L-BFGS-B', options=dict(maxiter=1000, ftol=1e-12))
        if not result.success or not np.isfinite(result.x).all():
            raise RuntimeError('Timing fit did not converge: ' + str(result.message))
        beta = np.zeros(design.shape[1]); beta[:len(result.x)] = result.x
        heads[name] = dict(weights=beta.tolist(), objective=float(result.fun), iterations=int(result.nit))
    z = np.c_[np.ones(len(qx)), np.clip((qx - mean) / scale, -5., 5.)]
    y = np.asarray([e[1] for e in presence]); w = np.asarray([e[2] for e in presence]); w /= w.sum()
    learned_presence = bool(min(np.count_nonzero(y == 0), np.count_nonzero(y == 1)) >= 30)
    beta = np.zeros(z.shape[1]); beta[0] = 30.  # disabled when negatives are insufficient
    if learned_presence:
        def objective(b):
            logits = z @ b; l2 = CONFIG['presenceL2']
            value = w @ (np.logaddexp(0., logits) - y * logits) + .5 * l2 * (b[1:] @ b[1:])
            grad = z.T @ (w * (expit(logits) - y)); grad[1:] += l2 * b[1:]
            return float(value), grad
        result = minimize(objective, np.zeros(z.shape[1]), jac=True, method='L-BFGS-B',
                          options=dict(maxiter=1000, ftol=1e-12))
        if not result.success or not np.isfinite(result.x).all():
            raise RuntimeError('Presence fit did not converge')
        beta = result.x
    common = dict(schema=SCHEMA, features=list(FEATURES), mean=mean.tolist(), scale=scale.tolist(),
                  presenceWeights=beta.tolist(), maximumShiftSeconds=CONFIG['maximumShiftSeconds'],
                  approved=False, version=CONFIG['version'])
    models = []
    for name, fitted in heads.items():
        for threshold in CONFIG['deletionThresholds'] if learned_presence else [0.]:
            models.append(dict(**common, name=name + '_delete_' + str(threshold),
                               timingWeights=fitted['weights'], deleteThreshold=threshold))
    details = dict(trainingSongs=len(train), trainingPairs=len(paired), trainingPresenceCases=len(presence),
                   negativeCases=int(np.count_nonzero(y == 0)), presenceTrained=learned_presence,
                   timingFits=heads, intervalTargets=True, annotationsUsedForFeatures=False)
    return models, details


def evaluate(data, model, transform=None):
    records = []
    for item in data:
        row, before = item['row'], item['sections']
        after, changes = (transform or correct)(before, item['x'], model, row['duration'])
        scores = []
        for ref in row['references']:
            scores.append(dict(annotator=ref['annotator'], before=structure_score(ref, before),
                               after=structure_score(ref, after)))
        remaining = {s['id']: s for s in after}; intervals = []
        for e in item['examples']:
            if e['kind'] not in ('keep_boundary', 'move_boundary'):
                continue
            p, ref = e['prediction'], e['reference']
            distance = lambda t: max(ref['earliest'] - t, 0., t - ref['latest'])
            old_error = distance(p['start'])
            # Deleting a matched true transition is a miss, never a free MAE gain.
            new_error = distance(remaining[p['id']]['start']) if p['id'] in remaining else 3.
            intervals.append(dict(id=p['id'], before=old_error, after=new_error,
                                  wasGood=old_error <= .25, broken=old_error <= .25 and new_error > .5))
        records.append(dict(id=row['id'], artist=row['artist'], genre=row.get('genre'), scores=scores,
                            intervals=intervals, changes=changes, correctedSections=after))
    flat = [s for r in records for s in r['scores']]
    pairs = [s for r in records for s in r['intervals']]
    def mean(values):
        values = [v for v in values if v is not None]
        return float(np.mean(values)) if values else None
    def label_f1(score):
        count = score['referenceCount'] + score['predictionCount']
        return 2. * score['labelMatches'] / count if count else None
    summary = dict(songs=len(records), matchedConsensusPairs=len(pairs),
                   changes=sum(len(r['changes']) for r in records), removed=sum(c['kind'] == 'remove' for r in records for c in r['changes']))
    for side in ('before', 'after'):
        summary[side] = dict(f1HalfSecond=mean(s[side]['0.5']['f1'] for s in flat),
                             f1ThreeSeconds=mean(s[side]['3.0']['f1'] for s in flat),
                             labelF1HalfSecond=mean(label_f1(s[side]['0.5']) for s in flat),
                             intervalMAESeconds=mean(p[side] for p in pairs))
    good = sum(p['wasGood'] for p in pairs); broken = sum(p['broken'] for p in pairs)
    severe = []
    for r in records:
        delta = mean(s['after']['0.5']['f1'] - s['before']['0.5']['f1'] for s in r['scores']
                     if s['after']['0.5']['f1'] is not None and s['before']['0.5']['f1'] is not None)
        if delta is not None and delta < -CONFIG['gates']['maximumSongF1Loss'] - 1e-9:
            severe.append(r['id'])
    summary.update(previouslyGood=good, brokenGood=broken, brokenGoodFraction=broken / good if good else None,
                   severeRegressions=severe)
    return dict(summary=summary, records=records)


def gate(summary):
    before, after, g = summary['before'], summary['after'], CONFIG['gates']
    enough = summary['songs'] >= CONFIG['minimumEvaluationSongs'] and summary['matchedConsensusPairs'] >= CONFIG['minimumEvaluationPairs']
    valid = all(v is not None for v in [*before.values(), *after.values(), summary['brokenGoodFraction']])
    checks = dict(sufficientEvaluation=enough, measurable=valid)
    if valid:
        checks.update(f1Gain=after['f1HalfSecond'] - before['f1HalfSecond'] >= g['minimumF1Gain'],
                      intervalGain=before['intervalMAESeconds'] - after['intervalMAESeconds'] >= g['minimumIntervalMAEGain'],
                      looseF1Preserved=after['f1ThreeSeconds'] >= before['f1ThreeSeconds'] - g['maximumLooseF1Loss'],
                      labelsPreserved=after['labelF1HalfSecond'] >= before['labelF1HalfSecond'] - g['maximumLabelF1Loss'],
                      goodBoundariesPreserved=summary['brokenGoodFraction'] <= g['maximumBrokenGoodFraction'],
                      noSevereRegression=not summary['severeRegressions'])
    return dict(passed=all(checks.values()), checks=checks)


def fit_and_evaluate(data, output):
    by_split = {k: [r for r in data if r['split'] == k] for k in CONFIG['fractions']}
    frozen_path = output / 'frozen-model.json'
    dataset_sha = sha(output / 'dataset.json')
    feature_sha = sha(output / 'feature-manifest.json')
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text())
        if frozen['datasetSHA256'] != dataset_sha or frozen['featuresSHA256'] != feature_sha:
            raise ValueError('Frozen model belongs to another dataset')
    else:
        emit(output, 'training', trainingStarted=True, trainingSongs=len(by_split['train']))
        models, fitting = fit_heads(by_split['train'])
        emit(output, 'validating', trainingStarted=True, candidates=len(models))
        candidates = []
        for model in models:
            evaluated = evaluate(by_split['validation'], model)
            candidates.append(dict(model=model, validation=evaluated, gate=gate(evaluated['summary'])))
        def rank(candidate):
            s = candidate['validation']['summary']; a, b = s['after'], s['before']
            return (candidate['gate']['passed'], (a['f1HalfSecond'] or 0.) - (b['f1HalfSecond'] or 0.),
                    -(a['intervalMAESeconds'] or 0.), -s['changes'])
        best = max(candidates, key=rank)
        frozen = dict(model=best['model'], validation=best['validation'], validationGate=best['gate'],
                      fitting=fitting, datasetSHA256=dataset_sha, featuresSHA256=feature_sha, frozenAt=time.time(),
                      candidates=[dict(name=c['model']['name'], summary=c['validation']['summary'], gate=c['gate']) for c in candidates],
                      testUsedForSelection=False)
        # This commit is made before any final-test labels are evaluated.
        write(frozen_path, frozen)
    emit(output, 'testing_frozen_model', trainingStarted=True, frozenModelSHA256=sha(frozen_path))
    tested = evaluate(by_split['test'], frozen['model'])
    test_gate = gate(tested['summary'])
    passed = frozen['validationGate']['passed'] and test_gate['passed']
    report = dict(schema=1, completedAt=time.time(), trainingCompleted=True, modelInstalled=False,
                  candidatePassesDevelopmentGate=passed, externalBlindTest=False,
                  limitation='Held out from this corrector only; SongFormer pretraining overlap unknown. Structural timestamps, not beats or voiced cues.',
                  frozenModelSHA256=sha(frozen_path), datasetSHA256=dataset_sha, featuresSHA256=feature_sha,
                  fitting=frozen['fitting'], validation=frozen['validation']['summary'], validationGate=frozen['validationGate'],
                  test=tested['summary'], testGate=test_gate, testResults=tested['records'],
                  remainingErrors='No missing-boundary insertion, section relabelling, beat/downbeat correction or voice scheduling learned here.',
                  decision='candidate_requires_external_validation' if passed else 'rejected_keep_current_engine')
    write(output / 'report.json', report)
    write(output / 'cue-corrector-candidate.json', dict(**frozen['model'],
          passedDevelopmentGate=passed, reportSHA256=sha(output / 'report.json'), frozenModelSHA256=sha(frozen_path)))
    emit(output, 'complete', trainingStarted=True, trainingCompleted=True, candidatePassesDevelopmentGate=passed,
         decision=report['decision'], report=str(output / 'report.json'))
    return report


def run(manifest, analysis, output, wait=False):
    import fcntl
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.nice(10)
        try:
            rows, split, protocol = prepare(manifest, analysis, output)
            if (output / 'report.json').exists():
                # A completed run is immutable; never reselect on a seen test.
                report = json.loads((output / 'report.json').read_text())
                if report['frozenModelSHA256'] != sha(output / 'frozen-model.json') or report['datasetSHA256'] != sha(output / 'dataset.json') or report['featuresSHA256'] != sha(output / 'feature-manifest.json'):
                    raise ValueError('Completed experiment artifacts changed')
                return report
            await_analysis(analysis, output, rows, wait)
            # Check the seal again after waiting in case source files changed.
            prepare(manifest, analysis, output)
            emit(output, 'preparing_dataset', trainingStarted=False, totalSongs=len(rows))
            examples, snapshot = dataset_snapshot(manifest, analysis, output, rows, protocol)
            data = load_data(rows, analysis, output, split, examples, snapshot)
            if (output / 'STOP').exists():
                raise InterruptedError('STOP requested')
            return fit_and_evaluate(data, output)
        except InterruptedError as error:
            emit(output, 'paused', error=str(error)); return None
        except BaseException as error:
            emit(output, 'failed', error=type(error).__name__ + ': ' + str(error)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-for-analysis', action='store_true')
    args = parser.parse_args()
    run(args.manifest.resolve(), args.analysis.resolve(), args.output.resolve(), args.wait_for_analysis)
