#!/usr/bin/env python3
"""Build a relocatable Windows development archive from an explicit source allowlist."""
import argparse
import hashlib
import json
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.1.0'


def download(url,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BandStudio-development-build'}),timeout=120) as response,target.open('wb') as f:shutil.copyfileobj(response,f)


def extract(zip_path,target):
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            path=(target/item.filename).resolve()
            if not path.is_relative_to(target.resolve()):raise ValueError('Archive path escapes destination')
        archive.extractall(target)


def source_files():
    files=[ROOT/'LICENSE',ROOT/'THIRD_PARTY_NOTICES.md']
    for name in ['services.py','listening.py','diagnostics.py','updater.py','preparation.py','platform_tools.py','worker.py','advanced.py','phone.py','creative.py']:files.append(ROOT/'desktop/studio'/name)
    files += [ROOT/'desktop/studio/assets/BandStudio.ico']
    files+=list((ROOT/'desktop/studio/windows').glob('*.py'))+list((ROOT/'desktop/studio/windows').glob('*.js'))+list((ROOT/'desktop/studio/windows').glob('*.ps1'))
    files+=[p for p in (ROOT/'desktop/studio/web').iterdir() if p.suffix in ('.html','.js','.css','.svg','.ico')]
    for name in ['reacue_structure.py','reacue_metal.py','reacue_performance.py','reacue_transcribe.py','reacue_words.py','reacue_chords.py','reacue_drums.py','reacue_stems.py','reacue_gpu.py']:files.append(ROOT/name)
    for component in ['stems','structure','words','chords','drums']:
        files.extend([ROOT/'install'/('install_'+component+'_windows.ps1'),ROOT/('requirements-'+component+'.txt')])
    files.append(ROOT/'requirements-whisper.txt')
    files.extend([ROOT/'tools/setup_studio_models.py',ROOT/'tools/setup_studio_rhythm.py',ROOT/'tools/setup_studio_creative.py'])
    return files


def build(output):
    if os.name!='nt':raise SystemExit('Run this builder on Windows x64 (GitHub Actions).')
    output=Path(output).resolve();stage=output/'stage';package=stage/'BandStudio-DEV';engine=package/'engine';engine.mkdir(parents=True,exist_ok=False)
    for source in source_files():
        if source.is_relative_to(ROOT/'desktop/studio'):relative=source.relative_to(ROOT/'desktop/studio')
        else:relative=source.relative_to(ROOT)
        dest=engine/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if source.suffix=='.ps1' and source.parent.name=='install':
            # Keep original executable/module filenames, while naming this product in console messages.
            text=source.read_text(encoding='utf-8-sig').replace('ReaCue','BandStudio')
            dest.write_bytes(b'\xef\xbb\xbf'+text.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
        else:shutil.copy2(source,dest)
    (engine/'build.json').write_text(json.dumps({'version':VERSION,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'runtime':1}))
    shutil.copy2(ROOT/'desktop/studio/windows/LIRE-MOI.txt',package/'LIRE-MOI.txt')
    shutil.copy2(ROOT/'desktop/studio/windows/THIRD_PARTY.txt',package/'WINDOWS_THIRD_PARTY.txt')
    shutil.copy2(ROOT/'LICENSE',package/'LICENSE');shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',package/'THIRD_PARTY_NOTICES.md')
    html=engine/'web/index.html';text=html.read_text(encoding='utf-8');text=text.replace("script-src 'self'","script-src 'self' 'unsafe-eval'");text=text.replace('<script src="diagnostics.js" defer>', '<script src="adapter.js" defer></script><script src="diagnostics.js" defer>');html.write_text(text,encoding='utf-8');shutil.copy2(ROOT/'desktop/studio/windows/adapter.js',engine/'web/adapter.js')
    uv=shutil.which('uv');assert uv,'uv must be installed on the build runner'
    managed=output/'python-build';env=os.environ.copy();env['UV_PYTHON_INSTALL_DIR']=str(managed)
    subprocess.run([uv,'python','install','3.12'],check=True,env=env)
    bases=list(managed.glob('cpython-3.12.*-windows-x86_64-*'));assert len(bases)==1,bases
    shutil.copytree(bases[0],engine/'python');python=engine/'python/python.exe';assert python.is_file()
    subprocess.run([uv,'pip','install','--python',str(python),'--system','--break-system-packages','-r',str(ROOT/'desktop/studio/windows/requirements.txt')],check=True)
    (engine/'tools').mkdir(exist_ok=True);shutil.copy2(uv,engine/'tools/uv.exe')
    download('https://raw.githubusercontent.com/astral-sh/uv/'+importlib.metadata.version('uv')+'/LICENSE-MIT',engine/'tools/uv-LICENSE-MIT')
    cache=output/'downloads';cache.mkdir(exist_ok=True)
    ffmpeg_url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';archive=cache/'ffmpeg.zip';download(ffmpeg_url,archive);checksum=cache/'ffmpeg.sha256';download(ffmpeg_url+'.sha256',checksum)
    expected=checksum.read_text().split()[0];assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
    unpack=cache/'ffmpeg';extract(archive,unpack);tools=engine/'import-tools';tools.mkdir()
    for name in ['ffmpeg.exe','ffprobe.exe']:shutil.copy2(next(unpack.rglob(name)),tools/name)
    ffroot=next(unpack.iterdir())
    for name in ['LICENSE','README.txt']:
        if (ffroot/name).is_file():shutil.copy2(ffroot/name,tools/('ffmpeg-'+name))
    deno_url='https://github.com/denoland/deno/releases/download/v2.9.8/deno-x86_64-pc-windows-msvc.zip';deno=cache/'deno.zip';download(deno_url,deno)
    assert hashlib.sha256(deno.read_bytes()).hexdigest()=='cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf'
    extract(deno,tools)
    download('https://raw.githubusercontent.com/denoland/deno/v2.9.8/LICENSE.md',tools/'deno-LICENSE.md')
    dependency_list=subprocess.check_output([str(python),'-c',"import importlib.metadata,json; print(json.dumps(sorted([(d.metadata['Name'],d.version) for d in importlib.metadata.distributions()])))"],text=True)
    (package/'BUNDLED_PACKAGES.json').write_text(dependency_list,encoding='utf-8')
    demo=package/'examples/Decouverte.bandstudio'
    subprocess.run([str(python),str(engine/'windows/demo.py'),str(demo)],check=True,env={**os.environ,'PYTHONPATH':str(engine),'PYTHONUTF8':'1'})
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/reference:System.Windows.Forms.dll','/win32icon:'+str(ROOT/'desktop/studio/assets/BandStudio.ico'),'/out:'+str(package/'BandStudio.exe'),str(ROOT/'desktop/studio/windows/Bootstrap.cs')],check=True)
    (package/'Demarrer-avec-console.cmd').write_bytes(b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nset PYTHONUTF8=1\r\n"%~dp0engine\\python\\python.exe" "%~dp0engine\\windows\\launcher.py"\r\nif errorlevel 1 pause\r\n')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();runtime=subprocess.check_output([str(python),'--version'],text=True).strip()
    manifest=dict(product='BandStudio',version=VERSION,commit=commit,platform='Windows 11 x64',python=runtime,models_bundled=False,ffmpeg_url=ffmpeg_url,ffmpeg_sha256=expected,deno_url=deno_url,deno_sha256=hashlib.sha256(deno.read_bytes()).hexdigest())
    (package/'BUILD_INFO.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    archive=output/('BandStudio-'+VERSION+'-Windows-x64.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(package.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):z.write(path,path.relative_to(stage))
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(archive)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist/bandstudio');args=parser.parse_args();build(args.output)
