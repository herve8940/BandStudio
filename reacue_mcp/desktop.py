"""Local, authenticated desktop host. Existing ReaCue engines remain authoritative.

The desktop bridge has its own mailbox: it never consumes the MCP/CLI bridge's
responses. Merely opening this application does not alter a REAPER project.
"""
from __future__ import annotations

import argparse
import contextlib
import html
import hmac
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .bridge import default_resource_dir

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "reacue_mcp" / "web"
VERSION = "2.0.0-preview.1"
BASE_REVISION = "de701dc13f8979379e17c184ef803339f05b29be"
MAX_BODY = 512 * 1024


class DesktopError(RuntimeError):
    pass


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as f:
            os.chmod(tmp, 0o600)
            json.dump(value, f, ensure_ascii=False, allow_nan=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class DesktopBridge:
    def __init__(self, resource: Path):
        self.directory = resource / "ReaCueDesktop"
        self.lock = threading.RLock()

    def alive(self):
        try:
            return time.time() - (self.directory / "heartbeat.json").stat().st_mtime < 5
        except OSError:
            return False

    @contextlib.contextmanager
    def mailbox_lock(self, timeout):
        # Separate windows/processes must not overwrite one another's requests.
        import fcntl  # The native Desktop host currently targets macOS.
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "client.lock").open("a") as lock:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise DesktopError("Une autre fenêtre attend REAPER. Réessaie dans un instant.")
                    time.sleep(.025)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def call(self, command, args=None, project_id=None, timeout=8):
        with self.lock, self.mailbox_lock(timeout):
            if not self.alive():
                raise DesktopError("Pont Desktop absent. Dans REAPER : Actions → Charger ReaScript → ReaCue_Desktop_Bridge.lua → Exécuter.")
            rid = uuid.uuid4().hex
            request = self.directory / "request.json"
            response = self.directory / "response.json"
            atomic_json(request, {"id": rid, "command": command, "args": args or {},
                                  "project_id": project_id, "expires": time.time() + timeout})
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline:
                    data = read_json(response, {})
                    if isinstance(data, dict) and data.get("id") == rid:
                        response.unlink(missing_ok=True)
                        if not data.get("ok"):
                            raise DesktopError(data.get("error") or "La commande REAPER a échoué.")
                        return data.get("result")
                    time.sleep(.025)
                raise DesktopError("REAPER ne répond pas. Ferme ses fenêtres de dialogue, puis réessaie.")
            finally:
                # Never leave a mutation to be executed after a timeout/reconnect.
                pending = read_json(request, {})
                if isinstance(pending, dict) and pending.get("id") == rid:
                    request.unlink(missing_ok=True)


class Desktop:
    def __init__(self, resource=None, bridge=None):
        self.resource = Path(resource or default_resource_dir()).resolve()
        self.bridge = bridge or DesktopBridge(self.resource)
        self.token = secrets.token_urlsafe(32)
        self.mcp = self.resource / "ReaCueMCP"
        self.published = self.resource / "reaper_www_root"
        self.cached_state = None
        self.state_at = 0.
        self.state_lock = threading.Lock()
        self.task = None
        self.task_lock = threading.Lock()

    def state(self, force=False):
        with self.state_lock:
            if not force and self.cached_state and time.monotonic() - self.state_at < .2:
                return self.cached_state
            state = self.bridge.call("state")
            self.cached_state, self.state_at = state, time.monotonic()
            return state

    def status(self):
        result = {"version": VERSION, "revision": BASE_REVISION,
                  "bridge": self.bridge.alive(), "source": str(ROOT),
                  "bridge_script": str(ROOT / "reaper" / "ReaCue_Desktop_Bridge.lua"),
                  "resource": str(self.resource), "platform": sys.platform,
                  "job": read_json(self.mcp / "cli_status.json", {}),
                  "task": self.task, "connected": False}
        if result["bridge"]:
            try:
                result["reaper"] = self.state()
                result["connected"] = True
            except DesktopError as e:
                result["error"] = str(e)
        else:
            result["error"] = "Ouvre REAPER et lance le pont Desktop pour retrouver ton projet."
        result["waiting"] = bool(not result["connected"] and self.cached_state and
                                 (self.resource / "ReaCueDesktop" / "heartbeat.json").exists())
        if result["waiting"]:
            result["error"] = "REAPER est en attente. Termine ou ferme sa fenêtre de dialogue pour reprendre."
        return result

    def published_data(self, name):
        if name not in {"reacue_song.json", "reacue_peaks.json", "reacue_library.json", "reacue_export.json"}:
            raise DesktopError("Données inconnues.")
        value = read_json(self.published / name, {})
        if name in {"reacue_song.json", "reacue_peaks.json"}:
            state = self.state()
            song = value if name == "reacue_song.json" else read_json(self.published / "reacue_song.json", {})
            # Never show or edit the last published song over another open project.
            published_project = song.get("project") if isinstance(song, dict) else None
            current = state.get("project")
            if not published_project or not current or os.path.normcase(os.path.abspath(published_project)) != os.path.normcase(os.path.abspath(current)):
                return {"stale": True, "message": "Publie le projet ouvert pour charger ses analyses et formes d’onde."}
            if name == "reacue_peaks.json" and value.get("song_id") != song.get("id"):
                return {"stale": True, "message": "Republie le morceau pour actualiser ses formes d’onde."}
        return value

    def library(self):
        data = read_json(self.published / "reacue_library.json", {})
        return data if isinstance(data, dict) else {}

    def control(self, payload):
        command = payload.get("command")
        allowed = {"transport", "seek", "loop", "rate", "track", "listen", "region", "record_track",
                   "open_project", "save", "native", "undo", "redo", "transpose"}
        if command not in allowed:
            raise DesktopError("Commande inconnue.")
        project_id = payload.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            raise DesktopError("Actualise la connexion au projet avant cette action.")
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise DesktopError("Arguments invalides.")
        if command == "open_project":
            path = Path(str(args.get("path", ""))).expanduser()
            if path.suffix.lower() != ".rpp" or not path.is_file():
                raise DesktopError("Choisis un projet REAPER .RPP existant.")
            args = {"path": str(path.resolve())}
        result = self.bridge.call(command, args, project_id=project_id)
        self.state_at = 0
        return result

    def run_task(self, payload):
        command = payload.get("command")
        if command not in {"prepare", "publish", "timecode", "library", "notes"}:
            raise DesktopError("Ce traitement est disponible dans les outils complets ReaCue.")
        state = self.state(force=True)
        if state.get("project_id") != payload.get("project_id"):
            raise DesktopError("Le projet a changé. Actualise avant de lancer le traitement.")
        if state.get("playing") or state.get("recording"):
            raise DesktopError("Arrête la lecture avant de lancer ce traitement.")
        if command not in {"library", "notes"} and not state.get("project"):
            raise DesktopError("Enregistre d’abord le projet REAPER.")
        with self.task_lock:
            if self.task and self.task.get("state") == "running":
                raise DesktopError("Un traitement Desktop est déjà en cours.")
            args = [sys.executable, "-m", "reacue_mcp.cli", command, "--resource-dir", str(self.resource),
                    "--origin-project", state.get("project", "")]
            if command == "prepare" and payload.get("reanalyse") is True:
                args.append("--reanalyse")
            if command == "prepare" and payload.get("bpm") is not None:
                bpm = float(payload["bpm"])
                if not 20 <= bpm <= 400:
                    raise DesktopError("Le tempo doit être compris entre 20 et 400 BPM.")
                args += ["--bpm", str(bpm)]
            env = dict(os.environ, REAPER_RESOURCE_PATH=str(self.resource),
                       REACUE_EXPECTED_PROJECT=state.get("project", ""))
            self.task = {"id": uuid.uuid4().hex, "command": command, "state": "running", "started": time.time()}
            task = self.task
            log_dir = self.resource / "ReaCueDesktop"
            log_dir.mkdir(parents=True, exist_ok=True)
            log = (log_dir / "tasks.log").open("a", encoding="utf-8")
            try:
                process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=log)
            except Exception:
                task["state"] = "error"
                log.close()
                raise
            def wait():
                code = process.wait()
                log.close()
                with self.task_lock:
                    task.update(state="done" if code == 0 else "error", exit_code=code, finished=time.time())
                self.state_at = 0
            threading.Thread(target=wait, daemon=True).start()
            return dict(task)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, desktop, port=0):
        self.desktop = desktop
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = "http://127.0.0.1:" + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    server_version = "ReaCueDesktop"

    def log_message(self, *args):
        pass  # Bootstrap URLs contain the local session secret.

    def send(self, code, content, kind="application/json; charset=utf-8", extra=None):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False)
        data = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; object-src 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def authorized(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return hmac.compare_digest(cookie["reacue_desktop"].value, self.server.desktop.token)
        except (KeyError, ValueError, CookieError):
            return False

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("Requête trop volumineuse.")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Format JSON requis.")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("Objet JSON requis.")
        return data

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        token = urllib.parse.parse_qs(url.query).get("token", [""])[0]
        if url.path == "/" and token and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}" and self.headers.get("Sec-Fetch-Site") != "cross-site" and hmac.compare_digest(token, self.server.desktop.token):
            self.send(303, "", extra={"Location": "/app/", "Set-Cookie": f"reacue_desktop={token}; HttpOnly; SameSite=Strict; Path=/"})
            return
        if not self.authorized():
            self.send(403, {"error": "Ouvre cette fenêtre depuis l’application ReaCue Desktop."})
            return
        d = self.server.desktop
        try:
            if url.path == "/api/status":
                return self.send(200, d.status())
            if url.path == "/api/state":
                return self.send(200, d.state())
            if url.path == "/api/library":
                return self.send(200, d.library())
            if url.path.startswith("/_/"):
                return self.send(200, d.bridge.call("web_api", {"commands": url.path[3:]},
                                 project_id=self.headers.get("X-ReaCue-Project")), "text/plain; charset=utf-8")
            if url.path.startswith("/api/published/"):
                return self.send(200, d.published_data(url.path.rsplit("/", 1)[-1]))
            if url.path.startswith("/app/"):
                base, relative = WEB / "reacue_desktop", url.path[5:] or "index.html"
            elif url.path.startswith("/legacy/"):
                base, relative = WEB, url.path[8:]
                if relative in {"reacue_song.json", "reacue_peaks.json", "reacue_library.json", "reacue_export.json"}:
                    return self.send(200, d.published_data(relative))
                if relative.startswith("reacue_gma3_") and "/" not in relative:
                    base = d.published
                elif relative.startswith("reacue_exports/"):
                    # Export engine publishes only these explicit download assets.
                    base, relative = d.published / "reacue_exports", relative[len("reacue_exports/"):]
            else:
                return self.send(404, {"error": "Ressource introuvable."})
            target = (base / urllib.parse.unquote(relative)).resolve()
            if not target.is_relative_to(base.resolve()) or not target.is_file():
                return self.send(404, {"error": "Ressource introuvable."})
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in {"application/javascript", "application/json"}:
                kind += "; charset=utf-8"
            data = target.read_bytes()
            if url.path.startswith("/legacy/") and target.suffix == ".html":
                project_id = html.escape(d.state().get("project_id", ""), quote=True)
                guard = ('<meta name="reacue-project" content="' + project_id + '">'
                         '<script src="/app/legacy-bridge.js"></script>')
                data = data.replace(b"<head>", ("<head>" + guard).encode(), 1)
                if target.name == "studio.html":
                    data = data.replace(b"</head>", b'<link rel="stylesheet" href="/app/legacy-theme.css"></head>', 1)
            self.send(200, data, kind)
        except (DesktopError, ValueError, OSError) as e:
            self.send(503, {"error": str(e)})

    def do_POST(self):
        if not self.authorized() or self.headers.get("X-ReaCue-Desktop") != "1":
            return self.send(403, {"error": "Session locale requise."})
        try:
            data = self.body()
            if self.path == "/api/control":
                result = self.server.desktop.control(data)
            elif self.path == "/api/task":
                result = self.server.desktop.run_task(data)
            elif self.path == "/api/open":
                target = data.get("target")
                if sys.platform != "darwin":
                    raise DesktopError("Ouvre cette application depuis ton système.")
                if target in {"REAPER", "BandPilot"}:
                    subprocess.Popen(["/usr/bin/open", "-a", target])
                elif target == "bridge":
                    subprocess.Popen(["/usr/bin/open", "-R", str(ROOT / "reaper" / "ReaCue_Desktop_Bridge.lua")])
                else:
                    raise DesktopError("Destination inconnue.")
                result = {"ok": True}
            else:
                return self.send(404, {"error": "Commande inconnue."})
            self.send(200, result)
        except (DesktopError, ValueError, OSError, TypeError) as e:
            self.send(400, {"error": str(e)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-dir", type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    desktop = Desktop(args.resource_dir)
    server = Server(desktop, args.port)
    print(json.dumps({"url": server.origin + "/?token=" + desktop.token, "pid": os.getpid()}), flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
