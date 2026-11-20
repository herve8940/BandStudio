"""Beat-synchronous spectral evidence, independent of chord names and song identity."""
import math
import numpy as np


def peaks(audio,edges,offset=0):
    import soundfile as sf
    from scipy.signal import resample_poly,stft
    duration=edges[-1]
    sr=11025;size=4096;hop=256
    count=len(edges)-1
    cell=np.zeros((count,12));low=np.zeros_like(cell);strength=np.zeros(count);counts=np.zeros(count);tuning=None
    from analysis_progress import emit
    with sf.SoundFile(audio) as stream:
        total=math.ceil(stream.frames/(20*stream.samplerate))
        for part in range(total):
            start=part*20;read_start=max(0,start-.5)
            stream.seek(round(read_start*stream.samplerate))
            data=stream.read(round(21*stream.samplerate),dtype='float32',always_2d=True).mean(axis=1)
            divisor=math.gcd(stream.samplerate,sr);data=resample_poly(data,sr//divisor,stream.samplerate//divisor)
            if len(data)<size:data=np.pad(data,(0,size-len(data)))
            f,t,z=stft(data,sr,nperseg=size,noverlap=size-hop,boundary='zeros')
            mag=abs(z);valid=(f>=65)&(f<=2600);f=f[valid];mag=mag[valid]
            # Isolate spectral peaks to keep guitar distortion/noise from
            # becoming an arbitrary chromatic chord.
            peak=(mag>np.roll(mag,1,axis=0))&(mag>=np.roll(mag,-1,axis=0))
            peak[[0,-1]]=False
            peak &= mag>np.max(mag,axis=0,keepdims=True)*.025
            left=np.log(np.maximum(np.roll(mag,1,axis=0),1e-12));center=np.log(np.maximum(mag,1e-12));right=np.log(np.maximum(np.roll(mag,-1,axis=0),1e-12))
            shift=np.clip(.5*(left-right)/(left-2*center+right-1e-12),-.5,.5)
            midi=69+12*np.log2((f[:,None]+shift*sr/size)/440)
            # Distortion produces strong high harmonics: downweight these so
            # a guitar's third/fifth harmonics do not masquerade as its root.
            weights=np.where(peak,mag,0)*(220/f[:,None])**.6
            if tuning is None and float(weights.sum())>1e-7:
                frac=(midi+.5)%1-.5
                hist,_=np.histogram(frac,bins=100,range=(-.5,.5),weights=weights)
                smooth=sum(np.roll(hist,i) for i in range(-3,4))
                tuning=(int(smooth.argmax())+.5)/100-.5
            pitch=np.mod(np.rint(midi-(tuning or 0)).astype(int),12)
            chroma=np.stack([np.sum(weights*(pitch==pc),axis=0) for pc in range(12)])
            bass=np.stack([np.sum(weights*(pitch==pc)*(f[:,None]<260),axis=0) for pc in range(12)])
            local_time=t+read_start;global_time=local_time+offset
            keep=(local_time>=start)&(local_time<start+20)&(global_time>=0)&(global_time<duration)
            bins=np.searchsorted(edges,global_time,side='right')-1
            keep &= (bins>=0)&(bins<count)
            bins=bins[keep];frame_times=global_time[keep]
            # Prefer the interior of a rhythmic cell: FFT windows straddling
            # changes otherwise mix neighbouring harmonies. Aggregate directly
            # into grid cells, keeping memory and runtime linear in song length.
            interior=(frame_times>=edges[bins]+.1*(edges[bins+1]-edges[bins]))&(frame_times<edges[bins+1]-.1*(edges[bins+1]-edges[bins]))
            weight=np.where(interior,1.,.1)
            counts+=np.bincount(bins,weights=weight,minlength=count)
            strength+=np.bincount(bins,weights=np.sum(mag[:,keep],axis=0)*weight,minlength=count)
            for pc in range(12):
                cell[:,pc]+=np.bincount(bins,weights=chroma[pc,keep]*weight,minlength=count)
                low[:,pc]+=np.bincount(bins,weights=bass[pc,keep]*weight,minlength=count)
            emit(completed=part+1,total=total,progressLabel=f'Calage de la grille Internet · extrait {part+1} sur {total}')
    if not counts.any():return None
    strength/=np.maximum(counts,1)
    cell/=np.maximum(np.linalg.norm(cell,axis=1,keepdims=True),1e-10)
    low/=np.maximum(np.max(low,axis=1,keepdims=True),1e-10)
    return dict(chroma=cell,bass=low,strength=strength,tuning=float(tuning or 0))


def note_salience(path,edges,offset=0,tuning=None):
    import soundfile as sf
    from scipy.signal import stft,resample_poly
    from scipy.optimize import nnls
    sr=11025;size=4096;hop=256;count=len(edges)-1
    spectrum=np.zeros((count,252));counts=np.zeros(count);energy=np.zeros(count)
    with sf.SoundFile(path) as stream:
        for start in range(0,math.ceil(stream.frames/stream.samplerate),20):
            begin=max(0,start-.4);stream.seek(round(begin*stream.samplerate));data=stream.read(round(20.8*stream.samplerate),dtype='float32',always_2d=True).mean(axis=1)
            d=math.gcd(sr,stream.samplerate);data=resample_poly(data,sr//d,stream.samplerate//d)
            if len(data)<size:data=np.pad(data,(0,size-len(data)))
            f,t,z=stft(data,sr,nperseg=size,noverlap=size-hop);mag=abs(z);valid=(f>=32)&(f<=4000);f=f[valid];mag=mag[valid]
            peak=(mag>np.roll(mag,1,axis=0))&(mag>=np.roll(mag,-1,axis=0));peak[[0,-1]]=False
            l=np.log(np.maximum(np.roll(mag,1,axis=0),1e-12));c=np.log(np.maximum(mag,1e-12));r=np.log(np.maximum(np.roll(mag,-1,axis=0),1e-12))
            shift=np.clip(.5*(l-r)/(l-2*c+r-1e-12),-.5,.5)
            midi=69+12*np.log2((f[:,None]+shift*sr/size)/440)
            weight=mag*peak*(mag>mag.max(axis=0,keepdims=True)*.025)
            if tuning is None and float(weight.sum())>1e-7:
                frac=(midi+.5)%1-.5;hist,_=np.histogram(frac,bins=100,range=(-.5,.5),weights=weight)
                tuning=(int(sum(np.roll(hist,i) for i in range(-3,4)).argmax())+.5)/100-.5
            idx=np.rint((midi-(tuning or 0)-24)*3).astype(int)
            local=t+begin;global_time=local+offset;bins=np.searchsorted(edges,global_time,side='right')-1
            keep=(local>=start)&(local<start+20)&(bins>=0)&(bins<count)
            b=bins[keep];counts+=np.bincount(b,minlength=count);energy+=np.bincount(b,weights=mag[:,keep].sum(axis=0),minlength=count)
            ii=idx[:,keep];bb=np.broadcast_to(b,ii.shape);ww=weight[:,keep]
            valid=(ii>=0)&(ii<252);np.add.at(spectrum,(bb[valid],ii[valid]),ww[valid])
    spectrum/=np.maximum(counts[:,None],1)
    notes=np.arange(28,85);D=np.zeros((252,len(notes)))
    for j,note in enumerate(notes):
        for h in range(1,13):
            x=(note+12*np.log2(h)-24)*3
            k=round(x)
            if k>=252:continue
            D[k,j]+=.7**(h-1)
    # smooth log spectrum tolerates vibrato and imperfect tuning; same dictionary kernel.
    spectrum=(spectrum+np.roll(spectrum,1,axis=1)*.5+np.roll(spectrum,-1,axis=1)*.5)
    D=(D+np.roll(D,1,axis=0)*.5+np.roll(D,-1,axis=0)*.5)
    # Solve non-negative note activations per saved rhythmic cell.
    D/=np.maximum(np.linalg.norm(D,axis=0),1e-10)
    activation=np.array([nnls(D,row)[0] for row in spectrum])
    activation=np.maximum(0,activation-activation.max(axis=1,keepdims=True)*.08)
    chroma=np.zeros((count,12));low=np.zeros_like(chroma)
    for j,n in enumerate(notes):
        chroma[:,n%12]+=activation[:,j]
        if n<60:low[:,n%12]+=activation[:,j]
    chroma/=np.maximum(np.linalg.norm(chroma,axis=1,keepdims=True),1e-9);low/=np.maximum(low.max(axis=1,keepdims=True),1e-9)
    return chroma,low,energy/np.maximum(counts,1)


def bass_evidence(project,edges,tuning=None):
    """Use the separated bass only when it carries an audible pitched signal.

    Harmonic dictionaries suppress overtones before pitch classes are folded.
    The dictionary is generated from equal temperament; no learned song labels.
    """
    from pathlib import Path
    import hashlib,json,uuid
    from preparation import media_file
    track=next((t for t in project.get('tracks',[]) if t['role']=='bass'),None)
    if track is None or not project.get('_root'):return None
    path=media_file(Path(project['_root']),track['file']);stat=path.stat()
    key=hashlib.sha256(json.dumps([2,str(path),stat.st_size,stat.st_mtime_ns,track.get('offset',0),tuning,edges.tolist()]).encode()).hexdigest()
    cache=Path(project['_root'])/'References'/('bass-evidence-'+key+'.npz')
    try:
        with np.load(cache,allow_pickle=False) as saved:
            chroma,energy=saved['chroma'],saved['energy']
        if chroma.shape!=(len(edges)-1,12) or energy.shape!=(len(edges)-1,) or not np.isfinite(chroma).all() or not np.isfinite(energy).all():raise ValueError('Invalid descriptor')
    except (OSError,ValueError,KeyError):
        _,chroma,energy=note_salience(path,edges,track.get('offset',0),tuning)
        temp=cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            cache.parent.mkdir(parents=True,exist_ok=True)
            with temp.open('wb') as stream:np.savez_compressed(stream,chroma=chroma,energy=energy)
            temp.replace(cache)
        except OSError:pass
        finally:temp.unlink(missing_ok=True)
    active=energy>max(1e-4,float(np.percentile(energy,90))*.08)
    return dict(chroma=chroma,active=active)
