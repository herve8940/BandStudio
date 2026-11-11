#!/usr/bin/env python3
"""Build a native standalone app and its own offline analysis runtime on this Mac."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'desktop-build' / 'standalone'


def clone(source, dest):
    if dest.exists():
        return
    source = Path(source).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-cR', str(source), str(dest)], check=True)


def prepare_runtime(source, engine):
    """APFS copy-on-write snapshots; no runtime symlink to the source installation."""
    engine.mkdir(parents=True, exist_ok=True)
    for name, version in [('.venv', '3.12'), ('.venv-demucs', '3.12'), ('.venv-structure', '3.11'),('.venv-import','3.12'),('.venv-words','3.12'),('.venv-chords','3.12'),('.venv-drums','3.12')]:
        base = (source / name / 'bin/python').resolve().parent.parent
        native = engine / ('python' + version.replace('.', ''))
        clone(base, native)
        target = engine / name
        clone(source / name, target)
        for item in (target / 'bin').iterdir():
            if item.name.startswith('python'):
                item.unlink()
                item.symlink_to('../../' + native.name + '/bin/python' + version)
        (target / 'pyvenv.cfg').write_text(f'home = {native}/bin\ninclude-system-site-packages = false\nversion = {version}\n')
        # Editable source references are irrelevant to these standalone workers.
        for p in (target / 'lib' / ('python' + version) / 'site-packages').glob('*.pth'):
            if str(source) in p.read_text(errors='replace'):
                p.unlink()
    clone(source / 'structure', engine / 'structure')
    for name in ('import-tools','words','chords','drums'):
        clone(source/name,engine/name)
    clone(Path.home() / '.cache/torch', engine / 'torch-cache')
    for name in ['reacue_structure.py', 'reacue_metal.py', 'reacue_performance.py','reacue_transcribe.py','reacue_words.py','reacue_chords.py','reacue_drums.py']:
        shutil.copy2(ROOT / name, engine / name)
    shutil.copy2(ROOT / 'desktop/studio/worker.py', engine / 'worker.py')
    shutil.copy2(ROOT / 'desktop/studio/services.py',engine/'services.py')
    shutil.copy2(ROOT / 'desktop/studio/compute.py',engine/'compute.py')
    shutil.copy2(ROOT / 'desktop/studio/catalog.py',engine/'catalog.py')
    shutil.copy2(ROOT / 'desktop/studio/artwork.py',engine/'artwork.py')
    shutil.copy2(ROOT / 'desktop/studio/preparation.py',engine/'preparation.py')
    shutil.copy2(ROOT / 'desktop/studio/platform_tools.py',engine/'platform_tools.py')
    shutil.copy2(ROOT / 'desktop/studio/advanced.py',engine/'advanced.py')
    shutil.copy2(ROOT / 'desktop/studio/phone.py',engine/'phone.py')
    shutil.copy2(ROOT/'desktop/studio/creative.py',engine/'creative.py')
    # No inherited DAW settings. Worker settings and model cache belong to the app.
    (engine / '.studio-owned').write_text('BandStudio standalone analysis runtime\n')


def build(source, prepare=False):
    BUILD.mkdir(parents=True, exist_ok=True)
    engine=BUILD / 'Engine'
    if prepare:
        prepare_runtime(source, engine)
    if engine.exists():
        (engine/'BandStudio_Remote.lua').unlink(missing_ok=True)
        for name in ('worker.py','services.py','listening.py','diagnostics.py','compute.py','catalog.py','artwork.py','updater.py','preparation.py','platform_tools.py','advanced.py','phone.py','creative.py'):
            shutil.copy2(ROOT/'desktop/studio'/name,engine/name)
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        (engine/'build.json').write_text(json.dumps({'version':'1.1.0','commit':revision,'runtime':1}))
    app=BUILD / 'BandStudio.app'
    contents=app / 'Contents'
    mac=contents / 'MacOS';mac.mkdir(parents=True,exist_ok=True)
    resources=contents / 'Resources';resources.mkdir(exist_ok=True)
    if (resources / 'web').exists():shutil.rmtree(resources / 'web')
    shutil.copytree(ROOT / 'desktop/studio/web', resources / 'web')
    shutil.copy2(ROOT/'desktop/studio/assets/BandStudio.icns',resources/'BandStudio.icns')
    for name in ['README.txt','capabilities.json']:
        shutil.copy2(ROOT/'desktop/studio'/name,resources/name)
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',resources/'THIRD_PARTY_NOTICES.md')
    (resources / 'studio.json').write_text(json.dumps({'runtime':str(engine),'library':str(BUILD / 'Projects')}))
    info=dict(CFBundleName='BandStudio',CFBundleDisplayName='BandStudio',CFBundleIdentifier='fr.bandstudio.mac',
              CFBundleExecutable='BandStudio',CFBundlePackageType='APPL',CFBundleIconFile='BandStudio.icns',CFBundleShortVersionString='1.1.0',
              CFBundleVersion='8',NSHighResolutionCapable=True,LSMinimumSystemVersion='12.0',
              CFBundleDocumentTypes=[dict(CFBundleTypeName='Projet BandStudio',CFBundleTypeExtensions=['bandstudio'],CFBundleTypeRole='Editor',LSTypeIsPackage=True)],
              NSHumanReadableCopyright='BandStudio · atelier de musique autonome')
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    cache=BUILD / 'swift-module-cache';cache.mkdir(exist_ok=True)
    subprocess.run(['xcrun','swiftc','-O','-target',platform.machine()+'-apple-macosx12.0','-module-cache-path',str(cache),
                    *[str(ROOT / 'desktop/studio' / f) for f in ['StudioDiagnostics.swift','StudioUpdates.swift','StudioSettings.swift','StudioCore.swift','StudioApp.swift','StudioWorkflows.swift','StudioAdvanced.swift','StudioPhone.swift','StudioRecording.swift','main.swift']],
                    '-o',str(mac / 'BandStudio'),'-framework','AppKit','-framework','WebKit','-framework','AVFoundation'],check=True)
    subprocess.run(['codesign','--force','--sign','-',str(app)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    print(app)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path.home()/'Documents/ReaCue');p.add_argument('--prepare-runtime',action='store_true')
    a=p.parse_args();build(a.source,a.prepare_runtime)
