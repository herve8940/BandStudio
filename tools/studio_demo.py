"""Copy an existing audio/stems folder into a native project. Never writes to its source."""
import argparse
import json
from pathlib import Path
import shutil
import uuid
import re
import shlex
import numpy as np
import soundfile as sf


def peaks(path):
    info=sf.info(path)
    result=np.zeros(720,dtype=np.float32)
    position=0
    for block in sf.blocks(path,blocksize=32768,dtype='float32',always_2d=True):
        indices=np.minimum(719,(np.arange(len(block))+position)*720//info.frames)
        np.maximum.at(result,indices,np.abs(block).max(axis=1))
        position+=len(block)
    return info.duration,result.tolist()


def create(source,output,publication=None):
    if output.exists():raise SystemExit('Le projet de destination existe déjà.')
    audio=output/'Audio';audio.mkdir(parents=True)
    original=next(source.glob('*.ogg'))
    target=audio/'original.wav'
    x,sr=sf.read(original,dtype='float32',always_2d=True)
    sf.write(target,x,sr,subtype='FLOAT')
    tracks=[]
    files=[('source','Original',target)]
    names={'drums':'Batterie','bass':'Basse','vocals':'Chant','guitar':'Guitare','piano':'Piano','other':'Autres instruments'}
    for role,name in names.items():
        matches=list(source.glob(f'*-stems/htdemucs_6s/*-{role}.wav'))
        if matches:
            dest=audio/(role+'.wav');shutil.copy2(matches[0],dest);files.append((role,name,dest))
    for role,name,path in files:
        duration,wave=peaks(path)
        tracks.append(dict(id=str(uuid.uuid4()),name=name,file='Audio/'+path.name,role=role,duration=duration,
                           offset=0,gain=.8,pan=0,muted=False,solo=False,peaks=wave))
    project=dict(version=1,id=str(uuid.uuid4()),name=source.name,tracks=tracks,sections=[],cues=[],bpm=0,beats=[],
                 notes='Projet de découverte : copie indépendante de tes fichiers audio. Les pistes proviennent de ta séparation existante.')
    if publication:
        song=json.loads(publication.read_text())
        if Path(song.get('project','')).parent.resolve()!=source.resolve():raise SystemExit('La publication appartient à un autre morceau.')
        duration=max(t['duration'] for t in tracks)
        # Use the saved exact region positions, including hand edits, and remove
        # the source item's project offset. Published bar indices may be stale.
        rpp=Path(song['project']).read_text(errors='replace')
        offsets=[]
        for block in re.split(r'\n  <TRACK ',rpp)[1:]:
            if re.search(r'FILE .*-(vocals|drums|bass|guitar|piano|other)\.wav',block):
                pos=re.search(r'\n\s+POSITION ([\d.]+)',block)
                offs=re.search(r'\n\s+SOFFS ([\d.]+)',block)
                if pos:offsets.append(float(pos[1])-(float(offs[1]) if offs else 0))
        if not offsets or max(offsets)-min(offsets)>.0001:
            raise SystemExit('Les pistes ne partagent pas une origine audio unique.')
        shift=offsets[0];starts={}
        for line in rpp.splitlines():
            if not line.startswith('  MARKER '):continue
            cols=shlex.split(line)
            if len(cols)<5 or cols[4]!='1':continue
            ident,pos,name=cols[1],float(cols[2])-shift,cols[3]
            if name:starts[ident]=(max(0,pos),name)
            elif ident in starts:
                start,name=starts.pop(ident);end=min(duration,pos)
                if end>start:
                    project['sections'].append(dict(id=str(uuid.uuid4()),name=name,start=start,end=end,locked=True,origin='manual'))
        project['sections'].sort(key=lambda s:s['start'])
        project['bpm']=song['bpm']
    (output/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2))
    print(output)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--publication',type=Path)
    a=p.parse_args();create(a.source,a.output,a.publication)
