"""Independent durable-job/lock/recovery tests. No audio, network or live REAPER."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from reacue_mcp import jobs as J, show_lock, cli, import_audio
from reacue_mcp.bridge import Bridge, BridgeError
from test_lua import load_run

ROOT = Path(__file__).resolve().parents[1]


def test_job_records_result_project_and_terminal_state(tmp_path):
    job = J.Job(tmp_path, "import-audio", job_id="example", project="/songs/Song.RPP", launch_command="import-audio --job example.json")
    assert not job.cancelled
    Path(job.data["cancel_file"]).touch()
    assert job.cancelled
    job.update("done", import_audio={"operation": "download", "file": "/audio.ogg"})
    record = json.loads(job.path.read_text())
    assert record["state"] == "done" and record["finished"] >= record["started"]
    assert record["project"] == "/songs/Song.RPP" and record["import_audio"]["file"] == "/audio.ogg"
    with pytest.raises(ValueError, match="already exists"):
        J.Job(tmp_path, "prepare", job_id="example")
    assert json.loads(job.path.read_text()) == record
    assert not list(tmp_path.rglob("*.tmp"))


def test_worker_lease_contends_and_releases(tmp_path):
    first, second = J.WorkerLease(tmp_path), J.WorkerLease(tmp_path)
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()
    assert second.acquire()
    second.release()
    second.release()


def test_worker_crash_releases_os_lease(tmp_path):
    code = "from reacue_mcp.jobs import WorkerLease; import os,sys; lease=WorkerLease(sys.argv[1]); assert lease.acquire(); os._exit(0)"
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, timeout=10, capture_output=True)
    assert result.returncode == 0, result.stderr
    lease = J.WorkerLease(tmp_path)
    assert lease.acquire()
    lease.release()


@pytest.mark.parametrize("pid", [None, True, False, 0, -1, "123", 1.5])
def test_invalid_pid_never_probed(monkeypatch, pid):
    monkeypatch.setattr(J, "os", SimpleNamespace(name="posix", kill=lambda *a: pytest.fail("invalid PID probed")))
    assert J.process_alive(pid) is None


def test_windows_process_check_never_sends_signal(monkeypatch):
    monkeypatch.setattr(J, "os", SimpleNamespace(name="nt", kill=lambda *a: pytest.fail("Windows kill called")))
    monkeypatch.setattr(J, "_windows_alive", lambda pid: pid == 123)
    assert J.process_alive(123) is True
    assert J.process_alive(456) is False


@pytest.mark.parametrize("handle,exit_code,error,query_ok,expected", [
    (7, 259, 0, True, True), (7, 0, 0, True, False), (0, 0, 87, False, False),
    (0, 0, 5, False, None), (7, 0, 0, False, None),
])
def test_windows_query_uses_readonly_handle_and_closes_it(monkeypatch, handle, exit_code, error, query_ok, expected):
    calls = []
    class Function:
        def __init__(self, fn): self.fn = fn
        def __call__(self, *args): return self.fn(*args)
    def opened(access, inherit, pid):
        calls.append(("open", access, inherit, pid))
        return handle
    def query(h, code):
        code._obj.value = exit_code
        return query_ok
    kernel = SimpleNamespace(OpenProcess=Function(opened), GetExitCodeProcess=Function(query),
        CloseHandle=Function(lambda h: calls.append(("close", h))))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    assert J._windows_alive(123) is expected
    assert calls[0] == ("open", 0x1000, False, 123)
    assert (("close", handle) in calls) == bool(handle)


@pytest.mark.parametrize("contents,locked", [(None, False), ('{"locked":false}', False),
    ('{"locked":true}', True), ('{}', True), ('[]', True), ('broken', True)])
def test_show_lock_is_conservative(tmp_path, contents, locked):
    if contents is not None:
        (tmp_path / "show_lock.json").write_text(contents)
    assert show_lock.locked(tmp_path) is locked


@pytest.mark.parametrize("command", ["apply_plan", "import_file", "timecode_tracks"])
def test_bridge_mutations_blocked_before_request(tmp_path, command):
    (tmp_path / "show_lock.json").write_text('{"locked":true}')
    bridge = Bridge(tmp_path)
    with pytest.raises(RuntimeError, match="[Vv]errouill|[Ll]ock"):
        asyncio.run(bridge.call(command))
    assert not bridge.req.exists()


def test_bridge_read_operation_is_not_blocked_by_show_lock(tmp_path):
    (tmp_path / "show_lock.json").write_text('{"locked":true}')
    with pytest.raises(BridgeError):  # missing heartbeat; this is not the lock's RuntimeError
        asyncio.run(Bridge(tmp_path).call("ping"))


def _cli_dir(monkeypatch, directory):
    monkeypatch.setattr(cli, "_dirs", lambda: (directory, directory / "cli_status.json", directory / "cli.log"))


def test_cli_lock_prevents_dispatch_and_finishes_ledger(tmp_path, monkeypatch):
    _cli_dir(monkeypatch, tmp_path)
    (tmp_path / "show_lock.json").write_text('{"locked":true}')
    monkeypatch.setattr(import_audio, "dispatch_request", lambda *a, **k: pytest.fail("locked import ran"))
    assert cli.main(["import-audio", "--job-id", "locked", "--request", '{}']) == 1
    record = json.loads((tmp_path / "jobs/locked.json").read_text())
    assert record["state"] == "error"
    lease = J.WorkerLease(tmp_path)
    assert lease.acquire()
    lease.release()


def test_cli_busy_does_not_replace_another_jobs_status(tmp_path, monkeypatch):
    _cli_dir(monkeypatch, tmp_path)
    status = tmp_path / "cli_status.json"
    status.write_text('{"id":"other","state":"running"}')
    lease = J.WorkerLease(tmp_path)
    assert lease.acquire()
    monkeypatch.setattr(import_audio, "dispatch_request", lambda *a, **k: pytest.fail("second import ran"))
    try:
        assert cli.main(["import-audio", "--job-id", "blocked", "--request", '{}']) == 1
    finally:
        lease.release()
    assert json.loads(status.read_text())["id"] == "other"
    assert json.loads((tmp_path / "jobs/blocked.json").read_text())["state"] == "error"


def test_cli_result_terminal_identity_and_expected_project_restored(tmp_path, monkeypatch):
    _cli_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("REACUE_EXPECTED_PROJECT", "/before.RPP")
    def downloaded(data, progress):
        assert os.environ["REACUE_EXPECTED_PROJECT"] == "/source.RPP"
        assert str(data["cancel_file"]).endswith("/jobs/import1.cancel")
        progress("downloaded")
        return {"operation": "download", "file": "/cache/audio.ogg"}
    monkeypatch.setattr(import_audio, "dispatch_request", downloaded)
    assert cli.main(["import-audio", "--job-id", "import1", "--origin-project", "/source.RPP", "--request", '{}']) == 0
    record = json.loads((tmp_path / "jobs/import1.json").read_text())
    assert record["state"] == "done" and record["project"] == "/source.RPP"
    assert record["import_audio"]["file"] == "/cache/audio.ogg"
    assert os.environ["REACUE_EXPECTED_PROJECT"] == "/before.RPP"


def test_cli_cancellation_terminal_is_not_success(tmp_path, monkeypatch):
    _cli_dir(monkeypatch, tmp_path)
    def cancelled(data, progress):
        Path(data["cancel_file"]).touch()
        raise import_audio.ImportCancelled("cancelled")
    monkeypatch.setattr(import_audio, "dispatch_request", cancelled)
    assert cli.main(["import-audio", "--job-id", "cancel", "--request", '{}']) == 130
    assert json.loads((tmp_path / "jobs/cancel.json").read_text())["state"] == "cancelled"


def test_cli_concert_extras_waits_for_parent_lease_and_records_completion(tmp_path, monkeypatch):
    from reacue_mcp import concert
    _cli_dir(monkeypatch, tmp_path)
    events = []
    real_lease = J.WorkerLease

    class HandoffLease(real_lease):
        attempts = 0

        def acquire(self):
            self.attempts += 1
            events.append(("acquire", self.attempts))
            return False if self.attempts == 1 else super().acquire()

        def release(self):
            events.append(("release",))
            super().release()

    monkeypatch.setattr(J, "WorkerLease", HandoffLease)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    setlist = str(tmp_path / "Concert.setlist.json")

    def extras(path):
        assert path == setlist
        assert J.lease_owned.get() is True
        record = json.loads((tmp_path / "jobs/extras.json").read_text())
        assert record["state"] == "running" and record["cmd"] == "concert-extras"
        events.append(("extras",))

    monkeypatch.setattr(concert, "extras_from_setlist", extras)
    assert cli.main(["concert-extras", "--setlist", setlist, "--job-id", "extras",
                     "--origin-project", "/songs/Concert.RPP"]) == 0
    record = json.loads((tmp_path / "jobs/extras.json").read_text())
    assert record["state"] == "done" and record["project"] == "/songs/Concert.RPP"
    assert record["finished"] >= record["started"]
    assert events == [("acquire", 1), ("sleep", 0.1), ("acquire", 2), ("extras",), ("release",)]
    assert J.lease_owned.get() is False
    following = real_lease(tmp_path)
    assert following.acquire()
    following.release()


def test_mcp_tools_return_lock_error_without_calling_bridge(tmp_path, monkeypatch):
    from reacue_mcp import server
    monkeypatch.setattr(show_lock, "locked", lambda *a: True)
    async def forbidden(*a, **k): pytest.fail("bridge called while locked")
    monkeypatch.setattr(server.bridge, "call", forbidden)
    for coroutine in (server.prepare_song(), server.new_song(["/fake.wav"]), server.build_concert("Show", ["Song"])):
        result = asyncio.run(coroutine)
        assert result.get("error")


def test_lua_runner_resumes_matching_job_without_launch(tmp_path):
    directory = tmp_path / "ReaCueMCP"
    directory.mkdir()
    install = tmp_path / "install"
    py = install / ".venv/bin/python"
    py.parent.mkdir(parents=True)
    py.touch()
    (directory / "reacue_install.txt").write_text(str(install))
    (directory / "cli_status.json").write_text(json.dumps({"id": "old", "cmd": "prepare", "launch_command": "prepare",
        "project": "/tmp/test.rpp", "state": "running", "pid": 123, "time": 1}))
    lua, runner = load_run(tmp_path)
    lua.execute('reaper.ExecProcess=function()return "0\\n" end; os.execute=function()error("duplicate launch")end')
    ok, error, record = runner.start("prepare", str(ROOT / "reaper"), False)
    assert ok and error is None and record.id == "old"
    result = runner.start("publish", str(ROOT / "reaper"), False)
    assert result[0] is False


def test_lua_ledger_status_is_specific_to_job(tmp_path):
    directory = tmp_path / "ReaCueMCP"
    (directory / "jobs").mkdir(parents=True)
    (directory / "cli_status.json").write_text('{"id":"new","cmd":"prepare","state":"running"}')
    (directory / "jobs/old.json").write_text('{"id":"old","cmd":"prepare","state":"done","prompter_published":true}')
    _, runner = load_run(tmp_path)
    status = runner.status("old")
    assert status[0] == "done" and status[4] is True and status[5].id == "old"


def _restored_flow(tmp_path, steps, record, song_state=None):
    directory = tmp_path / "ReaCueMCP"
    (directory / "jobs").mkdir(parents=True)
    project = "/songs/Song.RPP"
    digest = 2166136261
    for byte in project.encode():
        digest = ((digest ^ byte) * 16777619) & 0xffffffff
    checkpoint = {"project": project, "steps": steps, "i": 1, "finished": False, "ok": False}
    (directory / f"flow-{digest:08x}.json").write_text(json.dumps(checkpoint))
    (directory / "jobs/worker.json").write_text(json.dumps({"id": "worker", "project": project, **record}))
    lua, runner = load_run(tmp_path)
    lua.globals().R = runner
    lua.execute('''
      saves=0; starts=0
      ctx={R=R,L={},SEP="/",proj_file="/songs/Song.RPP",proj_key="current-key",
        tr=function(d,k)return d.en[k]end, lang=function()return "en"end,
        tabs={song={autosave=function()saves=saves+1 end}},
        start_cli=function() starts=starts+1; return true end,
        start_stems=function() starts=starts+1; return true end}
    ''')
    if song_state is not None:
        lua.globals().SONG_STATE = lua.table_from(song_state)
        lua.execute("ctx.tabs.song.state=function()return SONG_STATE end")
    flow = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_flow.lua"}]])(ctx)')
    assert flow.restore()
    return lua, flow


def test_flow_completed_stems_worker_still_requires_reaper_import(tmp_path):
    steps = [{"id": name, "status": "running" if name == "stems" else "pending"}
             for name in ("stems", "prepare", "publish", "save")]
    steps[0]["job_id"] = "worker"
    _, flow = _restored_flow(tmp_path, steps, {"cmd": "stems", "state": "done"})
    assert flow.run.i == 1  # downloading/separating is complete, importing is not
    assert flow.run.steps[1].status != "done"


def test_flow_restored_prepare_success_does_not_republish(tmp_path):
    steps = [{"id": "stems", "status": "done"}, {"id": "prepare", "status": "running", "job_id": "worker"},
             {"id": "publish", "status": "pending"}, {"id": "save", "status": "pending"}]
    lua, flow = _restored_flow(tmp_path, steps, {"cmd": "prepare", "state": "done", "prompter_published": True})
    assert flow.run.steps[3].status == "skipped"
    assert flow.run.i == 4
    assert flow.resume()
    assert lua.globals().starts == 0 and lua.globals().saves == 1


def test_managed_mcp_rejects_other_context_but_allows_nested_helpers(tmp_path, monkeypatch):
    import reacue_mcp.bridge as bridge_module
    monkeypatch.setattr(bridge_module, "BRIDGE_DIR", tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    called = []
    @J.managed_job
    async def inner():
        called.append("inner")
        return {"ok": True}
    @J.managed_job
    async def outer():
        called.append("outer")
        entered.set()
        await release.wait()
        return await inner()
    async def scenario():
        active = asyncio.create_task(outer())
        await entered.wait()
        refused = await inner()
        assert refused.get("error")
        assert called == ["outer"]
        release.set()
        assert await active == {"ok": True}
    asyncio.run(scenario())
    assert called == ["outer", "inner"]
    records = [json.loads(p.read_text()) for p in (tmp_path / "jobs").glob("*.json")]
    assert len(records) == 1 and records[0]["state"] == "done" and records[0]["cmd"] == "outer"
    assert J.lease_owned.get() is False


def test_managed_mcp_failure_releases_lease_and_keeps_error(tmp_path, monkeypatch):
    import reacue_mcp.bridge as bridge_module
    monkeypatch.setattr(bridge_module, "BRIDGE_DIR", tmp_path)
    @J.managed_job
    async def fail():
        raise RuntimeError("expected failure")
    with pytest.raises(RuntimeError, match="expected failure"):
        asyncio.run(fail())
    record = json.loads(next((tmp_path / "jobs").glob("*.json")).read_text())
    assert record["state"] == "error" and record["message"] == "expected failure"
    lease = J.WorkerLease(tmp_path)
    assert lease.acquire()
    lease.release()


def test_cli_lease_context_allows_nested_server_helper(tmp_path, monkeypatch):
    _cli_dir(monkeypatch, tmp_path)
    @J.managed_job
    async def helper():
        return {"operation": "inspect", "title": "Demo"}
    def inspect(data, progress):
        assert J.lease_owned.get() is True
        return asyncio.run(helper())
    monkeypatch.setattr(import_audio, "dispatch_request", inspect)
    assert cli.main(["import-audio", "--job-id", "nested", "--request", '{}']) == 0
    assert J.lease_owned.get() is False
    assert len(list((tmp_path / "jobs").glob("*.json"))) == 1


@pytest.mark.parametrize("single_mix,expected_step", [(True, 1), (False, 2)])
def test_restored_flow_reconciles_unsaved_reaper_changes(tmp_path, single_mix, expected_step):
    steps = [{"id": "stems", "status": "done"}, {"id": "prepare", "status": "running", "job_id": "worker"},
             {"id": "publish", "status": "pending"}, {"id": "save", "status": "pending"}]
    _, flow = _restored_flow(tmp_path, steps,
        {"cmd": "prepare", "state": "done", "prompter_published": True},
        {"single_mix": single_mix, "prepared": False})
    assert flow.run.i == expected_step
    assert flow.run.steps[2].status == "pending"
    assert flow.run.steps[3].status == "pending"


def test_stems_lease_loser_does_not_replace_active_workers_status(tmp_path, monkeypatch):
    import reacue_stems
    directory = tmp_path / "resources/ReaCueMCP"
    directory.mkdir(parents=True)
    output = tmp_path / "song-stems"
    output.mkdir()
    status = output / "demucs_status.json"
    original = {"state": "running", "pid": 4242, "model": "htdemucs", "id": "active"}
    status.write_text(json.dumps(original))
    lease = J.WorkerLease(directory)
    assert lease.acquire()
    monkeypatch.setattr(reacue_stems, "separate", lambda *a: pytest.fail("second Demucs worker ran"))
    try:
        assert reacue_stems.main(["separate", "--input", str(tmp_path / "song.wav"), "--out", str(output),
            "--resource-dir", str(directory.parent), "--job-id", "loser"]) == 1
    finally:
        lease.release()
    assert json.loads(status.read_text()) == original
    assert json.loads((directory / "jobs/loser.json").read_text())["state"] == "error"


@pytest.mark.parametrize("contents", ['{"locked":false} trailing garbage', '{"note":"locked false"}', '[{"locked":false}]'])
@pytest.mark.parametrize("command", ["import_file", "apply_plan", "timecode_tracks"])
def test_native_bridge_fails_closed_for_malformed_or_nonobject_lock(tmp_path, contents, command):
    from reacue_mcp.bridge import to_lua
    from test_lua import runtime, LUA_DIR
    directory = tmp_path / "ReaCueMCP"
    directory.mkdir()
    (directory / "show_lock.json").write_text(contents)
    (directory / "request.lua").write_text(to_lua({"id": "locked", "cmd": command, "args": {}}))
    lua = runtime(tmp_path)
    lua.execute(f'dofile([[{LUA_DIR / "ReaCue_Bridge.lua"}]])')
    result = json.loads((directory / "response.json").read_text())
    assert result["id"] == "locked" and not result["ok"]
    assert "verrouillé" in result["error"]


def test_native_bridge_valid_unlocked_lock_reaches_handler(tmp_path):
    from reacue_mcp.bridge import to_lua
    from test_lua import runtime, LUA_DIR
    directory = tmp_path / "ReaCueMCP"
    directory.mkdir()
    (directory / "show_lock.json").write_text('{"locked":false}')
    (directory / "request.lua").write_text(to_lua({"id": "allowed", "cmd": "apply_plan", "args": {}}))
    lua = runtime(tmp_path)
    lua.execute(f'dofile([[{LUA_DIR / "ReaCue_Bridge.lua"}]])')
    result = json.loads((directory / "response.json").read_text())
    assert result["id"] == "allowed"
    assert "verrouillé" not in result.get("error", "")
