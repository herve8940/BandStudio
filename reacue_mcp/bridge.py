"""Client du pont fichier vers ReaCue_Bridge.lua (tourne dans REAPER)."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import asyncio
from pathlib import Path

from .i18n import t


def default_resource_dir() -> Path:
    env = os.environ.get("REAPER_RESOURCE_PATH")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "REAPER"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "REAPER"
    return Path.home() / ".config" / "REAPER"


BRIDGE_DIR = default_resource_dir() / "ReaCueMCP"


def to_lua(v) -> str:
    """Sérialise des données Python en littéral Lua (lu sans accès à l'API côté REAPER)."""
    if v is None:
        return "nil"
    if hasattr(v, "item") and not isinstance(v, (str, bytes, dict, list, tuple)):
        v = v.item()                      # scalaires numpy -> Python
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return "0"
        return repr(v)
    if isinstance(v, str):
        # les caractères UTF-8 passent tels quels ; seuls \ " et les contrôles sont échappés
        out = []
        for c in v:
            if c == "\\":
                out.append("\\\\")
            elif c == '"':
                out.append('\\"')
            elif ord(c) < 32 or ord(c) == 127:
                out.append(f"\\{ord(c):03d}")
            else:
                out.append(c)
        return '"' + "".join(out) + '"'
    if isinstance(v, dict):
        return "{" + ",".join(f"[{to_lua(str(k))}]={to_lua(x)}" for k, x in v.items() if x is not None) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(to_lua(x) for x in v) + "}"
    return to_lua(str(v))


class BridgeError(RuntimeError):
    pass


class Bridge:
    def __init__(self, directory: Path = BRIDGE_DIR):
        self.dir = Path(directory)
        self.req = self.dir / "request.lua"
        self.res = self.dir / "response.json"
        self.heartbeat = self.dir / "heartbeat.txt"
        self._lock = asyncio.Lock()

    def alive(self) -> tuple[bool, str]:
        if not self.dir.exists():
            return False, t("bridge_dir_missing", dir=self.dir)
        if not self.heartbeat.exists():
            return False, t("bridge_no_heartbeat")
        age = time.time() - self.heartbeat.stat().st_mtime
        if age > 8:
            return False, t("bridge_silent", age=age)
        return True, "ok"

    async def call(self, cmd: str, args: dict | None = None, timeout: float = 30.0):
        if cmd in {"import_file", "apply_plan", "timecode_tracks"}:
            from .show_lock import require_edit
            require_edit(self.dir)
        ok, why = self.alive()
        if not ok:
            raise BridgeError(why)
        async with self._lock:
            rid = uuid.uuid4().hex
            self.res.unlink(missing_ok=True)
            tmp = self.req.with_suffix(".tmp")
            tmp.write_text(to_lua({"id": rid, "cmd": cmd, "args": args or {},
                                   "expected_project": os.environ.get("REACUE_EXPECTED_PROJECT")}), encoding="utf-8")
            os.replace(tmp, self.req)
            t_end = time.monotonic() + timeout
            while time.monotonic() < t_end:
                if self.res.exists():
                    try:
                        data = json.loads(self.res.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        await asyncio.sleep(0.05)
                        continue
                    if data.get("id") in (rid, None):
                        self.res.unlink(missing_ok=True)
                        if not data.get("ok"):
                            raise BridgeError(data.get("error", t("bridge_unknown_error")))
                        return data.get("result")
                await asyncio.sleep(0.05)
            self.req.unlink(missing_ok=True)
            raise BridgeError(t("bridge_timeout", timeout=timeout))
