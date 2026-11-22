#!/usr/bin/env python3
"""Replay automatic annotations in a new library without manual project inputs.

Only audio files and title/artist metadata are copied. Separation is reused,
not evaluated by this check. Each stage runs the real installed worker; no
project annotations, accepted maps or library preferences are imported. Reports
describe operational results and uncertainty, never musical accuracy scores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def clean_copy(source, target):
    from services import atomic
    from windows import project as model
    saved = json.loads((source / 'project.json').read_text())
    project = model.fresh(saved['name'])
    project['settings']['voice'] = 'Thomas' if sys.platform == 'darwin' else 'Système'
    target.mkdir(parents=True, exist_ok=False)
    roles = {'source', 'vocals', 'bass', 'drums', 'guitar', 'piano', 'other',
             'vocal_lead', 'vocal_backing', 'drum_kick', 'drum_snare',
             'drum_toms', 'drum_cymbals'}
    files = []
    for entry in saved['tracks']:
        role = entry['role']
        if role not in roles or any(t['role'] == role for t in project['tracks']):
            continue
        original = model.relative_file(source, entry['file'])
        copied = target / 'Audio' / (role + original.suffix)
        copied.parent.mkdir(exist_ok=True)
        # macOS clones are independent files, not hardlinks into the library.
        if sys.platform != 'darwin' or subprocess.run(
                ['cp', '-c', str(original), str(copied)], capture_output=True).returncode:
            shutil.copy2(original, copied)
        signature = digest(original)
        if digest(copied) != signature:
            raise ValueError('Audio copy differs from the input.')
        project['tracks'].append(model.track(copied, target, role, role))
        files.append(dict(role=role, source=str(original), sha256=signature))
    if not any(t['role'] == 'source' for t in project['tracks']):
        raise ValueError('No source audio.')
    metadata = source / 'Artwork.json'
    if metadata.is_file():
        values = json.loads(metadata.read_text())
        atomic(target / 'Artwork.json', {k: values[k] for k in ('title', 'artist') if k in values})
    atomic(target / 'project.json', project)
    atomic(target / 'baseline.json', project)
    return dict(projectSHA256=digest(source / 'project.json'), audio=files)


def check_export(project, root, folder, engine):
    """Use the normal one-click export, then read what was written to disk."""
    from musical_timing import count_plan, tempo_envelope
    from platform_tools import python_for
    from services import atomic, read_rpp
    folder.mkdir(parents=True,exist_ok=False)
    snapshot=folder/'snapshot.json'
    atomic(snapshot,{**project,'_root':str(root),'_rate':1,'_pitch':0,'_mode':'mix'})
    result=folder/'result.json'
    with (folder/'worker.log').open('w') as log:
        subprocess.run([str(python_for(engine,'.venv')),str(engine/'worker.py'),'reaper',
                        '--preflight','--engine',str(engine),'--project',str(snapshot),'--output',str(result)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
    path=Path(json.loads(result.read_text())['path'])
    tree=read_rpp(path)
    receipt=json.loads((path.parent/'validation.json').read_text())
    assert receipt['approval']['kind']=='technical'
    audio={}
    for track in (node for node in tree['children'] if node['kind']=='TRACK'):
        name=next(row[1] for row in track['lines'] if row[0]=='NAME')
        for item in (child for child in track['children'] if child['kind']=='ITEM'):
            for source in (child for child in item['children'] if child['kind']=='SOURCE'):
                for row in source['lines']:
                    if row[0]!='FILE':continue
                    media=(path.parent/row[1]).resolve()
                    assert media.is_relative_to(path.parent) and media.is_file()
                    audio[name]=media
    original=next(track for track in project['tracks'] if track['role']=='source')
    assert original['name'] in audio
    identical=None
    if Path(original['file']).suffix.lower()=='.wav':
        identical=digest(root/original['file'])==digest(audio[original['name']])
        assert identical
    lead=count_plan(project)['lead'] if project['settings']['exportCount'] else 0.
    expected=tempo_envelope(project,lead)
    envelope=next(n for n in tree['children'] if n['kind']=='TEMPOENVEX')
    points=[r for r in envelope['lines'] if r[0]=='PT']
    assert len(points)==len(expected)
    assert all(abs(float(row[1])-point['time'])<1e-8 and abs(float(row[2])-point['bpm'])<1e-8
               and row[3]=='1' for row,point in zip(points,expected))
    markers=[float(r[2]) for r in tree['lines'] if r[0]=='MARKER' and r[4]=='1']
    bounds=[s[side]+lead for s in project['sections'] for side in ('start','end')]
    assert len(markers)==len(bounds) and all(abs(a-b)<1e-8 for a,b in zip(markers,bounds))
    return dict(path=str(path),audioTracks=len(audio),tempoPoints=len(points),sections=len(bounds)//2,
                prerollSeconds=lead,sourceByteIdentical=identical)


def check(args):
    from batch_project import request, apply
    from musical_timing import BeatClock
    from services import atomic
    from windows import project as model
    # Some third-party model loaders change their process working directory.
    # Every worker snapshot and cache must keep an absolute project root.
    args.library, args.output, args.engine = (p.resolve() for p in (args.library, args.output, args.engine))
    selected = [p for p in sorted(args.library.glob('*.bandstudio'))
                if not args.song or any(name.casefold() in p.name.casefold() for name in args.song)]
    if not selected:
        raise ValueError('No matching projects.')
    # A new output directory is mandatory: previous manual edits cannot leak in.
    args.output.mkdir(parents=True, exist_ok=False)
    library = args.output / 'Projects'
    library.mkdir()
    report = dict(manualInputs=0, separation='reused audio; not evaluated',
                  groundTruth='none; operational checks only', projects=[])
    for index, source in enumerate(selected):
        root = library / source.name
        provenance = clean_copy(source, root)
        if args.reuse_raw_structure:
            provenance['rawStructureCache'] = seed_structure_cache(source, root, args.engine)
        item = dict(id=f'clean-{index}', title=source.stem,
                    options=dict(model='htdemucs', quality='standard', language='auto'))
        case = dict(name=source.stem, stages=[], provenance=provenance)
        report['projects'].append(case)
        atomic(args.output / 'report.json', report)
        for stage in args.stages:
            folder = args.output / 'Jobs' / str(index) / stage
            folder.mkdir(parents=True)
            command = request(item, stage, root, folder, args.engine, library)
            start = time.monotonic()
            print(json.dumps(dict(song=source.stem, stage=stage, status='running')), flush=True)
            with (folder / 'worker.log').open('w') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                        env={**os.environ, 'PYTHONUNBUFFERED': '1'}, timeout=3600)
            step = dict(stage=stage, seconds=round(time.monotonic() - start, 2), exitCode=result.returncode)
            case['stages'].append(step)
            if result.returncode:
                step['errorLog'] = str(folder / 'worker.log')
                atomic(args.output / 'report.json', report)
                print(json.dumps(step), flush=True)
                break
            p = apply(item, stage, root, folder, library)
            model.validate(p, root)
            assert not p.get('gridLocked')
            assert not any(s.get('locked') or s.get('reviewed') or s.get('origin') == 'manual' for s in p['sections'])
            assert not any(row.get('manual') for field in ('lyrics', 'chords') for row in p[field])
            assert not (p.get('structureProposal') or {}).get('memory')
            atomic(args.output / 'report.json', report)
            print(json.dumps(step), flush=True)
        p = model.load(root)
        clock = BeatClock(p)
        case.update(bpm=p['bpm'], firstBeat=p['settings']['firstBeat'],
                    timing=clock.payload(), analysisNote=p['analysisNote'],
                    sectionCount=len(p['sections']), lyricsCount=len(p['lyrics']),
                    chordCount=len(p['chords']), lyricsReference=p.get('lyricsReference'),
                    warnings=(p.get('structureProposal') or {}).get('warnings', []))
        case['originalsUnchanged'] = (digest(source / 'project.json') == provenance['projectSHA256']
            and all(digest(Path(row['source'])) == row['sha256'] for row in provenance['audio']))
        assert case['originalsUnchanged']
        if getattr(args,'export_reaper',False) and all(s['exitCode']==0 for s in case['stages']):
            case['export']=check_export(p,root,args.output/'Jobs'/str(index)/'reaper',args.engine)
        atomic(args.output / 'report.json', report)
        print(json.dumps({k: case[k] for k in ('name', 'bpm', 'firstBeat', 'sectionCount', 'lyricsCount', 'chordCount', 'warnings', 'originalsUnchanged')}, ensure_ascii=False), flush=True)
    return report


def seed_structure_cache(source, target, engine):
    """Only reuse checksum-verified raw segments from the identical model/input.

    Compute the cache key in the model's own environment: package versions are
    part of that key. A miss is a normal full inference, never a stale replay.
    """
    from platform_tools import python_for
    code = '''
from pathlib import Path
import json, os, sys
engine, source, target = map(Path, sys.argv[1:])
sys.path.insert(0, str(engine))
os.environ['REAPER_RESOURCE_PATH'] = str(target/'benchmark-state')
from analysis_cache import AnalysisCache
import reacue_structure
window = reacue_structure.choose_window()
p = json.loads((target/'project.json').read_text())
audio = target/next(t['file'] for t in p['tracks'] if t['role']=='source')
cached = AnalysisCache.create({'_root':str(source)}, 'structure', audio, engine, dict(window=window))
raw = cached.load() if cached else None
if raw is not None:
    assert set(raw)=={'segments'}, 'Only raw model segments are eligible'
    destination = AnalysisCache.create({'_root':str(target)}, 'structure', audio, engine, dict(window=window))
    destination.store(raw)
    assert destination.load()==raw
print(json.dumps(dict(reused=raw is not None, key=cached.key if cached else None, window=window)))
'''
    result = subprocess.run([str(python_for(engine, '.venv-structure')), '-c', code,
                             str(engine), str(source), str(target)],
                            capture_output=True, text=True, check=True, timeout=180)
    return json.loads(result.stdout.strip().splitlines()[-1])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--song', action='append', default=[])
    parser.add_argument('--export-reaper',action='store_true',help='Export each successful clean preparation and verify its media and timeline')
    parser.add_argument('--reuse-raw-structure', action='store_true',
                        help='Reuse only verified raw structure output with an exact input/model/environment cache key')
    parser.add_argument('--stages', nargs='+', default=['smartgrid', 'structure', 'key', 'lyrics', 'prepareReview', 'guides'],
                        choices=['smartgrid', 'structure', 'key', 'lyrics', 'prepareReview', 'guides'])
    report = check(parser.parse_args())
    if any(step['exitCode'] for project in report['projects'] for step in project['stages']):
        raise SystemExit(1)
