#!/usr/bin/env python3
"""Install/update the native app using staged files and a preserved previous version."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'desktop-build/standalone'
VERSION='0.2.0'


def copy(source,target):
    subprocess.run(['cp','-cR',str(source),str(target)],check=True)


def install(update=False):
    home=Path.home();applications=home/'Applications';support=home/'Library/Application Support/BandStudio';library=home/'Music/BandStudio'
    app=applications/'BandStudio.app';source=BUILD/'BandStudio.app'
    if app.exists() and not update:raise SystemExit('BandStudio est déjà installé. Utilise --update pour conserver une sauvegarde et mettre à jour.')
    subprocess.run(['codesign','--verify','--deep','--strict',str(source)],check=True)
    if not (BUILD/'Engine/.studio-owned').is_file():raise SystemExit('Le moteur indépendant doit être préparé avant l’installation.')
    ident=uuid.uuid4().hex[:10]
    engine=support/('Engine-'+VERSION+'-'+ident)
    engine_stage=support/('.Engine-install-'+ident);stage=applications/('.BandStudio-install-'+ident+'.app')
    for folder in (applications,support,library):folder.mkdir(parents=True,exist_ok=True)
    copy(BUILD/'Engine',engine_stage)
    for name in ('.venv','.venv-demucs','.venv-structure','.venv-import','.venv-words','.venv-chords','.venv-drums'):
        version='3.11' if name=='.venv-structure' else '3.12';base=engine/('python'+version.replace('.',''))
        (engine_stage/name/'pyvenv.cfg').write_text(f'home = {base}/bin\ninclude-system-site-packages = false\nversion = {version}\n')
    os.rename(engine_stage,engine)
    copy(source,stage)
    (stage/'Contents/Resources/studio.json').write_text(json.dumps({'runtime':str(engine),'library':str(library)}))
    subprocess.run(['codesign','--force','--sign','-',str(stage)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(stage)],check=True)
    backup=None
    if app.exists():
        previous=support/'PreviousVersions';previous.mkdir(exist_ok=True)
        backup=previous/('BandStudio-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.app')
        os.rename(app,backup)
    try:os.rename(stage,app)
    except BaseException:
        if backup and not app.exists():os.rename(backup,app)
        raise
    # Never replace a user's project while updating the program.
    if not update:
        for project in (BUILD/'Projects').glob('*.bandstudio'):
            dest=library/project.name
            if not dest.exists():copy(project,dest)
    record=dict(app=str(app),engine=str(engine),library=str(library),version=VERSION,previousApp=str(backup) if backup else None)
    temp=support/'installation.json.tmp';temp.write_text(json.dumps(record,indent=2));os.replace(temp,support/'installation.json')
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--update',action='store_true');a=p.parse_args();install(a.update)
