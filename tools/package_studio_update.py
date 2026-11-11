#!/usr/bin/env python3
"""Publish code-only, architecture-specific updates with a fixed runtime contract."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
from updater import allowed_path

def build(output,platform_name,app=None):
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    output.mkdir(parents=True,exist_ok=True)
    target=output/('BandStudio-update-'+platform_name+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for source in (ROOT/'desktop/studio').rglob('*'):
            if not source.is_file() or source.suffix not in ('.py','.html','.js','.css','.svg','.ps1'):continue
            path='engine/'+source.relative_to(ROOT/'desktop/studio').as_posix()
            if not allowed_path(path):continue
            content=source.read_bytes()
            if platform_name.startswith('windows') and path=='engine/web/index.html':
                content=content.decode().replace("script-src 'self'","script-src 'self' 'unsafe-eval'").replace('<script src="diagnostics.js"','<script src="adapter.js" defer></script><script src="diagnostics.js"').encode()
            archive.writestr(path,content)
        if platform_name.startswith('windows'):archive.write(ROOT/'desktop/studio/windows/adapter.js','engine/web/adapter.js')
        for source in ROOT.glob('reacue_*.py'):archive.write(source,'engine/'+source.name)
        archive.writestr('engine/build.json',json.dumps({'version':'1.1.0','commit':commit,'runtime':1}))
        if app:
            for source in app.rglob('*'):
                if source.is_file():
                    path='mac-app/'+source.relative_to(app).as_posix()
                    if allowed_path(path):archive.write(source,path)
    value={'platform':platform_name,'commit':commit,'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    target.with_suffix('.json').write_text(json.dumps(value,indent=2))
    print(target)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'dist/updates');p.add_argument('--platform',required=True);p.add_argument('--app',type=Path);a=p.parse_args();build(a.output,a.platform,a.app)
