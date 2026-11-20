"""Lightweight placement of a web chart's chord vocabulary on the saved grid.

No trained chord model and no new chord names: audio only distinguishes the
published candidates. Ambiguous placements remain visibly marked for review.
"""
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


def ordered_path(scores, labels, written, *, validate=True):
    """Align a written sequence without inventing durations or repetitions.

    Reject incomplete/contradictory sequences rather than force them onto audio.
    A source's explicit repeats are expanded by the caller, never inferred here.
    """
    import numpy as np
    if not written or len(written)>len(scores) or any(c not in labels for c in written):return None
    if len(written)*len(scores)>2_000_000:return None
    columns=np.array([labels.index(c) for c in written]);emissions=scores[:,columns]
    acc=np.full(len(written),-np.inf);acc[0]=emissions[0,0]
    advance=np.zeros(emissions.shape,dtype=bool)
    for i in range(1,len(scores)):
        moved=np.r_[-np.inf,acc[:-1]-.035]
        advance[i]=moved>acc
        acc=emissions[i]+np.maximum(acc,moved)
    if not np.isfinite(acc[-1]):return None
    position=len(written)-1;path=[]
    for i in range(len(scores)-1,-1,-1):
        path.append(columns[position])
        if advance[i,position]:position-=1
    path=np.array(path[::-1]);selected=scores[np.arange(len(scores)),path]
    regret=scores.max(axis=1)-selected
    if validate and (float(np.mean(regret))>.04 or float(np.mean(selected<.55))>.25):return None
    return path.tolist()


def bass_pedals(chroma, active, edges, pulse):
    """Mark whole sustained notes, including their beginning and ending.

    A centred window misses the edges of a pedal immediately next to a bass
    change. Short clear passing notes and actual bass changes remain separate.
    """
    import numpy as np
    dominant=chroma.argmax(axis=1)
    ordered=np.sort(chroma,axis=1)
    clear=active & ((ordered[:,-1]-ordered[:,-2])>=.35)
    notes=np.where(clear,dominant,-1)
    for i in range(1,len(notes)-1):
        if not clear[i] and active[i] and clear[i-1] and clear[i+1] and dominant[i-1]==dominant[i+1]:
            if edges[i+1]-edges[i]<=.6*pulse:notes[i]=dominant[i-1]
    pedal=np.zeros(len(notes),dtype=bool)
    start=0
    for end in range(1,len(notes)+1):
        if end<len(notes) and notes[end]==notes[start]:continue
        if notes[start]>=0 and edges[end]-edges[start]>=5.7*pulse:pedal[start:end]=True
        start=end
    return pedal


def bass_contradictions(candidates, bass, edges, pulse, pedals):
    """Bounded, independent evidence against a chord missing a stable bass.

    Passing notes, uncertain pitches and pedals do not rule out a harmony.
    This is audio compatibility, never a reward for following the written chart.
    """
    import numpy as np
    chroma=bass['chroma'];dominant=chroma.argmax(axis=1)
    ordered=np.sort(chroma,axis=1);clarity=ordered[:,-1]-ordered[:,-2]
    notes=np.where(bass['active'] & (clarity>=.35),dominant,-1)
    stable=np.zeros(len(notes),dtype=bool);start=0
    for end in range(1,len(notes)+1):
        if end<len(notes) and notes[end]==notes[start]:continue
        if notes[start]>=0 and edges[end]-edges[start]>=.8*pulse:stable[start:end]=True
        start=end
    strength=.12*np.clip(clarity/.5,0,1)*stable*~pedals
    missing=np.array([[pc not in pcs and pc!=root for _,(pcs,root) in candidates] for pc in dominant])
    return strength[:,None]*missing


def place(project,audio,labels,source_url,offset=0,transitions=None,sections=None,sequences=None,phrase_groups=None,written_chart=None):
    import numpy as np
    from services import beat_grid
    candidates=[(label,tones(label)) for label in labels if tones(label)]
    beats,duration=beat_grid(project)
    if len(beats)<2 or not candidates:return [],dict(status='needs_grid',message='Grille rythmique ou accords compatibles manquants : calage à compléter.')
    # Eighth notes use two cells per quarter, three per dotted quarter. Boundaries
    # always come from the existing grid, including variable tempo and pickups.
    subdivision=3 if project.get('settings',{}).get('pulseUnit')=='dottedQuarter' else 2
    edges=np.array(sorted(set([*beats,*[a+(b-a)*part/subdivision for a,b in zip(beats,beats[1:]) for part in range(1,subdivision)],duration])))
    if sequences:edges=np.unique(np.r_[edges,[s['start'] for s in project.get('sections',[])],[s['end'] for s in project.get('sections',[])]])
    edges=edges[(edges>=0)&(edges<=duration)]
    if len(edges)<2:return [],dict(status='needs_grid',message='Grille rythmique trop courte pour caler les accords.')
    from chord_features import peaks,bass_evidence
    features=peaks(audio,edges,offset)
    if features is None:return [],dict(status='no_audio',message='Aucun passage audio exploitable pour le calage.')
    cell,low,strength,tuning=(features[k] for k in ('chroma','bass','strength','tuning'))
    # A missing/unreadable optional stem must not prevent the original audio
    # path from producing its proposal (including interrupted separations).
    try:bass=bass_evidence(project,edges,tuning)
    except (OSError,ValueError,RuntimeError):bass=None
    templates=np.zeros((len(candidates),12));roots=[]
    for i,(_, (pcs,root)) in enumerate(candidates):
        templates[i,pcs]=1;templates[i]/=np.linalg.norm(templates[i]);roots.append(root)
    # Root and inversion share the same harmonic family. Keep suspended chords,
    # qualities and different tonics separate (e.g. C6 is not an alias for Am7).
    families=[(pcs[0],tuple(sorted(pcs))) for _,(pcs,_) in candidates]
    tonics=np.array([pcs[0] for _,(pcs,_) in candidates])
    same_family=np.array([[a==b for b in families] for a in families])
    acoustic=cell@templates.T+.12*low[:,roots]
    confidence_evidence=acoustic.copy()
    scores=acoustic.copy()
    reliable_family={}
    pulse=float(np.median(np.diff(beats)))
    if bass is not None:
        # A held bass pedal can accompany changing guitar chords. In that case
        # let the harmonic evidence decide instead of forcing that bass as root.
        dominant=bass['chroma'].argmax(axis=1)
        pedal=bass_pedals(bass['chroma'],bass['active'],edges,pulse)
        confidence_evidence-=bass_contradictions(candidates,bass,edges,pulse,pedal)
        support=bass['chroma'][:,roots].copy()
        support[pedal]=0
        strongest=acoustic.argmax(axis=1)
        for i,j in enumerate(strongest):
            alternatives=acoustic[i,tonics!=tonics[j]]
            if not len(alternatives):continue
            # A clear D chord over A is compatible with an inversion/pedal;
            # that A is not independent evidence for replacing D by A major.
            if (acoustic[i,j]>.82 and dominant[i]!=tonics[j] and dominant[i] in candidates[j][1][0]
                    and acoustic[i,j]-float(alternatives.max())>.12):
                support[i,tonics!=tonics[j]]=0
                reliable_family[i]=tonics[j]
        scores+=.40*support*bass['active'][:,None]
    if sections:
        from chord_sources import section_kind
        middle=(edges[:-1]+edges[1:])/2;occurrences={}
        for section in project.get('sections',[]):
            kind=section_kind(section['name']);published=sections.get(kind,[])
            occurrence=occurrences.get(kind,0);occurrences[kind]=occurrence+1
            options=[s for s in sequences or [] if s['kind']==kind]
            if options and (len(options)==1 or occurrence<len(options)):
                written=list(dict.fromkeys(options[0 if len(options)==1 else occurrence]['chords']))
                written_roots={tones(c)[0][0] for c in written if tones(c)}
                if len(written)>=2:
                    # Distinguish the variants actually printed for this verse
                    # or chorus. Do not remove a whole root absent from a short
                    # chart: its pickup, repeat or ending may simply be omitted.
                    published=[c for c in published if c in written or not tones(c) or tones(c)[0][0] not in written_roots]
            # Single written chords often mean "repeat the previous riff";
            # they are not a complete harmonic vocabulary for that section.
            if len(published)<2:continue
            rows=(middle>=section['start'])&(middle<section['end'])
            # Structural/vocal cues can anticipate the chord change. Fade the
            # chart vocabulary prior at both ends, leaving audio free to carry
            # a pickup or the last chord across an existing section boundary.
            distance=np.minimum(middle-section['start'],section['end']-middle)
            published_roots={tones(c)[0][0] for c in published if tones(c)}
            outside=np.array([root not in published_roots for root in tonics])
            weight=rows[:,None]*np.where(outside[None,:],np.clip(distance/(2*pulse),0,1)[:,None],1.)
            scores-=.22*weight*np.array([label not in published for label,_ in candidates])[None,:]
    quiet=strength<max(1e-5,float(np.percentile(strength,90))*.025)
    if bass is not None:quiet &= ~bass['active']
    scores[quiet]=0
    penalty=np.where(same_family,.025,.12)*(1-np.eye(len(candidates)))
    if transitions:
        published={tuple(pair) for pair in transitions}
        penalty+=np.array([[.12 if not same_family[i,j] and (a,b) not in published else 0 for j,(b,_) in enumerate(candidates)] for i,(a,_) in enumerate(candidates)])
    previous=np.zeros_like(scores,dtype=int);acc=scores[0].copy()
    for i in range(1,len(scores)):
        choices=acc[:,None]-penalty
        previous[i]=np.argmax(choices,axis=0);acc=scores[i]+np.max(choices,axis=0)
    path=[int(acc.argmax())]
    for i in range(len(scores)-1,0,-1):path.append(int(previous[i,path[-1]]))
    path=path[::-1];audio_path=path.copy();segments=[];uncertain=0;ordered_sections=0
    if sequences:
        from chord_sources import section_kind
        occurrences={};middle=(edges[:-1]+edges[1:])/2;phrases={}
        for index,section in enumerate(project.get('sections',[])):
            kind=section_kind(section['name']);options=[s for s in sequences if s['kind']==kind]
            occurrence=occurrences.get(kind,0);occurrences[kind]=occurrence+1
            if not options or (len(options)>1 and occurrence>=len(options)):continue
            written=options[0 if len(options)==1 else occurrence]
            sequence=written['chords']*max(1,min(16,written.get('repeat',1)))
            rows=np.flatnonzero((middle>=section['start'])&(middle<section['end']))
            if not len(rows):continue
            phrases[index]=(sequence,rows)
            proposed=ordered_path(scores[rows],[c[0] for c in candidates],sequence)
            if proposed is not None:
                for row,choice in zip(rows,proposed):path[row]=choice
                ordered_sections+=1
        # Share evidence only for independently matched audio occurrences AND
        # the same complete written progression. Different endings stay apart.
        for group in phrase_groups or []:
            members=[phrases[i] for i in group if i in phrases]
            if len(members)<2 or any(seq!=members[0][0] for seq,_ in members):continue
            if any(len(rows)!=len(members[0][1]) for _,rows in members):continue
            written=members[0][0];pooled=np.mean([scores[rows] for _,rows in members],axis=0)
            proposed=ordered_path(pooled,[c[0] for c in candidates],written)
            if proposed is None:continue
            # Pooling may not overrule a contradictory individual occurrence.
            if any(float(np.mean(scores[rows].max(axis=1)-scores[rows,np.asarray(proposed)]))>.04 for _,rows in members):continue
            def uncertainty(rows,choices):
                selected=scores[rows,np.asarray(choices)];competitors=scores[rows].copy()
                competitors[np.arange(len(rows)),np.asarray(choices)]=-np.inf
                margins=selected-competitors.max(axis=1)
                return int(np.sum((margins<.075)|(selected<.65)))
            if any(uncertainty(rows,proposed)>uncertainty(rows,[path[row] for row in rows]) for _,rows in members):continue
            for _,rows in members:
                for row,choice in zip(rows,proposed):path[row]=choice
    ordered_chart=False
    if written_chart and not sequences and len(written_chart)>=8:
        aligned=ordered_path(scores,[c[0] for c in candidates],written_chart,validate=False)
        if aligned is not None:
            # A chart can omit an interlude or repeat. Keep only local spans
            # independently supported by the audio; never force its bad spans.
            middle=(edges[:-1]+edges[1:])/2
            for section in project.get('sections',[]):
                rows=np.flatnonzero((middle>=section['start'])&(middle<section['end']))
                if len(rows)<16:continue
                choices=np.asarray(aligned)[rows];selected=scores[rows,choices]
                if len(set(choices))<3:continue
                regret=scores[rows].max(axis=1)-selected
                if float(np.mean(regret))>.035 or float(np.mean(selected<.55))>.25:continue
                if float(np.mean(regret[:3]))>.08 or float(np.mean(regret[-3:]))>.08:continue
                for row,choice in zip(rows,choices):path[row]=int(choice)
                ordered_chart=True
    # A written phrase may start after the structural cue or finish before it.
    # Keep an independently supported audio pickup/tail instead of stretching
    # the first/last written chord to the section's boundary.
    middle=(edges[:-1]+edges[1:])/2
    for section in project.get('sections',[]):
        near=(np.minimum(abs(middle-section['start']),abs(middle-section['end']))<pulse)
        for i in np.flatnonzero(near):
            choice=audio_path[i]
            observed=bass['chroma'][i] if bass is not None and bass['active'][i] else low[i]
            support=float(observed[tonics[choice]]-np.max(np.delete(observed,tonics[choice])))
            if tonics[path[i]]!=tonics[choice] and support>=.35 and scores[i,choice]-scores[i,path[i]]>.08:
                path[i]=audio_path[i]
    # Written order is a hypothesis, not permission to overwrite a clear
    # harmonic family already explaining the independently observed bass.
    for i,tonic in reliable_family.items():
        if tonics[path[i]]!=tonic:
            members=np.flatnonzero(tonics==tonic);path[i]=int(members[np.argmax(scores[i,members])])
    # The written bass is not always the played bass. Resolve the spelling of
    # a harmonic family from independent low-note evidence, after alignment.
    # If a pedal is outside its listed inversions, prefer its plain chord when
    # provided by the source; never invent a new label or a slash bass.
    for i,choice in enumerate(path):
        members=np.flatnonzero(same_family[choice])
        if len({roots[j] for j in members})<2:continue
        observed=bass['chroma'][i] if bass is not None and bass['active'][i] else low[i]
        order=np.argsort(observed);dominant_note=int(order[-1])
        supported=[j for j in members if roots[j]==dominant_note]
        plain=[j for j in members if '/' not in candidates[j][0]]
        if supported and observed[dominant_note]-observed[order[-2]]>=.35:
            path[i]=int(max(supported,key=lambda j:scores[i,j]))
        elif plain:path[i]=int(max(plain,key=lambda j:scores[i,j]))
    boundaries={s['start'] for s in project.get('sections',[])} if sequences else set()
    for i,choice in enumerate(path):
        if quiet[i]:continue
        # Confidence compares harmonic families, with bounded contradictions
        # from independently observed bass. Written order and decoding scores
        # never contribute; agreement is not a calibrated probability.
        family=same_family[choice];evidence=float(confidence_evidence[i,family].max())
        alternatives=confidence_evidence[i,~family]
        margin=evidence-max(alternatives) if len(alternatives) else evidence-.65
        confidence=float(np.clip(margin/.15,0,1))*min(1,evidence/.65)
        # Resolve inversion independently. Identical treble templates cannot
        # establish a slash bass; neither the website nor a Viterbi preference
        # is evidence that this note was played.
        if '/' in candidates[choice][0] or family.sum()>1:
            family_roots=sorted({roots[j] for j in np.flatnonzero(family) if roots[j]!=roots[choice]})
            observed=bass['chroma'][i] if bass is not None and bass['active'][i] else low[i]
            inversion_margin=float(observed[roots[choice]]-max((observed[j] for j in family_roots),default=0))
            # A plain chord is still valid over an unrepresented pedal note.
            # A slash chord needs positive evidence for its specified bass.
            if '/' in candidates[choice][0]:
                inversion_margin=min(inversion_margin,float(observed[roots[choice]]-np.max(np.delete(observed,roots[choice]))))
                confidence=min(confidence,float(np.clip(inversion_margin/.4,0,1)))
            elif family_roots and inversion_margin<-.3:
                confidence=min(confidence,.49)
        review=confidence<.5 or evidence<.65
        if review and not quiet[i]:uncertain+=1
        label=candidates[choice][0]
        if segments and segments[-1]['label']==label and edges[i]-segments[-1]['end']<.6 and edges[i] not in boundaries:
            segment=segments[-1];segment['end']=float(edges[i+1]);segment['_scores'].append(confidence)
        else:segments.append(dict(start=float(edges[i]),end=float(edges[i+1]),label=label,sourceURL=source_url,_scores=[confidence]))
    if not segments:return [],dict(status='no_audio',message='Grille Internet trouvée, mais aucun passage audio exploitable pour la caler.')
    for segment in segments:segment['confidence']=float(np.mean(segment.pop('_scores')))
    return segments,dict(status='proposed',subdivision=subdivision,tuningCents=round(float(tuning)*100,1),uncertainCells=uncertain,orderedSections=ordered_sections,orderedChart=ordered_chart,bassEvidence=bass is not None,
        message='Accords de la source calés sur les temps et contretemps détectés. Les placements restent des propositions à vérifier à l’écoute.')
