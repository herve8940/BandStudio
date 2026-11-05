"""Small durable job records; no model imports or REAPER mutations."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Job:
    def __init__(self, directory: Path, command: str, *, job_id: str | None = None,
                 project: str = "", **details):
        self.directory = Path(directory)
        self.id = job_id or uuid.uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.id):
            raise ValueError("Invalid job identifier")
        self.path = self.directory / "jobs" / (self.id + ".json")
        if self.path.exists():
            raise ValueError("Job identifier already exists")
        now = time.time()
        self.data = {"id": self.id, "cmd": command, "project": project,
                     "state": "running", "pid": os.getpid(), "started": now,
                     "time": now, "cancel_file": str(self.directory / "jobs" / (self.id + ".cancel")),
                     "cancellable": command == "import-audio", **details}
        atomic_json(self.path, self.data)

    def update(self, state: str | None = None, **details) -> dict:
        self.data.update(details)
        if state is not None:
            self.data["state"] = state
        self.data["time"] = time.time()
        if self.data["state"] in ("done", "error", "cancelled"):
            self.data["finished"] = self.data["time"]
        atomic_json(self.path, self.data)
        return dict(self.data)

    @property
    def cancelled(self) -> bool:
        return Path(self.data["cancel_file"]).exists()


def process_alive(pid) -> bool | None:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        return _windows_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (OSError, OverflowError):
        return None


def _windows_alive(pid: int) -> bool | None:
    # os.kill(pid, 0) terminates processes on Windows. Query a read-only handle instead.
    import ctypes
    from ctypes import wintypes
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    except (OSError, AttributeError, OverflowError):
        return None


class WorkerLease:
    """OS-owned single-worker lease, released even if the process crashes."""
    def __init__(self, directory: Path):
        self.path = Path(directory) / "worker.lock"
        self.file = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if not self.path.stat().st_size:
                    f.write(b"0")
                    f.flush()
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            f.close()
            return False
        self.file = f
        return True

    def release(self):
        if self.file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.file.close()
            self.file = None


# Context-local ownership allows nested server helpers without allowing another
# MCP request to join an unrelated task running in the same process.
from contextvars import ContextVar
from functools import wraps

lease_owned = ContextVar("reacue_lease_owned", default=False)


def managed_job(function):
    @wraps(function)
    async def run(*args, **kwargs):
        if lease_owned.get():
            return await function(*args, **kwargs)
        from .bridge import BRIDGE_DIR
        from . import show_lock
        if show_lock.locked(BRIDGE_DIR):
            return {"error": show_lock.message()}
        lease = WorkerLease(BRIDGE_DIR)
        if not lease.acquire():
            return {"error": "Un traitement est déjà en cours. Attends sa fin."}
        token = lease_owned.set(True)
        job = None
        try:
            job = Job(BRIDGE_DIR, function.__name__, source="mcp")
            result = await function(*args, **kwargs)
            job.update("error" if isinstance(result, dict) and result.get("error") else "done",
                       message=str(result.get("error", "")) if isinstance(result, dict) else "")
            return result
        except BaseException as exc:
            if job is not None:
                job.update("error", message=str(exc))
            raise
        finally:
            lease_owned.reset(token)
            lease.release()
    return run
