"""Conservative audio checks for proposed structure, never manual boundaries."""
import copy
import uuid
import numpy as np


def boundary(features,time,window=2.):
    middle=features['middle'];left=(middle>=time-window)&(middle<time);right=(middle>=time)&(middle<time+window)
    if left.sum()<2 or right.sum()<2:return None
    evidence={}
    def covered(key):
        coverage=features.get(key+'Coverage')
        return coverage is None or min(coverage[left].mean(),coverage[right].mean())>=.9
    for key in ('harmony','bass','texture'):
        x=features[key][left].mean(axis=0);y=features[key][right].mean(axis=0)
        usable=covered('harmony' if key=='texture' else key) and min(np.linalg.norm(x),np.linalg.norm(y))>=.05
        evidence[key]=float(1-x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-9)) if usable else 0.
    for key in ('voice','drums'):
        evidence[key]=abs(float(features[key+'Energy'][left].mean()-features[key+'Energy'][right].mean())) if covered(key) else 0.
    from musical_patterns import used_roles,HARMONIC_ROLES,VOICE_ROLES,DRUM_ROLES
    roles=used_roles(features)
    harmonic=[r for r in roles if r in HARMONIC_ROLES]
    level=max((float(features[r+'_level']) for r in harmonic),default=0)
    for role in roles:
        energy=features[role+'_energy'];coverage=features[role+'_coverage']
        if min(coverage[left].mean(),coverage[right].mean())<.9:continue
        if role in harmonic and float(features[role+'_level'])>=max(1e-5,.12*level):
            x=features[role+'_chroma'][left].mean(axis=0);y=features[role+'_chroma'][right].mean(axis=0)
            if min(energy[left].mean(),energy[right].mean())>.08 and min(np.linalg.norm(x),np.linalg.norm(y))>=.05:
                novelty=float(1-x@y/(np.linalg.norm(x)*np.linalg.norm(y)))
                evidence['harmony']=max(evidence['harmony'],novelty)
        family='voice' if role in VOICE_ROLES else 'drums' if role in DRUM_ROLES else None
        if family:evidence[family]=max(evidence[family],abs(float(energy[left].mean()-energy[right].mean())))
    return evidence


def supports_change(project,time,features=None):
    from musical_patterns import describe
    if features is None:
        try:features=describe(project)
        except (OSError,ValueError):return False
    if features is None:return False
    e=boundary(features,time)
    if not e:return False
    # Harmony and its timbre are one family; four drum stems are also one.
    return sum((e['harmony']>.12 or e['texture']>.08,e['bass']>.30,e['voice']>.30,e['drums']>.30))>=2


def refine(project,features=None):
    from musical_patterns import describe
    from structure_review import protected,measures
    rows=copy.deepcopy(project.get('sections',[]));changes=[]
    bars,_=measures(project);beats=np.asarray(project.get('beats',[]))
    if not bars or len(beats)<4:return rows,changes
    if features is None:features=describe(project)
    if features is None:return rows,changes
    for i in range(1,len(rows)):
        previous,current=rows[i-1:i+1];old=current['start']
        if protected(previous) or protected(current) or abs(previous['end']-old)>.001:continue
        if old-previous['start']<4 or current['end']-old<4:continue
        near=beats[np.abs(beats-old)<3]
        if len(near)<3:continue
        pulse=float(np.median(np.diff(near)));radius=min(1.3,1.35*pulse)
        # A cue already on a pulse may deliberately anticipate a chord. Only
        # off-pulse model estimates can move backwards to a stronger arrival.
        off_pulse=min(abs(near-old))>.18*pulse
        candidates=[b for b in bars if .35*pulse<abs(b-old)<=radius and (b>old or off_pulse)
                    and previous['start']+2<b<current['end']-2]
        before=boundary(features,old)
        if not candidates or not before:continue
        ranked=[]
        for at in candidates:
            e=boundary(features,at)
            # Joint harmonic/bass novelty, not a loud fill or a vocal pickup.
            if not e or e['harmony']<.17 or e['bass']<.30:continue
            score=e['harmony']+e['bass']
            if score<(before['harmony']+before['bass'])*1.28+.025:continue
            # Require the same arrival on a short window. A loud fill/change
            # elsewhere in the surrounding two seconds cannot move the cue.
            short=boundary(features,at,max(.6,1.5*pulse))
            if not short or short['harmony']<.17 or short['bass']<.30:continue
            ranked.append((score,at))
        ranked.sort(reverse=True)
        if not ranked or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<.10):continue
        _,at=ranked[0];previous['end']=at;current['start']=at
        changes.append(dict(id=str(uuid.uuid4()),kind='adjust',time=at,before=current['name'],after=current['name'],
                            reason=f'Début proposé à {at:.2f} s au lieu de {old:.2f} s : harmonie et basse concordantes sur une mesure locale, à deux échelles d’écoute.'))
    return rows,changes
