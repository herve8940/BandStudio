"""Lightweight placement of a web chart's chord vocabulary on the saved grid.

No trained chord model and no new chord names: audio only distinguishes the
published candidates. Ambiguous placements remain visibly marked for review.
"""
import math
import re


def tones(label):
    match=re.fullmatch(r'([A-G])([#b]?)([^/]*)(?:/([A-G])([#b]?))?',label)
    if not match:return None
    letter,acc,quality,bass,bacc=match.groups()
    def pitch(l,a):return (dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[l]+{'':0,'#':1,'b':-1}[a or ''])%12
    root=pitch(letter,acc);q=quality.lower() if not quality.startswith('M') else 'maj'+quality[1:]
    if q in ('','maj'):intervals=[0,4,7]
    elif q in ('m','min'):intervals=[0,3,7]
    elif q=='5':intervals=[0,7]
    elif q in ('4','sus','sus4'):intervals=[0,5,7]
    elif q in ('2','sus2'):intervals=[0,2,7]
    elif q in ('7','m7','maj7','7+','m7+'):intervals=[0,3 if q in ('m7','m7+') else 4,7,11 if q in ('maj7','7+','m7+') else 10]
    elif q in ('6','m6'):intervals=[0,3 if q=='m6' else 4,7,9]
    elif q=='add9':intervals=[0,2,4,7]
    elif q in ('dim','°'):intervals=[0,3,6]
    elif q in ('dim7','°7'):intervals=[0,3,6,9]
    elif q in ('m7b5','m7(b5)'):intervals=[0,3,6,10]
    elif q in ('aug','+'):intervals=[0,4,8]
    else:return None
    return [(root+i)%12 for i in intervals],pitch(bass,bacc) if bass else root


def place(project,audio,labels,source_url,offset=0,transitions=None,sections=None):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly,stft
    from services import beat_grid
    candidates=[(label,tones(label)) for label in labels if tones(label)]
    beats,duration=beat_grid(project)
    if len(beats)<2 or not candidates:return [],dict(status='needs_grid',message='Grille rythmique ou accords compatibles manquants : calage à compléter.')
    # Eighth notes use two cells per quarter, three per dotted quarter. Boundaries
    # always come from the existing grid, including variable tempo and pickups.
    subdivision=3 if project.get('settings',{}).get('pulseUnit')=='dottedQuarter' else 2
    edges=np.array(sorted(set([*beats,*[a+(b-a)*part/subdivision for a,b in zip(beats,beats[1:]) for part in range(1,subdivision)],duration])))
    edges=edges[(edges>=0)&(edges<=duration)]
    if len(edges)<2:return [],dict(status='needs_grid',message='Grille rythmique trop courte pour caler les accords.')
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
            if tuning is None:
                frac=(midi+.5)%1-.5
                hist,_=np.histogram(frac,bins=100,range=(-.5,.5),weights=weights)
                smooth=sum(np.roll(hist,i) for i in range(-3,4))
                tuning=(int(smooth.argmax())+.5)/100-.5
            pitch=np.mod(np.rint(midi-tuning).astype(int),12)
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
    if not counts.any():return [],dict(status='no_audio',message='Aucun passage audio exploitable pour le calage.')
    strength/=np.maximum(counts,1)
    cell/=np.maximum(np.linalg.norm(cell,axis=1,keepdims=True),1e-10)
    low/=np.maximum(np.max(low,axis=1,keepdims=True),1e-10)
    templates=np.zeros((len(candidates),12));roots=[]
    for i,(_, (pcs,root)) in enumerate(candidates):
        templates[i,pcs]=1;templates[i]/=np.linalg.norm(templates[i]);roots.append(root)
    scores=cell@templates.T+.12*low[:,roots]
    if sections:
        from chord_sources import section_kind
        middle=(edges[:-1]+edges[1:])/2
        for section in project.get('sections',[]):
            published=sections.get(section_kind(section['name']),[])
            # Single written chords often mean "repeat the previous riff";
            # they are not a complete harmonic vocabulary for that section.
            if len(published)<2:continue
            rows=(middle>=section['start'])&(middle<section['end'])
            scores-=.22*rows[:,None]*np.array([label not in published for label,_ in candidates])[None,:]
    quiet=strength<max(1e-5,float(np.percentile(strength,90))*.025)
    scores[quiet]=0
    penalty=.035*(1-np.eye(len(candidates)))
    if transitions:
        published={tuple(pair) for pair in transitions}
        penalty+=np.array([[.12 if a!=b and (a,b) not in published else 0 for b,_ in candidates] for a,_ in candidates])
    previous=np.zeros_like(scores,dtype=int);acc=scores[0].copy()
    for i in range(1,len(scores)):
        choices=acc[:,None]-penalty
        previous[i]=np.argmax(choices,axis=0);acc=scores[i]+np.max(choices,axis=0)
    path=[int(acc.argmax())]
    for i in range(len(scores)-1,0,-1):path.append(int(previous[i,path[-1]]))
    path=path[::-1];segments=[];uncertain=0
    for i,choice in enumerate(path):
        if quiet[i]:continue
        alternatives=np.delete(scores[i],choice)
        margin=scores[i,choice]-max(alternatives) if len(alternatives) else 0
        confidence=float(np.clip(margin/.15,0,1))*min(1,float(scores[i,choice]/.65))
        review=confidence<.5 or scores[i,choice]<.65
        if review and not quiet[i]:uncertain+=1
        label=candidates[choice][0]
        if segments and segments[-1]['label']==label and edges[i]-segments[-1]['end']<.6:
            segment=segments[-1];segment['end']=float(edges[i+1]);segment['_scores'].append(confidence)
        else:segments.append(dict(start=float(edges[i]),end=float(edges[i+1]),label=label,sourceURL=source_url,_scores=[confidence]))
    if not segments:return [],dict(status='no_audio',message='Grille Internet trouvée, mais aucun passage audio exploitable pour la caler.')
    for segment in segments:segment['confidence']=float(np.mean(segment.pop('_scores')))
    return segments,dict(status='proposed',subdivision=subdivision,tuningCents=round(float(tuning)*100,1),uncertainCells=uncertain,
        message='Accords de la source calés sur les temps et contretemps détectés. Les placements restent des propositions à vérifier à l’écoute.')
