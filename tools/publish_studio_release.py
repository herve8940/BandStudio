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
    notes=dist/'notes.md';notes.write_text(f'''BandStudio · préparation musicale pour tous les musiciens.

Windows : extraire le ZIP complet dans un nouveau dossier puis ouvrir BandStudio.exe. Les installations existantes peuvent recevoir le code à la fermeture via les mises à jour automatiques. Les paquets update macOS sont destinés aux installations existantes.

Correctifs d’analyse : compatibilité NumPy / soxr, sélection CUDA pour Demucs et Beat This, segments courts pour les cartes de 4 Go et reprise CPU en cas de manque de mémoire GPU. Après mise à jour, relancer **Réglages → Analyses locales → Rythme avancé → Installer / vérifier** pour réparer un environnement existant. Les modèles et morceaux sont conservés.

Un second clic sur Play pendant la préparation des guides ne démarre plus un travail concurrent. Les diagnostics précisent le traitement, les versions des bibliothèques, le matériel détecté et le périphérique de calcul utilisé.

Tests Windows : reproduction puis réparation de l’erreur NumPy, imports Beat This, rééchantillonnage soxr, inférence Demucs sur CPU, démarrage avec DLL téléchargées, audio et exports. La sélection CUDA et le repli sont testés par simulation ; aucune mesure sur une GTX 1650 physique n’est revendiquée.

Révision : {sha}
''',encoding='utf-8')
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
    gh('release','edit','bandstudio-main','--notes-file',str(notes))

if __name__=='__main__':main()
