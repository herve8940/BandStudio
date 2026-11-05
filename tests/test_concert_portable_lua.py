"""Portable concert publication through the real Lua loader; REAPER APIs are mocked."""
import json
from pathlib import Path
import shutil

import pytest

pytest.importorskip("lupa")
from lupa import lua54

from reacue_mcp import concert as C, concert_manage as M
from reacue_mcp.bridge import to_lua
from test_concert_manage import D

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def portable(tmp_path):
    song = D.write_song(tmp_path / "source", "Song", 120, [("Intro", 4, (80, 100, 120))], ["Vocals", "Drums"])
    show = C.build_concert("Original", [str(song)], out_dir=tmp_path / "Concerts", publish=False)
    package = tmp_path / "Package"
    result = M.dispatch_request({"operation": "portable", "setlist": str(show.setlist), "destination": str(package)})
    M.dispatch_request({"operation": "rename", "setlist": result["setlist"], "name": "Sur scène"})
    moved = tmp_path / "USB" / "Concert prêt"
    moved.parent.mkdir()
    shutil.move(package, moved)
    shutil.rmtree(song.parent)
    shutil.rmtree(show.rpp.parent)
    return moved


def runtime(tmp_path):
    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().RES = str(tmp_path / "REAPER")
    lua.globals().MKDIR = lambda p: Path(p).mkdir(parents=True, exist_ok=True)
    lua.execute('''
      reaper = {GetResourcePath=function() return RES end, GetOS=function() return "OSX64" end,
        GetExtState=function() return "" end,
        RecursiveCreateDirectory=function(p) MKDIR(p); return 1 end}
    ''')
    lib = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_concert_lib.lua"}]])')
    return lua, lib


def test_load_and_publish_renamed_package_after_usb_move(portable, tmp_path):
    lua, lib = runtime(tmp_path)
    side = portable / "Sur scène.concert.lua"
    concert = lib.load_file(str(side))
    assert concert is not None
    for key, suffix in (("rpp", ".RPP"), ("setlist", ".setlist.json"), ("prompter", ".prompteur.json"), ("package_web", ".web")):
        assert Path(concert[key]) == portable / ("Sur scène" + suffix)
        assert Path(concert[key]).exists()
    assert Path(concert.songs[1].project).is_file()
    fingerprint = C._fingerprint(concert.songs[1].project)
    assert concert.songs[1].project_sum == fingerprint["project_sum"]
    assert concert.songs[1].project_size == fingerprint["project_size"]
    assert lib.publish_prompter(concert) is True
    www = Path(lua.globals().RES) / "reaper_www_root"
    expected = Path(concert.prompter).read_bytes()
    assert (www / "reacue_song.json").read_bytes() == expected
    data = json.loads(expected)
    files = data["lighting"]["files"]
    assert files
    for entry in files:
        assert (www / entry["url"]).read_bytes() == (Path(concert.package_web) / entry["url"]).read_bytes()
    before = (www / "reacue_song.json").stat().st_mtime_ns
    assert lib.publish_prompter(concert) is True
    assert (www / "reacue_song.json").stat().st_mtime_ns == before


@pytest.mark.parametrize("bad_asset", ["missing", "missing_later", "../outside.xml"])
def test_incomplete_or_unsafe_lighting_keeps_previous_publication(portable, tmp_path, bad_asset):
    lua, lib = runtime(tmp_path)
    concert = lib.load_file(str(portable / "Sur scène.concert.lua"))
    www = Path(lua.globals().RES) / "reaper_www_root"
    www.mkdir(parents=True)
    published = www / "reacue_song.json"
    published.write_text('{"previous": true}')
    prompter = Path(concert.prompter)
    data = json.loads(prompter.read_text())
    first_asset = www / data["lighting"]["files"][0]["url"]
    first_asset.write_bytes(b"previous lighting asset")
    if bad_asset in ("missing", "missing_later"):
        index = 1 if bad_asset == "missing_later" else 0
        (Path(concert.package_web) / data["lighting"]["files"][index]["url"]).unlink()
    else:
        data["lighting"]["files"][0]["url"] = bad_asset
        prompter.write_text(json.dumps(data))
    assert lib.publish_prompter(concert) is False
    assert json.loads(published.read_text()) == {"previous": True}
    assert first_asset.read_bytes() == b"previous lighting asset"
    assert not (www.parent / "outside.xml").exists()


def test_loader_preserves_absolute_posix_windows_and_unc_paths(tmp_path):
    _, lib = runtime(tmp_path)
    path = tmp_path / "Show.concert.lua"
    data = {"name": "Show", "rpp": r"C:\Shows\Show.RPP", "setlist": r"\\server\shows\Show.setlist.json",
            "prompter": "/opt/shows/Show.prompteur.json", "songs": [{"project": "songs/Song.RPP", "start": 0}]}
    path.write_text("return " + to_lua(data))
    loaded = lib.load_file(str(path))
    for key in ("rpp", "setlist", "prompter"):
        assert loaded[key] == data[key]
    assert Path(loaded.songs[1].project) == tmp_path / "songs" / "Song.RPP"


@pytest.mark.parametrize("worker", ["status", "history"])
def test_management_and_save_block_durable_worker_after_window_reopens(tmp_path, worker):
    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      started, denied = 0, 0
      reaper = {GetPlayState=function() return 0 end}
      ctx = {R={}, U={}, L={}, SEP="/", T=function(k) return k end,
        tr=function(d,k) return d.en[k] end, require_edit=function() return true end,
        show_result=function() denied=denied+1 end, start_cli=function() started=started+1; return true end}
    ''')
    if worker == "status":
        lua.execute('ctx.R.active_job=function() return {state="running",pid=123} end')
    else:
        lua.execute('ctx.R.active_job=function() return nil end; ctx.jobs={busy=function() return true end}')
    tab = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_tab_concert.lua"}]])')(lua.globals().ctx)
    assert not tab.manage("rename", "/shows/Show.setlist.json", "New")
    assert tab.save() is None
    assert lua.globals().started == 0 and lua.globals().denied == 2


def test_recovery_list_and_restore_refuse_original_project_open_in_other_tab(tmp_path):
    lua, lib = runtime(tmp_path)
    concert_dir = tmp_path / "Concerts"
    archive = concert_dir / ".reacue-archive" / "20261105-first"
    invalid = concert_dir / ".reacue-trash" / "20261105-invalid"
    archive.mkdir(parents=True)
    invalid.mkdir(parents=True)
    (archive / "recovery.json").write_text(json.dumps({"version": 1, "name": "Show", "setlist": "Show.setlist.json",
                                                      "original_directory": str(concert_dir)}))
    (invalid / "recovery.json").write_text(json.dumps({"version": 1, "setlist": "../../outside.setlist.json"}))
    lua.globals().LIB = lib
    lua.globals().CDIR = str(concert_dir)
    def subdirs(folder, index):
        names = sorted(p.name for p in Path(folder).iterdir() if p.is_dir()) if Path(folder).is_dir() else []
        return names[index] if index < len(names) else None
    lua.globals().SUBDIRS = subdirs
    lua.execute('''
      started, denied = 0, 0
      reaper.EnumerateSubdirectories=function(p,i) return SUBDIRS(p,i) end
      reaper.GetPlayState=function() return 0 end
      reaper.EnumProjects=function(i)
        if i==0 then return 10, CDIR.."/Other.RPP" end
        if i==1 then return 20, CDIR.."/Show.RPP" end
      end
      ctx={R=LIB.R, L={read=LIB.read,concert_dir=function() return CDIR end}, U={}, SEP="/",
        T=function(k) return k end, tr=function(d,k) return d.en[k] end,
        require_edit=function() return true end, show_result=function() denied=denied+1 end,
        start_cli=function() started=started+1; return true end}
    ''')
    tab = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_tab_concert.lua"}]])')(lua.globals().ctx)
    choices = tab.recoveries()
    assert len(choices) == 1 and choices[1].name == "Show"
    assert choices[1].path == str(archive / "Show.setlist.json")
    assert not tab.manage("restore", choices[1].path)
    assert lua.globals().started == 0 and lua.globals().denied == 1


def test_failed_setlist_write_prevents_build_and_preserves_editor_for_retry(tmp_path):
    lua, lib = runtime(tmp_path)
    folder = tmp_path / "Concerts"
    folder.mkdir()
    path = folder / "Show.setlist.json"
    initial = {"name": "Show", "gap_s": 4, "songs": [{"project": "/songs/One.RPP", "title": "One"}]}
    path.write_text(json.dumps(initial))
    lua.globals().LIB = lib
    lua.globals().CDIR = str(folder)
    lua.execute('''
      started, errors = 0, {}
      reaper.GetPlayState=function() return 0 end
      ctx={R=LIB.R, L={read=LIB.read,concert_dir=function() return CDIR end}, U={}, SEP="/",
        T=function(k) return k end, tr=function(d,k) return d.en[k] end, slug=function(s) return s end,
        require_edit=function() return true end, show_result=function(_,msg) errors[#errors+1]=msg end,
        start_cli=function() started=started+1; return true end, cli_setlist=function(p) return p end}
      original_write=ctx.R.write_atomic
      ctx.R.write_atomic=function() return false end
    ''')
    factory = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_tab_concert.lua"}]])')
    tab = factory(lua.globals().ctx)
    assert tab.load_setlist(str(path))
    # Another saved version exists; failed I/O must not silently merge it into the editor.
    path.write_text(json.dumps(dict(initial, gap_s=8)))
    assert tab.build() is False
    assert lua.globals().started == 0
    assert "Could not save" in lua.globals().errors[1]
    assert json.loads(path.read_text())["gap_s"] == 8
    path.unlink()
    lua.execute('ctx.R.write_atomic=original_write')
    assert tab.save() == str(path)
    assert json.loads(path.read_text())["gap_s"] == 4

    # A failed first save must not bind a new draft to the failed destination.
    draft = factory(lua.globals().ctx)
    lua.execute('ctx.R.write_atomic=function() return false end')
    assert draft.save() is None
    new_folder = tmp_path / "Other concerts"
    lua.globals().CDIR = str(new_folder)
    lua.execute('ctx.R.write_atomic=original_write')
    saved = Path(draft.save())
    assert saved.parent == new_folder and saved.is_file()

