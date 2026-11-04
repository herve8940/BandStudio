"""Publication success/failure handoff, without REAPER or the drawing simulator."""
from pathlib import Path
import pytest

LuaRuntime = pytest.importorskip("lupa.lua54").LuaRuntime


@pytest.fixture
def flow():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      reaper = {time_precise=function() return 10 end}
      publication = nil
      commands = {}
      saves = 0
      callback = nil
      ctx = {
        L={}, R={tr=function(k) return k end,
          status=function() return "done", "ok", "prepare", nil, publication end},
        tr=function(t, k) return t.en[k] end,
        proj_file="/song.RPP", proj_key="song",
        tabs={song={autosave=function() saves=saves+1 end}},
        start_cli=function(cmd, label, cb)
          commands[#commands+1]=cmd
          callback=cb
          return true
        end
      }
    ''')
    path = Path(__file__).resolve().parents[1] / "reaper" / "ReaCue_flow.lua"
    f = lua.eval(f"dofile([[{path}]])(ctx)")
    return lua, f


@pytest.mark.parametrize("published", [True, False, None])
def test_flow_uses_explicit_publication_success_or_retries(flow, published):
    lua, f = flow
    g = lua.globals()
    g.publication = published
    assert f.start(lua.table_from({"single_mix": False}))
    assert list(g.commands.values()) == ["prepare"]
    g.callback("done", "prepared")
    if published is True:
        assert list(g.commands.values()) == ["prepare"]
        assert f.run.steps[3].status == "skipped"
    else:
        assert list(g.commands.values()) == ["prepare", "publish"]
        g.callback("done", "published")
    assert g.saves == 1 and f.run.finished and f.run.ok


def test_flow_failed_publication_resume_does_not_reprepare(flow):
    lua, f = flow
    g = lua.globals()
    f.start(lua.table_from({"single_mix": False}))
    g.callback("done", "prepared")
    g.callback("error", "publish failed")
    assert not f.run.ok and g.saves == 0
    assert f.resume()
    assert list(g.commands.values()) == ["prepare", "publish", "publish"]
    g.callback("done", "published")
    assert g.saves == 1 and f.run.ok


def test_flow_cancel_after_prepare_does_not_save(flow):
    lua, f = flow
    g = lua.globals()
    g.publication = True
    f.start(lua.table_from({"single_mix": False}))
    f.cancel()
    g.callback("done", "prepared")
    assert g.saves == 0 and not f.run.ok and f.run.finished
    assert list(g.commands.values()) == ["prepare"]
