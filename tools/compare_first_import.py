"""Offline first-import replay against a frozen engine and frozen public pages.

The manifest points to private prepared snapshots: raw model proposals, no
manual annotations, no accepted preparation, no song-memory library. Run the
same command once per engine revision. Corpus files are not redistributed.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import time


def run(engine,manifest,output):
    sys.path.insert(0,str(engine.resolve()))
    import chord_sources as chords
    import structure_review as review
    import structure_sources
    results=[];output.mkdir(parents=True,exist_ok=True)
    for case in json.loads(manifest.read_text()):
        p=json.loads(Path(case['snapshot']).read_text());p['_root']=str(Path(case['snapshot']).parent.resolve())
        p['_library']=str(Path(p['_root']).parent.resolve())
        assert not p.get('preparation') and not p.get('chords')
        assert not any(review.protected(s) for s in p['sections'])
        reference=copy.deepcopy(case['chart']);page=Path(case['page']).read_text()
        provider=next(v for v in chords.PROVIDERS if v['id']=='cifraclub')
        title,artist=chords.identity(p)
        chords.fetch=lambda url:(page,url)
        _,status,source=chords._read_chart(provider,title,artist,reference['sources'][0]['url'])
        assert status=='found'
        reference['sources'][0]=source;reference['catalogVersion']=chords.CATALOG_VERSION
        p['chordReference']=reference
        sources,checks=structure_sources.chart_references(reference)
        timed=case.get('timed')
        if timed:sources.insert(0,{**timed,'format':'timed'})
        frozen=dict(timed=timed,note='' if timed else 'Aucune structure minutée disponible.',chart=reference,sources=sources,checks=checks)
        structure_sources.collect=lambda *args:copy.deepcopy(frozen)
        start=time.monotonic();proposal=review.propose(p);elapsed=time.monotonic()-start
        assert not proposal.get('memory')
        name=Path(case['snapshot']).parent.name
        (output/(name+'.json')).write_text(json.dumps(proposal,ensure_ascii=False,indent=2))
        uncertain=[c for c in proposal['chords'] if c.get('confidence',0)<.5]
        covered=sum(c['end']-c['start'] for c in proposal['chords'])
        result=dict(name=p['name'],sections=len(proposal['sections']),chords=len(proposal['chords']),
                    changes=[dict(kind=c['kind'],time=round(c['time'],3),after=c['after']) for c in proposal['changes']],
                    chordCoverageSeconds=round(covered,3),uncertainSeconds=round(sum(c['end']-c['start'] for c in uncertain),3),
                    seconds=round(elapsed,3),memoryUsed=False,manualInputs=0)
        results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    (output/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--engine',type=Path,default=Path(__file__).resolve().parents[1]/'desktop/studio')
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.engine,args.manifest,args.output)
