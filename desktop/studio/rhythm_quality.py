"""Small supervised quality calibrator, separate from the frozen beat network.

It can request human review; it never invents beats, changes a protected grid,
or promotes a doubtful grid to automatic. Fitted offline from labelled music.
"""
import json
import math
from pathlib import Path

FEATURES = ('agreement', 'phase', 'tempoVariation', 'beatStrength',
            'weakBeatFraction', 'barStrength', 'barSupport', 'offGridFraction')
MODEL_PATH = Path(__file__).with_name('rhythm-quality.json')


def features(result, beat_logits, downbeat_logits, fps=50):
    import numpy as np
    beats=np.asarray(result.get('beats',[]),dtype=float)
    logits=np.asarray(beat_logits,dtype=float).reshape(-1)
    down=np.asarray(downbeat_logits,dtype=float).reshape(-1)
    if len(beats)<4 or not len(logits):return None
    indices=np.clip(np.rint(beats*fps).astype(int),0,len(logits)-1)
    intervals=np.diff(beats);period=float(np.median(intervals))
    if period<=0:return None
    phase=int(np.argmin(abs(beats-result['firstBeat'])))
    bar_indices=indices[phase::max(1,int(result['beatsPerBar']))]
    strengths=logits[indices]
    # How much confident beat evidence is left outside the decoded pulse path?
    peaks=np.flatnonzero((logits[1:-1]>logits[:-2]) & (logits[1:-1]>=logits[2:]) & (logits[1:-1]>0))+1
    insertion=np.searchsorted(indices,peaks)
    distances=np.minimum(abs(peaks-indices[np.clip(insertion,0,len(indices)-1)]),
                         abs(peaks-indices[np.clip(insertion-1,0,len(indices)-1)]))
    values=[result.get('agreement',0),result.get('phaseConfidence',0),
            min(2.,float(np.std(intervals)/period)),float(np.percentile(strengths,25))/8,
            float(np.mean(strengths<0)),float(np.median(down[bar_indices]))/8,
            float(np.mean(down[bar_indices]>0)),float(np.mean(distances>fps*.07)) if len(peaks) else 0.]
    return values if all(math.isfinite(x) for x in values) else None


def probability(values, model):
    if values is None:return 0.
    z=model['intercept']+sum(w*(x-m)/s for x,m,s,w in zip(values,model['mean'],model['scale'],model['weights']))
    return 1/(1+math.exp(-max(-40.,min(40.,z))))


def assess(result, beat_logits, downbeat_logits, fps=50):
    try:
        model=json.loads(MODEL_PATH.read_text())
        if model['schema']!=1 or model['features']!=list(FEATURES) or model['approved'] is not True:return result
        if any(len(model[key])!=len(FEATURES) for key in ('mean','scale','weights')):return result
        numbers=[model['intercept'],model['threshold'],*model['mean'],*model['scale'],*model['weights']]
        if not all(math.isfinite(x) for x in numbers) or min(model['scale'])<=0 or not 0<=model['threshold']<=1:return result
        value=probability(features(result,beat_logits,downbeat_logits,fps),model)
        from services import calibrate_grid
        return calibrate_grid({**result,'learnedQuality':round(value,4),
            'learnedReviewRequired':value<model['threshold'],'qualityModel':model['version']})
    except (OSError,ValueError,KeyError,TypeError):
        return result
