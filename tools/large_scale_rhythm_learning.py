"""Resumable, local fine-tuning of Beat This's 1,026-parameter output head.

The 20M-parameter acoustic backbone is frozen. Human labels supervise training;
predictions are never treated as labels. Artist/work grouping, previous-exposure
exclusions, a frozen protocol and a single held-out test prevent leakage.
This experiment NEVER installs weights or edits a BandStudio project.
"""
from __future__ import annotations
import argparse
import collections
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time
import unicodedata

import numpy as np

CHECKPOINT_SHA = '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
HARD_ROCK = {'acdc', 'ledzeppelin', 'queen', 'defleppard', 'deeppurple', 'bonjovi', 'gunsnroses', 'scorpions'}
METRICS = ('beatF1', 'barF1', 'cueAccuracy')
DECODER_FILES = ('advanced.py', 'services.py', 'listening.py', 'musical_timing.py',
                 'platform_tools.py', 'analysis_progress.py', 'rhythm_quality.py', 'rhythm_adapter.py')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(2**20): h.update(block)
    return h.hexdigest()


def atomic(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.partial')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False))
    os.replace(tmp, path)


def save_npz(path, **arrays):
    path = Path(path); tmp = path.with_name(path.name+'.partial')
    with tmp.open('wb') as f: np.savez(f, **arrays)
    os.replace(tmp, path)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalized(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return re.sub(r'[^a-z0-9]', '', text)


def style(artist, genre):
    if normalized(artist) in HARD_ROCK: return 'hard rock'
    return genre if genre in ('rock', 'blues', 'pop') else 'other'


def prepare(repo, output, engine):
    if (output/'manifest.json').exists(): raise ValueError('Experiment already prepared; resume it instead of replacing its split.')
    data = repo/'tmp/learning-benchmark/data'
    annotation_root = data/'beat_this_annotations-1.0/gtzan/annotations/beats'
    index_path = repo/'tmp/cue-learning/index.txt'
    metadata = {}
    for line in index_path.read_text().splitlines():
        if ':::' not in line: continue
        filename, artist, title = map(str.strip, line.split(':::'))
        genre, number, _ = filename.split('.')
        metadata[f'gtzan_{genre}_{number}'] = (artist, title, genre)
    prior = {p.stem for folder in ('tmp/learning-benchmark/run', 'tmp/learning-benchmark/holdout', 'tmp/cue-learning/evidence')
             for p in (repo/folder).glob('*.npz')}
    specs = np.load(data/'gtzan.npz', allow_pickle=False)
    rows=[]; excluded=[]; hashes={}; songs={}
    for key in sorted(k.removesuffix('/track') for k in specs.files):
        path=annotation_root/(key+'.beats'); labels=np.loadtxt(path, ndmin=2)
        artist, title, genre=metadata.get(key, ('','','unknown'))
        reason=None
        if not artist or not title: reason='unidentified_artist_or_title'
        elif len(labels)<16 or labels.shape[1] not in (1,2) or not np.isfinite(labels).all(): reason='invalid_annotations'
        elif np.any(np.diff(labels[:,0])<=0): reason='nonincreasing_annotations'
        spec=np.asarray(specs[key+'/track']); sha=hashlib.sha256(spec.tobytes()).hexdigest()
        identity=(normalized(artist), normalized(re.sub(r'\(v\d+\)', '', title)))
        if sha in hashes: reason='exact_duplicate:'+hashes[sha]
        elif identity in songs: reason='repeated_artist_title:'+songs[identity]
        if reason:
            excluded.append(dict(id=key,reason=reason)); continue
        hashes[sha]=key; songs[identity]=key
        rows.append(dict(id=key,artist=artist,title=title,genre=genre,style=style(artist,genre),
                         frames=len(spec),duration=len(spec)/50,hasDownbeats=labels.shape[1]==2,
                         inputSHA256=sha,annotationSHA256=digest(path),previouslyEvaluated=key in prior))
    # Connected components keep collaborators and identically named works in
    # one partition. Short generic titles such as "Intro" are not work IDs.
    parent={normalized(r['artist']):normalized(r['artist']) for r in rows}
    def find(a):
        parent.setdefault(a,a)
        while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
        return a
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[max(a,b)]=min(a,b)
    works={}
    for r in rows:
        a=normalized(r['artist'])
        for member in r['artist'].split(';'): union(a,normalized(member))
        work=normalized(re.sub(r'\(v\d+\)', '',r['title']))
        if len(work)>=10:
            if work in works: union(a,works[work])
            else: works[work]=a
    for r in rows:r['group']=find(normalized(r['artist']))
    # Search for coverage using metadata only, NEVER model outcomes. Previously
    # evaluated clips of test artists are excluded, not moved into training.
    for seed in range(20261118,20262118):
        partitions={g:('train' if (v:=int(hashlib.sha256(f'{seed}:{g}'.encode()).hexdigest()[:8],16)/2**32)<.7
                       else 'validation' if v<.85 else 'test') for g in {r['group'] for r in rows}}
        counts=collections.Counter(); coverage=collections.Counter()
        for r in rows:
            split=partitions[r['group']]
            if split=='test' and r['previouslyEvaluated']:continue
            counts[split]+=1;coverage[split,r['style']]+=1
        if (counts['train']>=450 and counts['validation']>=80 and counts['test']>=80
            and all(coverage[s,g]>=5 for s in ('validation','test') for g in ('rock','hard rock','blues','pop'))):break
    else: raise ValueError('Could not form independent, style-covered splits from this corpus')
    kept=[]
    for r in rows:
        split=partitions[r['group']]
        if split=='test' and r['previouslyEvaluated']:
            excluded.append(dict(id=r['id'],reason='previously_evaluated_test_artist')); continue
        kept.append({**r,'split':split})
    output.mkdir(parents=True,exist_ok=True)
    decoder=output/'decoder';decoder.mkdir()
    for name in DECODER_FILES:
        shutil.copy2(repo/'desktop/studio'/name,decoder/name)
    shutil.copy2(Path(__file__),output/'runner.py')
    checkpoint=engine/'rhythm/final0.ckpt'
    if digest(checkpoint)!=CHECKPOINT_SHA:raise ValueError('Unexpected base model')
    manifest=dict(schema=1,created=now(),seed=seed,inventoryCount=len(specs.files),excerpts=kept,excluded=excluded,
        splitCounts=dict(collections.Counter(r['split'] for r in kept)),
        styleCoverage={s:dict(collections.Counter(r['style'] for r in kept if r['split']==s)) for s in ('train','validation','test')},
        data=str(data/'gtzan.npz'),annotationRoot=str(annotation_root),checkpoint=str(checkpoint),checkpointSHA256=CHECKPOINT_SHA,
        features=str(repo/'tmp/learning-scale-1000/features'),
        sources=['https://zenodo.org/records/13922116','https://github.com/boblsturm/GTZAN/blob/main/index.txt',
                 'https://github.com/CPJKU/beat_this'],
        indexSHA256=digest(index_path),spectrogramArchiveSHA256=digest(data/'gtzan.npz'),runnerSHA256=digest(output/'runner.py'),
        decoderSHA256={p.name:digest(p) for p in decoder.glob('*.py')},
        selection='All identified unique GTZAN inputs; artist/collaborator/work components, approximately 70/15/15 split. First metadata-only seed with >=80 validation/test tracks and >=5 each target style. Previously evaluated test clips excluded.',
        limitation='30-second excerpts, not 1,000 full songs; styles are artist pools with crossover. Classical artist names can denote composers. Not a benchmark of verse/chorus recognition.')
    atomic(output/'manifest.json',manifest)
    protocol=dict(method='Fine-tune only SumHead linear weights/bias on frozen 512-dimensional acoustic representations; 1,026 trainable parameters.',
        baseCheckpointSHA256=CHECKPOINT_SHA,epochs=12,evaluateEpochs=[1,3,6,12],learningRate=.0003,
        batchSize=8,threads=2,targetStyleWeight=3,positiveWeights={'beat':19,'downbeat':86},shiftToleranceFrames=3,
        distillationWeight=.02,blendCandidates=[.25,.5,1.],seed=seed,
        selection='Best validation mean of beat F1, bar F1 and cue anticipation accuracy, among candidates passing validation gates; otherwise best validation score remains research-only.',
        gate=dict(minMeanGain=.01,minCueGain=.005,maxMetricDrop=.002,maxStyleMeanDrop=.01,
                  maxHarmfulFraction=.02,noCorrectTrackBroken=True),
        testing='70 ms one-to-one F1 after first 5 s. Cue anticipation: leads of 4/8 beats before annotated downbeats; correct within 70 ms. One final held-out test after freezing model; no test-driven retuning.',
        deployment='Never install automatically. A passed gate produces a candidate for separate integration and listening checks.',
        limits='No uploads, no paid compute, CPU-only, two torch threads, low priority; stop/resume at a track or epoch boundary.')
    atomic(output/'protocol.json',protocol)
    atomic(output/'seal.json',dict(manifestSHA256=digest(output/'manifest.json'),protocolSHA256=digest(output/'protocol.json')))
    atomic(output/'status.json',dict(stage='prepared',updated=now(),inventoryCount=manifest['inventoryCount'],retained=len(kept),splitCounts=manifest['splitCounts']))
    print(json.dumps({k:manifest[k] for k in ('inventoryCount','splitCounts','styleCoverage')},indent=2))


class Progress:
    def __init__(self,output):self.output=output;self.started=time.time()
    def write(self,stage,**values):
        status=dict(stage=stage,pid=os.getpid(),updated=now(),elapsedSeconds=round(time.time()-self.started),**values)
        atomic(self.output/'status.json',status)
        print(json.dumps(status,ensure_ascii=False),flush=True)
    def check(self):
        if (self.output/'STOP').exists():
            self.write('paused',message='STOP requested; remove STOP and resume with --run.');raise InterruptedError('STOP requested')
        if shutil.disk_usage(self.output).free<2*1024**3:raise RuntimeError('Less than 2 GiB free; resume after freeing space.')


def extract_features(model,spect):
    """Same chunks/overlap as Spect2Frames; keep full-precision head inputs."""
    import torch
    from beat_this.inference import split_piece, aggregate_prediction
    chunks,starts=split_piece(spect,1500,border_size=6,avoid_short_end=True)
    captured=[]
    hook=model.task_heads.register_forward_pre_hook(lambda _,args:captured.append(args[0].detach()[0]))
    try:
        with torch.inference_mode():predictions=[model(c.unsqueeze(0)) for c in chunks]
    finally:hook.remove()
    predictions=[{k:v[0] for k,v in p.items()} for p in predictions]
    beat,down=aggregate_prediction(predictions,starts,len(spect),1500,6,'keep_first',spect.device)
    features=torch.zeros((len(spect),captured[0].shape[-1]),dtype=torch.float32)
    for start,part in reversed(list(zip(starts,captured))):
        features[start+6:start+6+len(part)-12]=part[6:-6]
    with torch.inference_mode():reconstructed=model.task_heads(features.unsqueeze(0))
    error=max(float(torch.max(abs(reconstructed[k][0]-v))) for k,v in (('beat',beat),('downbeat',down)))
    if error>.0001:raise ValueError(f'Feature reconstruction differs from official inference: {error}')
    return features.numpy(),beat.numpy(),down.numpy(),error


def extract(manifest,output,progress,limit=None):
    import torch
    from beat_this.inference import load_model
    features=Path(manifest['features']);features.mkdir(parents=True,exist_ok=True)
    model=load_model(manifest['checkpoint'],device='cpu');model.eval()
    head=model.task_heads.beat_downbeat_lin
    if head.weight.shape!=(2,512):raise ValueError('Unexpected output architecture')
    save_npz(output/'initial-head.npz',weight=head.weight.detach().numpy(),bias=head.bias.detach().numpy())
    specs=np.load(manifest['data'],allow_pickle=False)
    rows=manifest['excerpts'][:limit] if limit else manifest['excerpts']
    elapsed=[]
    for i,row in enumerate(rows):
        progress.check();stem=features/row['id'];meta=stem.with_suffix('.json')
        if meta.exists() and stem.with_suffix('.npy').exists() and stem.with_suffix('.npz').exists():
            record=json.loads(meta.read_text())
            if record['inputSHA256']!=row['inputSHA256'] or record['checkpointSHA256']!=CHECKPOINT_SHA:raise ValueError('Stale feature cache')
        else:
            start=time.monotonic();spec=np.asarray(specs[row['id']+'/track'])
            if hashlib.sha256(spec.tobytes()).hexdigest()!=row['inputSHA256']:raise ValueError('Input changed')
            x,beat,down,error=extract_features(model,torch.from_numpy(spec.astype('float32')))
            tmp=stem.with_suffix('.npy.partial')
            with tmp.open('wb') as f:np.save(f,x,allow_pickle=False)
            os.replace(tmp,stem.with_suffix('.npy'))
            save_npz(stem.with_suffix('.npz'),beat=beat,downbeat=down)
            atomic(meta,dict(inputSHA256=row['inputSHA256'],checkpointSHA256=CHECKPOINT_SHA,shape=list(x.shape),reconstructionError=error))
            elapsed.append(time.monotonic()-start)
        if i<3 or (i+1)%5==0 or i+1==len(rows):
            progress.write('extracting',completed=i+1,total=len(rows),current=row['id'],
                secondsPerNewExcerpt=round(float(np.mean(elapsed)),2) if elapsed else None,
                estimatedExtractionSecondsRemaining=round((len(rows)-i-1)*float(np.mean(elapsed))) if elapsed else None)
    del model


def labels_for(row,manifest):
    path=Path(manifest['annotationRoot'])/(row['id']+'.beats')
    if digest(path)!=row['annotationSHA256']:raise ValueError('Annotations changed')
    values=np.loadtxt(path,ndmin=2);labels=np.zeros((2,row['frames']),dtype='float32')
    indices=np.rint(values[:,0]*50).astype(int);valid=(indices>=0)&(indices<row['frames'])
    labels[0,indices[valid]]=1
    if row['hasDownbeats']:labels[1,indices[valid&(values[:,1]==1)]]=1
    return labels,values


def f1(reference,estimated,tolerance=.07):
    ref=sorted(t for t in reference if t>=5);est=sorted(t for t in estimated if t>=5)
    i=j=hits=0
    while i<len(ref) and j<len(est):
        if abs(ref[i]-est[j])<=tolerance:hits+=1;i+=1;j+=1
        elif est[j]<ref[i]:j+=1
        else:i+=1
    return 2*hits/(len(ref)+len(est)) if ref or est else 0.


def measure(row,reference,beat,down):
    from advanced import grid_from_frames
    from services import before_beat
    grid=grid_from_frames(beat,down,row['duration'],quality=False)
    pulses=np.asarray(grid['beats']);phase=int(np.argmin(abs(pulses-grid['firstBeat']))) if len(pulses) else 0
    result=dict(beatF1=f1(reference[:,0],pulses),barF1=None,cueAccuracy=None)
    if row['hasDownbeats']:
        result['barF1']=f1(reference[reference[:,1]==1,0],pulses[phase::grid['beatsPerBar']])
        correct=[]
        for i in np.flatnonzero(reference[:,1]==1):
            for lead in (4,8):
                if i>=lead and reference[i-lead,0]>=5:
                    proposed=before_beat(float(reference[i,0]),lead,grid['beats'],grid['bpm'] or 120)
                    correct.append(abs(proposed-reference[i-lead,0])<=.07)
        result['cueAccuracy']=float(np.mean(correct)) if correct else None
    return result


def evaluate(rows,manifest,initial,weight,bias,progress,stage):
    import torch
    features=Path(manifest['features']);results=[]
    dw=torch.from_numpy(np.asarray(weight-initial['weight'],dtype='float32'))
    db=torch.from_numpy(np.asarray(bias-initial['bias'],dtype='float32'))
    for i,row in enumerate(rows):
        progress.check();_,ref=labels_for(row,manifest)
        z=np.load(features/(row['id']+'.npz'),allow_pickle=False)
        before=measure(row,ref,z['beat'],z['downbeat'])
        if torch.count_nonzero(dw) or torch.count_nonzero(db):
            x=torch.from_numpy(np.load(features/(row['id']+'.npy'),allow_pickle=False))
            delta=(x@dw.T+db).numpy()
            after=measure(row,ref,z['beat']+delta[:,0]+delta[:,1],z['downbeat']+delta[:,1])
        else:after=before.copy()
        results.append(dict(id=row['id'],genre=row['genre'],style=row['style'],before=before,after=after))
        if (i+1)%25==0:progress.write(stage,completed=i+1,total=len(rows))
    return results


def summarize(results):
    output={}
    for side in ('before','after'):
        output[side]={k:float(np.mean(v)) if (v:=[r[side][k] for r in results if r[side][k] is not None]) else None for k in METRICS}
    output['meanGain']=float(np.mean([output['after'][k]-output['before'][k] for k in METRICS if output['before'][k] is not None]))
    output['count']=len(results)
    output['harmful']=[r['id'] for r in results if any(r['before'][k] is not None and r['after'][k]-r['before'][k]<-.1 for k in METRICS)]
    output['brokenCorrect']=[r['id'] for r in results if all(r['before'][k] is not None and r['before'][k]>=.95 for k in METRICS)
                             and any(r['after'][k]<.9 for k in METRICS)]
    return output


def gate(results,protocol):
    s=summarize(results);g=protocol['gate']
    styles={style:summarize([r for r in results if r['style']==style]) for style in ('rock','hard rock','blues','pop') if any(r['style']==style for r in results)}
    checks=dict(meanGain=s['meanGain']>g['minMeanGain'],
        cueGain=s['after']['cueAccuracy'] is not None and s['after']['cueAccuracy']-s['before']['cueAccuracy']>g['minCueGain'],
        metricFloors=all(s['after'][k]>=s['before'][k]-g['maxMetricDrop'] for k in METRICS if s['before'][k] is not None),
        styles=all(t['meanGain']>=-g['maxStyleMeanDrop'] for t in styles.values()),
        harmful=len(s['harmful'])<=math.floor(g['maxHarmfulFraction']*len(results)),
        correctTracks=not s['brokenCorrect'])
    return dict(passed=all(checks.values()),checks=checks,summary=s,styles=styles)


def train(manifest,protocol,output,progress):
    import torch
    from beat_this.model.beat_tracker import SumHead
    from beat_this.model.loss import ShiftTolerantBCELoss
    initial=dict(np.load(output/'initial-head.npz',allow_pickle=False));head=SumHead(512)
    head.beat_downbeat_lin.load_state_dict({k:torch.from_numpy(v.copy()) for k,v in initial.items()})
    optimizer=torch.optim.AdamW(head.parameters(),lr=protocol['learningRate'],weight_decay=0)
    losses=[ShiftTolerantBCELoss(pos_weight=protocol['positiveWeights'][k],tolerance=protocol['shiftToleranceFrames']) for k in ('beat','downbeat')]
    rows=[r for r in manifest['excerpts'] if r['split']=='train'];val=[r for r in manifest['excerpts'] if r['split']=='validation']
    labels={r['id']:labels_for(r,manifest)[0] for r in rows}
    state=output/'training.pt';start=0;candidates=[]
    if state.exists():
        saved=torch.load(state,map_location='cpu');head.load_state_dict(saved['head']);optimizer.load_state_dict(saved['optimizer'])
        start=saved['epoch'];candidates=saved['candidates']
    basew=torch.from_numpy(initial['weight']);baseb=torch.from_numpy(initial['bias'])
    for epoch in range(start+1,protocol['epochs']+1):
        progress.check();head.train();order=np.random.default_rng(protocol['seed']+epoch).permutation(len(rows));total=[]
        for offset in range(0,len(rows),protocol['batchSize']):
            progress.check();batch=[rows[i] for i in order[offset:offset+protocol['batchSize']]]
            length=max(r['frames'] for r in batch);x=torch.zeros((len(batch),length,512));y=torch.zeros((len(batch),2,length));mask=torch.zeros_like(y)
            for i,r in enumerate(batch):
                n=r['frames'];x[i,:n]=torch.from_numpy(np.load(Path(manifest['features'])/(r['id']+'.npy'),allow_pickle=False))
                y[i,:,:n]=torch.from_numpy(labels[r['id']]);mask[i,0,:n]=1
                if r['hasDownbeats']:mask[i,1,:n]=1
                if r['style']!='other':mask[i]*=protocol.get('targetStyleWeight',1)
            predicted=head(x);loss=sum(fn(predicted[k],y[:,i],mask[:,i]) for i,(fn,k) in enumerate(zip(losses,('beat','downbeat'))))
            raw=head.beat_downbeat_lin(x);base=x@basew.T+baseb
            loss+=protocol['distillationWeight']*((raw-base)**2*mask.permute(0,2,1)).mean()
            if not torch.isfinite(loss):raise ValueError('Training loss is not finite')
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(head.parameters(),1.);optimizer.step();total.append(float(loss.detach()))
            if offset%(protocol['batchSize']*20)==0:progress.write('training',epoch=epoch,epochs=protocol['epochs'],completed=min(offset+len(batch),len(rows)),total=len(rows),loss=float(np.mean(total)))
        weight=head.beat_downbeat_lin.weight.detach().numpy().copy();bias=head.beat_downbeat_lin.bias.detach().numpy().copy()
        save_npz(output/f'head-epoch-{epoch:02}.npz',weight=weight,bias=bias)
        if epoch in protocol['evaluateEpochs']:
            for blend in protocol['blendCandidates']:
                w=initial['weight']+blend*(weight-initial['weight']);b=initial['bias']+blend*(bias-initial['bias'])
                results=evaluate(val,manifest,initial,w,b,progress,'validating')
                assessment=gate(results,protocol);candidate=dict(epoch=epoch,blend=blend,**assessment)
                candidates.append(candidate);atomic(output/f'validation-{epoch:02}-{blend:g}.json',dict(candidate=candidate,results=results))
        tmp=state.with_suffix('.partial');torch.save(dict(epoch=epoch,head=head.state_dict(),optimizer=optimizer.state_dict(),candidates=candidates),tmp);os.replace(tmp,state)
        progress.write('epoch_complete',epoch=epoch,epochs=protocol['epochs'],loss=float(np.mean(total)))
    accepted=[c for c in candidates if c['passed']]
    best=max(accepted or candidates,key=lambda c:(c['summary']['meanGain'],-c['blend'],-c['epoch']))
    z=np.load(output/f'head-epoch-{best["epoch"]:02}.npz',allow_pickle=False)
    weight=initial['weight']+best['blend']*(z['weight']-initial['weight']);bias=initial['bias']+best['blend']*(z['bias']-initial['bias'])
    save_npz(output/'frozen-head.npz',weight=weight,bias=bias)
    atomic(output/'frozen.json',dict(created=now(),candidate=best,candidates=candidates,
        manifestSHA256=digest(output/'manifest.json'),protocolSHA256=digest(output/'protocol.json'),modelSHA256=digest(output/'frozen-head.npz')))


def run(output,smoke_limit=None):
    import fcntl
    import torch
    progress=Progress(output);lock=(output/'run.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        try:os.nice(10)
        except OSError:pass
        signal.signal(signal.SIGHUP,signal.SIG_IGN)
        manifest=json.loads((output/'manifest.json').read_text());protocol=json.loads((output/'protocol.json').read_text())
        seal=json.loads((output/'seal.json').read_text())
        if seal!={'manifestSHA256':digest(output/'manifest.json'),'protocolSHA256':digest(output/'protocol.json')}:raise ValueError('Prepared experiment changed; create a new experiment instead')
        if digest(manifest['checkpoint'])!=CHECKPOINT_SHA:raise ValueError('Base checkpoint changed')
        if digest(__file__)!=manifest['runnerSHA256']:raise ValueError('Runner changed after protocol freeze')
        for name,sha in manifest['decoderSHA256'].items():
            if digest(output/'decoder'/name)!=sha:raise ValueError('Decoder changed after protocol freeze')
        sys.path.insert(0,str(output/'decoder'))
        # Fail before the expensive extraction if a packaged dependency is missing.
        __import__('advanced')
        __import__('services')
        torch.set_num_threads(protocol['threads']);torch.set_num_interop_threads(1);torch.manual_seed(protocol['seed'])
        if (output/'report.json').exists():
            progress.write('complete',report=str(output/'report.json'),message='Existing final report; test not rerun.');return
        extract(manifest,output,progress,limit=smoke_limit)
        if smoke_limit:
            progress.write('smoke_complete',completed=smoke_limit);return
        if not (output/'frozen.json').exists():train(manifest,protocol,output,progress)
        if seal!={'manifestSHA256':digest(output/'manifest.json'),'protocolSHA256':digest(output/'protocol.json')}:raise ValueError('Experiment changed while running')
        frozen=json.loads((output/'frozen.json').read_text())
        if frozen['manifestSHA256']!=digest(output/'manifest.json') or frozen['protocolSHA256']!=digest(output/'protocol.json') or frozen['modelSHA256']!=digest(output/'frozen-head.npz'):raise ValueError('Frozen experiment changed')
        initial=dict(np.load(output/'initial-head.npz',allow_pickle=False));trained=dict(np.load(output/'frozen-head.npz',allow_pickle=False))
        results=evaluate([r for r in manifest['excerpts'] if r['split']=='test'],manifest,initial,trained['weight'],trained['bias'],progress,'testing_frozen_model')
        assessment=gate(results,protocol)
        approved=bool(frozen['candidate']['passed'] and assessment['passed'])
        report=dict(completed=now(),candidatePassesGate=approved,installed=False,
            validation=frozen['candidate'],test=assessment,results=results,manifestSHA256=digest(output/'manifest.json'),
            protocolSHA256=digest(output/'protocol.json'),modelSHA256=digest(output/'frozen-head.npz'),
            limitation=manifest['limitation'])
        atomic(output/'report.json',report)
        progress.write('complete',candidatePassesGate=approved,installed=False,report=str(output/'report.json'))
    except InterruptedError:pass
    except BaseException as error:
        progress.write('failed',error=type(error).__name__+': '+str(error));raise
    finally:lock.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repo',type=Path);p.add_argument('--engine',type=Path)
    p.add_argument('--smoke-limit',type=int)
    args=p.parse_args();output=args.output.resolve()
    if args.prepare:
        if not args.repo or not args.engine:p.error('--prepare needs --repo and --engine')
        prepare(args.repo.resolve(),output,args.engine.resolve())
    if args.run:run(output,args.smoke_limit)
