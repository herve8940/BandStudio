"""Artist-separated rhythm corpus for the rock / hard rock / blues / pop cue audit.

Public annotations and mel inputs: https://zenodo.org/records/13922116
Artist/title index: https://github.com/boblsturm/GTZAN/blob/main/index.txt
No audio, artist, genre, or title is used as a predictor feature.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))
DATA = ROOT / 'tmp/learning-benchmark/data'
OUT = ROOT / 'tmp/cue-learning'
GROUPS = {
    'train': {
        'blues': ('John Lee Hooker', 'Robert Johnson', 'Kelly Joe Phelps', 'Stevie Ray Vaughan'),
        'rock': ('Morphine', 'The Rolling Stones', 'Simple Minds', 'Sting'),
        'hard rock': ('Led Zeppelin', 'Queen', 'Scorpions'),
        'pop': ('Britney Spears', 'Celine Dion', 'Mariah Carey', 'Alanis Morissette', 'Christina Aguilera'),
    },
    'validation': {
        'blues': ('Magic Slim & The Teardrops', 'Clifton Chenier'),
        'rock': ('Ani DiFranco', 'Jethro Tull'),
        'hard rock': ('Def Leppard', 'Deep Purple', 'Ozzy Osbourne'),
        'pop': ("Destiny's Child", 'Janet Jackson'),
    },
    'test': {
        'blues': ('Hot Toddy', 'Albert Collins'),
        'rock': ('Survivor', 'The Stone Roses'),
        'hard rock': ('AC/DC', "Guns N' Roses", 'Bon Jovi'),
        'pop': ('Mandy Moore', 'Madonna', 'Jennifer Lopez'),
    },
}


def prepare():
    prior = set()
    for name in ('run', 'holdout'):
        prior.update(r['id'] for r in json.loads((ROOT/f'tmp/learning-benchmark/{name}/baseline.json').read_text()))
    index = []
    for line in (OUT/'index.txt').read_text().splitlines():
        if ':::' not in line: continue
        name, artist, title = map(str.strip, line.split(':::'))
        genre, number, _ = name.split('.')
        if genre not in ('rock', 'metal', 'blues', 'pop'): continue
        key = f'gtzan_{genre}_{number}'
        path = DATA/f'beat_this_annotations-1.0/gtzan/annotations/beats/{key}.beats'
        values = np.loadtxt(path, ndmin=2)
        if len(values) < 16 or values.shape[1] != 2 or sum(values[:,1] == 1) < 3: continue
        delta = np.diff(values[:,0]); bars = np.diff(np.flatnonzero(values[:,1] == 1))
        variation = float(np.std(delta)/np.median(delta))
        complexity = variation + .2*float(np.mean(bars != 4))
        index.append(dict(id=key, artist=artist, title=title, originalGenre=genre,
                          intervalCV=variation, complexity=complexity,
                          annotation=str(path.relative_to(DATA))))
    selected = []; songs = set()
    for split, genres in GROUPS.items():
        for genre, artists in genres.items():
            for artist in artists:
                candidates = [r for r in index if r['artist'].casefold() == artist.casefold()
                              and not (split == 'test' and r['id'] in prior)]
                count = 6 if split == 'train' and genre == 'blues' else (5 if split == 'train' else 4)
                kept = 0
                for row in sorted(candidates, key=lambda r:(-r['complexity'], r['id'])):
                    identity = (artist.casefold(), re.sub(r'\s*\(v\d+\)', '', row['title'].casefold()))
                    if identity in songs: continue
                    songs.add(identity)
                    selected.append({**row, 'genre':genre, 'split':split})
                    kept += 1
                    if kept >= count: break
    manifest = dict(schema=1, sources=['https://zenodo.org/records/13922116',
        'https://github.com/boblsturm/GTZAN/blob/main/index.txt'], excerpts=selected,
        selection='Highest annotation timing variability / non-four meters per artist, fixed artist splits; same artist-title deduplicated; all previously evaluated excerpts excluded from test.',
        limitation='30-second excerpts, not full-song section labels. Genres describe the artist pool, with stylistic crossover. Limited artists per genre; no claim of universal accuracy.')
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    for split in GROUPS:
        print(split, {g:sum(r['split']==split and r['genre']==g for r in selected) for g in GROUPS[split]})


def infer(engine):
    import torch
    from beat_this.inference import Spect2Frames
    checkpoint = engine/'rhythm/final0.ckpt'
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
    rows = json.loads((OUT/'manifest.json').read_text())['excerpts']
    specs = np.load(DATA/'gtzan.npz', allow_pickle=False)
    torch.set_num_threads(4)
    predictor = Spect2Frames(checkpoint_path=str(checkpoint), device='cpu')
    evidence = OUT/'evidence'; evidence.mkdir(exist_ok=True)
    seen = {}
    for i, row in enumerate(rows):
        key = row['id']; spect = np.asarray(specs[key+'/track'], dtype=np.float32)
        digest = hashlib.sha256(spect.tobytes()).hexdigest()
        if digest in seen: raise ValueError(f'Exact duplicate: {key}, {seen[digest]}')
        seen[digest] = key
        target = evidence/(key+'.npz')
        cached = next((p for p in [target, *[ROOT/f'tmp/learning-benchmark/{n}/{key}.npz' for n in ('run', 'holdout')]] if p.exists()), None)
        if cached:
            z = np.load(cached, allow_pickle=False)
            assert str(z['inputSHA256']) == digest
            beat, down = z['beat'], z['downbeat']
        else:
            with torch.inference_mode(): beat, down = predictor(torch.from_numpy(spect))
            beat, down = beat.cpu().numpy(), down.cpu().numpy()
        np.savez_compressed(target, beat=beat, downbeat=down, duration=len(spect)/50, inputSHA256=digest)
        print(f'{i+1}/{len(rows)} {key} {row["split"]} {"cache" if cached else "inferred"}', flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--prepare', action='store_true'); p.add_argument('--engine', type=Path)
    a=p.parse_args()
    if a.prepare: prepare()
    if a.engine: infer(a.engine)
