"""User presets and track removal: real Lua modules, isolated files and simulated REAPER."""
import json
from pathlib import Path

import pytest

pytest.importorskip("lupa")
from lupa import lua54

ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / "reaper"


@pytest.fixture
def app(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.RES, g.SCRIPTS = str(tmp_path), str(LUA) + "/"
    lua.execute(r'''
      play, locked, now, answer, active = 0, false, 1000, 1, "project-a"
      ext, projext, calls, buttons = {}, {}, {}, {}
      TRACKS = {{name="Chant", guid="a", file="voice.wav"}, {name="Basse",guid="b", file="bass.wav"},
        {name="CLICK",guid="c"}, {name="TIMECODE LTC",guid="d"}}
      output_names = {"Out 1", "Out 2", "Out 3", "Out 4"}
      reaper = {
        GetResourcePath=function() return RES end, GetOS=function() return "OSX64" end,
        GetExtState=function(_,k) return ext[k] or "" end, SetExtState=function(_,k,v) ext[k]=v end,
        RecursiveCreateDirectory=function() return 1 end, time_precise=function() return now end,
        GetPlayState=function() return play end, GetNumAudioOutputs=function() return #output_names end,
        GetOutputChannelName=function(i) return output_names[i+1] end,
        GetMaxMIDIOutputs=function() return 1 end, GetMIDIOutputName=function() return midi_enabled, "IAC" end,
        EnumProjects=function() return active, "/songs/"..active..".RPP" end,
        CountTracks=function() return #TRACKS end, GetTrack=function(_,i) return TRACKS[i+1] end,
        GetTrackName=function(p) return true,p.name end, GetTrackGUID=function(p) return p.guid end,
        ValidatePtr2=function(_,p) for _,t in ipairs(TRACKS) do if p==t then return true end end return false end,
        ShowMessageBox=function(msg) calls[#calls+1]="confirm"; question=msg; if on_confirm then on_confirm() end; return answer end,
        Undo_BeginBlock2=function() calls[#calls+1]="begin"; undo_snapshot={table.unpack(TRACKS)} end,
        Undo_EndBlock2=function(_,label) calls[#calls+1]="end"; undo_label=label end,
        Undo_DoUndo2=function() calls[#calls+1]="undo"; TRACKS=undo_snapshot end,
        PreventUIRefresh=function(n) calls[#calls+1]="refresh"..n end,
        DeleteTrack=function(p)
          if fail_delete and p.guid=="a" then error("simulated failure") end
          for i,t in ipairs(TRACKS) do if p==t then table.remove(TRACKS,i); calls[#calls+1]="delete:"..p.guid; return end end
        end,
        SetProjExtState=function(_,_,k,v) projext[k]=v end,
        TrackList_AdjustWindows=function() end, UpdateArrange=function() calls[#calls+1]="arrange" end,
      }
      gfx = {mouse_x=0, mouse_y=0, h=720}
      R=dofile(SCRIPTS.."ReaCue_run.lua")
      U={heading=function() end, text=function() end, text_w=function(s) return #s*6 end,
        fit=function(s) return s end, para=function() return 16 end,
        button=function(id,lab,x,y,w,h) buttons[#buttons+1]={id=id,x=x,y=y,w=w,h=h,label=lab}; return false end}
      ctx={R=R, U=U, SEP="/", dir=SCRIPTS, flow={}, tabs={},
        require_edit=function() return not locked end, is_locked=function() return locked end,
        L={read=R.read,exists=R.exists,lang=function() return lang or "fr" end,
          role_of_track=function(n) return n=="Chant" and "vocals" or n=="Basse" and "bass" or nil end},
        tr=function(tbl,k) return tbl[lang or "fr"][k] end}
      settings=dofile(SCRIPTS.."ReaCue_tab_settings.lua")(ctx)
      ctx.tabs.settings=settings
      ctx.tabs.lighting={parse_ltc=function(v) local a,b=tostring(v):match("^(%d+)/(%d+)$"); a=tonumber(a or v); return a and {a=a,b=tonumber(b)} end}
      ctx.tabs.song={tracks_changed=function() changed=(changed or 0)+1 end}
      ctx.tabs.stage={invalidate=function() invalidated=(invalidated or 0)+1 end}
      presets=settings.presets()
      tracks=dofile(SCRIPTS.."ReaCue_tracks.lua")(ctx)
    ''')
    return lua, g, tmp_path


def success(value):
    return value[0] if isinstance(value, tuple) else value


def data(path):
    return json.loads(path.read_text())


def test_presets_roundtrip_scopes_nil_false_and_unknown_preserved(app):
    lua, g, root = app
    path = root / "ReaCueMCP/reacue_settings.json"
    path.write_text(json.dumps({"click_to_master": False, "click_hw_output": 2, "custom": {"keep": 1}}))
    assert success(g.presets.create("Scène été", lua.table_from({"live": True})))
    assert success(g.settings.set("click_hw_output", 0))
    assert success(g.settings.set("lyrics_model", "large-v3-turbo"))
    assert success(g.presets.apply("Scène été"))
    result = data(path)
    assert result["click_hw_output"] == 2 and result["click_to_master"] is False
    assert result["custom"] == {"keep": 1} and result["lyrics_model"] == "large-v3-turbo"
    assert success(g.presets.create("Sortie principale", lua.table_from({"models": True})))
    assert success(g.settings.set("click_hw_output", None))
    assert success(g.presets.create("Auto", lua.table_from({"live": True})))
    assert success(g.settings.set("click_hw_output", 0))
    assert success(g.presets.apply("Auto"))
    assert "click_hw_output" not in data(path)


def test_presets_rename_duplicate_delete_restore_and_collision(app):
    lua, g, root = app
    assert success(g.presets.create("Base", lua.table_from({"models": True})))
    assert success(g.presets.rename("Base", "Copie", True))
    assert success(g.presets.rename("Copie", "Autre", False))
    assert not success(g.presets.rename("Autre", "Base", False))
    assert success(g.presets.delete("Base"))
    assert success(g.presets.create("Base", lua.table_from({"live": True})))
    assert success(g.presets.restore())
    result = data(root / "ReaCueMCP/reacue_presets.json")
    assert set(result["presets"]) == {"Autre", "Base", "Base (2)"}
    assert result["presets"]["Base (2)"]["scopes"] == {"models": True}


@pytest.mark.parametrize("failure", ["write", "rename"])
def test_presets_atomic_failure_keeps_storage_and_settings(app, failure):
    lua, g, root = app
    assert success(g.presets.create("Base", lua.table_from({"models": True})))
    sp = root / "ReaCueMCP/reacue_settings.json"
    assert success(g.settings.set("lyrics_model", "large-v3-turbo"))
    before = sp.read_bytes()
    pp = root / "ReaCueMCP/reacue_presets.json"
    presets_before = pp.read_bytes()
    if failure == "write":
        lua.execute('local open=io.open; io.open=function(p,m) if m=="wb" then return nil end return open(p,m) end')
    else:
        lua.execute('os.rename=function() return nil,"simulated disk error" end')
    assert not success(g.presets.rename("Base", "Changed", False))
    assert not success(g.presets.apply("Base"))
    assert pp.read_bytes() == presets_before and sp.read_bytes() == before
    assert g.settings.get("lyrics_model") == "large-v3-turbo"


@pytest.mark.parametrize("broken", ["not json", '{"version":1,"presets":{"bad":1},"trash":[]}'])
def test_presets_corrupt_file_is_never_overwritten(app, broken):
    lua, g, root = app
    p = root / "ReaCueMCP/reacue_presets.json"
    p.write_text(broken)
    assert not success(g.presets.create("New", lua.table_from({"live": True})))
    assert p.read_text() == broken


def test_apply_refuses_corrupt_settings_and_unavailable_outputs(app):
    lua, g, root = app
    assert success(g.settings.set("click_hw_output", 2))
    assert success(g.presets.create("Scène", lua.table_from({"live": True})))
    sp = root / "ReaCueMCP/reacue_settings.json"
    before = sp.read_bytes()
    lua.execute('output_names={"Out 1","Out 2"}')
    assert not success(g.presets.apply("Scène"))
    assert sp.read_bytes() == before
    lua.execute('output_names={"Different 1","Different 2","Different 3","Different 4"}')
    assert not success(g.presets.apply("Scène"))
    lua.execute('output_names={"Out 1","Out 2","Out 3","Out 4"}')
    sp.write_text("broken")
    assert not success(g.presets.apply("Scène"))
    assert sp.read_text() == "broken"


def test_lighting_midi_and_ltc_validation(app):
    lua, g, _ = app
    assert success(g.settings.set("gma3_ltc_output", "3/4"))
    assert success(g.settings.set("gma3_mtc_output", "IAC"))
    assert success(g.presets.create("MA3", lua.table_from({"lighting": True})))
    assert not success(g.presets.apply("MA3"))
    g.midi_enabled = True
    assert success(g.presets.apply("MA3"))


@pytest.mark.parametrize("block", ["locked=true", "play=1", "play=5", "ctx.job={}", "ctx.flow.run={finished=false}",
                                  "ctx.R.active_job=function() return {} end", "ctx.jobs={busy=function() return true end}"])
def test_all_preset_mutations_and_track_removal_obey_guards(app, block):
    lua, g, root = app
    assert success(g.presets.create("Base", lua.table_from({"live": True})))
    before = (root / "ReaCueMCP/reacue_presets.json").read_bytes()
    g.tracks.open()
    g.tracks.toggle(1)
    lua.execute(block)
    assert not success(g.presets.create("Other", lua.table_from({"models": True})))
    assert not success(g.presets.rename("Base", "New", False))
    assert not success(g.presets.delete("Base"))
    assert not success(g.presets.restore())
    assert not success(g.presets.apply("Base"))
    assert not success(g.settings.set("click_volume", .1))
    assert not success(g.settings.set_lyrics_profile("advanced"))
    assert not success(g.tracks.remove())
    assert len(g.TRACKS) == 4 and list(g.calls.values()) == []
    assert (root / "ReaCueMCP/reacue_presets.json").read_bytes() == before


def test_tracks_multiselect_one_undo_files_preserved_and_publication_dirty(app):
    lua, g, root = app
    audio = root / "voice.wav"
    audio.write_bytes(b"original audio")
    g.TRACKS[1].file = str(audio)
    g.tracks.open()
    for i in (1, 2, 3, 4):
        g.tracks.toggle(i)
    assert not g.tracks.selected[3] and not g.tracks.selected[4]
    assert success(g.tracks.remove())
    assert [r.name for r in g.TRACKS.values()] == ["CLICK", "TIMECODE LTC"]
    calls = list(g.calls.values())
    assert calls.count("begin") == calls.count("end") == 1
    assert calls.index("delete:b") < calls.index("delete:a")
    assert audio.read_bytes() == b"original audio"
    assert g.projext.publication_dirty == "1" and g.changed == g.invalidated == 1
    g.reaper.Undo_DoUndo2("project-a")
    assert len(g.TRACKS) == 4


def test_tracks_generated_require_opt_in_and_explicit_warning(app):
    lua, g, _ = app
    g.tracks.open()
    g.tracks.set_protect(False)
    g.tracks.toggle(3)
    g.answer = 0
    assert not success(g.tracks.remove())
    assert len(g.TRACKS) == 4 and "ATTENTION" in g.question
    g.answer = 1
    assert success(g.tracks.remove())
    assert len(g.TRACKS) == 3


@pytest.mark.parametrize("mutation", [
    'active="project-b"', 'table.remove(TRACKS,1)', 'TRACKS[1].name="Other"',
    'table.remove(TRACKS,1); reaper.ValidatePtr2=nil; reaper.GetTrackGUID=function() error("invalid pointer dereference") end',
    'on_confirm=function() active="project-b" end', 'on_confirm=function() locked=true end',
])
def test_tracks_project_and_references_revalidated_after_dialog(app, mutation):
    lua, g, _ = app
    g.tracks.open()
    g.tracks.toggle(1)
    lua.execute(mutation)
    assert not success(g.tracks.remove())
    assert not any(c.startswith("delete:") for c in g.calls.values())
    assert "begin" not in list(g.calls.values())


def test_tracks_partial_failure_rolls_back_and_balances_ui_refresh(app):
    lua, g, _ = app
    g.tracks.open()
    g.tracks.toggle(1)
    g.tracks.toggle(2)
    g.fail_delete = True
    assert not success(g.tracks.remove())
    assert [r.name for r in g.TRACKS.values()] == ["Chant", "Basse", "CLICK", "TIMECODE LTC"]
    calls = list(g.calls.values())
    assert calls.count("refresh1") == calls.count("refresh-1") == 1
    assert calls[-1] == "undo"


def test_tracks_failure_before_first_change_does_not_undo_previous_user_work(app):
    lua, g, _ = app
    g.tracks.open()
    g.tracks.toggle(1)
    g.fail_delete = True
    assert not success(g.tracks.remove())
    assert len(g.TRACKS) == 4 and "undo" not in list(g.calls.values())


@pytest.mark.parametrize("width", [360, 620, 900])
def test_presets_and_tracks_controls_fit_narrow_width(app, width):
    lua, g, _ = app
    assert success(g.presets.create("Répétition", lua.table_from({"live": True})))
    assert g.presets.draw(14, 80, width) < 650
    g.tracks.open()
    assert g.tracks.draw(14, 80, width) < 650
    for button in g.buttons.values():
        assert button.x >= 14 and button.x + button.w <= 14 + width + .01
        assert button.w > 0


@pytest.fixture(scope="module")
def concert_ui(tmp_path_factory):
    import test_reacue_window as W
    return W.TL.make_concert(tmp_path_factory.mktemp("presets_ui"))


@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("width", [620, 920])
def test_real_window_new_views_are_accessible_and_fit(concert_ui, lang, width):
    import test_reacue_window as W
    from test_doc_screenshots import watch, check_text
    lua, g = W.rt(concert_ui, lang=lang)
    gx = W.open_window(lua, g)
    gx.w = width
    ctx = g.REACUE_CTX
    ctx.goto_tab("settings")
    ctx.tabs.settings.set_page("presets")
    p = ctx.tabs.settings.presets()
    # Each runtime may share the same fictitious resource directory.
    assert success(p.create(f"Scène {lang} {width}", lua.table_from({"live": True})))
    watch(lua)
    W.frame(lua, g)
    assert "Presets" in W.TL.texts(g)
    assert ("Appliquer" if lang == "fr" else "Apply") in W.TL.texts(g)
    check_text(g, width)
    assert ctx.layout_h < 720
    ctx.goto_tab("song")
    ctx.tabs.song.tracks().open()
    watch(lua)
    W.frame(lua, g)
    assert ("Actualiser" if lang == "fr" else "Refresh") in W.TL.texts(g)
    assert any("CLICK" in text for text in W.TL.texts(g))
    check_text(g, width)
    assert ctx.layout_h < 720


def test_stage_and_lighting_guards_keep_stop_and_transport_available(concert_ui):
    import test_reacue_window as W
    lua, g = W.rt(concert_ui)
    W.open_window(lua, g)
    ctx = g.REACUE_CTX
    # Exercise each module's entry points independently of the root guards.
    lua.execute('''
      stage_locked=false
      REACUE_CTX.is_locked=function() return stage_locked end
      REACUE_CTX.require_edit=function() return not stage_locked end
      REACUE_CTX.set_locked=function(on) stage_locked=on; return true end
      REACUE_CTX.start_cli=function() error("must not start processing") end
      TRACKS[#TRACKS+1]={name="TIMECODE LTC"}
    ''')
    stage, light = ctx.tabs.stage, ctx.tabs.lighting
    assert light.test_start(False)
    g.stage_locked = True
    assert light.test_stop("user")  # Restoration remains possible when lock becomes active.
    assert light.test_active() is False
    assert light.test_start(False) is False
    assert light.remote_test("start") is False
    assert light.set("gma3_fps", 30) is False
    assert light.make_tracks() is False and light.export_now() is False
    assert stage.rebuild(True) is False
    assert stage.set_rehearsal(True) is False
    assert stage.set_rate(.8) is False
    assert ctx.open_live(ctx.c) is False
    assert ctx.open_built("/some/other.RPP") is False
    assert ctx.change_pin() is False
    ctx.goto_tab("stage")
    W.frame(lua, g)
    assert "Déverrouiller…" in W.TL.texts(g)
    state = g.state.play
    ctx.L.toggle_play()
    assert g.state.play != state


def test_song_public_mutations_refuse_lock_and_setlist_io_failure(concert_ui):
    import test_reacue_window as W
    lua, g = W.rt(concert_ui)
    W.open_window(lua, g)
    ctx = g.REACUE_CTX
    lua.execute('REACUE_CTX.require_edit=function() return false end; REACUE_CTX.is_locked=function() return true end')
    song = ctx.tabs.song
    for action in (song.prepare, song.reanalyse, song.publish, song.separate, song.do_all, song.undo, song.redo):
        assert action() is False
    assert song.autosave(ctx.proj_key) is False
    assert ctx.add_to_setlist("New locked concert", "/source.RPP", "Source") is False
    assert g.state.saves == 0
    lua.execute('REACUE_CTX.require_edit=function() return true end; REACUE_CTX.is_locked=function() return false end')
    folder = Path(ctx.L.concert_dir())
    folder.mkdir(exist_ok=True)
    target = folder / "Unreadable.setlist.json"
    target.write_text("broken")
    assert ctx.add_to_setlist("Unreadable", "/source.RPP", "Source") is False
    assert target.read_text() == "broken"
    lua.execute('REACUE_CTX.R.write_atomic=function() return false end')
    assert ctx.add_to_setlist("Disk full", "/source.RPP", "Source") is False
    assert not (folder / "Disk full.setlist.json").exists()
