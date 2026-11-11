#!/usr/bin/env python3
"""Build the native preview using an existing ReaCue installation's environments.

The source is copied into the app. Only venvs/model resources are symlinked; the
installed source, REAPER configuration and existing scripts are never replaced.
"""
import argparse
import json
import plistlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(runtime, output, update=False):
    runtime, output = Path(runtime).expanduser().resolve(), Path(output).expanduser().resolve()
    if not (runtime / '.venv/bin/python').is_file():
        raise SystemExit('Installation ReaCue avec .venv/bin/python requise.')
    if output.exists():
        info_path=output/'Contents/Info.plist'
        if not update or not info_path.is_file() or plistlib.loads(info_path.read_bytes()).get('CFBundleIdentifier')!='fr.reacue.desktop.preview':
            raise SystemExit(f'La destination existe déjà : {output}. Utilise --update pour cette preview uniquement.')
        old_engine=output/'Contents/Resources/engine'
        if old_engine.exists():shutil.rmtree(old_engine)
    contents = output / 'Contents'
    mac = contents / 'MacOS'; mac.mkdir(parents=True,exist_ok=True)
    resources = contents / 'Resources'; resources.mkdir(exist_ok=True)
    # External venv links cannot be sealed inside a valid macOS app signature.
    # Keep the reusable runtime beside the signed native launcher instead.
    companion=output.with_suffix('.runtime')
    engine=companion/'engine'
    if companion.exists():
        owner=companion/'.reacue-desktop-owner'
        if not update or not owner.is_file() or owner.read_text()!=str(output):
            raise SystemExit(f'Dossier compagnon déjà présent : {companion}')
        if engine.exists():shutil.rmtree(engine)
    engine.mkdir(parents=True)
    (companion/'.reacue-desktop-owner').write_text(str(output))
    (resources/'desktop.json').write_text(json.dumps({'engine':companion.name+'/engine'}))
    for folder in ('reacue_mcp', 'reaper', 'install', 'docs'):
        shutil.copytree(ROOT / folder, engine / folder, ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
    for file in ROOT.iterdir():
        if file.is_file() and (file.suffix in ('.py','.txt','.command','.bat') or file.name in ('LICENSE','README.md','LISEZMOI.md','THIRD_PARTY_NOTICES.md')):
            shutil.copy2(file,engine/file.name)
    for path in runtime.iterdir():
        if path.is_dir() and (path.name.startswith('.venv') or path.name in ('structure','words','chords','drums','models','stems','import-tools')):
            (engine/path.name).symlink_to(path,target_is_directory=True)
    (engine/'.desktop-runtime').write_text(str(runtime)+'\n')
    info = dict(CFBundleName='ReaCue Desktop Test',CFBundleDisplayName='ReaCue Desktop Test',
                CFBundleIdentifier='fr.reacue.desktop.preview',CFBundleExecutable='ReaCueDesktop',
                CFBundlePackageType='APPL',CFBundleShortVersionString='2.0.0',CFBundleVersion='1',
                NSHighResolutionCapable=True,LSMinimumSystemVersion='12.0',
                NSAppTransportSecurity={'NSAllowsLocalNetworking':True},
                NSHumanReadableCopyright='ReaCue · version de test locale')
    with (contents/'Info.plist').open('wb') as f:plistlib.dump(info,f)
    # Keep the module cache inside the build workspace (works in a sandbox too).
    cache=output.parent/'swift-module-cache';cache.mkdir(exist_ok=True)
    subprocess.run(['xcrun','swiftc','-O','-module-cache-path',str(cache),
                    str(ROOT/'desktop/mac/ReaCueDesktop.swift'),'-o',str(mac/'ReaCueDesktop'),
                    '-framework','AppKit','-framework','WebKit'],check=True)
    subprocess.run(['codesign','--force','--sign','-',str(output)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(output)],check=True)
    print(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'desktop-build/ReaCue Desktop Test.app')
    parser.add_argument('--update',action='store_true')
    args=parser.parse_args();build(args.runtime,args.output,args.update)
