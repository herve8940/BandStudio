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

Windows : correction des formes d’onde des morceaux longs (débordement d’entiers après 68 secondes). Les anciens affichages sont recalculés à l’ouverture sans modifier l’audio. La fenêtre démarre maximisée et le transport reste accessible sur les petits écrans.

Mes morceaux : liste avec pochettes intégrées aux fichiers ou miniatures des liens importés, choix manuel d’une image et suppression réversible dans la corbeille BandStudio.

Tout préparer : enchaînement des analyses installées puis des guides, depuis Séparer & analyser ou Pistes & structure. Les pistes déjà séparées et les repères protégés sont conservés. Une interruption conserve les étapes terminées. La validation finale reste à faire après écoute.

REAPER : le décompte avant la musique est rétabli pour laisser aux musiciens le temps de se préparer. Les pistes, le tempo, les régions et les repères sont décalés ensemble. Le nombre de mesures et l’inclusion du décompte dans les exports restent réglables dans Click & cues. Refais l’export REAPER pour retrouver ce départ préparé.

Annonces Windows : voix locales OneCore en français et anglais, normalisation du niveau et cache distinct par langue. Si une langue manque, l’application indique comment l’ajouter dans Réglages → Voix Windows. Aucun texte n’est envoyé à un service vocal en ligne.

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
