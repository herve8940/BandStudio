"""Four real WAV inputs, human beat labels, real TTS, before/after guide audio.

Markers are deliberately close synthetic stress markers on annotated pulses;
they are NOT claims about the songs' verse/chorus structure.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from advanced import grid_from_frames
from rhythm_benchmark import score
from windows.project import fresh
import services

DATA=ROOT/'tmp/learning-benchmark/data'
OUT=ROOT/'output/cue-learning/audio-audit'
CASES=[
    ('rock','gtzan_rock_00040',ROOT/'tmp/learning-benchmark/audio/gtzan_rock_00040.wav'),
    ('blues','gtzan_blues_00047',ROOT/'tmp/learning-benchmark/audio/gtzan_blues_00047.wav'),
    ('hard rock','gtzan_metal_00067',ROOT/'tmp/cue-learning/hard-rock.wav'),
    ('pop','gtzan_pop_00075',ROOT/'tmp/cue-learning/pop.wav'),
]


def stats(result):
    waves=[sf.read(result['files'][k],dtype='float32')[0] for k in ('calls','cues','counts')]
    speaking=sum((abs(x[:,0])>.001).astype(int) for x in waves)
    counts=result['countEvents']
    duplicates=len(counts)-len({round(e['time'],6) for e in counts})
    return dict(overlapSeconds=float(np.count_nonzero(speaking>1)/44100),
                duplicateCountPulses=duplicates,announcements=len(result['events']),
                warnings=result.get('guideWarnings',[]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',type=Path,required=True,help='Prepared local BandStudio engine')
    parser.add_argument('--inference-only',action='store_true')
    args=parser.parse_args();engine=args.engine;inference_only=args.inference_only
    if inference_only:
        import torch
        from beat_this.inference import Audio2Frames
        torch.set_num_threads(4)
        predictor=Audio2Frames(checkpoint_path=str(engine/'rhythm/final0.ckpt'),device='cpu')
    ref_path=ROOT/'output/learning-benchmark/reference-engine/services.py'
    spec=importlib.util.spec_from_file_location('before_services',ref_path)
    before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
    OUT.mkdir(exist_ok=True)
    rows=[]
    for genre,key,audio in CASES:
        folder=OUT/key;folder.mkdir(exist_ok=True)
        signal,sr=sf.read(audio,dtype='float32',always_2d=True)
        evidence=folder/'audio-logits.npz'
        if evidence.exists():
            z=np.load(evidence,allow_pickle=False);beat,down=z['beat'],z['downbeat']
        else:
            if not inference_only:raise ValueError('Run --inference-only in the rhythm environment first')
            with torch.inference_mode():beat,down=predictor(signal.mean(axis=1),sr)
            beat,down=beat.cpu().numpy(),down.cpu().numpy()
            np.savez_compressed(evidence,beat=beat,downbeat=down)
        if inference_only:
            print(key+' audio inference cached',flush=True)
            continue
        grid=grid_from_frames(beat,down,len(signal)/sr,quality=False)
        reference=np.loadtxt(DATA/f'beat_this_annotations-1.0/gtzan/annotations/beats/{key}.beats',ndmin=2)
        p=fresh(key);p['tracks']=[dict(role='source',duration=len(signal)/sr,offset=0)]
        p['beats']=reference[:,0].tolist();p['bpm']=float(60/np.median(np.diff(reference[:,0])))
        p['settings'].update(voice='Thomas',speechRate=210,countClick=False,firstBeat=float(reference[reference[:,1]==1,0][0]))
        index=int(np.searchsorted(reference[:,0],12));first,second,target=reference[[index,index+2,index+5],0]
        p['sections']=[dict(id='a',name='Couplet',start=float(first),end=float(second)),
                       dict(id='b',name='Refrain',start=float(second),end=len(signal)/sr)]
        p['cues']=[dict(id='c',name='Attention à la reprise',time=float(target))]
        snapshot=folder/'snapshot.json';services.atomic(snapshot,p)
        metrics={}
        for name,module in [('before',before),('after',services)]:
            output=folder/name;output.mkdir(exist_ok=True)
            # Reuse identical speech samples on both sides of the comparison.
            if name=='after':shutil.copytree(folder/'before/voice',output/'voice',dirs_exist_ok=True)
            module.guides(snapshot,output/'result.json')
            result=json.loads((output/'result.json').read_text());metrics[name]=stats(result)
        assert metrics['after']['overlapSeconds']==0
        assert metrics['after']['duplicateCountPulses']==0
        assert metrics['after']['announcements']==3 and not metrics['after']['warnings']
        rows.append(dict(id=key,genre=genre,audioSHA256=hashlib.sha256(audio.read_bytes()).hexdigest(),
            audioBeatF1=score(reference[:,0],grid['beats']),**metrics))
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    if inference_only:return
    report=dict(referenceServicesSHA256=hashlib.sha256(ref_path.read_bytes()).hexdigest(),
        servicesSHA256=hashlib.sha256((ROOT/'desktop/studio/services.py').read_bytes()).hexdigest(),
        note=__doc__,results=rows)
    (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
