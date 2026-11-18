"""Supervised ranking of uncertain bar proposals; frozen beat network/beat times.

Only a separately validated, approved model can change the proposed meter/phase.
An adapted grid always remains subject to listening review. Manual project grids
are never inputs here: this runs only during a new advanced rhythm analysis.
"""
import hashlib
import json
import math
from pathlib import Path

MODEL_PATH = Path(__file__).with_name('rhythm-adapter.json')
BASE_FEATURES = ('barMean', 'barLow', 'barPositive', 'barMass', 'otherMean',
            'contrast', 'intervalCV', 'coverage', 'meter2', 'meter3',
            'meter4', 'meter6', 'barMeanMeter4', 'contrastMeter4',
            'softF1', 'confidentF1', 'strongF1', 'logitContrast', 'meter5', 'meter7')
FEATURES = BASE_FEATURES + tuple(a+'*'+b for i,a in enumerate(BASE_FEATURES) for b in BASE_FEATURES[i:])


def fingerprint(beats):
    return hashlib.sha256(json.dumps(beats, separators=(',', ':')).encode()).hexdigest()


def proposals(result, logits, fps=50):
    import numpy as np
    beats = np.asarray(result.get('beats', []), dtype=float)
    down = np.asarray(logits, dtype=float).reshape(-1)
    if len(beats) < 16 or not len(down): return []
    frames = np.clip(np.rint(beats*fps).astype(int), 0, len(down)-1)
    strengths = np.array([max(down[max(0, f-2):f+3]) for f in frames])
    probability = 1/(1+np.exp(-np.clip(strengths, -30, 30)))
    base = (int(result['beatsPerBar']), int(np.argmin(abs(beats-result['firstBeat']))))
    candidates = [base] + [(m, p) for m in range(2,13) for p in range(m) if (m, p) != base]
    output = []
    for meter, phase in candidates:
        mask = np.arange(len(beats)) % meter == phase % meter
        indices = np.flatnonzero(mask)
        if len(indices) < 3: continue
        on, off = probability[mask], probability[~mask]
        spans = np.diff(beats[indices]); mean = float(np.mean(on))
        other = float(np.mean(off))
        values = [mean, float(np.quantile(on, .25)), float(np.mean(on > .5)),
                  float(on.sum()/max(.001, probability.sum())), other, mean-other,
                  min(2., float(np.std(spans)/np.median(spans))),
                  float((beats[indices[-1]]-beats[indices[0]])/max(.1, beats[-1]-beats[0])),
                  float(meter==2), float(meter==3), float(meter==4), float(meter==6),
                  mean*(meter==4), (mean-other)*(meter==4),
                  float(2*on.sum()/(mask.sum()+probability.sum())),
                  float(2*np.count_nonzero(strengths[mask]>1.4)/(mask.sum()+np.count_nonzero(strengths>1.4))),
                  float(2*np.count_nonzero(strengths[mask]>3)/(mask.sum()+np.count_nonzero(strengths>3))),
                  float((np.clip(strengths[mask],-8,8).mean()-np.clip(strengths[~mask],-8,8).mean())/8),
                  float(meter==5), float(meter==7)]
        expanded=values+[a*b for i,a in enumerate(values) for b in values[i:]]
        output.append(dict(meter=meter, phase=phase, firstBeat=float(beats[phase]), features=expanded))
    return output


def choose(result, downbeat_logits, model, fps=50):
    import numpy as np
    if not result.get('gridReviewRequired', True): return None
    items = proposals(result, downbeat_logits, fps)
    if not items: return None
    x = np.asarray([r['features'] for r in items])
    gain = ((x-x[0])/np.asarray(model['scale'])) @ np.asarray(model['weights'])
    index = int(gain.argmax())
    return {**items[index], 'predictedGain':float(gain[index])} if index and gain[index] >= model['margin'] else None


def adapt(result, beat_logits, downbeat_logits, fps=50):
    try:
        model = json.loads(MODEL_PATH.read_text())
        if model['schema'] != 1 or model['approved'] is not True or model['features'] != list(FEATURES): return result
        if any(len(model[k]) != len(FEATURES) for k in ('scale', 'weights')): return result
        if not all(math.isfinite(v) for v in [*model['scale'], *model['weights'], model['margin']]): return result
        if min(model['scale']) <= 0 or model['margin'] < 0: return result
        proposal = choose(result, downbeat_logits, model, fps)
        if proposal is None: return result
        from services import calibrate_grid
        return calibrate_grid({**result, 'learnedReviewRequired':True,
            'learnedBarProposal':dict(meter=proposal['meter'], firstBeat=proposal['firstBeat'],
                beatsSHA256=fingerprint(result['beats']), version=model['version']),
            'barAdaptation':dict(previousMeter=result['beatsPerBar'], previousFirstBeat=result['firstBeat'],
                predictedGain=round(proposal['predictedGain'], 4))})
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return result
