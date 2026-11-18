"""Experimental supervised structure correction; no automatic model loading.

Inputs are audio and fresh section predictions, never human reference labels.
The training tool calls this module explicitly. Installing/approving a model is
a separate operation. This does not change beats, meter, or spoken cue timing.
"""
from __future__ import annotations

import copy
import math
import unicodedata

import numpy as np

SCHEMA = 1
LABELS = ('intro', 'verse', 'chorus', 'prechorus', 'bridge', 'inst', 'outro')
OFFSETS = (-.6, -.3, 0., .3, .6)
FEATURES = (
    'previousDuration', 'duration', 'position', 'samePreviousLabel',
    *(f'current:{x}' for x in LABELS), *(f'previous:{x}' for x in LABELS),
    *(f'{kind}@{offset}' for kind in ('energy', 'flux', 'noveltyShort', 'noveltyLong') for offset in OFFSETS),
    *(f'{kind}:{part}' for kind in ('flux', 'noveltyShort', 'noveltyLong') for part in ('peakOffset', 'peakHeight')),
)


def normalized_label(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if c.isalpha())
    return {'couplet': 'verse', 'refrain': 'chorus', 'prerefrain': 'prechorus',
            'pont': 'bridge', 'instrumental': 'inst', 'solo': 'inst'}.get(value, value)


def audio_features(path):
    """20 ms audio descriptors, independent of annotations and model targets."""
    import soundfile as sf
    from scipy.signal import resample_poly, stft
    audio, sr = sf.read(path, dtype='float32', always_2d=True)
    duration = len(audio) / sr
    mono = audio.mean(axis=1)
    del audio
    if sr != 8000:
        divisor = math.gcd(sr, 8000)
        mono = resample_poly(mono, 8000 // divisor, sr // divisor)
    if len(mono) < 512 or not np.isfinite(mono).all():
        raise ValueError('Audio is too short or non-finite')
    freq, times, spectrum = stft(mono, fs=8000, window='hann', nperseg=512,
                                 noverlap=352, boundary=None, padded=False)
    power = np.abs(spectrum) ** 2
    del spectrum, mono
    edges = (0, 70, 140, 280, 560, 1120, 2240, 3200, 4001)
    bands = np.stack([np.log1p(1e6 * power[(freq >= lo) & (freq < hi)].mean(axis=0))
                      for lo, hi in zip(edges, edges[1:])], axis=1)
    energy = np.log1p(1e6 * power.mean(axis=0))
    del power
    bands = (bands - np.median(bands, axis=0)) / np.maximum(bands.std(axis=0), .2)
    flux = np.r_[0., np.maximum(np.diff(bands, axis=0), 0.).mean(axis=1)]
    novelty = []
    for seconds in (.25, 1.):
        width = max(1, round(seconds / .02))
        padded = np.pad(bands, ((width, width), (0, 0)), mode='edge')
        sums = np.vstack([np.zeros((1, bands.shape[1])), np.cumsum(padded, axis=0)])
        indices = np.arange(len(bands)) + width
        before = (sums[indices] - sums[indices - width]) / width
        after = (sums[indices + width + 1] - sums[indices + 1]) / width
        novelty.append(np.sqrt(np.mean((after - before) ** 2, axis=1)))
    curves = np.stack([energy, flux, *novelty], axis=1)
    # Per-recording unsupervised scaling is also available at inference time.
    curves = (curves - np.median(curves, axis=0)) / np.maximum(curves.std(axis=0), .05)
    return dict(times=times, curves=np.clip(curves, -8., 8.), duration=duration)


def boundary_features(sections, audio, duration):
    times, curves = np.asarray(audio['times']), np.asarray(audio['curves'])
    rows = []
    for i, section in enumerate(sections):
        t = float(section['start'])
        previous = sections[max(0, i - 1)]
        name, prev = normalized_label(section['name']), normalized_label(previous['name'])
        values = [np.log1p(max(0., t - previous['start'])) / 6.,
                  np.log1p(max(0., section['end'] - t)) / 6., t / max(duration, 1.), float(name == prev)]
        values += [float(name == label) for label in LABELS] + [float(prev == label) for label in LABELS]
        for channel in range(4):
            values += np.interp(t + np.asarray(OFFSETS), times, curves[:, channel]).tolist()
        local = np.flatnonzero((times >= t - 1.) & (times <= t + 1.))
        for channel in (1, 2, 3):
            if len(local):
                peak = local[int(np.argmax(curves[local, channel]))]
                values += [float(times[peak] - t), float(curves[peak, channel])]
            else:
                values += [0., 0.]
        rows.append(values)
    result = np.asarray(rows, dtype=float).reshape(-1, len(FEATURES))
    if not np.isfinite(result).all():
        raise ValueError('Non-finite boundary features')
    return result


def standardized(x, model):
    if model['schema'] != SCHEMA or model['features'] != list(FEATURES):
        raise ValueError('Incompatible corrector features')
    mean, scale = np.asarray(model['mean']), np.asarray(model['scale'])
    if mean.shape != (len(FEATURES),) or scale.shape != mean.shape or not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
        raise ValueError('Invalid corrector normalization')
    return np.c_[np.ones(len(x)), np.clip((np.asarray(x) - mean) / scale, -5., 5.)]


def timing_shifts(design, model):
    coefficients = np.asarray(model['timingWeights'])
    if coefficients.shape != (design.shape[1],) or not np.isfinite(coefficients).all():
        raise ValueError('Invalid timing model')
    maximum = float(model['maximumShiftSeconds'])
    if not 0 <= maximum <= 1.:
        raise ValueError('Unsafe maximum shift')
    raw = design @ coefficients
    guard = model.get('uncertaintyGuard')
    if guard is not None:
        if guard.get('kind') != 'ensemble_abstention' or maximum > .25 or model.get('deleteThreshold', 0.) != 0.:
            raise ValueError('Invalid conservative correction policy')
        alternatives = np.asarray(guard['alternativeWeights'])
        tolerance = float(guard['maximumDisagreementSeconds'])
        if alternatives.shape != (2, design.shape[1]) or not np.isfinite(alternatives).all() or not 0 < tolerance <= .15:
            raise ValueError('Invalid correction uncertainty guard')
        proposals = np.c_[raw, design @ alternatives.T]
        # Disagreement is measured BEFORE clipping; clipping must not conceal
        # an unstable estimate. No title, annotation, or reference time is used.
        uncertain = np.ptp(proposals, axis=1) > tolerance
        opposing = (proposals.min(axis=1) < -.02) & (proposals.max(axis=1) > .02)
        raw = np.where(uncertain | opposing | (np.abs(raw) < .02), 0., raw)
    return np.clip(raw, -maximum, maximum)


def correct(sections, features, model, duration):
    """Apply a bounded experimental model to fresh predictions only.

    Any manual, reviewed, locked, or provenance-free section vetoes the entire
    operation, including changes to adjacent ends. Labels are never rewritten.
    """
    original = copy.deepcopy(sections)
    if not sections or any(s.get('locked') or s.get('reviewed') or s.get('origin') != 'analysis' for s in sections):
        return original, []
    starts = np.asarray([s['start'] for s in sections], dtype=float)
    if not np.isfinite(starts).all() or not math.isfinite(duration) or duration <= starts[-1] or starts[0] < 0 or (np.diff(starts) <= 0).any():
        raise ValueError('Invalid section timeline')
    if len(features) != len(sections):
        raise ValueError('Boundary feature count differs from sections')
    design = standardized(features, model)
    shifts = timing_shifts(design, model)
    threshold = float(model.get('deleteThreshold', 0.))
    if not 0 <= threshold <= .1:
        raise ValueError('Unsafe deletion threshold')
    positive = np.ones(len(sections))
    if threshold:
        weights = np.asarray(model['presenceWeights'])
        if weights.shape != (design.shape[1],) or not np.isfinite(weights).all():
            raise ValueError('Invalid presence model')
        positive = 1. / (1. + np.exp(-np.clip(design @ weights, -30., 30.)))
    kept, changes = [copy.deepcopy(sections[0])], []
    for i in range(1, len(sections)):
        section, t = copy.deepcopy(sections[i]), starts[i]
        # Short fragments only; classifier scores are not calibrated confidence.
        remove = threshold > 0 and positive[i] < threshold and section['end'] - t <= 12. and t - starts[i-1] >= 2.
        if remove:
            changes.append(dict(id=section.get('id'), kind='remove', before=float(t), presenceScore=float(positive[i])))
            continue
        next_start = starts[i+1] if i+1 < len(starts) else duration
        lo, hi = (starts[i-1] + t) / 2., (t + next_start) / 2.
        changed = float(np.clip(t + shifts[i], lo + 1e-6, hi - 1e-6))
        section['start'] = changed
        if abs(changed - t) > 1e-6:
            changes.append(dict(id=section.get('id'), kind='move', before=float(t), after=changed))
        kept.append(section)
    for left, right in zip(kept, kept[1:]):
        left['end'] = right['start']
    kept[-1]['end'] = duration
    return kept, changes
