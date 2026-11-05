"""Transactional concert management and self-contained copies; never runs audio models."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import signal
import tempfile
import threading
import time
import uuid

from . import concert as C
from .bridge import to_lua
from .i18n import get_lang


def _message(fr, en):
    return fr if get_lang() == "fr" else en


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _absolute(value):
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _resolve(value, base):
    p = Path(value).expanduser()
    if PureWindowsPath(str(value)).is_absolute() and os.name != "nt" and not p.is_absolute():
        raise ValueError(f"Chemin inaccessible sur cette machine / Inaccessible path: {value}")
    return (p if p.is_absolute() else base / p).resolve()


def _name(value):
    name = str(value or "").strip()
    if not name or any(ord(c) < 32 for c in name) or name in (".", ".."):
        raise ValueError("Nom de concert invalide / Invalid concert name")
    return name, C._slug(name)


class _LuaData:
    """Read only the literal grammar emitted by bridge.to_lua, never execute Lua."""
    def __init__(self, text):
        self.text = re.sub(r"^\s*--[^\n]*(?:\n|$)", "", text)
        self.pos = 0

    def ws(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def take(self, token):
        self.ws()
        if not self.text.startswith(token, self.pos):
            raise ValueError("Concert Lua: données littérales attendues / expected literal data")
        self.pos += len(token)

    def value(self):
        self.ws()
        ch = self.text[self.pos:self.pos + 1]
        if ch == '"':
            self.pos += 1
            out = []
            while self.pos < len(self.text):
                c = self.text[self.pos]
                self.pos += 1
                if c == '"':
                    return "".join(out)
                if c == "\\":
                    c = self.text[self.pos]
                    self.pos += 1
                    if c.isdigit():
                        digits = c
                        while len(digits) < 3 and self.text[self.pos:self.pos + 1].isdigit():
                            digits += self.text[self.pos]
                            self.pos += 1
                        c = chr(int(digits))
                    else:
                        c = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'}.get(c, c)
                out.append(c)
            raise ValueError("Concert Lua: chaîne incomplète / incomplete string")
        if ch == "{":
            self.pos += 1
            seq, obj = [], {}
            self.ws()
            while self.text[self.pos:self.pos + 1] != "}":
                if self.text[self.pos:self.pos + 1] == "[":
                    self.pos += 1
                    key = self.value()
                    self.take("]")
                    self.take("=")
                    obj[key] = self.value()
                else:
                    seq.append(self.value())
                self.ws()
                if self.text[self.pos:self.pos + 1] != ",":
                    break
                self.pos += 1
                self.ws()
            self.take("}")
            if seq and obj:
                raise ValueError("Concert Lua: table mixte / mixed table")
            return obj if obj else seq
        for token, val in (("true", True), ("false", False), ("nil", None)):
            if self.text.startswith(token, self.pos):
                self.pos += len(token)
                return val
        match = re.match(r"-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", self.text[self.pos:])
        if not match:
            raise ValueError("Concert Lua: expression refusée / expression refused")
        self.pos += len(match[0])
        return float(match[0]) if any(c in match[0] for c in ".eE") else int(match[0])

    def read(self):
        self.take("return")
        value = self.value()
        self.ws()
        if self.pos != len(self.text) or not isinstance(value, dict):
            raise ValueError("Concert Lua invalide / Invalid concert Lua")
        return value


def _files(roots):
    out = []
    for root in roots:
        if root.is_symlink():
            raise ValueError(f"Lien symbolique dans le concert / Symlink in concert: {root}")
        members = sorted(root.rglob("*")) if root.is_dir() else [root]
        for p in members:
            if p.is_symlink():
                raise ValueError(f"Lien symbolique dans le concert / Symlink in concert: {p}")
            if p.is_file():
                out.append(p)
    return out


def _bundle(setlist):
    path = Path(setlist).expanduser().resolve()
    if not path.name.endswith(".setlist.json") or not path.is_file():
        raise ValueError("Setlist introuvable / Setlist not found")
    data = _json(path)
    if not isinstance(data, dict) or not isinstance(data.get("songs"), list):
        raise ValueError("Setlist invalide / Invalid setlist")
    slug = path.name[:-len(".setlist.json")]
    sources = set()
    for e in data["songs"]:
        ref = (e.get("project") or e.get("path")) if isinstance(e, dict) else e
        if ref:
            sources.add(_resolve(ref, path.parent))
    if path in sources or (path.parent / (slug + ".RPP")).resolve() in sources:
        raise ValueError("Le concert ne peut pas être son propre morceau source / Concert cannot be its own source song")
    def owned(p):
        if not p.name.startswith(slug + ".") or p.resolve() in sources:
            return False
        # Audio next to concerts may also be used by the original song projects.
        # Only concert sidecars and our explicitly named package directories belong to us.
        if p.is_dir():
            return p.name in {slug + ext for ext in (".media", ".sources", ".web")}
        return p.name.lower().endswith((".rpp", ".rpp-bak", ".json", ".lua", ".pdf"))
    roots = [p for p in path.parent.iterdir() if owned(p)]
    from .lighting import clean_name
    light = path.parent / "grandMA3" / clean_name(data.get("name") or slug, "Concert")
    if light.exists():
        roots.append(light)
    return path, data, slug, sorted(roots)


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    shutil.copy2(source, target)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or _digest(source) != _digest(target):
        raise OSError(f"Copie non vérifiée / Copy verification failed: {source}")


def _rpp(text, base, locate):
    """Preserve opaque FX data and all musical edits, replace FILE references only."""
    result = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"^(\s*)FILE\s+(.+?)(\r?\n)?$", line)
        if match:
            fields = C.tokens("FILE " + match[2])
            if len(fields) < 2:
                raise ValueError("Référence FILE invalide / Invalid FILE reference")
            ref = locate(_resolve(fields[1], base))
            line = match[1] + "FILE " + C.q(ref) + (" " + " ".join(C.q(v) for v in fields[2:]) if len(fields) > 2 else "") + (match[3] or "")
        result.append(line)
    return "".join(result)


def _is_rpp(path):
    return path.name.lower().endswith((".rpp", ".rpp-bak"))


def _install(source, destination):
    """Exclusive creation works on USB/FAT as well: never replace a late collision."""
    if source.is_dir():
        destination.mkdir()
        try:
            for child in source.iterdir():
                _install(child, destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    else:
        created = False
        try:
            with destination.open("xb") as output:
                created = True
                with source.open("rb") as data:
                    shutil.copyfileobj(data, output, length=1024 * 1024)
            shutil.copystat(source, destination)
            if _digest(source) != _digest(destination):
                raise OSError(f"Échec de vérification / Verification failed: {destination}")
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise


def _walk(value, transform):
    if isinstance(value, dict):
        return {k: _walk(v, transform) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, transform) for v in value]
    return transform(value) if isinstance(value, str) else value


def _commit(stage, target, roots, move, new_directory, snapshots=None):
    """Install without replacing existing files; restore originals on any commit failure."""
    installed, saved, made_dirs = [], [], []
    parts = []
    for p in stage.iterdir():
        if p.name == "grandMA3" and not new_directory:
            parts.extend((child, Path("grandMA3") / child.name) for child in p.iterdir())
        else:
            parts.append((p, Path(p.name)))
    backup = Path(tempfile.mkdtemp(prefix=".reacue-rollback-", dir=roots[0].parent)) if move else None
    if backup:
        (backup / "transaction.json").write_text(json.dumps({"version": 1, "destination": str(target),
            "originals": [{"path": str(p), "stored": str(i)} for i, p in enumerate(roots)]}, indent=2), encoding="utf-8")
    def stash(source):
        stored = backup / str(roots.index(source))
        os.replace(source, stored)
        saved.append((source, stored))
    def unchanged():
        for p, expected in (snapshots or {}).items():
            check = p
            for root, stored in saved:
                if p == root or root in p.parents:
                    check = stored / p.relative_to(root) if p != root else stored
                    break
            stat = check.stat()
            if (stat.st_size, stat.st_mtime_ns) != expected:
                raise OSError(f"Concert modifié pendant l'opération / Concert changed during operation: {p}")
    try:
        if new_directory:
            if target.exists():
                raise FileExistsError(str(target))
        else:
            for p, rel in parts:
                dest = target / rel
                if dest.exists() and not (move and dest in roots):
                    raise FileExistsError(str(dest))
        unchanged()
        # Keep originals available throughout long copies. Only an owned destination
        # shared by the old and new names (e.g. the same grandMA3 slug) needs staging first.
        if move and not new_directory:
            destinations = {target / rel for _, rel in parts}
            for source in roots:
                if source in destinations:
                    stash(source)
        if new_directory:
            _install(stage, target)
            installed.append(target)
        else:
            target.mkdir(parents=True, exist_ok=True)
            # grandMA3 may contain other concerts; merge this one subdirectory only.
            for p, rel in parts:
                dest = target / rel
                if not dest.parent.exists():
                    dest.parent.mkdir(parents=True)
                    made_dirs.append(dest.parent)
                _install(p, dest)
                installed.append(dest)
        unchanged()
        if move:
            for source in roots:
                if not any(original == source for original, _ in saved):
                    stash(source)
    except BaseException:
        for p in reversed(installed):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
        for original, stored in reversed(saved):
            original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stored, original)
        for folder in reversed(made_dirs):
            try:
                folder.rmdir()
            except OSError:
                pass
        raise
    finally:
        if backup and backup.exists() and not any(p.name != "transaction.json" for p in backup.iterdir()):
            (backup / "transaction.json").unlink(missing_ok=True)
            backup.rmdir()
    if backup:
        if backup.exists():
            shutil.rmtree(backup)


def _dispatch_request(request: dict, progress=None) -> dict:
    """rename/duplicate/archive/trash/restore/portable; destination is a folder, never overwritten."""
    operation = request.get("operation")
    if operation not in ("rename", "duplicate", "archive", "trash", "restore", "portable"):
        raise ValueError("Opération inconnue / Unknown operation")
    path, data, old, roots = _bundle(request.get("setlist") or "")
    old_name = data.get("name") or old
    name, slug = _name(request.get("name") or old_name)
    if operation in ("rename", "duplicate") and not request.get("name"):
        raise ValueError("Nom requis / Name required")
    destination = request.get("destination")
    recovery = operation in ("archive", "trash")
    portable = operation == "portable"
    relative_paths = portable or (path.parent / (old + ".package.json")).is_file()
    move = operation in ("rename", "archive", "trash", "restore")
    manifest = None
    if operation == "restore":
        manifest_path = path.parent / "recovery.json"
        manifest = _json(manifest_path)
        if manifest.get("version") != 1 or manifest.get("setlist") != path.name:
            raise ValueError("Archive de récupération invalide / Invalid recovery archive")
        destination = destination or manifest["original_directory"]
    if recovery:
        bucket = path.parent / (".reacue-archive" if operation == "archive" else ".reacue-trash")
        target = bucket / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    elif portable:
        if not destination:
            raise ValueError("Nouveau dossier destination requis / New destination folder required")
        target = Path(destination).expanduser().resolve()
    else:
        target = Path(destination).expanduser().resolve() if destination else path.parent
    if target == path.parent and slug == old:
        raise ValueError("Choisir un autre nom / Choose another name")
    if portable and (target == path.parent or any(target == r or r in target.parents for r in roots)):
        raise ValueError("Destination dans le concert source / Destination inside source concert")
    new_directory = portable or recovery or not target.exists()
    if portable and target.exists():
        raise FileExistsError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".reacue-stage-", dir=target.parent))
    mapping, source_files = {}, _files(roots)
    snapshots = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in source_files}
    from .lighting import clean_name
    old_light = clean_name(old_name, "Concert")
    new_light = clean_name(name, "Concert")
    warnings = []
    def renamed(rel):
        parts = list(rel.parts)
        parts = [(slug + p[len(old):]) if p.startswith(old + ".") else p for p in parts]
        parts = [p.replace("reacue_gma3_" + old_light + "__", "reacue_gma3_" + new_light + "__")
                 .replace(old_light + "_Timecode", new_light + "_Timecode")
                 .replace(old_light + "_conduite", new_light + "_conduite") for p in parts]
        if len(parts) > 1 and parts[0] == "grandMA3" and parts[1] == old_light:
            parts[1] = new_light
            parts = [new_light + p[len(old_light):] if p.startswith(old_light + "_") else p for p in parts]
        return Path(*parts)
    for p in source_files:
        mapping[p.resolve()] = renamed(p.relative_to(path.parent))
    # Validate collisions before any source is moved.
    try:
        if not new_directory:
            for rel in mapping.values():
                dest = target / rel
                if dest.exists() and not (move and dest in source_files):
                    raise FileExistsError(str(dest))
        for p, rel in list(mapping.items()):
            _copy(p, stage / rel)
        if progress:
            progress(_message("Vérification des fichiers du concert", "Checking concert files"))
        source_projects = []
        if portable:
            if not (path.parent / (old + ".RPP")).is_file():
                raise ValueError("Construire le concert avant de le rendre portable / Build concert before packaging")
            if not (path.parent / (old + ".concert.lua")).is_file():
                raise FileNotFoundError("Données concert manquantes / Missing concert sidecar")
            for e in data["songs"]:
                ref = (e.get("project") or e.get("path") or e.get("name")) if isinstance(e, dict) else e
                p = _resolve(ref, path.parent)
                if not p.is_file():
                    p = C.find_project(ref)
                source_projects.append(p)
                token = hashlib.sha256(str(p).encode()).hexdigest()[:10]
                mapping[p] = Path(slug + ".sources") / token / p.name
                _copy(p, stage / mapping[p])
                for nearby in p.parent.iterdir():
                    if nearby.is_file() and (nearby.name.lower().startswith(("paroles", "lyrics")) or nearby.name in ("paroles_calage.json",)):
                        mapping[nearby.resolve()] = mapping[p].parent / nearby.name
                        _copy(nearby, stage / mapping[nearby.resolve()])
            queued = list(mapping)
            done = set()
            while queued:
                p = queued.pop()
                if p in done or not _is_rpp(p):
                    continue
                done.add(p)
                output = mapping[p]
                def collect(source):
                    if not source.is_file():
                        raise FileNotFoundError(f"Média manquant / Missing media: {source}")
                    if source not in mapping:
                        token = hashlib.sha256(str(source).encode()).hexdigest()[:16]
                        mapping[source] = Path(slug + ".media") / (token + "-" + source.name)
                        _copy(source, stage / mapping[source])
                        queued.append(source)
                    return Path(os.path.relpath(mapping[source], output.parent)).as_posix()
                original = p.read_text(encoding="utf-8-sig")
                if re.search(r"(?m)^\s*<(?:VST|AU|CLAP|DX|JS)\b", original):
                    warning = _message("Plugins et éventuels samples externes non inclus : ",
                                       "Plugins and possible external samples are not included: ") + p.name
                    if warning not in warnings:
                        warnings.append(warning)
                rendered = _rpp(original, p.parent, collect)
                (stage / output).write_text(rendered, encoding="utf-8")
            web = stage / (slug + ".web")
            shutil.copytree(Path(__file__).parent / "web", web, dirs_exist_ok=True)
        # Rewrite explicit path values, retaining all timing, lyrics and manual musical edits.
        def transform(value, base, output_parent):
            try:
                source = _resolve(value, base)
            except (ValueError, OSError):
                return value
            if source in mapping:
                return Path(os.path.relpath(mapping[source], output_parent)).as_posix() if relative_paths else str(target / mapping[source])
            if source.is_dir() and any(root == source or root in source.parents for root in roots):
                rel = renamed(source.relative_to(path.parent))
                return Path(os.path.relpath(rel, output_parent)).as_posix() if relative_paths else str(target / rel)
            if relative_paths and _absolute(value):
                raise ValueError(f"Dépendance non collectée / Uncollected dependency: {value}")
            if not relative_paths and not _absolute(value) and (base / value).exists():
                return str(source)
            return value
        for source, rel in list(mapping.items()):
            output = stage / rel
            if _is_rpp(source):
                if not portable:
                    def relocated(p):
                        if relative_paths:
                            if p not in mapping:
                                raise ValueError(f"Dépendance hors package / Dependency outside package: {p}")
                            return Path(os.path.relpath(mapping[p], rel.parent)).as_posix()
                        return str(target / mapping[p]) if p in mapping else str(p)
                    txt = _rpp(source.read_text(encoding="utf-8-sig"), source.parent,
                               relocated)
                    output.write_text(txt, encoding="utf-8")
                continue
            if source.name.endswith(".concert.lua"):
                side = _LuaData(source.read_text(encoding="utf-8-sig")).read()
                side = _walk(side, lambda v: transform(v, source.parent, rel.parent))
                side.update(name=name, rpp=(slug + ".RPP") if relative_paths else str(target / (slug + ".RPP")),
                            setlist=(slug + ".setlist.json") if relative_paths else str(target / (slug + ".setlist.json")),
                            prompter=(slug + ".prompteur.json") if relative_paths else str(target / (slug + ".prompteur.json")))
                if relative_paths:
                    side["package_web"] = slug + ".web"
                    for song in side.get("songs", []):
                        p = stage / song["project"]
                        song.update(C._fingerprint(p))
                output.write_text("-- ReaCue concert data\nreturn " + to_lua(side) + "\n", encoding="utf-8")
            elif source.suffix.lower() == ".json":
                value = _walk(_json(source), lambda v: transform(v, source.parent, rel.parent))
                if rel.parts[0] == "grandMA3":
                    value = _walk(value, lambda v: new_light if v == old_light else v)
                if source == path:
                    value["name"] = name
                if isinstance(value, dict) and isinstance(value.get("concert"), dict):
                    value["concert"]["name"] = name
                    value["id"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]
                output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Lighting files and links are reused exactly, only names/links change.
        old_names = {p.name: rel.name for p, rel in mapping.items() if p.name != rel.name}
        for output in stage.rglob("*"):
            if output.is_file() and output.suffix.lower() in (".xml", ".lua", ".json", ".csv"):
                text = output.read_text(encoding="utf-8-sig")
                for before, after in old_names.items():
                    text = text.replace(before, after)
                text = text.replace("reacue_gma3_" + old_light + "__", "reacue_gma3_" + new_light + "__")
                output.write_text(text, encoding="utf-8")
        if relative_paths:
            sidecar = stage / (slug + ".concert.lua")
            if sidecar.is_file():
                value = _LuaData(sidecar.read_text(encoding="utf-8")).read()
                for song in value.get("songs", []):
                    song.update(C._fingerprint(stage / song["project"]))
                sidecar.write_text("-- ReaCue concert data\nreturn " + to_lua(value) + "\n", encoding="utf-8")
        if portable:
            prom = stage / (slug + ".prompteur.json")
            if not prom.is_file():
                raise FileNotFoundError("Prompteur manquant / Missing prompter")
            pj = _json(prom)
            for f in (pj.get("lighting") or {}).get("files", []):
                light = stage / "grandMA3" / new_light / f["name"]
                if not light.is_file():
                    raise FileNotFoundError(f"Fichier lumière manquant / Missing lighting file: {light.name}")
                shutil.copy2(light, stage / (slug + ".web") / Path(f["url"]).name)
            web_data = _walk(pj, lambda v: "../" + v if any(v == str(rel) for rel in mapping.values()) else v)
            (stage / (slug + ".web") / "reacue_song.json").write_text(json.dumps(web_data, ensure_ascii=False), encoding="utf-8")
        package_manifest = stage / (slug + ".package.json")
        if portable or package_manifest.exists():
            checks = {str(p.relative_to(stage)): _digest(p) for p in stage.rglob("*") if p.is_file() and p != package_manifest}
            package_manifest.write_text(json.dumps({"version": 1, "name": name, "files": checks}, indent=2), encoding="utf-8")
        if recovery:
            (stage / "recovery.json").write_text(json.dumps({"version": 1, "operation": operation,
                "original_directory": str(path.parent), "setlist": slug + ".setlist.json", "name": name}, indent=2), encoding="utf-8")
        for p, snapshot in snapshots.items():
            if (p.stat().st_size, p.stat().st_mtime_ns) != snapshot:
                raise OSError(f"Concert modifié pendant l'opération / Concert changed during operation: {p}")
        _commit(stage, target, roots, move, new_directory, snapshots)
        if move:
            for old_root in roots:
                if old_root.parent != path.parent:
                    try:
                        old_root.parent.rmdir()
                    except OSError:
                        pass
        if operation == "restore":
            (path.parent / "recovery.json").unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass
        final = target / (slug + ".setlist.json")
        return {"operation": operation, "name": name, "setlist": str(final), "projet": str(target / (slug + ".RPP")),
                "path": str(target), "files": len(mapping), "warnings": warnings,
                "message": _message("Concert traité : ", "Concert updated: ") + name + " — " + str(target)
                           + (("\n" + "\n".join(warnings)) if warnings else "")}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def dispatch_request(request: dict, progress=None) -> dict:
    """Allow normal CLI cancellation to unwind the transaction and remove staged files."""
    previous = None
    can_handle = threading.current_thread() is threading.main_thread()
    if can_handle:
        previous = signal.getsignal(signal.SIGTERM)
        def cancelled(signum, frame):
            raise InterruptedError("Gestion du concert annulée / Concert operation cancelled")
        signal.signal(signal.SIGTERM, cancelled)
    try:
        return _dispatch_request(request, progress)
    finally:
        if can_handle:
            signal.signal(signal.SIGTERM, previous)
