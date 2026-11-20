"""Conservative audio checks for proposed structure, never manual boundaries."""
import copy
import uuid
import numpy as np


def boundary(features,time,window=2.):
    middle=features['middle'];left=(middle>=time-window)&(middle<time);right=(middle>=time)&(middle<time+window)
    if left.sum()<2 or right.sum()<2:return None
    evidence={}
    for key in ('harmony','bass','texture'):
        x=features[key][left].mean(axis=0);y=features[key][right].mean(axis=0)
        if min(np.linalg.norm(x),np.linalg.norm(y))<.05:return None
        evidence[key]=float(1-x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-9))
    for key in ('voice','drums'):
        evidence[key]=abs(float(features[key+'Energy'][left].mean()-features[key+'Energy'][right].mean()))
    return evidence


def supports_change(project,time,features=None):
    from musical_patterns import describe
    if features is None:
        try:features=describe(project)
        except (OSError,ValueError):return False
    if features is None or not features['available'].all():return False
    e=boundary(features,time)
    if not e:return False
    return sum((e['harmony']>.12,e['bass']>.30,e['texture']>.08,e['voice']>.30,e['drums']>.30))>=2


def refine(project,features=None):
    from musical_patterns import describe
    from structure_review import protected,measures
    rows=copy.deepcopy(project.get('sections',[]));changes=[]
    bars,_=measures(project);beats=np.asarray(project.get('beats',[]))
    if not bars or len(beats)<4:return rows,changes
    if features is None:features=describe(project)
    if features is None or not features['available'].all():return rows,changes
    for i in range(1,len(rows)):
        previous,current=rows[i-1:i+1];old=current['start']
        if protected(previous) or protected(current) or abs(previous['end']-old)>.001:continue
        if old-previous['start']<4 or current['end']-old<4:continue
        near=beats[np.abs(beats-old)<3]
        if len(near)<3:continue
        pulse=float(np.median(np.diff(near)));radius=min(1.3,1.35*pulse)
        # A functional cue may anticipate the harmonic arrival. Do not move
        # it earlier into the previous section on a louder preparatory chord.
        candidates=[b for b in bars if .35*pulse<b-old<=radius and previous['start']+2<b<current['end']-2]
        before=boundary(features,old)
        if not candidates or not before:continue
        ranked=[]
        for at in candidates:
            e=boundary(features,at)
            # Joint harmonic/bass novelty, not a loud fill or a vocal pickup.
            if not e or e['harmony']<.17 or e['bass']<.30:continue
            score=e['harmony']+e['bass']
            if score<(before['harmony']+before['bass'])*1.28+.025:continue
            ranked.append((score,at))
        ranked.sort(reverse=True)
        if not ranked or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<.10):continue
        _,at=ranked[0];previous['end']=at;current['start']=at
        changes.append(dict(id=str(uuid.uuid4()),kind='adjust',time=at,before=current['name'],after=current['name'],
                            reason=f'Début proposé à {at:.2f} s au lieu de {old:.2f} s : changement conjoint d’harmonie et de basse sur une mesure locale.'))
    return rows,changes
