"""Compare musical phrases on the saved pulse grid, with independent stem checks.

Similarity is evidence for a proposal, not a calibrated correctness probability.
Only individually confirmed sections/manual chords can teach another occurrence.
"""
from ui_language import ui_text
import copy
import hashlib
import json
import math
from pathlib import Path
import uuid

import numpy as np
from preparation import media_file

VERSION=2
HARMONIC_ROLES=('guitar','piano','other')
VOICE_ROLES=('vocals','vocal_lead','vocal_backing')
DRUM_ROLES=('drums','drum_kick','drum_snare','drum_toms','drum_cymbals')
ROLES=HARMONIC_ROLES+('bass',)+VOICE_ROLES+DRUM_ROLES+('source',)
ROLE_LABELS=dict(guitar='guitare',piano='piano',other='autres instruments',bass='basse',
                vocals='chant',vocal_lead='chant principal',vocal_backing='chœurs',drums='batterie',
                drum_kick='grosse caisse',drum_snare='caisse claire',drum_toms='toms',drum_cymbals='cymbales',source='mix original')


def track_features(path,offset,edges,bass=False):
    """Small descriptors per half pulse, streamed in chunks, before mixer gains.

    Sum channel powers: an out-of-phase stereo stem must not disappear when
    analysed. Counts also distinguish missing media coverage from real silence.
    """
    from scipy.signal import resample_poly,stft
    import soundfile as sf
    n=len(edges)-1;sr=8000;size=2048;hop=256
    chroma=np.zeros((n,12));texture=np.zeros((n,6));power=np.zeros(n);counts=np.zeros(n)
    with sf.SoundFile(path) as stream:
        for start in range(0,math.ceil(stream.frames/stream.samplerate),20):
            begin=max(0,start-.3);stream.seek(round(begin*stream.samplerate))
            data=stream.read(round(20.6*stream.samplerate),dtype='float32',always_2d=True)
            divisor=math.gcd(sr,stream.samplerate)
            data=resample_poly(data,sr//divisor,stream.samplerate//divisor,axis=0)
            if len(data)<size:data=np.pad(data,((0,size-len(data)),(0,0)))
            f,t,z=stft(data.T,sr,nperseg=size,noverlap=size-hop)
            mag=np.sqrt(np.mean(np.abs(z)**2,axis=0));local=t+begin
            bins=np.searchsorted(edges,local+offset,side='right')-1
            keep=(local>=start)&(local<start+20)&(local<stream.frames/stream.samplerate)&(bins>=0)&(bins<n)
            bins=bins[keep];mag=mag[:,keep]
            counts+=np.bincount(bins,minlength=n)
            power+=np.bincount(bins,weights=np.sum(mag**2,axis=0),minlength=n)
            valid=(f>=45)&(f<=(700 if bass else 2600))
            freq=f[valid];m=mag[valid]
            peaks=(m>np.roll(m,1,axis=0))&(m>=np.roll(m,-1,axis=0));peaks[[0,-1]]=False
            midi=np.rint(69+12*np.log2(freq/440)).astype(int)%12
            weighted=m*peaks*(220/freq[:,None])**.6
            for pc in range(12):chroma[:,pc]+=np.bincount(bins,weights=weighted[midi==pc].sum(axis=0),minlength=n)
            for i,(lo,hi) in enumerate(zip((0,100,200,400,800,1600),(100,200,400,800,1600,4001))):
                texture[:,i]+=np.bincount(bins,weights=np.sum(mag[(f>=lo)&(f<hi)]**2,axis=0),minlength=n)
    return dict(chroma=chroma/np.maximum(counts[:,None],1),texture=texture/np.maximum(counts[:,None],1),
                power=power/np.maximum(counts,1),coverage=counts>0)


def normalized_track(raw):
    energy=np.sqrt(raw['power']);scale=max(float(np.percentile(energy,90)),1e-5)
    chroma=raw['chroma']/np.maximum(np.linalg.norm(raw['chroma'],axis=1,keepdims=True),1e-9)
    texture=np.sqrt(raw['texture']);texture/=np.maximum(np.linalg.norm(texture,axis=1,keepdims=True),1e-9)
    return dict(chroma=chroma,texture=texture,energy=np.clip(energy/scale,0,2),
                coverage=raw['coverage'],level=np.array(scale))


def describe(project):
    from services import beat_grid
    beats,length=beat_grid(project)
    if len(beats)<4:return None
    edges=np.unique(np.r_[0,beats,[(a+b)/2 for a,b in zip(beats,beats[1:])],length])
    edges=edges[(edges>=0)&(edges<=length)];middle=(edges[1:]+edges[:-1])/2
    if len(middle)<16 or len(middle)>30000:return None
    root=Path(project['_root']);selected=[];seen=set();incomplete=False
    harmonic=any(t['role'] in HARMONIC_ROLES for t in project['tracks'])
    for t in project['tracks']:
        role=t['role']
        if role not in ROLES or (role=='source' and harmonic):continue
        try:
            path=media_file(root,t['file']);stat=path.stat();offset=float(t.get('offset',0))
        except (OSError,ValueError):incomplete=True;continue
        key=(str(path),offset)
        if key in seen:continue  # One physical file is never two independent votes.
        seen.add(key);selected.append((role,path,offset,stat.st_size,stat.st_mtime_ns))
    signature=dict(version=VERSION,edges=edges.tolist(),files=[(r,str(p),o,s,m) for r,p,o,s,m in selected])
    digest=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    cache=root/'References'/('phrases-'+digest+'.npz')
    try:
        with np.load(cache,allow_pickle=False) as saved:result={k:saved[k] for k in saved.files}
        if np.array_equal(result['edges'],edges) and all(np.isfinite(v).all() for v in result.values()):return result
    except (OSError,ValueError,KeyError):pass
    raw={}
    for role,path,offset,_,_ in selected:
        try:track=track_features(path,offset,edges,bass=role=='bass')
        except (OSError,ValueError,RuntimeError):incomplete=True;continue
        if not all(np.isfinite(v).all() for v in track.values()):incomplete=True;continue
        if role in raw:
            for key in ('chroma','texture','power'):raw[role][key]+=track[key]
            raw[role]['coverage']|=track['coverage']
        else:raw[role]=track
    # An unreadable optional stem must not disable every other instrument.
    if not any(r in raw for r in HARMONIC_ROLES+('source',)):
        source=next((t for t in project['tracks'] if t['role']=='source'),None)
        if source:
            try:
                path=media_file(root,source['file']);offset=source.get('offset',0)
                if (str(path),offset) not in seen:raw['source']=track_features(path,offset,edges)
            except (OSError,ValueError,RuntimeError):pass
    if not raw:return None
    result=dict(edges=edges,middle=middle,roles=np.array([r in raw for r in ROLES]),
                available=np.array(['bass' in raw,any(r in raw for r in VOICE_ROLES),any(r in raw for r in DRUM_ROLES)]))
    for role,track in raw.items():
        for key,value in normalized_track(track).items():result[role+'_'+key]=value
    families=dict(harmony=[r for r in HARMONIC_ROLES if r in raw] or ['source'],bass=['bass'],
                  voice=['vocals'] if 'vocals' in raw else list(VOICE_ROLES[1:]),
                  drums=['drums'] if 'drums' in raw else list(DRUM_ROLES[1:]))
    for family,roles in families.items():
        tracks=[raw[r] for r in roles if r in raw]
        if tracks:
            combined={k:sum(t[k] for t in tracks) for k in ('chroma','texture','power')}
            combined['coverage']=np.logical_or.reduce([t['coverage'] for t in tracks])
            values=normalized_track(combined)
        else:
            values=dict(chroma=np.zeros((len(middle),12)),texture=np.zeros((len(middle),6)),energy=np.zeros(len(middle)),coverage=np.zeros(len(middle),bool))
        result[family+'Energy']=values['energy'];result[family+'Coverage']=values['coverage']
        if family in ('harmony','bass'):result[family]=values['chroma']
        if family=='harmony':result['texture']=values['texture']
    cache.parent.mkdir(parents=True,exist_ok=True)
    # A broken/temporarily missing stem should be retried on the next review.
    if not incomplete:
        temp=cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('wb') as stream:np.savez_compressed(stream,**result)
            temp.replace(cache)
        finally:temp.unlink(missing_ok=True)
    return result


def used_roles(features):
    return [r for r,present in zip(ROLES,features.get('roles',[])) if present]


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
    available=features['available']
    result['usable']=bool(available[1] and (available[0] or available[2]) and
                          np.mean(features['harmonyEnergy'][ia])>.08 and np.mean(features['harmonyEnergy'][ib])>.08)
    # Missing stems cannot veto the evidence from present instruments, but an
    # unread/offset region is not evidence for matching silence.
    for index,key in ((0,'bass'),(2,'drums')):
        if not available[index]:result['bass' if key=='bass' else 'drumsEnergy']=1.
        elif key+'Coverage' in features:
            if min(features[key+'Coverage'][ia].mean(),features[key+'Coverage'][ib].mean())<.9:result['usable']=False
            if max(features[key+'Energy'][ia].mean(),features[key+'Energy'][ib].mean())<.08:
                result['bass' if key=='bass' else 'drumsEnergy']=1.
    for key in ('voiceCoverage','harmonyCoverage'):
        if key in features and min(features[key][ia].mean(),features[key][ib].mean())<.9:result['usable']=False
    checks={};roles=used_roles(features)
    harmonic_level=max((float(features[r+'_level']) for r in roles if r in HARMONIC_ROLES),default=0)
    for role in roles:
        if role not in HARMONIC_ROLES+VOICE_ROLES[1:]+DRUM_ROLES[1:]:continue
        if role in HARMONIC_ROLES and float(features[role+'_level'])<max(1e-5,.12*harmonic_level):continue
        x,y=values(role+'_energy',ia),values(role+'_energy',ib)
        if max(x.mean(),y.mean())<.08:continue
        covered=min(features[role+'_coverage'][ia].mean(),features[role+'_coverage'][ib].mean())>=.9
        activity=abs(float(np.mean(x>.2)-np.mean(y>.2)))
        if role in HARMONIC_ROLES:
            checks[role]=bool(covered and activity<=.25 and cosine(role+'_chroma')>=.80 and cosine(role+'_texture')>=.85)
        elif role in DRUM_ROLES:
            checks[role]=bool(covered and activity<=.30 and cosine(role+'_energy')>=.70)
        else:checks[role]=bool(covered and activity<=.25)
    result['stemChecks']=checks
    result['matches']=bool(result['usable'] and result['harmony']>=.90 and result['bass']>=.85 and result['texture']>=.93
                           and result['drumsEnergy']>=.85 and result['voiceDifference']<=.18 and all(checks.values()))
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
                                reason=ui_text('Passage comparable à « ', 'Passage similar to “ ')+donor['name']+ui_text(' » confirmé : harmonie, basse, batterie et chant concordants.', ' ” confirmed by matching harmony, bass, drums and vocals.')))
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
