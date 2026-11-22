"""Conservative one-time recovery of the withdrawn whole-bar migration."""
import copy
import json
import math
from pathlib import Path
from musical_timing import grid


def _legacy_sections(project, *, force=False, protected_ids=()):
    """Frozen v1 reproduction, used only to recognize its exact prior output."""
    rows=copy.deepcopy(project.get('sections',[]));changes=[]
    settings=project['settings'];meter=settings['beatsPerBar']
    beats=sorted(set(t for t in project.get('beats',[]) if math.isfinite(t) and t>=0))
    detected=settings['gridMode']!='fixed'
    if detected and len(beats)<2:return rows,changes
    at,_,anchor=grid(project)
    length=max((s['end'] for s in rows),default=0)
    bars=[]
    for n in range(20000):
        t=at(anchor+n*meter)
        if t>length or (detected and t>beats[-1]+1e-7):break
        if t>=0:bars.append(t)
    if not bars:return rows,changes
    paired=meter in (2,4) and settings.get('pulseUnit')!='dottedQuarter'
    protected_ids=set(protected_ids)
    def protected(s):
        return s['id'] in protected_ids or (not force and
            (s.get('locked') or s.get('reviewed') or s.get('origin')=='manual'))
    def nonmusical(s):
        return s.get('announce') is False or s['name'].strip().casefold() in (
            'silence','silence initial','avant départ','levée')
    for previous,current in zip(rows,rows[1:]):
        old=current['start']
        if (protected(previous) or protected(current) or nonmusical(previous) or nonmusical(current)
                or abs(previous['end']-old)>1e-7):continue
        if detected and not beats[0]<=old<=beats[-1]:continue
        near=min(range(len(bars)),key=lambda j:abs(bars[j]-old))
        span=at(anchor+(near+1)*meter)-bars[near]
        candidates=[j for j,t in enumerate(bars) if previous['start']+1e-7<t<current['end']-1e-7
                    and abs(t-old)<=span+1e-7]
        if not candidates:continue
        previous_bar=min(range(len(bars)),key=lambda j:abs(bars[j]-previous['start']))
        even=[j for j in candidates if (j-previous_bar)%2==0]
        chosen=min(even if paired and even else candidates,key=lambda j:(round(abs(bars[j]-old),5),(j-previous_bar)%4!=0,j))
        target=bars[chosen]
        if abs(target-old)<1e-7:continue
        previous['end']=current['start']=target
        changes.append(dict(id=current['id'],before=old,after=target))
    return rows,changes


def _canonical(value):
    if isinstance(value,dict):return {k:_canonical(v) for k,v in value.items() if v is not None}
    if isinstance(value,list):return [_canonical(v) for v in value]
    return value


def _grid_signature(project):
    settings=project.get('settings',{})
    return [project.get('beats'),project.get('bpm'),
            [settings.get(k) for k in ('gridMode','firstBeat','beatsPerBar','manualBPM','pulseUnit')]]


def rollback_section_grid(project,root):
    """Restore only unchanged v1 migrations; preserve all later musician edits."""
    from services import atomic
    if project.get('sectionGridVersion')!=1:return False
    root=Path(root);source=root/'Backups/section-grid-v1/project.json'
    restored=False;original=None
    try:
        original=json.loads(source.read_text(encoding='utf-8'))
        if original.get('id') and original.get('id')==project.get('id') and _grid_signature(original)==_grid_signature(project):
            expected,changes=_legacy_sections(original,force=True)
            moved={c['id'] for c in changes}
            for i,section in enumerate(expected):
                if section['id'] in moved or (i+1<len(expected) and expected[i+1]['id'] in moved):section['reviewed']=False
            restored=bool(changes) and _canonical(expected)==_canonical(project.get('sections'))
    except (OSError,ValueError,TypeError,KeyError,IndexError,AttributeError,ZeroDivisionError,OverflowError):
        # A missing, malformed or foreign backup never authorizes moving music.
        restored=False
    current=root/'project.json';backup=root/'Backups/section-grid-rollback-v2/project.json'
    before=current.read_bytes()
    backup.parent.mkdir(parents=True,exist_ok=True)
    try:
        with backup.open('xb') as f:f.write(before)
    except FileExistsError:pass
    updated=copy.deepcopy(project);updated['sectionGridVersion']=2
    if restored:
        updated['sections']=copy.deepcopy(original['sections']);updated['guideKey']=''
        updated.pop('structureProposal',None)
        if updated.get('preparation'):
            updated['preparation'].pop('fingerprint',None);updated['preparation'].pop('validatedAt',None)
    atomic(current,updated)
    project.clear();project.update(updated)
    return restored


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--rollback',type=Path,required=True)
    root=parser.parse_args().rollback
    rollback_section_grid(json.loads((root/'project.json').read_text(encoding='utf-8')),root)

