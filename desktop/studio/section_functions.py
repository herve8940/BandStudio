"""Functional section proposals from local singing, chart headings and stems.

No title-specific rules. A web heading supplies a name, never a timestamp.
Unconfirmed proposals and protection of accepted regions remain distinct.
"""
import copy
from difflib import SequenceMatcher
import math
import re
import uuid

import numpy as np
from chart_sections import fingerprints,SCHEMA


def timed_words(project):
    result=[]
    for row in sorted(project.get('lyrics',[]),key=lambda r:r['start']):
        plain=fingerprints(row.get('text',''));detail=row.get('words') or []
        spoken=[k for w in detail for k in fingerprints(w.get('text',w.get('w','')))]
        agreement=SequenceMatcher(None,plain,spoken,autojunk=False).ratio()
        if detail and agreement>=.8:
            for word in detail:
                at=word.get('start',word.get('t'));end=word.get('end')
                if not isinstance(at,(int,float)) or not isinstance(end,(int,float)) or not math.isfinite(at+end) or not row['start']-.1<=at<end<=row['end']+.1:continue
                for token in fingerprints(word.get('text',word.get('w',''))):result.append(dict(key=token,start=at,end=end))
        else:
            for index,token in enumerate(plain):result.append(dict(key=token,start=row['start'] if index==0 else None,end=row['end']))
    return result[:3000]


def locate(block,words):
    """Match a distinctive prefix with insertions/substitutions, without guessing
    sub-line timestamps where the local transcription has none.
    """
    prefix=block.get('words',[])[:24]
    if not 6<=len(prefix)<=24 or len(set(prefix))<4:return []
    keys=[w['key'] for w in words];candidates=[]
    for start,key in enumerate(keys):
        if key not in prefix[:2] or words[start]['start'] is None:continue
        window=keys[start:start+len(prefix)+6]
        matcher=SequenceMatcher(None,prefix,window,autojunk=False)
        blocks=[b for b in matcher.get_matching_blocks() if b.size]
        if not blocks or blocks[0].a>1 or blocks[0].b>1:continue
        exact=sum(b.size for b in blocks);span=blocks[-1].b+blocks[-1].size
        if exact<max(6,.70*len(prefix)) or exact/max(span,len(prefix))<.60:continue
        end=words[start+span-1]['end'];at=words[start]['start']
        if not .5<end-at<35:continue
        score=2*exact/(len(prefix)+span)
        candidates.append(dict(time=at,end=end,score=score,index=start,matched=exact))
    # Consecutive repeated short words must not create duplicate entrances.
    accepted=[]
    for candidate in sorted(candidates,key=lambda c:-c['score']):
        if not any(abs(c['time']-candidate['time'])<3 for c in accepted):accepted.append(candidate)
    return sorted(accepted,key=lambda c:c['time'])


def chart_anchors(project):
    words=timed_words(project);anchors=[]
    for source in (project.get('chordReference') or {}).get('sources',[]):
        if source.get('anchorSchema')!=SCHEMA:continue
        for index,block in enumerate(source.get('sectionAnchors',[])[:128]):
            if not isinstance(block,dict) or not isinstance(block.get('words'),list):continue
            if not 6<=len(block['words'])<=256 or not all(isinstance(w,str) and re.fullmatch('[0-9a-f]{20}',w) for w in block['words']):continue
            if not isinstance(block.get('kind'),str) or not isinstance(block.get('name'),str):continue
            for found in locate(block,words):
                anchors.append(dict(**found,kind=block['kind'],name=block['name'],publisher=source['publisher'],
                                    url=source['url'],block=index,words=block['words']))
    return anchors


def pulse(project):
    if project.get('settings',{}).get('gridMode')=='fixed':
        from services import pulse_bpm
        return 60/pulse_bpm(project)
    beats=np.asarray(project.get('beats',[]),dtype=float)
    spans=np.diff(beats);spans=spans[(spans>.15)&(spans<2)]
    return float(np.median(spans)) if len(spans) else .5


def vocal_support(features,at,end):
    if features is None or not features['available'][1]:return False
    mask=(features['middle']>=at)&(features['middle']<min(end,at+8))
    return bool(mask.sum()>=4 and features['voiceCoverage'][mask].all() and np.mean(features['voiceEnergy'][mask]>.15)>.35)


def similar_singing(features,a,b):
    """Same sung text may repeat with different drums/bass ornamentation.
    Require harmonic agreement as well as the lyric match, not identical fills.
    """
    if features is None:return False
    width=min(a['end']-a['time'],b['end']-b['time'],12)
    if width<4:return False
    masks=[(features['middle']>=c['time'])&(features['middle']<c['time']+width) for c in (a,b)]
    if min(m.sum() for m in masks)<8:return False
    if any(not features[key+'Coverage'][m].all() for key in ('harmony','bass') for m in masks):return False
    def cosine(key):
        x,y=[features[key][m].mean(axis=0) for m in masks]
        return float(x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-9))
    return (cosine('harmony')>=.9 and cosine('texture')>=.9 and
            (not features['available'][0] or cosine('bass')>=.8) and
            all(vocal_support(features,c['time'],c['end']) for c in (a,b)))


def lyric_events(project,features,anchors):
    from structure_review import kind,protected
    dt=pulse(project);events=[]
    allowed={'verse','chorus','prechorus','bridge','postchorus'}
    rows=project.get('sections',[])
    for a in anchors:
        if a['score']<.78 or not vocal_support(features,a['time'],a['end']):continue
        if a['kind'] not in allowed|{'unknown'}:continue
        peers=[b for b in anchors if abs(b['time']-a['time'])>max(12,8*dt) and b['score']>=.78 and
               SequenceMatcher(None,a['words'][:24],b['words'][:24],autojunk=False).ratio()>=.8]
        donors=[]
        for b in peers:
            near=min(rows,key=lambda s:abs(s['start']-b['time']),default=None)
            if not near or abs(near['start']-b['time'])>max(1.5,3*dt):continue
            target=kind(near['name'])
            if target not in allowed or (a['kind']!='unknown' and a['kind']!=target):continue
            if similar_singing(features,a,b):donors.append((target,near,b))
        if not donors or len({d[0] for d in donors})!=1:continue
        target,donor,b=donors[0]
        # A verse quotation at the end of a song does not change an outro/last
        # refrain into another verse. The surrounding function takes priority.
        covering=next((s for s in rows if s['start']<=a['time']<s['end']),None)
        if not covering or protected(covering):continue
        if kind(covering['name']) in ('outro','solo','bridge') and target=='verse':continue
        if target=='verse' and a['time']>.82*rows[-1]['end']:continue
        near=min(rows,key=lambda s:abs(s['start']-a['time']))
        if abs(near['start']-a['time'])<=max(1.5,3*dt):continue
        # Place within the saved pulse grid, allowing sung pickups. A source's
        # arbitrary line wrap never determines the boundary.
        estimate=a['time']+np.clip(donor['start']-b['time'],-dt,dt)
        events.append(dict(time=float(estimate),kind=target,method='lyrics-repeat',support=2,
                           reason='Paroles répétées retrouvées dans un '+donor['name'].lower()+
                                  ' et accompagnement harmonique concordant ; repère à écouter.',publisher=a['publisher']))
    return events


def fit_reference(project,reference,extra=()):
    """Fit an offset on several distinct, ordered musical landmarks.

    Keep local interpolation when an edit has a longer tail; only cover the
    whole recording when its duration corroborates the fitted video pre-roll.
    """
    from structure_review import kind,confirmed
    if not reference:return None
    entries=reference['entries'];points=[]
    for s in project.get('sections',[]):
        k=kind(s['name'])
        if k in ('intro','verse','chorus','prechorus','bridge','solo','outro','postchorus'):
            points.append(dict(time=s['start'],kind=k,trusted=bool(confirmed(s))))
    points.extend(dict(time=e['time'],kind=e['kind'],trusted=False) for e in extra)
    points.sort(key=lambda p:p['time'])
    hypotheses={round(p['time']-e['time'],4) for p in points for e in entries
                if p['kind']==kind(e['name']) and abs(p['time']-e['time'])<=30}
    options=[];seen=set()
    for offset in hypotheses:
        matched=[];used=set();last=-1
        for index,e in enumerate(entries):
            candidates=[(abs(p['time']-e['time']-offset),j,p) for j,p in enumerate(points)
                        if j not in used and p['time']>last and p['kind']==kind(e['name']) and abs(p['time']-e['time']-offset)<=1.6]
            if not candidates:continue
            error,j,p=min(candidates,key=lambda c:(c[0],-c[2]['trusted']))
            matched.append((e['time'],p['time'],p['trusted']));used.add(j);last=p['time']
        signature=tuple((a,b) for a,b,_ in matched)
        if signature in seen or len(matched)<3:continue
        seen.add(signature)
        span=matched[-1][0]-matched[0][0]
        if span<max(20,reference['duration']*.20):continue
        if any(b[0]-a[0]<4 or not .88<=(b[1]-a[1])/(b[0]-a[0])<=1.12 for a,b in zip(matched,matched[1:])):continue
        differences=np.array([b-a for a,b,_ in matched]);center=float(np.median(differences))
        error=float(np.mean(abs(differences-center)))
        if max(abs(differences-center))>1.6 or error>.8:continue
        options.append(dict(anchors=matched,offset=center,error=error,span=span))
    if not options:return None
    options.sort(key=lambda r:(len(r['anchors']),sum(a[2] for a in r['anchors']),-r['error'],r['span']),reverse=True)
    best=options[0]
    if any(len(r['anchors'])==len(best['anchors']) and abs(r['offset']-best['offset'])>2 and abs(r['error']-best['error'])<.25 for r in options[1:]):return None
    length=max(t['offset']+t['duration'] for t in project['tracks'] if not t['role'].startswith('guide_'))
    best['whole']=bool(abs(length-reference['duration']-best['offset'])<=3 and best['span']>=reference['duration']*.30)
    return best


def mapped_time(fit,time):
    anchors=fit['anchors']
    if anchors[0][0]<=time<=anchors[-1][0]:
        return float(np.interp(time,[a for a,b,_ in anchors],[b for a,b,_ in anchors]))
    return time+fit['offset'] if fit['whole'] else None


def transition_support(features,at,dt):
    from section_evidence import boundary
    values=boundary(features,at,max(1.,3*dt)) if features is not None else None
    if not values:return 0,0.
    votes=sum((values['harmony']>.10 or values['texture']>.07,values['bass']>.18,
               values['voice']>.20,values['drums']>.20))
    strength=sum(min(1.,values[key]/scale) for key,scale in (('harmony',.25),('bass',.4),('voice',.5),('drums',.5)))
    return votes,strength


def timed_events(project,reference,features,extra,anchors):
    from structure_review import kind
    fit=fit_reference(project,reference,extra)
    if not fit:return [],None
    dt=pulse(project);events=[]
    for index,entry in enumerate(reference['entries']):
        target=kind(entry['name']);at=mapped_time(fit,entry['time'])
        if at is None or target not in ('verse','chorus','prechorus','bridge','break','solo','instrumental','intro','outro','postchorus'):continue
        if any(abs(entry['time']-a)<.01 for a,b,_ in fit['anchors']):continue
        votes,strength=transition_support(features,at,dt)
        # An interlude can be sung. Translating it to "Instrumental" would be
        # misleading when the isolated voice clearly carries a melody here.
        if target in ('instrumental','solo') and vocal_support(features,at,at+8):continue
        nearby=[a for a in anchors if abs(a['time']-at)<=2.5 and a['score']>=.8 and
                a['kind'] in (target,'unknown',*(['chorus'] if target=='postchorus' else [])) and vocal_support(features,a['time'],a['end'])]
        # A pre-chorus is supported by its repeated position immediately before
        # a chorus, not by being short or by a rise in volume alone.
        repeated_pre=(target=='prechorus' and index+1<len(reference['entries']) and
                      kind(reference['entries'][index+1]['name'])=='chorus' and
                      sum(kind(e['name'])=='prechorus' for e in reference['entries'])>=2)
        if votes<2 and not nearby and not (repeated_pre and votes>=1):continue
        if nearby:
            closest=min(nearby,key=lambda a:abs(a['time']-at))
            # A line can start on a pickup before the written section. Do not
            # shift a reliable map by more than one local pulse for that alone.
            at=float(np.clip(closest['time'],at-dt,at+dt))
        conflicts=sorted({a['kind'] for a in anchors if abs(a['time']-at)<=2.5 and a['score']>=.8 and
                          a['kind'] not in (target,'unknown','intro') and not (target=='postchorus' and a['kind']=='chorus')})
        reason='Fonction « '+entry['name']+' » publiée par '+reference['publisher']+', adaptée aux repères locaux ; concordance des instruments ou du chant, à écouter.'
        if conflicts:
            from structure_review import label
            reason+=' Autre lecture publiée : '+', '.join(label(k) for k in conflicts)+'.'
        events.append(dict(time=at,kind=target,method='timed-reference',support=votes,reason=reason,
                           disputed=bool(conflicts),allowRepeat=bool(nearby and target=='verse' and re.search(r'\d',entry['name'])),publisher=reference['publisher']))
    return events,fit


def break_events(project,features):
    """A short interruption of the band, bounded by sustained music on both sides.
    Vocal pauses, fills, sparse intros and the final fade are not band breaks.
    """
    if features is None or not features['available'][[0,2]].all():return []
    dt=pulse(project);mid=features['middle'];events=[]
    keys=('harmony','bass','drums')
    levels=np.vstack([features[k+'Energy'] for k in keys])
    quiet=np.all(levels<.09,axis=0)
    starts=np.flatnonzero(quiet&~np.r_[False,quiet[:-1]])
    ends=np.flatnonzero(quiet&~np.r_[quiet[1:],False])+1
    for a,b in zip(starts,ends):
        at=float(features['edges'][a]);end=float(features['edges'][b])
        if not max(2.,4*dt)<=end-at<=16*dt:continue
        left=(mid>=at-4*dt)&(mid<at);right=(mid>=end)&(mid<end+4*dt)
        if min(left.sum(),right.sum())<6:continue
        if any(min(features[k+'Energy'][left].mean(),features[k+'Energy'][right].mean())<.25 for k in keys):continue
        if any(not features[k+'Coverage'][a:b].all() for k in keys):continue
        covering=next((s for s in project['sections'] if s['start']+4*dt<at<end<s['end']-4*dt),None)
        if not covering:continue
        events.append(dict(time=at,end=end,kind='break',method='band-break',support=3,
                           reason='Interruption brève de l’accompagnement, suivie de sa reprise sur les pistes séparées ; à écouter.',publisher='Audio local'))
    return events


def place_events(project,events,features,protected_ids=None):
    from structure_review import protected,kind,label,measures
    original=project.get('sections',[]);rows=copy.deepcopy(original);changes=[];warnings=[];dt=pulse(project)
    bars,_=measures(project)
    fixed={s['id'] for s in original if protected(s)} if protected_ids is None else protected_ids
    changed_ids=set()
    # Reference maps supply the full functional sequence. A repeated lyric
    # gives a local missing occurrence; it cannot erase a contradictory map.
    ordered=sorted(events,key=lambda e:(e['time'],e['method']!='timed-reference'))
    reduced=[]
    for event in ordered:
        near=next((e for e in reduced if abs(e['time']-event['time'])<2*dt),None)
        if near:
            if near['kind']!=event['kind']:
                warnings.append('Fonction discutée autour de '+f"{event['time']:.1f}"+' s : écouter la proposition et ses sources.')
                if event['method']=='timed-reference':reduced.remove(near);reduced.append(event)
            elif event['method']=='timed-reference':reduced.remove(near);reduced.append(event)
        else:reduced.append(event)
    # Return events are resolved when placing the break, after preceding edits.
    for event in list(reduced):
        if event['kind']=='break' and 'end' in event:
            reduced.append({**event,'time':event['end'],'kind':'return','from':event['time'],'reason':'Reprise après le break ; fonction du passage conservée.'})
    break_returns={}
    for event in sorted(reduced,key=lambda e:e['time']):
        target=event['kind'];estimate=event['time'];nearest=min(rows,key=lambda s:abs(s['start']-estimate),default=None)
        if target=='return':
            target=break_returns.get(event['from'])
            if not target:continue
        if nearest is None:continue
        if event.get('disputed'):warnings.append('Noms différents selon les sources autour de '+f'{estimate:.1f}'+' s : écouter avant de valider.')
        close=abs(nearest['start']-estimate)<=(.1 if event['method']=='band-break' else max(.75,2*dt))
        if close:
            if nearest['id'] in fixed or kind(nearest['name'])==target:continue
            if kind(nearest['name']) in ('silence','avant depart'):continue
            # Do not rename the lead-in on a line starting just before a section.
            before=nearest['name'];nearest['name']=label(target);changed_ids.add(nearest['id'])
            changes.append(dict(id=str(uuid.uuid4()),kind='rename',time=nearest['start'],before=before,after=nearest['name'],reason=event['reason']))
            continue
        covering=next((s for s in rows if s['start']<estimate<s['end']),None)
        if not covering or covering['id'] in fixed:continue
        if kind(covering['name'])==target and not event.get('allowRepeat'):continue
        if event['method']=='band-break':at=estimate
        else:
            candidates=[b for b in bars if abs(b-estimate)<=max(1.1,2.5*dt) and covering['start']+.75<b<covering['end']-.75]
            if not candidates:continue
            at=min(candidates,key=lambda b:abs(b-estimate)-.10*transition_support(features,b,dt)[1])
        if min(at-covering['start'],covering['end']-at)<max(.75,dt):continue
        if event.get('allowRepeat') and min(at-covering['start'],covering['end']-at)<8*dt:continue
        if target=='break':break_returns[estimate]=kind(covering['name'])
        before=covering['name'];end=covering['end'];covering['end']=at;changed_ids.add(covering['id'])
        new=dict(id=str(uuid.uuid4()),name=label(target),start=at,end=end,origin='reference',locked=False,reviewed=False)
        rows.append(new);changed_ids.add(new['id']);rows.sort(key=lambda s:s['start'])
        changes.append(dict(id=str(uuid.uuid4()),kind='insert',time=at,before=before,after=new['name'],reason=event['reason']))
    for row in rows:
        if row['id'] in changed_ids:row.update(origin='reference',locked=True,reviewed=False)
    return rows,changes,list(dict.fromkeys(warnings))


def analyse(project,features=None,reference=None,placement=None):
    from musical_patterns import describe
    from structure_review import protected
    if features is None:
        try:features=describe(project)
        except (OSError,ValueError):features=None
    anchors=chart_anchors(project)
    lyrics=lyric_events(project,features,anchors)
    timed,fit=timed_events(project,reference,features,lyrics,anchors) if reference else ([],None)
    events=lyrics+timed+break_events(project,features)
    # Evidence uses only the initial landmarks. Earlier completion proposals
    # may receive placements, but must never become corroborating evidence.
    rows,changes,warnings=place_events({**project,'sections':placement} if placement is not None else project,events,features,
                                      {s['id'] for s in project['sections'] if protected(s)})
    if fit and not fit['whole']:
        warnings.append('Version de durée différente : comparaison limitée aux repères intérieurs concordants, sans extrapoler le début ni la fin.')
    return dict(sections=rows,changes=changes,warnings=warnings,
                evidence=dict(lyricAnchors=len(anchors),repeatedEntries=len(lyrics),timedAnchors=len(fit['anchors']) if fit else 0,
                              referenceOffset=fit['offset'] if fit else None,wholeReference=fit['whole'] if fit else False),events=events)
