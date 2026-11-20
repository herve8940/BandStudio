"""Paired offline comparison on private copies, with frozen Internet references.

Scores distinguish uncertain estimates, exact recall, and synthetic correction
scenarios. They never label a similarity score as musical ground truth.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import types
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import structure_review as current
import structure_sources
import musical_patterns
import song_memory
from services import atomic


def clone_project(source,destination):
    p=json.loads((source/'project.json').read_text());destination.mkdir(parents=True,exist_ok=True)
    paths={t['file'] for t in p['tracks']}|set(p.get('guideFiles',{}).values())|{'Artwork.json'}
    for name in paths:
        a=(source/name).resolve();b=(destination/name).resolve()
        if not a.is_relative_to(source.resolve()) or not b.is_relative_to(destination.resolve()):raise ValueError('Media escapes project')
        if not a.is_file() or b.exists():continue
        b.parent.mkdir(parents=True,exist_ok=True)
        if sys.platform=='darwin':subprocess.run(['cp','-c',str(a),str(b)],check=True)
        else:shutil.copy2(a,b)
    p['_root']=str(destination.resolve());p['_library']=str(destination.parent.resolve());p.pop('structureProposal',None)
    return p


def music(p):
    return dict(sections=[(s['start'],s['end'],s['name']) for s in p.get('sections',[])],
                chords=[(s['start'],s['end'],s['text']) for s in p.get('chords',[])])


def metrics(proposal):
    uncertain=[c for c in proposal['chords'] if not c.get('manual') and c.get('confidence',0)<.5]
    clips=proposal.get('reviewPassages')
    if clips is None:
        clips=[];length=max((s['end'] for s in proposal['sections']),default=0)
        for change in proposal['changes']:
            clip=dict(start=max(0,change['time']-3),end=min(length,change['time']+4))
            if clips and clip['start']<=clips[-1]['end']:clips[-1]['end']=max(clips[-1]['end'],clip['end'])
            else:clips.append(clip)
    covered=sum(max(0,min(c['end'],p['end'])-max(c['start'],p['start'])) for c in uncertain for p in clips)
    return dict(sections=len(proposal['sections']),chords=len(proposal['chords']),changes=len(proposal['changes']),
                uncertainSegments=len(uncertain),uncertainSeconds=round(sum(c['end']-c['start'] for c in uncertain),3),
                repeatedGroups=proposal.get('repeatedGroups',0),transferredPhrases=proposal.get('transferredPhrases',0),
                reviewPassages=len(clips),uncertainSecondsCoveredByListening=round(covered,3),
                reviewSeconds=round(sum(c['end']-c['start'] for c in clips),3))


def run(manifest,references,output,baseline_commit):
    output.mkdir(parents=True,exist_ok=False)
    baseline=types.ModuleType('baseline_structure_review')
    code=subprocess.check_output(['git','show',baseline_commit+':desktop/studio/structure_review.py'],cwd=ROOT,text=True)
    exec(compile(code,'baseline_structure_review.py','exec'),baseline.__dict__)
    results=[]
    for item in json.loads(manifest.read_text()):
        source=Path(item['source']);before=hashlib.sha256((source/'project.json').read_bytes()).hexdigest()
        cached=references/source.name
        original_proposal=json.loads((cached/'proposal.json').read_text())
        chart=original_proposal.get('chordReference');maps=[]
        for file in (cached/'References').glob('structure-*.json'):
            value=json.loads(file.read_text())
            if 'duration' in value:maps.append(value)
        timed=maps[0] if maps else None
        sources,checks=structure_sources.chart_references(chart)
        if timed:sources.insert(0,{**timed,'format':'timed'})
        for file in (cached/'References').glob('structure-hook-*.json'):sources.append(json.loads(file.read_text()))
        frozen=dict(timed=timed,note='' if timed else 'Aucune structure minutée disponible.',chart=chart,
                    sources=sources,checks=original_proposal.get('sourceChecks',checks))
        structure_sources.collect=lambda *args:copy.deepcopy(frozen)
        p=clone_project(source,output/'Projects'/source.name)
        p['chordReference']=copy.deepcopy(chart)
        for mode,engine in [('before',baseline),('after',current)]:
            start=time.monotonic();proposal=engine.propose(copy.deepcopy(p))
            elapsed=time.monotonic()-start
            atomic(Path(p['_root'])/(mode+'.json'),proposal)
            if mode=='before':old=proposal;old_time=elapsed
            else:new=proposal;new_time=elapsed
        assert all(s in new['sections'] for s in p['sections'] if current.protected(s))
        accepted=current.apply_proposal({**p,'structureProposal':new})
        # This simulates the explicit export acceptance; it is not new musical
        # annotation, and no original/user document is changed.
        song_memory.remember(accepted,accepted=True)
        q=clone_project(source,output/'Projects'/('Renamed-'+source.name))
        q.update(id=str(uuid.uuid4()),name='Renamed audio',sections=[],chords=[],beats=[],downbeats=[],gridLocked=False)
        q.pop('preparation',None);q.pop('chordReference',None)
        q['settings'].update(gridMode='detected',manualBPM=120,firstBeat=0)
        q['tracks']=[t for t in q['tracks'] if t['role']=='source']
        start=time.monotonic();recalled=current.memory_proposal(q);recall_time=time.monotonic()-start
        assert recalled is not None
        restored=current.apply_proposal({**q,'structureProposal':recalled})
        exact=music(restored)==music(accepted) and song_memory.grid(restored)==song_memory.grid(accepted)
        assert exact
        atomic(Path(q['_root'])/'project.json',{k:v for k,v in {**q,'structureProposal':recalled}.items() if not k.startswith('_')})
        atomic(Path(p['_root'])/'project.json',{k:v for k,v in {**p,'structureProposal':new}.items() if not k.startswith('_')})
        # Test one withheld label on actual audio. Expected labels here are the
        # existing preparation, not an independent expert transcription.
        pattern=musical_patterns.analyse({**p,'sections':new['sections']})
        scenario=None
        if pattern['groups']:
            group=pattern['groups'][0];donor,target=group[:2]
            test={**p,'sections':copy.deepcopy(new['sections'])}
            expected=test['sections'][target]['name']
            test['sections'][donor].update(reviewed=True)
            test['sections'][target].update(name='Instrumental',origin='analysis',locked=False,reviewed=False)
            tested=musical_patterns.analyse(test)
            scenario=dict(kind='simulated_marker_validation_and_withheld_label',expected=expected,
                          actual=tested['sections'][target]['name'],recovered=tested['sections'][target]['name']==expected,
                          sourcePreserved=tested['sections'][donor]==test['sections'][donor])
        result=dict(name=p['name'],before={**metrics(old),'seconds':round(old_time,3)},after={**metrics(new),'seconds':round(new_time,3)},
                    timingScope='Comparison/recall only; separation, initial analysis, listening and export excluded.',
                    musicalOutputChanged=music(old)!=music(new),exactRecall=dict(seconds=round(recall_time,3),equal=exact,
                    sections=len(restored['sections']),chords=len(restored['chords'])),correctionScenario=scenario,
                    originalUnchanged=before==hashlib.sha256((source/'project.json').read_bytes()).hexdigest(),
                    accuracyReference='No independent chord transcription available; uncertainty is not an error rate.')
        results.append(result);atomic(output/'comparison.json',dict(baseline=baseline_commit,results=results))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',default='ae32164')
    args=parser.parse_args();run(args.manifest,args.references,args.output,args.baseline)
