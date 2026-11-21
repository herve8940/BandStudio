"""Reproducible supervised rhythm benchmark; never edits a user's projects.

Inputs: Zenodo 13922116 gtzan.zip and beat_this_annotations.zip, extracted
under --data. The official log-mel inputs bypass audio decoding only; the
installed Beat This network and BandStudio decoder both run for every excerpt.
GTZAN was excluded from final0's training. Our splits are for the calibrator,
not a claim that GTZAN recordings/artists are all independent.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))


def score(reference, estimated, tolerance=.07, min_time=5., max_time=float('inf')):
    """One-to-one ordered matching, 70 ms tolerance, ignoring first 5 s."""
    ref = sorted(t for t in reference if min_time <= t < max_time)
    est = sorted(t for t in estimated if min_time <= t < max_time)
    i = j = hits = 0
    while i < len(ref) and j < len(est):
        if abs(ref[i]-est[j]) <= tolerance:
            hits += 1; i += 1; j += 1
        elif est[j] < ref[i]: j += 1
        else: i += 1
    return 2*hits/(len(ref)+len(est)) if ref or est else 0.


def precision_metrics(reference, estimated):
    """Expose opening errors and sub-frame precision, in addition to MIR F1.

    Nearest-reference error alone hides missing/extra beats, so always report
    it alongside one-to-one F1 at the correct metric level, including t=0.
    """
    ref, est = np.asarray(reference), np.asarray(estimated)
    errors = [float(np.min(abs(est-t)))*1000 for t in ref] if len(est) else []
    return dict(fullF1_20ms=score(ref, est, .02, 0),
                introF1_20ms=score(ref, est, .02, 0, 10),
                introF1_70ms=score(ref, est, .07, 0, 10),
                nearestP95Ms=float(np.percentile(errors, 95)) if errors else None)


def select(data, exclude=(), holdout=False):
    """Select complexity BEFORE inference, independently within fixed ID blocks."""
    directory = data/'beat_this_annotations-1.0/gtzan/annotations/beats'
    result = []
    for genre in ('classical', 'jazz', 'reggae', 'metal', 'blues', 'rock'):
        partitions=(('test',0,99,10),) if holdout else (('train',0,59,12), ('validation',60,79,4), ('test',80,99,4))
        for split, low, high, count in partitions:
            candidates = []
            for path in sorted(directory.glob(f'gtzan_{genre}_*.beats')):
                number = int(path.stem.rsplit('_',1)[-1])
                if not low <= number <= high or path.stem in exclude: continue
                values = np.loadtxt(path, ndmin=2)
                if len(values) < 8 or values.shape[1] != 2: continue
                intervals = np.diff(values[:,0]); median = np.median(intervals)
                if median <= 0: continue
                variation = float(np.std(intervals)/median)
                meters = np.diff(np.flatnonzero(values[:,1] == 1))
                unusual = float(np.mean(meters != 4)) if len(meters) else 0
                complexity = variation + .2*unusual
                candidates.append(dict(id=path.stem, split=split, genre=genre,
                    complexity=complexity, intervalCV=variation,
                    unusualBarFraction=unusual, annotation=str(path.relative_to(data))))
            result.extend(sorted(candidates,key=lambda x:(-x['complexity'], x['id']))[:count])
    return result


def run(args):
    import torch
    from beat_this.inference import Spect2Frames
    from advanced import grid_from_frames
    args.output.mkdir(parents=True,exist_ok=True)
    checkpoint=args.engine/'rhythm/final0.ckpt'
    checksum=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if checksum != '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331':
        raise ValueError('Unexpected model; benchmark identity would be ambiguous')
    excluded=json.loads(args.exclude.read_text()) if args.exclude else []
    rows=select(args.data,{r['id'] for r in excluded},bool(args.exclude))
    manifest=dict(schema=1, source='https://zenodo.org/records/13922116',
        checkpointSHA256=checksum, selection='Highest annotated interval variability and non-4 bars within preassigned ID blocks',
        limitation='Small targeted corpus; adjacent IDs separated by split, exact duplicates rejected; artist independence not guaranteed. No full-song structure labels.', excerpts=rows)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    spectrograms=np.load(args.data/'gtzan.npz',allow_pickle=False)
    torch.set_num_threads(4)
    predictor=Spect2Frames(checkpoint_path=str(checkpoint),device='cpu')
    seen={r['inputSHA256']:r['id'] for r in excluded}; results=[]
    for n,row in enumerate(rows):
        key=row['id'];spect=np.asarray(spectrograms[key+'/track'],dtype=np.float32)
        digest=hashlib.sha256(spect.tobytes()).hexdigest()
        if digest in seen:
            print('SKIP exact duplicate',key,seen[digest],flush=True);continue
        seen[digest]=key
        evidence=args.output/(key+'.npz'); started=time.monotonic()
        if evidence.exists():
            saved=np.load(evidence,allow_pickle=False)
            if str(saved['inputSHA256']) != digest: raise ValueError('Stale evidence')
            beat, down=saved['beat'],saved['downbeat']
        else:
            beat,down=predictor(torch.from_numpy(spect))
            beat,down=beat.cpu().numpy(),down.cpu().numpy()
            np.savez_compressed(evidence,beat=beat,downbeat=down,duration=len(spect)/50,inputSHA256=digest)
        result=grid_from_frames(beat,down,len(spect)/50,quality=False)
        annotation=np.loadtxt(args.data/row['annotation'],ndmin=2)
        beats=np.asarray(result['beats'])
        phase=int(np.argmin(abs(beats-result['firstBeat']))) if len(beats) else 0
        bars=beats[phase::result['beatsPerBar']]
        metric=dict(beatF1=score(annotation[:,0],beats),barF1=score(annotation[annotation[:,1]==1,0],bars),
                    **precision_metrics(annotation[:,0], beats))
        results.append({**row,**metric, 'grid':result, 'inputSHA256':digest})
        (args.output/'baseline.json').write_text(json.dumps(results,indent=2))
        print(f'{n+1}/{len(rows)} {key} {row["split"]}: beat={metric["beatF1"]:.3f} bar={metric["barF1"]:.3f} ({time.monotonic()-started:.1f}s)',flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exclude',type=Path,help='Prior baseline: reserve 60 new excerpts for a fresh holdout; reject cross-run exact duplicates')
    run(p.parse_args())
