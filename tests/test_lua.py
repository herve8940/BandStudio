"""Scripts Lua de REAPER, exécutés dans Lua 5.4 (lupa) avec une API REAPER simulée."""
import json
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from lupa import lua54  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LUA_DIR = ROOT / "reaper"

FAKE_REAPER = r"""
local res, os_name = ...
reaper = {}
local ext = {}
function reaper.GetResourcePath() return res end
function reaper.GetOS() return os_name end
function reaper.GetExtState(s, k) return ext[s .. "/" .. k] or "" end
function reaper.SetExtState(s, k, v) ext[s .. "/" .. k] = v end
function reaper.RecursiveCreateDirectory() return 1 end
function reaper.time_precise() return os.clock() end
function reaper.defer(f) end
function reaper.atexit(f) end
function reaper.GetAppVersion() return "7.27/test" end
function reaper.EnumProjects() return nil, "/tmp/test.rpp" end
-- deux pistes audio + une piste VOICE générée (à ignorer)
local tracks = { { name = "Drums" }, { name = "Bass" }, { name = "VOICE" } }
local items = {
  { guid = "{A}", file = "/s/drums.wav", tr = 1, pos = 1.5 },
  { guid = "{B}", file = "/s/bass.wav", tr = 2, pos = 1.5 },
  { guid = "{C}", file = "/v/count.wav", tr = 3, pos = 0 },
}
function reaper.CountTracks() return #tracks end
function reaper.GetTrack(_, i) return tracks[i + 1] end
function reaper.CountMediaItems() return #items end
function reaper.GetMediaItem(_, i) return items[i + 1] end
function reaper.CountSelectedMediaItems() return 0 end
function reaper.GetSelectedMediaItem() return nil end
function reaper.GetActiveTake(it) return { it = it } end
function reaper.GetMediaItemTake_Source(tk) return tk end
function reaper.GetMediaSourceParent() return nil end
function reaper.GetMediaSourceFileName(src) return src.it.file end
function reaper.GetMediaItem_Track(it) return tracks[it.tr] end
function reaper.GetSetMediaItemInfo_String(it, k) return true, it.guid end
function reaper.GetMediaItemInfo_Value(it, k) if k == "D_POSITION" then return it.pos end return 10.0 end
function reaper.GetMediaItemTakeInfo_Value(tk, k) if k == "D_PLAYRATE" then return 1.0 end return 0.0 end
function reaper.GetSetMediaTrackInfo_String(tr, k) return true, tr.name end
function reaper.GetMediaTrackInfo_Value(tr, k)
  for i, t in ipairs(tracks) do if t == tr then return i end end
  return 0
end
"""


def runtime(res: Path, os_name="OSX64"):
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    L.execute(FAKE_REAPER, str(res), os_name)
    return L


@pytest.mark.parametrize("name", sorted(p.name for p in LUA_DIR.glob("*.lua")))
def test_lua_syntax(name):
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    src = (LUA_DIR / name).read_text(encoding="utf-8")
    ok, err = L.eval("function(s, n) local f, e = load(s, '=' .. n); return f ~= nil, tostring(e) end")(src, name)
    assert ok, err


def load_run(res, os_name="OSX64"):
    L = runtime(res, os_name)
    return L, L.eval(f"dofile([[{LUA_DIR / 'ReaCue_run.lua'}]])")


@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_status_json_parsing(tmp_path, ensure_ascii):
    _, M = load_run(tmp_path)
    msg = 'Morceau préparé\n\n  1-8  Intro\n! fichier "C:\\new\\temp\\x.wav" introuvable 🎸\\'
    s = json.dumps({"state": "done", "time": 1700000000.25, "pid": 12, "message": msg}, ensure_ascii=ensure_ascii)
    assert M.jfield(s, "state") == "done"
    assert M.jfield(s, "message") == msg
    assert M.jfield(s, "time") == 1700000000.25
    assert M.jfield(s, "absent") is None
    assert M.jfield(json.dumps({"message": ""}), "message") == ""


def test_status_written_by_cli_is_readable(tmp_path, bridge_dir):
    from reacue_mcp import cli
    cli._status("error", cmd="prepare", message="Erreur : chemin C:\\Users\\Zoé\\x\n(détails)")
    _, M = load_run(bridge_dir.parent)
    s = (bridge_dir / "cli_status.json").read_text(encoding="utf-8")
    assert M.jfield(s, "state") == "error"
    assert M.jfield(s, "message") == "Erreur : chemin C:\\Users\\Zoé\\x\n(détails)"


def test_language_from_settings(tmp_path):
    (tmp_path / "ReaCueMCP").mkdir()
    _, M = load_run(tmp_path)
    assert M.lang() == "fr" and M.tr("prepare").startswith("Préparation")
    (tmp_path / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"language": "en"}))
    assert M.lang() == "en" and M.tr("prepare") == "Preparing the song"


@pytest.mark.parametrize("text", ["À la fin — Élodie 🎸", "Léa, Zoé et François", '"une ligne"\n\t\\\x00\x1f'])
def test_json_encoder_escapes_ascii_controls_without_corrupting_utf8(tmp_path, text):
    _, M = load_run(tmp_path)
    encoded = M.json_encode(text)
    assert json.loads(encoded) == text
    assert M.json_decode(encoded) == text


def test_install_dir_priority(tmp_path):
    data = tmp_path / "ReaCueMCP"
    data.mkdir()
    inst = tmp_path / "My Apps" / "ReaCue été"
    (inst / "reacue_mcp").mkdir(parents=True)
    (inst / "reacue_mcp" / "cli.py").write_text("")
    L, M = load_run(tmp_path)
    # 3. dossier parent du script (<installation>/reaper)
    assert M.install_dir(str(inst / "reaper")) == str(inst)
    # 4. ancien emplacement macOS
    assert M.install_dir(None).endswith("/Documents/reacue-mcp")
    # 2. fichier écrit par l'installateur (fin de ligne Windows, barre finale)
    (data / "reacue_install.txt").write_bytes(b"C:\\Program Files\\ReaCue\\\r\n")
    assert M.install_dir(str(inst / "reaper")) == "C:\\Program Files\\ReaCue"
    # 1. ExtState manuel
    L.execute('reaper.SetExtState("ReaCue", "install_dir", "/opt/reacue", true)')
    assert M.install_dir(None) == "/opt/reacue"


def _argv_windows(cmdline: str) -> list[str]:
    """Découpage d'une ligne de commande comme CommandLineToArgvW (cas utiles ici)."""
    out, cur, i, inq, has = [], [], 0, False, False
    while i < len(cmdline):
        c = cmdline[i]
        if c == "\\":
            n = 0
            while i < len(cmdline) and cmdline[i] == "\\":
                n += 1
                i += 1
            if i < len(cmdline) and cmdline[i] == '"':
                cur.append("\\" * (n // 2))
                if n % 2:
                    cur.append('"')
                    i += 1
            else:
                cur.append("\\" * n)
            has = True
            continue
        if c == '"':
            inq = not inq
            has = True
        elif c in " \t" and not inq:
            if has:
                out.append("".join(cur))
            cur, has = [], False
        else:
            cur.append(c)
            has = True
        i += 1
    if has:
        out.append("".join(cur))
    return out


def test_windows_command_quoting(tmp_path):
    res = "C:\\Users\\Zoé N\\AppData\\Roaming\\REAPER"
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    L.execute(FAKE_REAPER, res, "Win64")
    M = L.eval(f"dofile([[{LUA_DIR / 'ReaCue_run.lua'}]])")
    assert M.is_windows()
    d = "C:\\Users\\Zoé N\\Documents\\ReaCue 0.9"
    py = M.python(d, True)
    assert py == d + "\\.venv\\Scripts\\python.exe"         # pythonw.exe absent ici -> python.exe
    line = M.command("prepare", d, py, True, "x.log")
    assert _argv_windows(line) == [py, d + "\\reacue_cli.py", "prepare", "--resource-dir", res]
    assert ">>" not in line and "nohup" not in line
    assert M.winq("C:\\a b\\") == '"C:\\a b\\\\"'


def test_macos_command_unchanged(tmp_path):
    _, M = load_run(tmp_path, "macOS-arm64")
    assert not M.is_windows()
    d = "/Users/x/Documents/reacue-mcp"
    line = M.command("publish", d, M.python(d, False), False, "/tmp/l o g.txt")
    assert line.startswith("cd '/Users/x/Documents/reacue-mcp' && nohup '/Users/x/Documents/reacue-mcp/.venv/bin/python'"
                           " -m reacue_mcp.cli publish --resource-dir ")
    assert line.endswith(">> '/tmp/l o g.txt' 2>&1 &")
    assert M.shq("it's") == "'it'\\''s'"


def test_bridge_ping_and_stems_skip_generated_tracks(tmp_path):
    from reacue_mcp.bridge import to_lua
    data = tmp_path / "ReaCueMCP"
    data.mkdir()
    for cmd in ("ping", "get_audio_items", "nope"):
        (data / "request.lua").write_text(to_lua({"id": "r1", "cmd": cmd, "args": {}}), encoding="utf-8")
        L = runtime(tmp_path)
        L.execute(f"dofile([[{LUA_DIR / 'ReaCue_Bridge.lua'}]])")     # une itération de la boucle
        r = json.loads((data / "response.json").read_text(encoding="utf-8"))
        assert r["id"] == "r1"
        if cmd == "ping":
            assert r["ok"] and r["result"]["bridge"] == "1.5.0"
        elif cmd == "get_audio_items":
            files = [d["file"] for d in r["result"]["items"]]
            assert files == ["/s/drums.wav", "/s/bass.wav"]          # piste VOICE ignorée
        else:
            assert not r["ok"] and "nope" in r["error"]
