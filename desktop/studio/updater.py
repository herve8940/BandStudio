"""Verified main-channel updates, staged while working and applied only after exit.

Only application code changes. Models, Python runtimes, projects and preferences
are excluded from the payload. A failed replacement restores every touched file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

REPO='herve8940/BandStudio'
BASE='https://github.com/'+REPO+'/releases/download/'
FEED=BASE+'bandstudio-main/update.json'
MAX_ARCHIVE=150_000_000

def data_dir():
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/BandStudio/Updates'
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/state'))/'BandStudio/Updates'

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');os.replace(tmp,path)

def read_json(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def enabled():return read_json(data_dir()/'preferences.json',{}).get('automatic',True)

def set_enabled(value):write_json(data_dir()/'preferences.json',{'automatic':bool(value)})

def platform_key():
    return 'windows-x64' if sys.platform=='win32' else 'macos-arm64' if platform.machine()=='arm64' else 'macos-x64'

def download(url,path,limit):
    if not url.startswith(BASE):raise ValueError('Source de mise à jour non autorisée.')
    request=urllib.request.Request(url,headers={'User-Agent':'BandStudio-Updater','Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=20) as response,path.open('wb') as target:
        if not response.geturl().startswith('https://'):raise ValueError('Téléchargement non sécurisé.')
        size=0
        while chunk:=response.read(1024*1024):
            size+=len(chunk)
            if size>limit:raise ValueError('Mise à jour trop volumineuse.')
            target.write(chunk)

def allowed_path(name):
    path=PurePosixPath(name)
    if '\\' in name or ':' in name or path.is_absolute() or any(x in ('..','.') for x in path.parts):return False
    if name.startswith('mac-app/Contents/'):
        return name!='mac-app/Contents/Resources/studio.json' and not name.startswith('mac-app/Contents/Resources/Engine/')
    if not name.startswith('engine/'):return False
    relative=PurePosixPath(*path.parts[1:])
    if relative.name=='build.json':return len(relative.parts)==1
    if len(relative.parts)==1:return relative.suffix=='.py'
    return relative.parts[0] in ('web','windows','install','tools') and relative.suffix in ('.py','.js','.css','.html','.svg','.ps1','.txt','.ico')

def extract(archive,destination):
    import zipfile
    with zipfile.ZipFile(archive) as z:
        seen=set();total=0
        for item in z.infolist():
            if item.is_dir():continue
            mode=item.external_attr>>16
            if not allowed_path(item.filename) or stat.S_ISLNK(mode) or item.filename.casefold() in seen:raise ValueError('Archive de mise à jour invalide.')
            seen.add(item.filename.casefold());total+=item.file_size
            if total>MAX_ARCHIVE*3:raise ValueError('Archive décompressée trop volumineuse.')
            target=destination/item.filename;target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
            target.chmod(0o755 if mode&0o111 else 0o644)
        if not (destination/'engine/build.json').is_file():raise ValueError('Version absente du paquet.')

def check(engine,app=None):
    folder=data_dir();folder.mkdir(parents=True,exist_ok=True)
    # mkdir is an interprocess lock, removed in finally; ignore stale locks after a crash.
    lock=folder/'checking'
    try:lock.mkdir()
    except FileExistsError:
        if time.time()-lock.stat().st_mtime<3600:return {'state':'checking','message':'Vérification en cours…'}
        lock.rmdir();lock.mkdir()
    stage=None
    try:
        current=read_json(engine/'build.json',{})
        with tempfile.TemporaryDirectory(dir=folder) as scratch:
            feed=Path(scratch)/'update.json';download(FEED,feed,100_000);manifest=read_json(feed,{})
            if manifest.get('schema')!=1 or manifest.get('runtime')!=1:raise ValueError('Une nouvelle installation complète est nécessaire.')
            revision=manifest.get('commit','')
            if not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('Révision de mise à jour invalide.')
            if current.get('commit')==revision:return {'state':'current','message':'BandStudio est à jour.'}
            asset=manifest['platforms'][platform_key()]
            if not re.fullmatch('[0-9a-f]{64}',asset['sha256']):raise ValueError('Empreinte invalide.')
            archive=Path(scratch)/'update.zip';download(asset['url'],archive,MAX_ARCHIVE)
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=asset['sha256']:raise ValueError('Empreinte incorrecte : mise à jour refusée.')
            stage=folder/('stage-'+uuid.uuid4().hex);stage.mkdir();extract(archive,stage)
            if read_json(stage/'engine/build.json',{}).get('commit')!=revision:raise ValueError('Révision différente du manifeste.')
            if app and not (stage/'mac-app/Contents/MacOS/BandStudio').is_file():raise ValueError('Application macOS absente.')
            pending={'stage':str(stage),'engine':str(engine.resolve()),'app':str(app.resolve()) if app else None,'commit':revision,'sha256':asset['sha256']}
            # Retain the verified archive and recheck on apply, so no staged executable is trusted blindly.
            shutil.copy2(archive,stage/'verified.zip');write_json(folder/'pending.json',pending)
        return {'state':'ready','message':'Mise à jour téléchargée. Installation à la fermeture de BandStudio.'}
    except Exception:
        if stage:shutil.rmtree(stage,ignore_errors=True)
        raise
    finally:lock.rmdir()

def apply_pending():
    folder=data_dir();pending=read_json(folder/'pending.json')
    if not pending:return False
    stage=Path(pending['stage']).resolve()
    if stage.parent!=folder.resolve() or not stage.name.startswith('stage-'):raise ValueError('Zone de mise à jour invalide.')
    archive=stage/'verified.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=pending['sha256']:raise ValueError('Paquet modifié après téléchargement.')
    verified=stage/'apply';verified.mkdir();extract(archive,verified)
    engine=Path(pending['engine']).resolve();app=Path(pending['app']).resolve() if pending.get('app') else None
    backup=folder/('backup-'+uuid.uuid4().hex);backup.mkdir()
    touched=[]
    try:
        for source in sorted(verified.rglob('*')):
            if not source.is_file():continue
            relative=source.relative_to(verified);base=engine if relative.parts[0]=='engine' else app
            if base is None:raise ValueError('Cible macOS manquante.')
            target=base.joinpath(*relative.parts[1:]);resolved=target.resolve()
            if not resolved.is_relative_to(base):raise ValueError('Lien symbolique hors de l’application.')
            previous=backup/relative
            if target.exists():previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,previous)
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name('.'+target.name+'.bandstudio-update');shutil.copy2(source,temp)
            touched.append((target,previous));os.replace(temp,target)
        if app:
            subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(app)],check=True,capture_output=True)
            subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True,capture_output=True)
        write_json(folder/'last-update.json',{'commit':pending['commit'],'backup':str(backup)})
        (folder/'pending.json').unlink();shutil.rmtree(stage)
        return True
    except BaseException:
        for target,previous in reversed(touched):
            if previous.exists():shutil.copy2(previous,target)
            else:target.unlink(missing_ok=True)
        if app:subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(app)],capture_output=True)
        shutil.rmtree(verified,ignore_errors=True)
        raise

def alive(pid):
    if sys.platform=='win32':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p;kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False
        code=ctypes.c_ulong();kernel.GetExitCodeProcess(handle,ctypes.byref(code));kernel.CloseHandle(handle);return code.value==259
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False

def schedule_apply(engine):
    if not enabled() or not (data_dir()/'pending.json').exists():return
    flags=0x08000000|0x00000008 if sys.platform=='win32' else 0
    subprocess.Popen([sys.executable,str(engine/'updater.py'),'apply','--wait-pid',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,start_new_session=sys.platform!='win32')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','apply','enable','disable','status']);p.add_argument('--engine',type=Path,default=Path(__file__).parent);p.add_argument('--app',type=Path);p.add_argument('--wait-pid',type=int);a=p.parse_args()
    try:
        if a.action in ('enable','disable'):set_enabled(a.action=='enable');result={'automatic':enabled()}
        elif a.action=='status':result={'automatic':enabled()}
        elif a.action=='check':result=check(a.engine,a.app)
        else:
            if a.wait_pid:
                while alive(a.wait_pid):time.sleep(1)
            result={'updated':apply_pending()}
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        try:
            from diagnostics import event
            event('update.error',error=error)
        except Exception:pass
        print(json.dumps({'state':'error','message':'Mise à jour indisponible : '+str(error)[:300]},ensure_ascii=False));sys.exit(1)
