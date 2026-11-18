"""Locate decoder losses on development clips, never reuse the final test.

Compare identical frozen-network logits through the official decoder, through
BandStudio's bar calibration, and through the complete BandStudio decoder.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch
from beat_this.model.postprocessor import Postprocessor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from advanced import grid_from_frames
from services import calibrate_grid,before_beat
from large_scale_rhythm_learning import f1,labels_for,summarize
from cue_benchmark import sha,write


def measure(row,reference,beats,downbeats):
    result=dict(beatF1=f1(reference[:,0],beats),barF1=None,cueAccuracy=None)
    if row['hasDownbeats']:
        result['barF1']=f1(reference[reference[:,1]==1,0],downbeats)
        correct=[]
        for i in np.flatnonzero(reference[:,1]==1):
            for lead in (4,8):
                if i>=lead and reference[i-lead,0]>=5:
                    at=before_beat(float(reference[i,0]),lead,list(beats),120)
                    correct.append(abs(at-reference[i-lead,0])<=.07)
        result['cueAccuracy']=float(np.mean(correct)) if correct else None
    return result


def bars(grid):
    beats=np.asarray(grid['beats'])
    phase=int(np.argmin(abs(beats-grid['firstBeat']))) if len(beats) else 0
    return beats[phase::grid['beatsPerBar']]


def run(experiment,output):
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    m=json.loads((experiment/'manifest.json').read_text());decoder=Postprocessor();results=[]
    for row in m['excerpts']:
        if row['split']=='test':continue
        _,ref=labels_for(row,m);z=np.load(Path(m['features'])/(row['id']+'.npz'),allow_pickle=False)
        b,d=decoder(torch.from_numpy(z['beat']),torch.from_numpy(z['downbeat']))
        calibrated=calibrate_grid(dict(beats=b.tolist(),downbeats=d.tolist(),bpm=120,duration=row['duration']))
        current=grid_from_frames(z['beat'],z['downbeat'],row['duration'],quality=False)
        results.append(dict(id=row['id'],split=row['split'],style=row['style'],
            official=measure(row,ref,b,d),officialWithBarCalibration=measure(row,ref,b,bars(calibrated)),
            bandstudio=measure(row,ref,current['beats'],bars(current))))
        if len(results)%100==0:print(json.dumps(dict(completed=len(results))),flush=True)
    summary={}
    for split in ('train','validation'):
        summary[split]={}
        for candidate in ('official','officialWithBarCalibration'):
            rows=[dict(id=r['id'],style=r['style'],before=r['bandstudio'],after=r[candidate]) for r in results if r['split']==split]
            summary[split][candidate]=dict(overall=summarize(rows),styles={s:summarize([r for r in rows if r['style']==s])
                for s in ('rock','hard rock','blues','pop') if any(r['style']==s for r in rows)})
    write(output,dict(scope='Development diagnostics only; the previous final test is excluded. Identical original model weights for every decoder.',
        sourceManifestSHA256=sha(experiment/'manifest.json'),decoderSHA256=sha(ROOT/'desktop/studio/advanced.py'),
        servicesSHA256=sha(ROOT/'desktop/studio/services.py'),summary=summary,results=results))
    print(json.dumps({k:v['overall']['meanGain'] for k,v in summary['validation'].items()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();run(a.experiment,a.output)
