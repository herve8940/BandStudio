"""Fetch exact public SALAMI/Internet Archive recordings, with provenance.

This is a structure-development corpus, not a new blind test or beat-labelled
training set. Archive genres are often absent; unknown genres remain unknown.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

from cue_benchmark import parse_salami,sha,write


def resolve_audio(row,output):
    parts=urllib.parse.urlsplit(row['url']).path.split('/')
    item,name=parts[2],urllib.parse.unquote('/'.join(parts[3:]))
    metadata=output/'metadata'/(row['id']+'.json')
    if not metadata.exists():
        url='https://archive.org/metadata/'+urllib.parse.quote(item,safe='')
        with urllib.request.urlopen(url,timeout=30) as response:raw=json.load(response)
        write(metadata,raw)
    raw=json.loads(metadata.read_text());files={f['name']:f for f in raw.get('files',[])}
    # Archive renamed its VBR derivatives. Match only that exact basename;
    # never substitute another performance or a similarly named song.
    candidates=[name,name.removesuffix('_vbr.mp3')+'.mp3'] if name.endswith('_vbr.mp3') else [name]
    filename=next((n for n in candidates if n in files and files[n].get('format')=='VBR MP3'),None)
    if filename is None:raise ValueError('Exact recording/derivative is no longer listed by Archive')
    return dict(downloadURL='https://archive.org/download/'+urllib.parse.quote(item,safe='')+'/'+urllib.parse.quote(filename,safe='/'),
                archiveMetadataSHA256=sha(metadata),archiveOriginal=files[filename].get('original'),
                archiveSubject=raw.get('metadata',{}).get('subject'),archiveLicense=raw.get('metadata',{}).get('licenseurl'))


def candidates(source):
    rows=list(csv.DictReader((source/'metadata/id_index_internetarchive.csv').open()))
    chosen=[]
    for row in rows:
        ident=row['SONG_ID'];files=sorted((source/'annotations'/ident/'parsed').glob('*_functions.txt'))
        if len(files)<2:continue
        refs=[dict(annotator=f.stem,source=str(f.resolve()),sha256=sha(f),**parse_salami(f)) for f in files]
        if not all(120<=r['duration']<=600 and len(r['segments'])>=5 for r in refs):continue
        url=urllib.parse.urlsplit(row['URL'])
        if url.hostname not in ('archive.org','www.archive.org') or not url.path.startswith('/download/'):continue
        chosen.append(dict(id='salami_'+ident,artist=row['ARTIST'],title=row['TITLE'],
            url=urllib.parse.urlunsplit(('https','archive.org',url.path,'','')),
            referenceDuration=float(row['SONG_DURATION']),references=refs,
            genre=None,genreStatus='not_supplied_by_source',
            usage='development_only_pretraining_overlap_unknown',beatReference=None))
    return sorted(chosen,key=lambda r:hashlib.sha256(r['artist'].casefold().encode()).hexdigest())


def fetch(row,output):
    import soundfile as sf
    path=output/'audio'/(row['id']+'.mp3');partial=path.with_suffix('.partial')
    try:
        provenance=resolve_audio(row,output)
        if not path.exists():
            request=urllib.request.Request(provenance['downloadURL'],headers={'User-Agent':'BandStudio-CueBenchmark/1.0'})
            with urllib.request.urlopen(request,timeout=30) as response,partial.open('wb') as f:
                length=0
                while block:=response.read(2**18):
                    length+=len(block)
                    if length>30*2**20:raise ValueError('Recording exceeds 30 MiB limit')
                    f.write(block)
            partial.replace(path)
        info=sf.info(path)
        if not all(abs(info.duration-r['duration'])<1.5 for r in row['references']):
            raise ValueError(f'Audio/annotation duration mismatch: {info.duration:.3f}')
        return dict(**row,**provenance,audio=str(path.resolve()),audioSHA256=sha(path),duration=info.duration,
                    sampleRate=info.samplerate,channels=info.channels,audioBytes=path.stat().st_size,
                    alignment='Exact recording basename from SALAMI and official Archive derivative; annotation endpoints within 1.5 s; no fitted time shift.')
    except Exception as error:
        partial.unlink(missing_ok=True)
        return dict(id=row['id'],url=row['url'],error=type(error).__name__+': '+str(error))


def run(source,output,limit=120):
    import fcntl
    output.mkdir(parents=True,exist_ok=True);(output/'audio').mkdir(exist_ok=True)
    lock=(output/'fetch.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows=candidates(source);write(output/'candidates.json',dict(source='https://github.com/DDMAL/salami-data-public',
        sourceArchiveSHA256=sha(source.parent/'salami.zip'),candidateCount=len(rows),tracks=rows))
    accepted=[];failed=[];start=time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0,len(rows),4):
            if (output/'STOP').exists():break
            if sum(r['audioBytes'] for r in accepted)>2*1024**3:break
            batch=rows[offset:offset+min(4,limit-len(accepted))]
            for result in pool.map(lambda r:fetch(r,output),batch):
                (failed if 'error' in result else accepted).append(result)
            status=dict(stage='fetching',updated=time.time(),accepted=len(accepted),target=limit,
                        failed=len(failed),elapsedSeconds=round(time.time()-start))
            write(output/'fetch-status.json',status);print(json.dumps(status),flush=True)
            write(output/'manifest.json',dict(schema=1,tracks=accepted,failures=failed,
                scope='Full songs, human structural annotations; no verified beats/cue lead labels. Development only; not held out.',
                genreCoverageVerified=False,pretrainingOverlapExcluded=False))
            if len(accepted)>=limit:break
    status.update(stage='complete' if len(accepted)>=limit else 'incomplete',availableCandidates=len(rows))
    write(output/'fetch-status.json',status);print(json.dumps(status),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--limit',type=int,default=120)
    args=parser.parse_args()
    if not 1<=args.limit<=200:parser.error('limit must be 1..200')
    run(args.source.resolve(),args.output.resolve(),args.limit)
