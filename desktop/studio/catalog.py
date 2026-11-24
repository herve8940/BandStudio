"""Local artwork and reversible library removal. Never deletes project contents."""
from ui_language import ui_text
import base64
import json
from pathlib import Path
import subprocess
import uuid
from platform_tools import executable, creation_flags


def member(library, path, include_trashed=False):
    library=Path(library).resolve();path=Path(path)
    if path.is_symlink() or path.resolve().parent!=library or path.suffix!='.bandstudio' or not (path/'project.json').is_file():
        raise ValueError(ui_text('Morceau hors de la bibliothèque.', 'Song outside the library.'))
    if not include_trashed and path.resolve() in pending(library):raise ValueError(ui_text('Morceau dans la corbeille de la bibliothèque.', 'Song in the library trash.'))
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
    result=[];hidden=set(pending(library))
    for path in sorted(Path(library).glob('*.bandstudio')):
        try:
            if path.resolve() in hidden:continue
            member(library,path,include_trashed=True)
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


def trash_records(library):
    """Physical trash plus reversible removals whose directory is still in use.

    A receipt is committed before attempting the move. If Windows refuses it,
    the receipt hides only that project ID, without touching any open media.
    Old trash folders (without receipts) remain restorable.
    """
    library=Path(library).resolve()
    root=library/'.Trash'
    if root.is_symlink():raise ValueError(ui_text('Corbeille invalide.', 'Invalid trash folder.'))
    records=[]
    for folder in root.glob('*'):
        if folder.is_symlink() or not folder.is_dir():continue
        stored=[p for p in folder.glob('*.bandstudio') if not p.is_symlink() and (p/'project.json').is_file()]
        records.extend((folder,p,False) for p in stored)
        if stored:continue
        try:
            receipt=folder/'removal.json'
            if receipt.is_symlink():continue
            item=json.loads(receipt.read_text(encoding='utf-8'));name=item['name']
            if not isinstance(name,str) or '/' in name or '\\' in name or not name.endswith('.bandstudio'):continue
            path=member(library,library/name,include_trashed=True)
            project=json.loads((path/'project.json').read_text(encoding='utf-8'))
            if isinstance(project,dict) and item.get('projectID') and project.get('id')==item['projectID']:records.append((folder,path,True))
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(records,key=lambda r:r[0].stat().st_mtime_ns,reverse=True)


def pending(library):
    return [path for _,path,in_place in trash_records(library) if in_place]


def trashed(library):
    return [path for _,path,_ in trash_records(library)]


def remove(library,path):
    path=member(library,path,include_trashed=True)
    if path in pending(library):return str(path) # Repeated requests are idempotent.
    project=json.loads((path/'project.json').read_text(encoding='utf-8'))
    folder=Path(library).resolve()/'.Trash'/uuid.uuid4().hex;folder.mkdir(parents=True)
    from services import atomic
    try:
        atomic(folder/'removal.json',dict(version=1,name=path.name,projectID=project.get('id')))
        try:path.rename(folder/path.name)
        except PermissionError:
            # REAPER, an antivirus or another reader may retain a Windows handle.
            # No copy/unlink fallback: audio must stay intact and restorable.
            if not project.get('id'):raise ValueError(ui_text('Le projet est verrouillé et son identifiant est manquant. Le morceau est conservé.', 'The project is locked and its ID is missing. The song was kept.'))
            return str(path)
    except Exception:
        (folder/'removal.json').unlink(missing_ok=True)
        (folder/'removal.json.tmp').unlink(missing_ok=True)
        folder.rmdir();raise
    return str(folder/path.name)


def rename(library,path,name):
    """Change the display name; stable paths preserve media and setlists."""
    path=member(library,path)
    if not isinstance(name,str):raise ValueError(ui_text('Donne un nom au morceau.', 'Enter a name for the song.'))
    name=name.strip()
    if not name or len(name)>200 or any(ord(c)<32 for c in name):
        raise ValueError(ui_text('Le nom doit contenir entre 1 et 200 caractères, sur une seule ligne.', 'Use a single-line name between 1 and 200 characters.'))
    target=path/'project.json'
    if target.is_symlink():raise ValueError(ui_text('Fichier de morceau invalide.', 'Invalid song file.'))
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
    items=trash_records(library)
    if not items:raise ValueError(ui_text('La corbeille BandStudio est vide.', 'The BandStudio trash is empty.'))
    folder,source,in_place=items[0]
    if in_place:
        (folder/'removal.json').unlink();folder.rmdir();return str(source)
    target=Path(library)/source.name
    if target.exists():target=target.with_name(target.stem+ui_text(' restauré ', ' restored ')+uuid.uuid4().hex[:6]+'.bandstudio')
    source.rename(target)
    (folder/'removal.json').unlink(missing_ok=True);folder.rmdir();return str(target)


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
    else:raise ValueError(ui_text('Action inconnue.', 'Unknown action.'))
    print(json.dumps(value,ensure_ascii=True))
