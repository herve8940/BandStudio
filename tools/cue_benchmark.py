"""Full-song cue evaluation with explicit, dimension-specific references.

No inference is run on the user's projects and no project is modified. SALAMI
is development data: overlap with pretrained structure-model training is not
excluded. Existing reviewed projects are personal acceptance cases, not an
independent test set. Neither source provides verified beat labels here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from cue_feedback import references


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while data:=f.read(2**20):h.update(data)
    return h.hexdigest()


def write(path,value):
    from services import atomic
    atomic(path,value)


def label(text):
    text=unicodedata.normalize('NFKD',str(text).casefold())
    text=''.join(x for x in text if not unicodedata.combining(x))
    text=re.sub(r'[^a-z]','',text)
    return {'couplet':'verse','refrain':'chorus','prerefrain':'prechorus',
            'pont':'bridge','instrumental':'inst','avantdepart':'silence',
            'nofunction':'unknown','end':'end'}.get(text,text)


def parse_salami(path):
    """Preserve simultaneous labels and unknown spans; merge repeated phrases."""
    events={}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        t,name=line.split(maxsplit=1);t=float(t)
        if t<0:raise ValueError('Negative annotation time')
        events.setdefault(t,set()).add(label(name))
    times=sorted(events);segments=[]
    for start,end in zip(times,times[1:]):
        labels=sorted(events[start]-{'end'}) or ['unknown']
        if segments and segments[-1]['labels']==labels:segments[-1]['end']=end
        else:segments.append(dict(start=start,end=end,labels=labels))
    return dict(duration=times[-1] if times else 0,segments=segments)


def match(reference,estimated,tolerance):
    """One-to-one monotone matching: max hits, then minimum total error."""
    ref=sorted(enumerate(reference),key=lambda v:v[1]);est=sorted(enumerate(estimated),key=lambda v:v[1])
    n,m=len(ref),len(est);table=[[(0,0.) for _ in range(m+1)] for _ in range(n+1)]
    decisions={}
    for i in range(1,n+1):
        for j in range(1,m+1):
            options=[(table[i-1][j],'r'),(table[i][j-1],'e')]
            distance=abs(ref[i-1][1]-est[j-1][1])
            if distance<=tolerance:
                hits,error=table[i-1][j-1];options.append(((hits+1,error-distance),'m'))
            table[i][j],decisions[i,j]=max(options,key=lambda v:v[0])
    pairs=[];i,j=n,m
    while i and j:
        choice=decisions[i,j]
        if choice=='m':pairs.append((ref[i-1][0],est[j-1][0]));i-=1;j-=1
        elif choice=='r':i-=1
        else:j-=1
    return list(reversed(pairs))


def boundary_score(ref,pred,tolerance=.5,complete=False):
    pairs=match([r['start'] for r in ref],[r['start'] for r in pred],tolerance)
    hits=len(pairs)
    return dict(referenceCount=len(ref),predictionCount=len(pred),matched=hits,
        recall=hits/len(ref) if ref else None,
        precision=hits/len(pred) if pred and complete else None,
        f1=2*hits/(len(ref)+len(pred)) if complete and (ref or pred) else None,
        missed=len(ref)-hits,extra=len(pred)-hits if complete else None,
        meanAbsoluteSeconds=sum(abs(ref[i]['start']-pred[j]['start']) for i,j in pairs)/hits if hits else None,
        labelMatches=sum(label(pred[j]['name']) in ref[i]['labels'] for i,j in pairs),
        mismatches=[dict(expected=r['start'],labels=r['labels']) for i,r in enumerate(ref) if i not in {a for a,b in pairs}])


def structure_score(reference,predictions):
    duration=reference['duration'];segments=reference['segments']
    known=[s for s in segments if 'unknown' not in s['labels'] and 'silence' not in s['labels']]
    ref=[s for s in known if .25<s['start']<duration-.25]
    # Unknown spans are not false-positive territory. Both annotators are
    # evaluated separately; never choose whichever agrees with the model.
    pred=[s for s in predictions if .25<s['start']<duration-.25 and
          any(k['start']-.5<=s['start']<k['end'] for k in known)]
    return {str(t):boundary_score(ref,pred,t,complete=True) for t in (.5,3.)}


def consensus_references(annotations,tolerance=.25):
    """Agreement gives bounded reference intervals, not exact invented times."""
    if len(annotations)!=2:raise ValueError('Exactly two independent annotations required')
    def eligible(ref):
        return [s for s in ref['segments'] if .25<s['start']<ref['duration']-.25
                and not set(s['labels'])&{'unknown','silence'}]
    a,b=map(eligible,annotations);pairs=match([s['start'] for s in a],[s['start'] for s in b],tolerance)
    anchors=[];used_a=set();used_b=set()
    for i,j in pairs:
        shared=set(a[i]['labels'])&set(b[j]['labels'])
        if not shared:continue
        anchors.append(dict(earliest=min(a[i]['start'],b[j]['start']),latest=max(a[i]['start'],b[j]['start']),
                            labels=sorted(shared),annotators=2))
        used_a.add(i);used_b.add(j)
    return dict(toleranceSeconds=tolerance,complete=False,beatReference=False,anchors=anchors,
                unresolved=[dict(annotator=k,**s) for k,rows,used in ((1,a,used_a),(2,b,used_b))
                            for i,s in enumerate(rows) if i not in used])


def local_projects(library,output):
    records=[]
    for path in sorted(Path(library).glob('*.bandstudio/project.json')):
        p=json.loads(path.read_text());root=path.parent
        events=[json.loads(f.read_text()) for f in (root/'Learning/events').glob('*.json')]
        refs=references(p,events)
        source=next((t for t in p['tracks'] if t['role']=='source'),None)
        if not source:continue
        audio=(root/source['file']).resolve()
        if not audio.is_relative_to(root.resolve()):raise ValueError('Audio outside project')
        row=dict(id=p['id'],name=p['name'],project=str(path),projectSHA256=sha(path),
                 audio=str(audio),audioSHA256=sha(audio),offset=source['offset'],duration=source['duration'],
                 usage='personal_acceptance_only',references=refs,beatReference=None,
                 completeStructureReference=False)
        results=[]
        for f in (root/'Analyses').glob('*/result.json'):
            try:r=json.loads(f.read_text())
            except (ValueError,OSError):continue
            if 'sections' in r and r.get('engine')=='SongFormer':results.append((f.stat().st_mtime,f,r))
        if results and refs:
            _,f,r=max(results,key=lambda x:x[0])
            # Historical results have no guaranteed audio fingerprint. Report
            # these comparisons as diagnostics, never as a held-out gain.
            pred=[{**s,'start':s['start']+source['offset']} for s in r['sections']]
            ref=[dict(start=x['marker']['start'],labels=[label(x['marker']['name'])])
                 for x in refs if x['kind']=='section' and x['marker']['start']>.25 and label(x['marker']['name'])!='silence']
            pred=[s for s in pred if s['start']>.25 and label(s['name'])!='silence']
            row['historicalStructureDiagnostic']=dict(predictionFile=str(f),predictionSHA256=sha(f),
                audioIdentityVerified=False,metrics={str(t):boundary_score(ref,pred,t,row['completeStructureReference']) for t in (.5,3.)})
        records.append(row)
    result=dict(schema=1,scope='Full local songs; only explicit reviewed marker positions are references.',
                tracks=records,summary=dict(songs=len(records),songsWithReviewedMarkers=sum(bool(r['references']) for r in records),
                reviewedMarkers=sum(len(r['references']) for r in records),
                verifiedBeatReferences=0,independentTestSongs=0,
                capturedCorrectionPairs=sum(x['original'] is not None for r in records for x in r['references'])))
    write(output,result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(local_projects(args.library,args.output)['summary'],ensure_ascii=False))
