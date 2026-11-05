"""Resume the actual Lua stems worker from the 'Do everything' flow, without REAPER."""
import json
import time
from pathlib import Path

import pytest

from test_stems import LUA_DIR, lua


@pytest.fixture
def recovery(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    install = tmp_path / "install"
    python = install / ".venv-demucs/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / "ReaCueMCP/reacue_install.txt").write_text(str(install))
    source = tmp_path / "My Song.mp3"
    source.write_bytes(b"audio")
    runtime, stems, runner = lua(tmp_path)
    g = runtime.globals()
    g["items"][1].take.file = str(source)
    g.S, g.R, g.INSTALL = stems, runner, str(install)
    runtime.execute('''
      clock = 100
      launches = 0
      reaper.time_precise = function() return clock end
      reaper.ExecProcess = function() return "0\\n" end
      os.execute = function() launches = launches + 1; return true end
      ctx = {
        L = {}, R = R, proj_file = "/song.RPP", proj_key = "song",
        tr = function(t, k) return t.en[k] end,
        refresh = function() end,
        tabs = {song = {autosave = function() end}},
        commands = {}
      }
      function ctx.start_stems(cb)
        if ctx.job then ctx.last_error = "busy"; return false end
        local job, err = S.start(R, INSTALL)
        if not job then ctx.last_error = err; return false end
        if job.ready then
          local message, err = S.finish(R, job)
          cb(message and "done" or "error", message or err)
          return true
        end
        ctx.job = {kind = "stems", sj = job, on_done = cb}
        return true
      end
      function ctx.start_cli(cmd, label, cb)
        ctx.commands[#ctx.commands + 1] = cmd
        ctx.job = {kind = "cli", on_done = cb}
        return true
      end
      function poll_stems()
        local job = ctx.job
        local state, value = S.poll(R, job.sj)
        if state == "running" then return state end
        ctx.job = nil
        if state == "ready" then
          local message, err = S.finish(R, job.sj)
          job.on_done(message and "done" or "error", message or err)
        else job.on_done("error", value) end
        return state
      end
    ''')
    flow = runtime.eval(f"dofile([[{LUA_DIR / 'ReaCue_flow.lua'}]])(ctx)")
    paths = stems.paths(str(source), "htdemucs")
    Path(paths.outroot).mkdir()
    return runtime, flow, paths, source


def status(paths, source, state, model="htdemucs"):
    Path(paths.status).write_text(json.dumps({
        "state": state, "pid": 4242, "time": time.time(),
        "input": str(source), "model": model,
    }))


def completed_files(paths):
    for stem in paths.stems.values():
        path = Path(stem.file)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"RIFF")


def assert_preparing_once(g, flow):
    assert g.launches == 0
    assert flow.run.steps[1].status == "done"
    assert flow.run.steps[2].status == "running"
    assert list(g.ctx.commands.values()) == ["prepare"]
    calls = list(g.calls.values())
    assert len([call for call in calls if call.startswith("src|")]) == 4
    assert len([call for call in calls if call.startswith("delete|")]) == 1


def test_reopened_flow_follows_existing_separation_then_imports_once(recovery):
    runtime, flow, paths, source = recovery
    g = runtime.globals()
    status(paths, source, "running")
    Path(paths.log).write_text(" 37%| progress")
    assert flow.start(runtime.table_from({"single_mix": True}))
    assert flow.run.steps[1].status == "running"
    assert not flow.run.finished and g.launches == 0
    assert g.poll_stems() == "running"
    assert len(g.calls) == 0
    completed_files(paths)
    status(paths, source, "done")
    assert g.poll_stems() == "ready"
    assert_preparing_once(g, flow)


def test_resume_failed_flow_reuses_completed_stems(recovery):
    runtime, flow, paths, source = recovery
    g = runtime.globals()
    status(paths, source, "running", model="htdemucs_6s")
    flow.start(runtime.table_from({"single_mix": True}))
    assert flow.run.finished and not flow.run.ok
    assert flow.run.steps[1].status == "failed"
    assert g.launches == 0
    completed_files(paths)
    status(paths, source, "done")
    assert flow.resume()
    assert_preparing_once(g, flow)


def test_recovered_job_with_removed_item_does_not_prepare_or_import(recovery):
    runtime, flow, paths, source = recovery
    g = runtime.globals()
    status(paths, source, "running")
    assert flow.start(runtime.table_from({"single_mix": True}))
    assert flow.run.steps[1].status == "running"
    completed_files(paths)
    status(paths, source, "done")
    runtime.execute("reaper.ValidatePtr2 = function() return false end")
    assert g.poll_stems() == "ready"
    assert flow.run.finished and not flow.run.ok
    assert flow.run.steps[1].status == "failed"
    assert len(g.ctx.commands) == 0 and len(g.calls) == 0
    assert g.launches == 0
