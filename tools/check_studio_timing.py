#!/usr/bin/env python3
"""Compare the native clock against Python on real recorded rhythm fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from musical_timing import BeatClock,count_plan
from windows.project import fresh


def fixtures():
    rows=[]
    for saved in json.loads((ROOT/'tests/fixtures/recorded_timing_grids.json').read_text()):
        p=fresh(saved['name']);settings=p['settings'];p.update(saved);p['settings']={**settings,**saved['settings']}
        clock=BeatClock(p);p['timingGrid']=clock.payload();duration=p['sessionDuration']
        times=[-3,0,*clock.beats[::13],duration-.01,duration+2]
        samples=[dict(time=t,coordinate=clock.coordinate(t),period=clock.period_at(t)) for t in times]
        plans=[]
        for pos in (0,duration/3,duration-.1):
            plan=count_plan(p,pos)
            plans.append(dict(position=pos,lead=plan['lead'],target=plan['target'],
                              times=[e['time'] for e in plan['events']],numbers=[e['number'] for e in plan['events']]))
        rows.append(dict(project=p,samples=samples,plans=plans))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('binary',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='bandstudio-timing-') as temp:
        path=Path(temp)/'timing.json';path.write_text(json.dumps(fixtures()))
        subprocess.run([str(args.binary.resolve()),'--timing-test',str(path)],check=True,timeout=60)
