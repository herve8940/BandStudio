#!/usr/bin/env python3
"""Publish immutable tested binaries first, then atomically replace the main feed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

def gh(*args):return subprocess.check_output(['gh',*args],text=True).strip()

def main():
    repo=os.environ['GH_REPO'];sha=os.environ['SOURCE_SHA'];dist=Path('release-assets')
    if gh('api','repos/'+repo+'/git/ref/heads/main','--jq','.object.sha')!=sha:
        print('main has advanced; publication belongs to the newer build.');return
    tag='bandstudio-'+sha[:12]
    manifests=list(dist.rglob('BandStudio-update-*.json'))
    assert len(manifests)==3,manifests
    platforms={}
    assets=[]
    for path in manifests:
        info=json.loads(path.read_text());asset=path.with_suffix('.zip')
        assert info['commit']==sha and hashlib.sha256(asset.read_bytes()).hexdigest()==info['sha256']
        platforms[info['platform']]={'url':f'https://github.com/{repo}/releases/download/{tag}/{asset.name}','sha256':info['sha256']}
        assets.append(str(asset))
    assets+=list(map(str,dist.rglob('BandStudio-1.1.0-Windows-x64.zip*')))
    notes=dist/'notes.md';notes.write_text('BandStudio · préparation musicale pour tous les musiciens.\n\nWindows : extraire le ZIP complet puis ouvrir BandStudio.exe. macOS : les paquets update sont destinés aux installations existantes.\n\nTests de mixage, exports, interface et installation Windows exécutés avant publication. Les moteurs IA facultatifs et les périphériques audio nécessitent une validation sur le matériel utilisé.\n\nRévision : '+sha+'\n')
    exists=subprocess.run(['gh','release','view',tag],capture_output=True).returncode==0
    if not exists:gh('release','create',tag,*assets,'--target',sha,'--title','BandStudio 1.1 · '+sha[:7],'--notes-file',str(notes),'--latest=true')
    # A retried job may find a release whose first upload was interrupted.
    remote={a['name']:a for a in json.loads(gh('api','repos/'+repo+'/releases/tags/'+tag))['assets']}
    for filename in assets:
        asset=Path(filename)
        if asset.name not in remote:
            gh('release','upload',tag,filename)
        else:
            uploaded=remote[asset.name]
            assert uploaded['size']==asset.stat().st_size,'Existing asset has a different size: '+asset.name
            if uploaded.get('digest'):
                assert uploaded['digest']=='sha256:'+hashlib.sha256(asset.read_bytes()).hexdigest(),'Existing asset differs: '+asset.name
    if gh('api','repos/'+repo+'/git/ref/heads/main','--jq','.object.sha')!=sha:
        print('main advanced during upload; keeping the previous update feed.');return
    feed=dist/'update.json';feed.write_text(json.dumps({'schema':1,'runtime':1,'version':'1.1.0','commit':sha,'platforms':platforms},indent=2))
    if subprocess.run(['gh','release','view','bandstudio-main'],capture_output=True).returncode:
        gh('release','create','bandstudio-main',str(feed),'--target',sha,'--title','BandStudio · mises à jour automatiques de main','--notes-file',str(notes),'--prerelease','--latest=false')
    else:gh('release','upload','bandstudio-main',str(feed),'--clobber')
    windows=list(map(str,dist.rglob('BandStudio-1.1.0-Windows-x64.zip*')))
    gh('release','upload','bandstudio-main',*windows,'--clobber')

if __name__=='__main__':main()
