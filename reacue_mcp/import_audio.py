"""Optional public YouTube audio import. Network access only on an explicit import request.

The downloader runs in .venv-import; the main environment needs only the standard library.
Completed source downloads are cached independently of trimming/encoding and project names.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import unicodedata
from urllib.parse import parse_qs, urlsplit
import uuid

ROOT = Path(__file__).resolve().parent.parent
MAX_DURATION = 3 * 3600
MAX_BYTES = 1024 * 1024 * 1024
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class ImportAudioError(RuntimeError):
    pass


class ImportCancelled(ImportAudioError):
    pass


def canonical_url(value):
    """Accept one concrete YouTube video, never an arbitrary downloader URL or playlist."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ImportAudioError("Lien YouTube invalide.")
    try:
        u = urlsplit(value.strip())
        host = (u.hostname or "").lower()
        if u.scheme not in ("https", "http") or u.username or u.password or u.port not in (None, 80, 443):
            raise ValueError()
        q = parse_qs(u.query)
        if "list" in q or "playlist" in u.path:
            raise ImportAudioError("Choisissez une seule vidéo, sans lien de playlist.")
        if host == "youtu.be":
            vid = u.path.strip("/")
        elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
            if u.path == "/watch":
                vid = q.get("v", [""])[0]
            else:
                match = re.fullmatch(r"/(?:shorts|embed)/([^/]+)/?", u.path)
                vid = match.group(1) if match else ""
        else:
            vid = ""
        if not VIDEO_ID.fullmatch(vid):
            raise ValueError()
    except ValueError:
        raise ImportAudioError("Collez le lien d'une vidéo YouTube publique (youtube.com/watch ou youtu.be).") from None
    return f"https://www.youtube.com/watch?v={vid}", vid


def safe_title(value):
    value = unicodedata.normalize("NFC", str(value or ""))
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")[:100].rstrip(" .")
    if not value or value in (".", ".."):
        raise ImportAudioError("Indiquez un titre de morceau.")
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value):
        value = "Morceau - " + value
    return value


def cache_root():
    from .bridge import default_resource_dir
    return default_resource_dir() / "ReaCueMCP" / "import-cache"


def _binary(name):
    found = shutil.which(name)
    if found:
        return found
    for base in (ROOT / "import-tools", Path.home() / ".deno/bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin")):
        p = base / (name + (".exe" if os.name == "nt" else ""))
        if p.is_file():
            return str(p)
    raise ImportAudioError(f"{name} introuvable. Lancez « Install ReaCue Import » puis rouvrez ReaCue.")


def dependencies():
    py = ROOT / ".venv-import" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.is_file():
        raise ImportAudioError("L'import depuis un lien n'est pas installé. Lancez « Install ReaCue Import » dans le dossier ReaCue.")
    ffmpeg, ffprobe = _binary("ffmpeg"), _binary("ffprobe")
    # Deno is the recommended, permission-restricted yt-dlp EJS runtime.
    deno = _binary("deno")
    return {"python": str(py), "ffmpeg": ffmpeg, "ffprobe": ffprobe, "deno": deno}


def _cancelled(cancel_file):
    if cancel_file and Path(cancel_file).exists():
        raise ImportCancelled("Import annulé. Le téléchargement partiel reste disponible pour une reprise.")


def _stop(proc):
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        proc.kill()
        proc.wait(timeout=5)


def _run(args, *, progress=None, cancel_file=None, timeout=180, label="Import", capture=False):
    """argv only; poll cancellation while draining output so a verbose child cannot deadlock."""
    _cancelled(cancel_file)
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **kw)
    lines = queue.Queue()
    def reader():
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    threading.Thread(target=reader, daemon=True).start()
    output, size, ended, start = [], 0, False, time.monotonic()
    try:
        while not ended or proc.poll() is None:
            _cancelled(cancel_file)
            if time.monotonic() - start > timeout:
                raise ImportAudioError(f"{label} : délai dépassé. Vérifiez la connexion puis relancez.")
            try:
                line = lines.get(timeout=0.15)
            except queue.Empty:
                continue
            if line is None:
                ended = True
                continue
            size += len(line)
            if capture and size > 8 * 1024 * 1024:
                raise ImportAudioError("Réponse du service trop volumineuse.")
            output.append(line)
            if not capture and len(output) > 100:
                output.pop(0)
            if progress and not capture and "%" in line:
                match = re.search(r"(\d+(?:\.\d+)?)%", line)
                if match:
                    progress(f"{label} : {match.group(1)} %")
        if proc.returncode:
            raise ImportAudioError(_friendly_error("".join(output)[-3000:]))
        return "".join(output)
    finally:
        _stop(proc)
        proc.stdout.close()


def _friendly_error(text):
    low = text.lower()
    if any(x in low for x in ("sign in", "login", "cookies", "private video", "age-restricted", "members-only")):
        return "Cette vidéo nécessite une connexion ou un accès restreint. Choisissez une vidéo publique accessible sans compte."
    if any(x in low for x in ("429", "403", "bot", "challenge", "javascript", "ejs")):
        return "YouTube refuse cet accès. Réessayez plus tard ou mettez à jour « Install ReaCue Import ». Aucun contournement n'est tenté."
    if any(x in low for x in ("unavailable", "not available", "copyright", "removed")):
        return "Cette vidéo n'est pas disponible. Choisissez une autre vidéo publique."
    return "Import impossible. Vérifiez la connexion et le composant « Install ReaCue Import ». " + text.strip()[-400:]


def _ytdlp(deps):
    return [deps["python"], "-m", "yt_dlp", "--ignore-config", "--no-plugin-dirs", "--no-playlist",
            "--no-remote-components", "--no-js-runtimes", "--js-runtimes", "deno:" + deps["deno"],
            "--no-cookies", "--no-cookies-from-browser", "--socket-timeout", "20", "--retries", "2",
            "--no-colors", "--no-cache-dir", "--ffmpeg-location", str(Path(deps["ffmpeg"]).parent)]


def _metadata(raw, url, vid):
    if not isinstance(raw, dict) or raw.get("_type") in ("playlist", "multi_video") or raw.get("id") != vid:
        raise ImportAudioError("Le lien doit désigner une seule vidéo YouTube.")
    if raw.get("is_live") or raw.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise ImportAudioError("Les directs en cours ou à venir ne sont pas importés. Choisissez une vidéo terminée.")
    if raw.get("availability") not in (None, "public") or (raw.get("age_limit") or 0) > 0:
        raise ImportAudioError("Cette vidéo n'est pas accessible publiquement sans restriction.")
    try:
        duration = float(raw["duration"])
    except (KeyError, ValueError, TypeError):
        duration = 0
    if not math.isfinite(duration) or not 1 <= duration <= MAX_DURATION:
        raise ImportAudioError("Durée non disponible ou hors limite (1 seconde à 3 heures).")
    return {"operation": "inspect", "url": url, "id": vid, "title": safe_title(raw.get("title") or vid),
            "duration": duration}


def _inspect(url, vid, deps, progress, cancel_file):
    if progress:
        progress("Lecture du titre et de la durée…")
    out = _run(_ytdlp(deps) + ["--skip-download", "--dump-single-json", "--", url],
               capture=True, progress=progress, cancel_file=cancel_file)
    try:
        raw = json.loads(next(line for line in reversed(out.splitlines()) if line.startswith("{")))
    except (ValueError, StopIteration):
        raise ImportAudioError("Métadonnées YouTube illisibles. Mettez à jour « Install ReaCue Import ».") from None
    return _metadata(raw, url, vid)


def _atomic_json(path, data):
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def _lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "active.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        old = _read_json(path)
        pid = old.get("pid")
        from .jobs import process_alive
        if process_alive(pid) is False:
            path.unlink(missing_ok=True)
            with _lock(folder):
                yield
            return
        raise ImportAudioError("Un import de cette vidéo est déjà en cours. Attendez sa fin ou annulez-le.") from None
    with os.fdopen(fd, "w") as f:
        json.dump({"pid": os.getpid()}, f)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _probe(path, deps, cancel_file=None):
    raw = _run([deps["ffprobe"], "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type",
                "-of", "json", str(path)], capture=True, cancel_file=cancel_file)
    try:
        obj = json.loads(raw)
        duration = float(obj["format"]["duration"])
        audio = next(s for s in obj["streams"] if s.get("codec_type") == "audio")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError()
        return duration, audio["codec_name"]
    except (ValueError, TypeError, KeyError, StopIteration):
        raise ImportAudioError("Le fichier reçu ne contient pas d'audio lisible.") from None


def _source(folder, meta, deps, progress, cancel_file):
    manifest = _read_json(folder / "source.json")
    name = manifest.get("file", "")
    source = folder / name
    if name and Path(name).name == name and source.is_file() and source.stat().st_size == manifest.get("size"):
        if _sha(source) == manifest.get("sha256"):
            return source, True
    # Only discard our own failed completed download. Keep .part files for yt-dlp's resume.
    if name and Path(name).name == name and name.startswith("source.") and source.is_file():
        source.unlink()
        (folder / "source.json").unlink(missing_ok=True)
    if progress:
        progress("Téléchargement de l'audio…")
    output = _run(_ytdlp(deps) + ["--format", "bestaudio", "--max-filesize", str(MAX_BYTES), "--continue",
                         "--newline", "--progress", "--progress-delta", "1", "--no-mtime", "--no-simulate",
                         "--print", "after_move:filepath", "--output", str(folder / "source.%(ext)s"), "--", meta["url"]],
         progress=progress, cancel_file=cancel_file, timeout=3600, label="Téléchargement")
    candidates = []
    for line in output.splitlines():
        p = Path(line.strip())
        if p.name.startswith("source.") and p.suffix in (".m4a", ".webm", ".opus", ".ogg", ".mp3", ".mp4"):
            if p.is_file() and p.resolve().parent == folder.resolve():
                candidates.append(p)
    if not candidates or not 0 < candidates[-1].stat().st_size <= MAX_BYTES:
        raise ImportAudioError("Le téléchargement n'a pas produit un fichier audio complet (limite : 1 Go).")
    source = candidates[-1]
    try:
        duration, _ = _probe(source, deps, cancel_file)
    except ImportCancelled:
        raise
    except ImportAudioError:
        source.unlink(missing_ok=True)
        raise
    if abs(duration - meta["duration"]) > max(3, meta["duration"] * 0.02):
        source.unlink(missing_ok=True)
        raise ImportAudioError("Le téléchargement semble incomplet. Réessayez l'import.")
    _atomic_json(folder / "source.json", {"file": source.name, "size": source.stat().st_size,
                                          "sha256": _sha(source), "metadata": meta})
    return source, False


def _range(data, duration):
    try:
        start = float(data.get("start") or 0)
        end = float(duration if data.get("end") in (None, "") else data["end"])
    except (ValueError, TypeError):
        raise ImportAudioError("Début et fin doivent être exprimés en secondes.") from None
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration + 0.1 or end - start < 0.5:
        raise ImportAudioError("Passage invalide : 0 ≤ début < fin ≤ durée, avec au moins une demi-seconde.")
    return start, min(end, duration)


def dispatch_request(data, progress=None):
    if not isinstance(data, dict):
        raise ImportAudioError("Demande d'import invalide.")
    operation = data.get("operation", "inspect")
    if operation not in ("inspect", "download"):
        raise ImportAudioError("Opération d'import inconnue.")
    url, vid = canonical_url(data.get("url"))
    cancel_file = data.get("cancel_file")
    _cancelled(cancel_file)
    deps = dependencies()
    if operation == "inspect":
        return _inspect(url, vid, deps, progress, cancel_file)
    fmt = data.get("format", "best")
    if fmt not in ("best", "mp3"):
        raise ImportAudioError("Choisissez le format best ou mp3.")
    title = safe_title(data.get("title"))
    root_value = data.get("root")
    if not isinstance(root_value, str) or not root_value or len(root_value) > 2048:
        raise ImportAudioError("Dossier des projets invalide.")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise ImportAudioError("Le dossier des projets n'existe pas. Choisissez-le dans les réglages ReaCue.")
    target = root / title
    if target.exists():
        raise ImportAudioError("Un morceau de ce titre existe déjà. Choisissez un autre titre ; aucun fichier n'a été remplacé.")
    folder = cache_root() / vid
    with _lock(folder):
        stored = _read_json(folder / "source.json").get("metadata")
        meta = stored if isinstance(stored, dict) and stored.get("url") == url else _inspect(url, vid, deps, progress, cancel_file)
        start, end = _range(data, meta["duration"])
        source, cached = _source(folder, meta, deps, progress, cancel_file)
        _cancelled(cancel_file)
        _, codec = _probe(source, deps, cancel_file)
        ext = "mp3" if fmt == "mp3" else {"aac": "m4a", "opus": "ogg", "vorbis": "ogg", "mp3": "mp3", "flac": "flac"}.get(codec)
        if not ext:
            raise ImportAudioError("Ce codec ne peut pas être conservé sans recompression. Choisissez MP3.")
        temporary = root / (".reacue-import-" + uuid.uuid4().hex)
        temporary.mkdir()
        try:
            output = temporary / (title + "." + ext)
            args = [deps["ffmpeg"], "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(source),
                    "-ss", str(start), "-t", str(end - start), "-map", "0:a:0", "-vn", "-map_metadata", "-1"]
            args += ["-c:a", "copy"] if fmt == "best" else ["-c:a", "libmp3lame", "-q:a", "2"]
            args += ["-avoid_negative_ts", "make_zero", str(output)]
            if progress:
                progress("Préparation du passage…")
            _run(args, cancel_file=cancel_file, timeout=600)
            actual, _ = _probe(output, deps, cancel_file)
            if not output.is_file() or not 0 < output.stat().st_size <= MAX_BYTES or abs(actual - (end - start)) > 0.5:
                raise ImportAudioError("Le passage exporté est incomplet. Aucun projet n'a été créé.")
            _cancelled(cancel_file)
            # mkdir is the no-overwrite reservation; commit only our own newly created directory.
            target.mkdir()
            try:
                os.replace(output, target / output.name)
            except BaseException:
                target.rmdir()
                raise
            result = {"operation": "download", "file": str(target / output.name), "folder": str(target),
                      "title": title, "duration": actual, "start": start, "end": end, "cached": cached,
                      "format": fmt, "url": url}
            return result
        except FileExistsError:
            raise ImportAudioError("Ce titre vient d'être créé. Choisissez un autre titre ; rien n'est écrasé.") from None
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
