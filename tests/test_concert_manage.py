"""Real generated concert bundles, file operations and fault injection; no REAPER/models."""
import json
import os
from pathlib import Path
import shutil
import signal
import sys

import pytest

from reacue_mcp import concert as C, concert_manage as M

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import concert_demo as D


@pytest.fixture
def show(tmp_path, lang):
    lang("en")
    projects = D.write_demo(tmp_path / "songs")
    result = C.build_concert("Original show", [str(p) for p in projects], out_dir=tmp_path / "Concerts", publish=False)
    assert not result.warnings
    return result


def request(show, operation, **extra):
    return M.dispatch_request(dict(operation=operation, setlist=str(show.setlist), **extra))


def snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def side(path):
    return M._LuaData(Path(path).read_text(encoding="utf-8")).read()


def test_rename_moves_all_companions_and_retains_sources_and_edits(show):
    songs = snapshot(show.song_srcs[0].path.parent.parent)
    show.rpp.write_text(show.rpp.read_text() + "\n// hand edit remains\n")
    extra = show.rpp.with_suffix(".notes.json")
    extra.write_text(json.dumps({"project": str(show.rpp), "note": "manual"}))
    result = request(show, "rename", name="Renamed evening")
    dest = Path(result["projet"])
    assert dest.is_file() and "hand edit remains" in dest.read_text()
    assert not show.setlist.exists() and not show.rpp.exists() and not show.sidecar.exists()
    assert not list(dest.parent.glob("Original show.*"))
    assert not (dest.parent / "grandMA3" / "Original_show").exists()
    assert (dest.parent / "grandMA3" / "Renamed_evening").is_dir()
    meta = side(dest.with_suffix(".concert.lua"))
    assert meta["name"] == "Renamed evening" and meta["rpp"] == str(dest)
    assert meta["songs"][0]["start"] == show.songs[0]["start"]
    assert json.loads(dest.with_suffix(".notes.json").read_text())["project"] == str(dest)
    assert snapshot(show.song_srcs[0].path.parent.parent) == songs


def test_duplicate_preserves_original_and_live_profile(show):
    before = snapshot(show.rpp.parent)
    result = request(show, "duplicate", name="Second show")
    for rel, content in before.items():
        assert (show.rpp.parent / rel).read_bytes() == content
    copied = json.loads(Path(result["setlist"]).read_text())
    original = json.loads(show.setlist.read_text())
    assert copied["songs"] == original["songs"]
    assert copied["live"] == original["live"]
    assert json.loads(Path(result["projet"]).with_suffix(".prompteur.json").read_text())["concert"]["name"] == "Second show"


@pytest.mark.parametrize("operation", ["archive", "trash"])
def test_recoverable_move_and_restore_with_collision(show, operation):
    result = request(show, operation)
    saved = Path(result["setlist"])
    assert saved.is_file() and not show.setlist.exists()
    assert (saved.parent / "recovery.json").is_file()
    assert all(s.path.is_file() for s in show.song_srcs)
    show.rpp.write_text("another concert")
    with pytest.raises(FileExistsError):
        M.dispatch_request({"operation": "restore", "setlist": str(saved)})
    assert saved.exists() and show.rpp.read_text() == "another concert"
    show.rpp.unlink()
    restored = M.dispatch_request({"operation": "restore", "setlist": str(saved)})
    assert Path(restored["setlist"]) == show.setlist and show.rpp.is_file()
    assert not saved.exists()
    assert side(show.sidecar)["setlist"] == str(show.setlist)


def test_name_collision_and_copy_failure_leave_everything_untouched(show, monkeypatch):
    before = snapshot(show.rpp.parent)
    (show.rpp.parent / "Taken.RPP").write_text("existing")
    with pytest.raises(FileExistsError):
        request(show, "rename", name="Taken")
    assert show.rpp.exists()
    (show.rpp.parent / "Taken.RPP").unlink()
    monkeypatch.setattr(M, "_copy", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        request(show, "rename", name="New")
    assert snapshot(show.rpp.parent) == before


def test_commit_failure_restores_every_original(show, monkeypatch):
    before = snapshot(show.rpp.parent)
    original = M._install
    count = 0
    def fail_mid_commit(src, dst):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("injected commit failure")
        return original(src, dst)
    monkeypatch.setattr(M, "_install", fail_mid_commit)
    with pytest.raises(OSError, match="injected"):
        request(show, "rename", name="New")
    assert snapshot(show.rpp.parent) == before


def test_cancellation_during_destination_install_keeps_original(show, monkeypatch):
    before = snapshot(show.rpp.parent)
    handler = signal.getsignal(signal.SIGTERM)
    def cancel(source, destination):
        assert show.setlist.is_file() and show.rpp.is_file()
        signal.raise_signal(signal.SIGTERM)
    monkeypatch.setattr(M, "_install", cancel)
    with pytest.raises(InterruptedError, match="cancelled"):
        request(show, "rename", name="Cancelled")
    assert snapshot(show.rpp.parent) == before
    assert signal.getsignal(signal.SIGTERM) == handler


def test_portable_reports_external_plugins_in_visible_result(show, tmp_path):
    song = show.song_srcs[0].path
    original = song.read_text()
    song.write_text(original.replace("<TRACK", '<VST "External instrument"\n  opaque_plugin_state\n>\n<TRACK', 1))
    result = request(show, "portable", destination=str(tmp_path / "With plugins"))
    assert result["warnings"] and "external samples" in result["message"]
    assert Path(result["setlist"]).is_file()


def test_portable_survives_source_removal_and_destination_move(show, tmp_path, monkeypatch):
    before = snapshot(show.rpp.parent)
    destination = tmp_path / "Portable"
    result = request(show, "portable", destination=str(destination))
    assert snapshot(show.rpp.parent) == before
    assert (destination / "Original show.web" / "studio.html").exists()
    assert list((destination / "Original show.web").glob("reacue_gma3_*"))
    moved = tmp_path / "USB" / "On stage"
    moved.parent.mkdir()
    shutil.move(destination, moved)
    shutil.rmtree(show.song_srcs[0].path.parent.parent)
    shutil.rmtree(show.rpp.parent)
    monkeypatch.chdir(tmp_path)
    for rpp in moved.rglob("*.RPP"):
        for line in rpp.read_text().splitlines():
            if line.strip().startswith("FILE "):
                value = C.tokens(line.strip())[1]
                assert not M._absolute(value)
                assert (rpp.parent / value).is_file()
    setlist = moved / Path(result["setlist"]).name
    data = json.loads(setlist.read_text())
    assert all(not M._absolute(e["project"]) and (moved / e["project"]).is_file() for e in data["songs"])
    meta = side(moved / "Original show.concert.lua")
    assert meta["setlist"] == "Original show.setlist.json"
    assert all((moved / s["project"]).is_file() for s in meta["songs"])
    assert C._reload(setlist).songs
    assert C.build_from_setlist(setlist, publish=False).rpp.exists()


def test_portable_missing_media_or_existing_destination_is_all_or_nothing(show, tmp_path):
    target = tmp_path / "portable"
    target.mkdir()
    with pytest.raises(FileExistsError):
        request(show, "portable", destination=str(target))
    target.rmdir()
    media = next(show.song_srcs[0].path.parent.glob("*.wav"))
    media.unlink()
    with pytest.raises(FileNotFoundError, match="Missing media"):
        request(show, "portable", destination=str(target))
    assert not target.exists() and show.rpp.is_file()
    assert not list(tmp_path.glob(".reacue-stage-*"))


def test_lua_sidecar_parser_never_executes_expressions(tmp_path):
    with pytest.raises(ValueError):
        M._LuaData('return os.execute("touch anything")').read()
    from reacue_mcp.bridge import to_lua
    sample = {"name": 'é"\n\\', "songs": [{"start": 1.25, "project": "relative/song.RPP"}]}
    assert M._LuaData("return " + to_lua(sample)).read() == sample


def test_management_refuses_concert_open_in_other_tab_and_global_edit_lock(tmp_path):
    from lupa import lua54
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    L.execute('''
      called, denied = 0, 0
      reaper = {GetOS=function() return "OSX64" end, GetPlayState=function() return 0 end,
        EnumProjects=function(i) if i == 0 then return 10, "/songs/Song.RPP" elseif i == 1 then return 20, "/shows/Show.RPP" end end}
      local R = {shq=function(s) return "'" .. s .. "'" end}
      ctx = {R=R, L={}, U={}, SEP="/", T=function(k) return k end,
        tr=function(d,k) return d.en[k] end, require_edit=function() return true end,
        show_result=function() denied=denied+1 end, start_cli=function() called=called+1; return true end}
    ''')
    tab = L.eval(f'dofile([[{Path(__file__).resolve().parents[1] / "reaper/ReaCue_tab_concert.lua"}]])')(L.globals().ctx)
    assert not tab.manage("rename", "/shows/Show.setlist.json", "New")
    assert L.globals().called == 0 and L.globals().denied == 1
    L.execute('ctx.require_edit=function() return false end')
    assert not tab.manage("duplicate", "/shows/Closed.setlist.json", "New")
    assert L.globals().called == 0
    L.execute('ctx.require_edit=function() return true end')
    assert tab.manage("duplicate", "/shows/Closed.setlist.json", "New")
    assert L.globals().called == 1
