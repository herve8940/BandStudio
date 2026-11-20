"""Compare musical phrases on the saved pulse grid, with independent stem checks.

Similarity is evidence for a proposal, not a calibrated correctness probability.
Only individually confirmed sections/manual chords can teach another occurrence.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import uuid

import numpy as np
from preparation import media_file

VERSION=1


def describe(project):
    from services import beat_grid
    from scipy.signal import resample_poly,stft
    beats,length=beat_grid(project)
    if len(beats)<4:return None
    edges=np.unique(np.r_[beats,[(a+b)/2 for a,b in zip(beats,beats[1:])],length])
    edges=edges[(edges>=0)&(edges<=length)];middle=(edges[1:]+edges[:-1])/2
    if len(middle)<16 or len(middle)>30000:return None
    root=Path(project['_root']);tracks=project['tracks']
    selected={}
    for key,roles in [('harmony',('guitar','other','piano','source')),('bass',('bass',)),('voice',('vocals',)),('drums',('drums',))]:
        selected[key]=next((t for role in roles for t in tracks if t['role']==role),None)
    paths={k:media_file(root,t['file']) for k,t in selected.items() if t}
    signature=dict(version=VERSION,edges=edges.tolist(),files=[(k,str(p),p.stat().st_size,p.stat().st_mtime_ns,selected[k].get('offset',0)) for k,p in paths.items()])
    digest=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    cache=root/'References'/('phrases-'+digest+'.npz')
    try:
        with np.load(cache,allow_pickle=False) as saved:
            result={k:saved[k] for k in saved.files}
        if np.array_equal(result['edges'],edges) and all(np.isfinite(v).all() for v in result.values()):return result
    except (OSError,ValueError,KeyError):pass
    import soundfile as sf
    result=dict(edges=edges,middle=middle,available=np.array([int(selected[k] is not None) for k in ('bass','voice','drums')]))
    n=len(middle);sr=8000;size=2048;hop=256
    for key,path in paths.items():
        chroma=np.zeros((n,12));texture=np.zeros((n,6));energy=np.zeros(n);counts=np.zeros(n)
        with sf.SoundFile(path) as stream:
            for start in range(0,math.ceil(stream.frames/stream.samplerate),20):
                begin=max(0,start-.3);stream.seek(round(begin*stream.samplerate))
                data=stream.read(round(20.6*stream.samplerate),dtype='float32',always_2d=True).mean(axis=1)
                divisor=math.gcd(sr,stream.samplerate);data=resample_poly(data,sr//divisor,stream.samplerate//divisor)
                if len(data)<size:data=np.pad(data,(0,size-len(data)))
                f,t,z=stft(data,sr,nperseg=size,noverlap=size-hop)
                mag=np.abs(z);local=t+begin;global_time=local+selected[key].get('offset',0)
                bins=np.searchsorted(edges,global_time,side='right')-1
                keep=(local>=start)&(local<start+20)&(bins>=0)&(bins<n)
                bins=bins[keep];mag=mag[:,keep]
                counts+=np.bincount(bins,minlength=n)
                energy+=np.bincount(bins,weights=np.sum(mag**2,axis=0),minlength=n)
                if key not in ('harmony','bass'):continue
                valid=(f>=45)&(f<=(700 if key=='bass' else 2600))
                freq=f[valid];m=mag[valid]
                peaks=(m>np.roll(m,1,axis=0))&(m>=np.roll(m,-1,axis=0));peaks[[0,-1]]=False
                midi=np.rint(69+12*np.log2(freq/440)).astype(int)%12
                weighted=m*peaks*(220/freq[:,None])**.6
                for pc in range(12):chroma[:,pc]+=np.bincount(bins,weights=weighted[midi==pc].sum(axis=0),minlength=n)
                for i,(lo,hi) in enumerate(zip((0,100,200,400,800,1600),(100,200,400,800,1600,4001))):
                    texture[:,i]+=np.bincount(bins,weights=np.sum(mag[(f>=lo)&(f<hi)]**2,axis=0),minlength=n)
        energy=np.sqrt(energy/np.maximum(counts,1));energy=np.clip(energy/max(float(np.percentile(energy,90)),1e-9),0,2)
        if key in ('harmony','bass'):
            chroma/=np.maximum(np.linalg.norm(chroma,axis=1,keepdims=True),1e-9)
            result[key]=chroma
            if key=='harmony':
                texture=np.sqrt(texture/np.maximum(counts[:,None],1));texture/=np.maximum(np.linalg.norm(texture,axis=1,keepdims=True),1e-9)
                result['texture']=texture
        result[key+'Energy']=energy
    for key in ('bass','voice','drums'):
        if key+'Energy' not in result:result[key+'Energy']=np.zeros(n)
    if 'bass' not in result:result['bass']=np.zeros((n,12))
    cache.parent.mkdir(parents=True,exist_ok=True)
    # Cache is optional and contains only small descriptors, never model labels.
    temp=cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('wb') as stream:np.savez_compressed(stream,**result)
        temp.replace(cache)
    finally:temp.unlink(missing_ok=True)
    return result


def resampled(values,count):
    if values.ndim==1:return np.interp(np.linspace(0,len(values)-1,count),np.arange(len(values)),values)
    return np.column_stack([resampled(values[:,i],count) for i in range(values.shape[1])])


def compare(features,a,b,min_cells=16):
    ia=np.flatnonzero((features['middle']>=a['start'])&(features['middle']<a['end']))
    ib=np.flatnonzero((features['middle']>=b['start'])&(features['middle']<b['end']))
    if min(len(ia),len(ib))<min_cells or not .85<=len(ia)/len(ib)<=1.18:return None
    count=min(len(ia),len(ib),512)
    def values(key,indices):return resampled(features[key][indices],count)
    def cosine(key):
        x,y=values(key,ia),values(key,ib)
        if x.ndim==1:return float(x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-9))
        return float(np.mean(np.sum(x*y,axis=1)/np.maximum(np.linalg.norm(x,axis=1)*np.linalg.norm(y,axis=1),1e-9)))
    result={key:cosine(key) for key in ('harmony','bass','texture','drumsEnergy')}
    # Different lyrics/levels are normal in repeated verses. Compare the share
    # of sung frames, not the singer's exact amplitude contour.
    result['voiceDifference']=abs(float(np.mean(values('voiceEnergy',ia)>.2))-float(np.mean(values('voiceEnergy',ib)>.2)))
    result['usable']=bool(features['available'].all() and np.mean(features['harmonyEnergy'][ia])>.08 and np.mean(features['harmonyEnergy'][ib])>.08)
    result['matches']=bool(result['usable'] and result['harmony']>=.90 and result['bass']>=.85 and result['texture']>=.93
                           and result['drumsEnergy']>=.85 and result['voiceDifference']<=.18)
    return result


def analyse(project,features=None):
    from structure_review import confirmed,protected,kind
    features=describe(project) if features is None else features
    if features is None:return dict(sections=copy.deepcopy(project['sections']),changes=[],pairs=[],groups=[])
    rows=project['sections'];pairs=[];groups=[];changes=[];result=copy.deepcopy(rows)
    for i,a in enumerate(rows):
        for j,b in enumerate(rows[i+1:],i+1):
            if kind(a['name']) in ('silence','avant depart') or kind(b['name']) in ('silence','avant depart'):continue
            evidence=compare(features,a,b)
            if evidence and evidence['matches']:pairs.append(dict(a=i,b=j,**evidence))
    # Complete-link groups avoid passing a weak match through a chain of repeats.
    connected={frozenset((p['a'],p['b'])) for p in pairs}
    for i,row in enumerate(rows):
        match=next((g for g in groups if all(frozenset((i,j)) in connected for j in g)),None)
        if match is None:groups.append([i])
        else:match.append(i)
    for group in groups:
        known=[rows[i] for i in group if confirmed(rows[i]) and kind(rows[i]['name']) not in ('intro','instrumental')]
        if not known or len({kind(s['name']) for s in known})!=1:continue
        donor=known[0]
        for i in group:
            target=result[i]
            if protected(target) or kind(target['name']) not in ('intro','instrumental'):continue
            before=target['name'];target.update(name=donor['name'],origin='reference',locked=True,reviewed=False)
            changes.append(dict(id=str(uuid.uuid4()),kind='rename',time=target['start'],before=before,after=target['name'],
                                reason='Passage comparable à « '+donor['name']+' » confirmé : harmonie, basse, batterie et chant concordants.'))
    return dict(sections=result,changes=changes,pairs=pairs,groups=[g for g in groups if len(g)>1])


def transfer_chords(project,pattern,features=None):
    """Transfer a completely hand-checked phrase; target stays unreviewed."""
    from structure_review import confirmed,kind
    from services import beat_grid
    beats,_=beat_grid(project);beats=np.asarray(beats)
    rows=project['sections'];chords=copy.deepcopy(project.get('chords',[]));transfers=[]
    for group in pattern['groups']:
        donors=[]
        for i in group:
            section=rows[i]
            if not confirmed(section):continue
            phrase=[c for c in chords if c.get('manual') and c['start']>=section['start']-.001 and c['end']<=section['end']+.001]
            if not phrase:continue
            phrase.sort(key=lambda c:c['start'])
            if abs(phrase[0]['start']-section['start'])>.1 or abs(phrase[-1]['end']-section['end'])>.1:continue
            if any(abs(a['end']-b['start'])>.1 for a,b in zip(phrase,phrase[1:])):continue
            donors.append((i,phrase))
        if not donors:continue
        # Different manually written progressions are exceptions, not votes.
        signature=lambda phrase:[(c['text'],round((c['end']-c['start'])/sum(x['end']-x['start'] for x in phrase),2)) for c in phrase]
        if len({json.dumps(signature(phrase)) for _,phrase in donors})!=1:continue
        i,phrase=donors[0];source=rows[i]
        source_beats=beats[(beats>=source['start'])&(beats<source['end'])]
        for j in group:
            target=rows[j]
            if j==i or kind(target['name'])!=kind(source['name']):continue
            if any(c.get('manual') and c['start']<target['end'] and c['end']>target['start'] for c in chords):continue
            target_beats=beats[(beats>=target['start'])&(beats<target['end'])]
            if len(source_beats)!=len(target_beats) or len(source_beats)<4:continue
            x=np.unique(np.r_[source['start'],source_beats,source['end']]);y=np.unique(np.r_[target['start'],target_beats,target['end']])
            if len(x)!=len(y):continue
            mapped=[dict(id=str(uuid.uuid4()),start=float(np.interp(c['start'],x,y)),end=float(np.interp(c['end'],x,y)),text=c['text'],manual=False,
                         confidence=.49) for c in phrase]
            # A strong average over the verse can hide a different final chord.
            # Check every chord interval independently before transferring any.
            if features is None:features=describe(project)
            if features is None:continue
            checks=[compare(features,a,b,min_cells=4) for a,b in zip(phrase,mapped)]
            if any(not check or not check['matches'] for check in checks):continue
            # Confidence intentionally stays uncertain: transferring a human
            # phrase does not mean the target occurrence has been listened to.
            if any(c['start']<target['start'] or c['end']>target['end'] for c in mapped):continue
            if any((c['start']<target['start']<c['end'] or c['start']<target['end']<c['end']) for c in chords):continue
            chords=[c for c in chords if c['end']<=target['start'] or c['start']>=target['end']]+mapped
            transfers.append(dict(source=source['id'],target=target['id'],start=target['start'],end=target['end']))
    return sorted(chords,key=lambda c:c['start']),transfers


def listening_plan(project,changes,pattern):
    """One listening action covers changes AND uncertain chords, including variants.

    Group by musical phrase for navigation; all uncertain occurrences remain in
    the queue, so a shorter counter never conceals unchecked music.
    """
    from windows.project import duration
    length=duration(project);clips=[]
    for c in changes:clips.append(dict(start=max(0,c['time']-3),end=min(length,c['time']+4),reason=c['after']))
    for c in project.get('chords',[]):
        if not c.get('manual') and c.get('confidence',0)<.5:
            section=next((s for s in project['sections'] if s['start']<=c['start']<s['end']),None)
            clips.append(dict(start=max(0,c['start']-.75),end=min(length,c['end']+.75),
                              reason=(section['name']+' · ' if section else '')+'accords à vérifier'))
    merged=[]
    for clip in sorted(clips,key=lambda c:c['start']):
        if merged and clip['start']<=merged[-1]['end']+1:
            merged[-1]['end']=max(merged[-1]['end'],clip['end'])
            if clip['reason'] not in merged[-1]['reason']:merged[-1]['reason']+=' / '+clip['reason']
        else:merged.append(clip.copy())
    return [dict(id=str(uuid.uuid4()),**clip) for clip in merged]
