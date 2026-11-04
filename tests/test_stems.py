"""Séparation de stems : lanceur Python (reacue_stems.py, Demucs simulé) et action REAPER (Lua 5.4)."""
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LUA_DIR = ROOT / "reaper"
sys.path.insert(0, str(ROOT))

import reacue_stems  # noqa: E402

from test_lua import _argv_windows  # noqa: E402


# --------------------------------------------------------------------------- #
# reacue_stems.py
# --------------------------------------------------------------------------- #
def _fake_demucs(monkeypatch, write=True, exit_code=None):
    calls = []

    def main(argv):
        calls.append(argv)
        print("  50%|█████     | 10/20 [00:01<00:01]", file=sys.stderr)
        if write:
            model, out, inp = argv[1], Path(argv[3]), Path(argv[-1])
            track = inp.name.rsplit(".", 1)[0]
            for s in reacue_stems.MODELS[model]:
                f = out / model / f"{track}-{s}.wav"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"RIFF")
        if exit_code is not None:
            raise SystemExit(exit_code)

    pkg = types.ModuleType("demucs")
    sep = types.ModuleType("demucs.separate")
    sep.main = main
    pkg.separate = sep
    monkeypatch.setitem(sys.modules, "demucs", pkg)
    monkeypatch.setitem(sys.modules, "demucs.separate", sep)
    return calls


def test_stem_files_keep_original_name(tmp_path):
    files = reacue_stems.stem_files("/m/Song-E minor-120bpm.mp3", tmp_path, "htdemucs_6s")
    assert [f.name for f in files][:2] == ["Song-E minor-120bpm-vocals.wav", "Song-E minor-120bpm-drums.wav"]
    assert all(f.parent == tmp_path / "htdemucs_6s" for f in files) and len(files) == 6
    assert len(reacue_stems.stem_files("a.wav", tmp_path, "htdemucs")) == 4


def test_separate_done(tmp_path, monkeypatch):
    calls = _fake_demucs(monkeypatch)
    src = tmp_path / "Ma chanson l'été-G minor-104bpm.mp3"
    src.write_bytes(b"x")
    out = tmp_path / "out"
    stdout = sys.stdout
    assert reacue_stems.main(["separate", "--input", str(src), "--out", str(out)]) == 0
    assert sys.stdout is stdout                                         # sorties rétablies
    assert calls[0][:5] == ["-n", "htdemucs", "-o", str(out), "--filename"]
    assert calls[0][5] == "{track}-{stem}.{ext}" and calls[0][-1] == str(src)
    st = json.loads((out / "demucs_status.json").read_text(encoding="utf-8"))
    assert st["state"] == "done" and st["model"] == "htdemucs" and len(st["files"]) == 4
    assert "50%|" in (out / "demucs.log").read_text(encoding="utf-8")   # progression lue par REAPER


def test_separate_errors(tmp_path, monkeypatch):
    _fake_demucs(monkeypatch, write=False, exit_code=1)
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    assert reacue_stems.separate(str(src), str(tmp_path / "o"), "inconnu") == 1      # modèle inconnu -> htdemucs
    st = json.loads((tmp_path / "o" / "demucs_status.json").read_text(encoding="utf-8"))
    assert st["state"] == "error" and st["model"] == "htdemucs" and "demucs exit 1" in st["message"]
    assert reacue_stems.separate(str(tmp_path / "absent.mp3"), str(tmp_path / "p")) == 1
    st = json.loads((tmp_path / "p" / "demucs_status.json").read_text(encoding="utf-8"))
    assert st["state"] == "error" and "FileNotFoundError" in st["message"]


def test_check_disk_space_fails_when_low(tmp_path, monkeypatch):
    src = tmp_path / "song.mp3"
    src.write_bytes(b"x")
    out = tmp_path / "out"
    monkeypatch.setattr(reacue_stems, "check_disk_space", lambda p, min_mb=500: (False, 100))
    assert reacue_stems.separate(str(src), str(out)) == 1
    st = json.loads((out / "demucs_status.json").read_text(encoding="utf-8"))
    assert st["state"] == "error"
    assert "Espace disque insuffisant" in st["message"]


def test_requirements_pin_intel_mac():
    req = (ROOT / "requirements-stems.txt").read_text(encoding="utf-8")
    assert "demucs==4.0.1" in req
    assert 'torch==2.2.2 ; sys_platform == "darwin" and platform_machine == "x86_64"' in req
    assert 'numpy<2 ; sys_platform == "darwin" and platform_machine == "x86_64"' in req


# --------------------------------------------------------------------------- #
# Lua : ReaCue_stems.lua
# --------------------------------------------------------------------------- #
lupa = pytest.importorskip("lupa")
from lupa import lua54  # noqa: E402

FAKE = r"""
local res, os_name = ...
reaper = {}
calls = {}
local function log(...) calls[#calls + 1] = table.concat({ ... }, "|") end
function reaper.GetResourcePath() return res end
function reaper.GetOS() return os_name end
function reaper.GetExtState() return "" end
tracks = { { name = "Mix" }, { name = "CLICK" }, { name = "VOIX" } }
local take0 = { file = "/m/song.mp3", D_STARTOFFS = 2.5, D_PLAYRATE = 1.0 }
items = {
  { tr = 1, take = take0, D_POSITION = 4.0, D_LENGTH = 200.0 },
  { tr = 2, take = { file = "", midi = true }, D_POSITION = 0, D_LENGTH = 10 },
  { tr = 3, take = { file = "/v/x.wav" }, D_POSITION = 0, D_LENGTH = 1 },
}
selected = nil
function reaper.GetSelectedMediaItem() return selected end
function reaper.CountMediaItems() return #items end
function reaper.GetMediaItem(_, i) return items[i + 1] end
function reaper.GetActiveTake(it) return it.take end
function reaper.TakeIsMIDI(tk) return tk.midi == true end
function reaper.GetMediaItem_Track(it) return tracks[it.tr] end
function reaper.GetSetMediaTrackInfo_String(tr, k, v, set) if set then tr.name = v end return true, tr.name end
function reaper.GetMediaTrackInfo_Value(tr) for i, t in ipairs(tracks) do if t == tr then return i end end return 0 end
function reaper.GetMediaItemInfo_Value(it, k) return it[k] end
function reaper.GetMediaItemTakeInfo_Value(tk, k) return tk[k] end
function reaper.Undo_BeginBlock() log("undo_begin") end
function reaper.Undo_EndBlock(n) log("undo_end", n) end
function reaper.PreventUIRefresh() end
function reaper.UpdateArrange() end
function reaper.InsertTrackAtIndex(i) table.insert(tracks, i + 1, { name = "" }) end
function reaper.GetTrack(_, i) return tracks[i + 1] end
function reaper.AddMediaItemToTrack(tr) local it = { tr_ref = tr } ; log("item", tr == nil and "?" or "ok") ; return it end
function reaper.SetMediaItemInfo_Value(it, k, v) it[k] = v end
function reaper.AddTakeToMediaItem(it) it.take = {} ; return it.take end
function reaper.PCM_Source_CreateFromFile(f) return { file = f } end
function reaper.SetMediaItemTake_Source(tk, src) tk.src = src.file ; log("src", src.file) end
function reaper.SetMediaItemTakeInfo_Value(tk, k, v) tk[k] = v end
function reaper.GetSetMediaItemTakeInfo_String(tk, k, v) tk.name = v return true, v end
function reaper.GetMediaItemTake_Source(tk) return tk end
function reaper.GetMediaSourceParent() return nil end
function reaper.GetMediaSourceFileName(src) return src.file end
function reaper.DeleteTrackMediaItem(tr, it) log("delete", tr.name, it.take.file) end
"""


def lua(res, os_name="OSX64"):
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    L.execute(FAKE, str(res), os_name)
    S = L.eval(f"dofile([[{LUA_DIR / 'ReaCue_stems.lua'}]])")
    R = L.eval(f"dofile([[{LUA_DIR / 'ReaCue_run.lua'}]])")
    return L, S, R


def test_lua_models_match_python(tmp_path):
    L, S, _ = lua(tmp_path)
    for model, stems in reacue_stems.MODELS.items():
        assert list(S.MODELS[model].values()) == list(stems)
    assert S.DEFAULT_MODEL == reacue_stems.DEFAULT_MODEL == "htdemucs"


def test_paths_posix_and_windows(tmp_path):
    _, S, _ = lua(tmp_path)
    p = S.paths("/Music/My Song-E minor-120bpm.mp3", "htdemucs_6s")
    assert p.outroot == "/Music/My Song-E minor-120bpm-stems"
    assert p.status == p.outroot + "/demucs_status.json"
    assert p.stems[1].file == "/Music/My Song-E minor-120bpm-stems/htdemucs_6s/My Song-E minor-120bpm-vocals.wav"
    py_files = [f.as_posix() for f in reacue_stems.stem_files("/Music/My Song-E minor-120bpm.mp3",
                                                        "/Music/My Song-E minor-120bpm-stems", "htdemucs_6s")]
    assert [p.stems[i].file for i in range(1, 7)] == py_files          # même convention que Demucs
    w = S.paths("C:\\Users\\Zoé\\Music\\a.b.wav", "htdemucs")
    assert w.outdir == "C:\\Users\\Zoé\\Music\\a.b-stems\\htdemucs" and len(w.stems) == 4
    assert w.stems[4].file.endswith("\\a.b-other.wav")


def test_model_from_settings(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    _, S, R = lua(tmp_path)
    assert S.model(R) == "htdemucs"
    (tmp_path / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"stems_model": "htdemucs"}))
    assert S.model(R) == "htdemucs"
    (tmp_path / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"stems_model": "bad"}))
    assert S.model(R) == "htdemucs"


def test_commands_quoting(tmp_path):
    _, S, R = lua(tmp_path)
    d, f, out = "/Users/x/Re Cue", "/m/l'été.mp3", "/m/l'été-stems"
    line = S.command(R, d, S.python(d, False), False, f, out, "htdemucs_6s")
    assert line == ("cd '/Users/x/Re Cue' && nohup '/Users/x/Re Cue/.venv-demucs/bin/python' reacue_stems.py separate"
                    " --input '/m/l'\\''été.mp3' --out '/m/l'\\''été-stems' --model htdemucs_6s > /dev/null 2>&1 &")
    L, S, R = lua("C:\\R", "Win64")
    d = "C:\\Program Files\\ReaCue"
    py = S.python(d, True)
    assert py == d + "\\.venv-demucs\\Scripts\\python.exe"
    line = S.command(R, d, py, True, "D:\\Mes chansons\\a b.mp3", "D:\\Mes chansons\\a b-stems", "htdemucs")
    assert _argv_windows(line) == [py, d + "\\reacue_stems.py", "separate", "--input", "D:\\Mes chansons\\a b.mp3",
                                   "--out", "D:\\Mes chansons\\a b-stems", "--model", "htdemucs"]


def test_progress_from_tqdm_log(tmp_path):
    _, S, _ = lua(tmp_path)
    log = " 9%|██  | 23.4/274.9 [00:34<05:22]\r 17%|███ | 46.8/274.9\r"
    assert S.progress(log) == 17 and S.progress("") == 0 and S.progress(None) == 0


def test_pick_item_and_import(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    (tmp_path / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"language": "en"}))
    L, S, R = lua(tmp_path)
    item = S.pick_item()
    assert item is not None and item.take.file == "/m/song.mp3"         # CLICK / VOIX ignorées
    p = S.paths("/m/song.mp3", "htdemucs_6s")
    L.eval("function(S, R, it, p) return S.import(R, it, p) end")(S, R, item, p)
    names = [L.eval("tracks")[i].name for i in range(1, 10)]
    assert names == ["Mix", "Vocals", "Drums", "Bass", "Guitar", "Piano", "Other", "CLICK", "VOIX"]
    calls = list(L.eval("calls").values())
    assert calls[0] == "undo_begin" and calls[-1] == "undo_end|ReaCue: separate stems"
    assert "delete|Mix|/m/song.mp3" in calls                           # l'item d'origine est retiré
    assert "src|/m/song-stems/htdemucs_6s/song-vocals.wav" in calls


def test_import_keeps_alignment(tmp_path):
    L, S, R = lua(tmp_path)
    got = L.eval("""function(S, R)
      local it = items[1]
      local p = S.paths("/m/song.mp3", "htdemucs")
      local made = {}
      local add = reaper.AddMediaItemToTrack
      reaper.AddMediaItemToTrack = function(tr) local x = add(tr); made[#made + 1] = x; return x end
      S.import(R, it, p)
      local x = made[1]
      return #made, x.D_POSITION, x.D_LENGTH, x.take.D_STARTOFFS, x.take.D_PLAYRATE, x.C_BEATATTACHMODE
    end""")(S, R)
    assert tuple(got) == (4, 4.0, 200.0, 2.5, 1.0, 0)


def _run_action(L, S, script_dir):
    L.execute("boxes = {} ; function reaper.ShowMessageBox(m) boxes[#boxes + 1] = m end")
    S.run(str(script_dir))
    return list(L.eval("boxes").values())


def test_run_not_installed_then_cached(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    inst = tmp_path / "inst"                       # installation sans .venv-demucs
    (tmp_path / "ReaCueMCP" / "reacue_install.txt").write_text(str(inst))
    song = tmp_path / "music" / "My Song.mp3"
    song.parent.mkdir()
    song.write_bytes(b"x")
    L, S, R = lua(tmp_path)
    L.execute(f"items[1].take.file = [[{song}]]")
    boxes = _run_action(L, S, LUA_DIR)
    assert len(boxes) == 1 and "pas installée" in boxes[0] and ".venv-demucs" in boxes[0]
    # stems déjà séparés (cache) : import immédiat, sans Demucs
    for f in reacue_stems.stem_files(song, song.parent / "My Song-stems", "htdemucs"):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"RIFF")
    L, S, R = lua(tmp_path)
    L.execute(f"items[1].take.file = [[{song}]]")
    boxes = _run_action(L, S, LUA_DIR)
    assert len(boxes) == 1 and boxes[0].startswith("Stems importés (htdemucs) : Chant, Batterie, Basse")
    assert "delete|Mix|" + str(song) in list(L.eval("calls").values())


def test_run_no_item_and_offline(tmp_path):
    L, S, R = lua(tmp_path)
    L.execute("items[1].tr = 2")                   # plus aucun item audio hors pistes générées
    assert "Sélectionne l'item audio" in _run_action(L, S, LUA_DIR)[0]
    L, S, R = lua(tmp_path)
    L.execute("items[1].take.file = '/absent/x.mp3'")
    assert "OFFLINE" in _run_action(L, S, LUA_DIR)[0]


def test_lyrics_found_next_to_original_song(tmp_path):
    from reacue_mcp import lyrics
    song = tmp_path / "Song"
    stems = song / "Song-stems" / "htdemucs_6s"
    stems.mkdir(parents=True)
    (song / "paroles.txt").write_text("a\n", encoding="utf-8")
    assert lyrics.find_lyrics_file([str(stems / "Song-vocals.wav")]) == song / "paroles.txt"
    (stems / "lyrics.txt").write_text("b\n", encoding="utf-8")          # à côté des stems : prioritaire
    assert lyrics.find_lyrics_file([str(stems / "Song-vocals.wav")]) == stems / "lyrics.txt"

def test_pid_alive_macos_and_windows(tmp_path):
    L, S, R = lua(tmp_path, os_name="OSX64")
    # macOS: REAPER ExecProcess returns "0\n" when /bin/kill -0 succeeds
    L.execute('reaper.ExecProcess = function(cmd, t) return "0\\n" end')
    assert S.pid_alive(1234, False) is True

    # macOS: REAPER ExecProcess returns "1\n..." when process is dead
    L.execute('reaper.ExecProcess = function(cmd, t) return "1\\nkill: 1234: No such process" end')
    assert S.pid_alive(1234, False) is False

    # macOS: REAPER ExecProcess returns nil on failure
    L.execute('reaper.ExecProcess = function(cmd, t) return nil end')
    assert S.pid_alive(1234, False) is True

    # Windows: tasklist output
    L.execute('reaper.ExecProcess = function(cmd, t) return "0\\npython.exe 1234 Console 1" end')
    assert S.pid_alive(1234, True) is True
    L.execute('reaper.ExecProcess = function(cmd, t) return "0\\nINFO: No tasks running with specified criteria" end')
    assert S.pid_alive(1234, True) is False


def test_poll_alive_macos_demucs_flow(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    L, S, R = lua(tmp_path, os_name="OSX64")
    outroot = tmp_path / "song-stems"
    outroot.mkdir()
    status_file = outroot / "demucs_status.json"
    status_file.write_text(json.dumps({"state": "running", "pid": 4242, "time": 1000}), encoding="utf-8")
    (outroot / "demucs.log").write_text("Selected model is a bag of 1 models.\n 15%|\u2588\u258c        | 15/100", encoding="utf-8")

    outroot_posix = outroot.as_posix()
    status_posix = status_file.as_posix()
    log_posix = (outroot / "demucs.log").as_posix()

    L.execute("""
    reaper.ExecProcess = function(cmd, timeout)
      if cmd:find("/bin/kill -0 4242") then
        return "0\\n"
      end
      return "1\\nNo such process"
    end
    reaper.time_precise = function() return 1005 end
    """)
    job = L.eval(f"""{{
      item = items[1],
      model = "htdemucs_6s",
      t0 = 1000,
      p = {{
        outroot = [[{outroot_posix}]],
        status = [[{status_posix}]],
        log = [[{log_posix}]],
        stems = {{}}
      }}
    }}""")
    state, pct = S.poll(R, job)
    assert state == "running"
    assert pct == 15



@pytest.mark.parametrize("model", ["htdemucs_6s", "htdemucs_ft"])
def test_explicit_model_is_preserved_in_python_and_lua(tmp_path, monkeypatch, model):
    calls = _fake_demucs(monkeypatch)
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "out"
    assert reacue_stems.main(["separate", "--input", str(source), "--out", str(output), "--model", model]) == 0
    assert calls[0][1] == model
    status = json.loads((output / "demucs_status.json").read_text(encoding="utf-8"))
    assert status["model"] == model and len(status["files"]) == len(reacue_stems.MODELS[model])
    settings_dir = tmp_path / "ReaCueMCP"
    settings_dir.mkdir()
    (settings_dir / "reacue_settings.json").write_text(json.dumps({"stems_model": model}), encoding="utf-8")
    _, S, R = lua(tmp_path)
    assert S.model(R) == model
