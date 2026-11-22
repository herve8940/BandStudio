"""Local artwork and reversible library removal. Never deletes project contents."""
import base64
import json
from pathlib import Path
import subprocess
import uuid
from platform_tools import executable, creation_flags


def member(library, path):
    library=Path(library).resolve();path=Path(path)
    if path.is_symlink() or path.resolve().parent!=library or path.suffix!='.bandstudio' or not (path/'project.json').is_file():
        raise ValueError('Morceau hors de la bibliothèque.')
    return path.resolve()


def cover(path):
    path=Path(path)/'Artwork.jpg'
    if path.is_file() and not path.is_symlink() and path.stat().st_size<=512_000:
        return 'data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')
    return ''


def entry(path):
    path=Path(path)
    from artwork import info
    p=json.loads((path/'project.json').read_text(encoding='utf-8'))
    return dict(path=str(path),name=p.get('name') or path.stem,artwork=cover(path),**info(path,p.get('name') or path.stem))


def entries(library):
    result=[]
    for path in sorted(Path(library).glob('*.bandstudio')):
        try:
            member(library,path)
            result.append(entry(path.resolve()))
        except (OSError,ValueError):continue
    return result


def extract(source, project, engine):
    """Read embedded artwork (or a chosen image); missing artwork is normal."""
    project=Path(project);project.mkdir(parents=True,exist_ok=True)
    target=project/('artwork-'+uuid.uuid4().hex+'.jpg')
    try:
        result=subprocess.run([str(executable(engine,'ffmpeg')),'-nostdin','-hide_banner','-loglevel','error','-y',
            '-protocol_whitelist','file,pipe,crypto,data','-i',str(source),'-map','0:v:0','-frames:v','1',
            '-vf','scale=512:512:force_original_aspect_ratio=decrease','-q:v','3',str(target)],
            capture_output=True,timeout=30,creationflags=creation_flags())
        if result.returncode or not target.is_file() or target.stat().st_size>512_000:return False
        target.replace(project/'Artwork.jpg');return True
    except (OSError,subprocess.TimeoutExpired):return False
    finally:target.unlink(missing_ok=True)


def trashed(library):
    root=Path(library).resolve()/'.Trash'
    if root.is_symlink():raise ValueError('Corbeille invalide.')
    return sorted((p for p in root.glob('*/*.bandstudio') if not p.is_symlink() and not p.parent.is_symlink()
                   and (p/'project.json').is_file()),key=lambda p:p.parent.stat().st_mtime_ns,reverse=True)


def remove(library,path):
    path=member(library,path);trashed(library) # Reject a redirected trash directory.
    folder=Path(library)/'.Trash'/uuid.uuid4().hex;folder.mkdir(parents=True)
    try:path.rename(folder/path.name)
    except Exception:folder.rmdir();raise
    return str(folder/path.name)


def rename(library,path,name):
    """Change the display name; stable paths preserve media and setlists."""
    path=member(library,path)
    if not isinstance(name,str):raise ValueError('Donne un nom au morceau.')
    name=name.strip()
    if not name or len(name)>200 or any(ord(c)<32 for c in name):
        raise ValueError('Le nom doit contenir entre 1 et 200 caractères, sur une seule ligne.')
    target=path/'project.json'
    if target.is_symlink():raise ValueError('Fichier de morceau invalide.')
    project=json.loads(target.read_text(encoding='utf-8'))
    approval=project.get('preparation') or {}
    if approval.get('validatedAt'):
        from preparation import fingerprint
        snapshot={**project,'_root':str(path)}
        try:
            # A label change keeps a valid musical approval. Never revalidate
            # stale settings, edits or missing/modified media while renaming.
            if approval.get('fingerprint')==fingerprint(snapshot):
                snapshot['name']=name
                project['preparation']={**approval,'fingerprint':fingerprint(snapshot)}
        except (OSError,ValueError,KeyError):pass
    project['name']=name
    from services import atomic
    atomic(target,project)
    return name


def restore(library):
    items=trashed(library)
    if not items:raise ValueError('La corbeille BandStudio est vide.')
    source=items[0];target=Path(library)/source.name
    if target.exists():target=target.with_name(target.stem+' restauré '+uuid.uuid4().hex[:6]+'.bandstudio')
    source.rename(target);source.parent.rmdir();return str(target)


if __name__=='__main__':
    import sys
    action,library=sys.argv[1:3]
    if action=='extract':value=extract(sys.argv[3],library,sys.argv[4])
    elif action=='seed':
        from artwork import seed
        seed(library,sys.argv[3],sys.argv[4],json.loads(sys.argv[5]));value=True
    elif action=='remove':value=remove(library,sys.argv[3])
    elif action=='rename':value=rename(library,sys.argv[3],sys.argv[4])
    elif action=='restore':value=restore(library)
    else:raise ValueError('Action inconnue.')
    print(json.dumps(value,ensure_ascii=True))
