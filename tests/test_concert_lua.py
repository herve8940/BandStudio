"""Fenêtre « ReaCue - Concert » et sa bibliothèque (Lua 5.4 via lupa, API REAPER simulée) : transport,
double appui, sections, arrêt automatique, télécommande Régie (PIN, nonce), QR code (décodé), FR / EN.
Le concert est construit par le vrai code Python à partir des projets de démonstration (fictifs)."""
import json
import sys
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from lupa import lua54  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LUA_DIR = ROOT / "reaper"
sys.path.insert(0, str(ROOT / "tools"))
import concert_demo as D  # noqa: E402
from reacue_mcp import concert as C, i18n  # noqa: E402

FAKE = r"""
state = {play=0, pos=0, cursor=0, stopped=0, played=0, paused=0, cmds={}, ext={assistant_seen="1"}, persist={}, opened=nil,
         ops={}, color={0,0,0,1}, font={14,0}, dock=0, execs={}, seeks={}, t=1000.0, inputs=nil, shell={}}
reaper = {
  EnumProjects=function(i, s) return 1, PROJFILE end,
  GetOS=function() return OSNAME end,
  GetPlayState=function() return state.play end,
  GetPlayPosition=function() return state.pos end,
  GetCursorPosition=function() return state.cursor end,
  OnStopButton=function() state.play=0; state.stopped=state.stopped+1 end,
  OnPlayButton=function() state.play=1; state.played=state.played+1; state.pos=state.cursor end,
  OnPauseButton=function() if state.play==1 then state.play=2 elseif state.play==2 then state.play=1 end; state.paused=state.paused+1 end,
  SetEditCurPos=function(t, mv, seek) state.cursor=t; table.insert(state.seeks, {t, seek and 1 or 0}); if seek then state.pos=t end end,
  GetExtState=function(a,b) return state.ext[b] or "" end,
  SetExtState=function(a,b,v,p) state.ext[b]=v; if p then state.persist[b]=v end end,
  GetResourcePath=function() return RES end,
  RecursiveCreateDirectory=function(d) return 1 end,
  EnumerateFiles=function(dir,i) local t=FILES[dir]; return t and t[i+1] or nil end,
  Main_OnCommand=function(c) table.insert(state.cmds,c) end,
  Main_openProject=function(p) state.opened=p end,
  ShowMessageBox=function(m) state.msgbox=m; return 1 end,
  GetUserInputs=function(t,n,cap,def) if state.inputs then return true, state.inputs end return false, def end,
  time_precise=function() return state.t end,
  defer=function(f) state.deferred=f end, atexit=function(f) state.atexit=f end,
  get_ini_file=function() return INIPATH end,
  ExecProcess=function(cmd, t) table.insert(state.execs, {cmd, t}); return EXEC(cmd) end,
  EnumProjectMarkers3=function(p, i) local r=REGIONS[i+1]; if not r then return 0 end return i+1, r[1], r[2], r[3], r[4], i+1, r[5] end,
  ColorFromNative=function(c) return (c>>16)&255, (c>>8)&255, c&255 end,
  TimeMap2_timeToBeats=function(p, t) local m=0; for k=1,#BARS do if BARS[k] <= t + 1e-9 then m=k-1 end end; return 0, m, 4, 0, 4 end,
}
-- pistes, items, carte son, boucle/vitesse (contrôle avant concert, mode répétition)
TRACKS, ITEMS, AUDIO_ON, NOUT = {}, {}, 1, 2
state.toggles, state.rep, state.sel, state.rate, state.mutelog = {}, 1, {12, 20}, 1.0, {}
reaper.CountTracks=function() return #TRACKS end
reaper.GetTrack=function(p, i) return TRACKS[i+1] end
reaper.GetTrackName=function(tr) return true, tr.name end
reaper.GetMediaTrackInfo_Value=function(tr, k) if k=="B_MUTE" then return tr.mute or 0 elseif k=="B_MAINSEND" then return tr.main or 1 end return 0 end
reaper.SetMediaTrackInfo_Value=function(tr, k, v) if k=="B_MUTE" then tr.mute=v; table.insert(state.mutelog, {tr.name, v}) end end
reaper.GetTrackNumSends=function(tr, c) return #(tr.sends or {}) end
reaper.GetTrackSendInfo_Value=function(tr, c, i, k) return tr.sends[i+1] end
reaper.CountMediaItems=function() return #ITEMS end
reaper.GetMediaItem=function(p, i) return ITEMS[i+1] end
reaper.GetActiveTake=function(it) return it end
reaper.TakeIsMIDI=function(t) return t.midi or false end
reaper.GetMediaItemTake_Source=function(t) return t end
reaper.GetMediaSourceParent=function(s) return nil end
reaper.GetMediaSourceFileName=function(s, b) return s.file or "" end
reaper.GetMediaSourceSampleRate=function(s) return s.sr or 44100 end
reaper.GetMediaItem_Track=function(it) return TRACKS[it.track] end
reaper.Audio_IsRunning=function() return AUDIO_ON end
reaper.GetAudioDeviceInfo=function(k, b) return true, "Fake Device" end
reaper.GetNumAudioOutputs=function() return NOUT end
reaper.GetSetRepeat=function(v) if v >= 0 then state.rep=v end return state.rep end
reaper.GetSet_LoopTimeRange=function(set, loop, a, b, auto) if set then state.sel={a, b} end return state.sel[1], state.sel[2] end
reaper.GetToggleCommandState=function(c) return state.toggles[c] or 0 end
reaper.Master_GetPlayRate=function() return state.rate end
reaper.CSurf_OnPlayRateChange=function(r) state.rate=r end
reaper.TimeMap2_beatsToTime=function(p, tpos, m) return BARS[m+1] end
local _moc = reaper.Main_OnCommand
reaper.Main_OnCommand=function(c, f) if c==40671 then state.toggles[c] = 1 - (state.toggles[c] or 0) end; _moc(c, f) end
os.execute = function(cmd) table.insert(state.shell, cmd); return true end
local function op(...) table.insert(state.ops, {...}) end
-- polices « installées » (largeur moyenne d'un caractère / taille) ; absente : largeur par défaut 0,55
FONTW = FONTW or { Menlo = 0.62, ["Avenir Next Condensed"] = 0.6, Consolas = 0.62, ["Arial Narrow"] = 0.6 }
gfx = setmetatable({w=540,h=300,mouse_x=0,mouse_y=0,mouse_cap=0,x=0,y=0}, {__index=function(t,k)
  return function(...)
    local a = {...}
    if k=="getchar" then return 0
    elseif k=="measurestr" then local s=a[1]; return utf8.len(s)*state.font[1]*(FONTW[state.font[3] or ""] or 0.55), state.font[1]
    elseif k=="dock" then if a[1] and a[1] >= 0 then state.dock=a[1] end return state.dock
    elseif k=="set" then state.color={a[1],a[2],a[3],a[4] or 1}
    elseif k=="setfont" then state.font={a[3] or 14, a[4] or 0, a[2]}
    elseif k=="init" then if a[2] then gfx.w=a[2] end if a[3] then gfx.h=a[3] end
    elseif k=="drawstr" then op("text", gfx.x, gfx.y, a[1], state.font[1], state.font[2], state.color[1], state.color[2], state.color[3], state.color[4], state.font[3])
    elseif k=="rect" then op("rect", a[1],a[2],a[3],a[4], state.color[1], state.color[2], state.color[3], state.color[4], a[5] or 1)
    elseif k=="roundrect" then op("rrect", a[1],a[2],a[3],a[4], state.color[1], state.color[2], state.color[3], state.color[4])
    elseif k=="circle" then op("circle", a[1],a[2],a[3], state.color[1], state.color[2], state.color[3], state.color[4])
    elseif k=="triangle" then op("tri", a[1],a[2],a[3],a[4],a[5],a[6], state.color[1], state.color[2], state.color[3], state.color[4])
    end
    return 0 end end})
"""
INI = "[REAPER]\ncsurf_cnt=1\ncsurf_0=HTTP 0 8090 '' 'prompteur.html' 0 ''\n"


@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return make_concert(tmp_path_factory.mktemp("concert"))


def make_concert(tmp):
    """Concert de démonstration construit par le vrai code Python ; régions lues dans le RPP."""
    ps = D.write_demo(tmp / "projects")
    i18n.set_lang("fr")
    res = C.build_concert("Concert test", [str(p) for p in ps], 4.0, out_dir=tmp / "Concerts", publish=False)
    root = C.parse_rpp(res.rpp.read_text(encoding="utf-8"))
    regions, pending = [], {}
    for line in root.lines("MARKER"):
        tk = C.tokens(line)
        if int(tk[4]) & 1:
            if len(tk) > 5:
                pending[tk[1]] = (float(tk[2]), tk[3], int(tk[5]))
            else:
                st, name, col = pending.pop(tk[1])
                regions.append((True, st, float(tk[2]), name, col & 0xFFFFFF))
    regions.sort(key=lambda r: r[1])
    return res, regions, tmp


def runtime(concert, lang="fr", os_name="OSX64", ips=("192.168.1.20",), proj=None, exec_fn=None):
    res, regions, tmp = concert
    rdir = tmp / f"res_{lang}"
    (rdir / "ReaCueMCP").mkdir(parents=True, exist_ok=True)
    (rdir / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"language": lang}), encoding="utf-8")
    ini = rdir / "reaper.ini"
    ini.write_text(INI, encoding="utf-8")
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    L.execute(FAKE)
    g = L.globals()
    g.PROJFILE = str(proj or res.rpp)
    g.OSNAME = os_name
    g.RES = str(rdir)
    g.INIPATH = str(ini)
    g.FILES = L.table_from({str(res.rpp.parent): L.table_from(sorted(p.name for p in res.rpp.parent.iterdir()))})
    g.REGIONS = L.table_from([L.table_from(r) for r in regions])
    side = res.song_srcs
    bars = []
    for d, s in zip(res.songs, side):
        bars += [b + d["start"] for b in s.bar_lines[s.i0 - s.ci:s.i0 + s.n_bars + 1]]
    g.BARS = L.table_from(sorted(bars))
    g.state.ext["concert_dir"] = str(res.rpp.parent)

    def default_exec(cmd):
        if "getifaddr" in cmd:
            n = int(cmd[-1])
            return f"0\n{ips[n]}\n" if n < len(ips) else "1\n"
        return "1\n"
    g.EXEC = exec_fn or default_exec
    return L, g


def lib(L):
    return L.execute(f"return dofile([[{LUA_DIR / 'ReaCue_concert_lib.lua'}]])")


def window(L, g, dock=0, h=300):
    g.state.dock = dock
    L.execute(f"dofile([[{LUA_DIR / 'ReaCue_Concert.lua'}]])")
    if dock:
        L.globals().gfx.h = h
    return L.globals().gfx


def frame(L, g, click=None):
    gx = L.globals().gfx
    L.execute("state.ops = {}")
    if click:
        gx.mouse_x, gx.mouse_y, gx.mouse_cap = click[0], click[1], 1
        g.state.deferred()
        gx.mouse_cap = 0
        L.execute("state.ops = {}")
    g.state.deferred()


class Texts(list):
    """textes dessinés ; « in » ignore la casse : titres et étiquettes en capitales (thème Studio pro)"""
    def __contains__(self, s):
        if list.__contains__(self, s):
            return True
        return isinstance(s, str) and s.upper() in {t.upper() for t in self if isinstance(t, str)}


def texts(g):
    return Texts(list(o.values())[3] for o in g.state.ops.values() if list(o.values())[0] == "text")


def find_text(g, s):
    for o in g.state.ops.values():
        o = list(o.values())
        if o[0] == "text" and s in o[3]:
            return o[1], o[2]
    for o in g.state.ops.values():             # titres en capitales
        o = list(o.values())
        if o[0] == "text" and s.upper() in o[3].upper():
            return o[1], o[2]
    return None


def render(g, w, h):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (int(w), int(h)), (0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    col = lambda r, gg, b, a: (int(r * 255), int(gg * 255), int(b * 255), int(255 * (a if a is not None else 1)))
    for o in g.state.ops.values():
        o = list(o.values())
        if o[0] == "rect":
            x, y, ww, hh, r, gg, b, a, fill = o[1:10]
            if ww > 0 and hh > 0 and fill:
                d.rectangle([x, y, x + ww - 1, y + hh - 1], fill=col(r, gg, b, a))
    return img


# ------------------------------------------------------------------------------------------- lib
def test_lib_transport_sections_remote(concert):
    res = concert[0]
    L, g = runtime(concert)
    M = lib(L)
    c = M.load_concert()
    st = g.state
    assert len(c.songs) == 3 and c.songs[2].title == "Second Demo"
    assert M.play_state() == "stop"
    M.toggle_play(); assert st.play == 1 and M.play_state() == "play"
    M.toggle_play(); assert st.play == 2 and M.play_state() == "pause"
    M.stop(); assert st.play == 0
    secs = M.song_sections(c, 2)
    assert [s.name for s in secs.values()] == ["Intro", "Couplet 1", "Refrain 1", "Solo"]
    s2 = res.songs[1]
    assert M.song_index(c, s2["start"] + 1) == 2
    st.cursor = s2["start"] + 1
    M.next(c); assert st.cursor == pytest.approx(res.songs[2]["start"])
    st.cursor = res.songs[2]["start"] + 5
    M.prev(c); assert st.cursor == pytest.approx(res.songs[2]["start"])     # début du morceau en cours
    M.prev(c); assert st.cursor == pytest.approx(s2["start"])               # puis le précédent
    # arrêt automatique en fin de morceau
    k = M.crossed_stop(c, res.songs[0]["stop"] - 0.1, res.songs[0]["stop"] + 0.05)
    assert k == 1
    st.play = 1; M.after_stop(c, k); assert st.play == 0 and st.cursor == pytest.approx(s2["start"])
    # télécommande : PIN généré (jamais en dur), persistant, nonce anti-rejeu, accusé
    pin = M.remote_pin()
    assert len(pin) == 4 and pin.isdigit() and st.persist["remote_pin"] == pin and M.remote_pin() == pin
    assert not M.set_remote_pin("12a4") and M.set_remote_pin("4821")
    st.ext["remote"] = "toggle||4821|n1"; assert tuple(M.remote_poll(c)) == ("toggle", "ok") and st.play == 1
    assert st.ext["remote_ack"] == "n1|ok" and st.ext["remote"] == ""
    st.ext["remote"] = "toggle||4821|n1"; assert tuple(M.remote_poll(c)) == ("toggle", "dup")
    st.ext["remote"] = "stop||0000|n2"; assert tuple(M.remote_poll(c)) == ("stop", "badpin") and st.play == 1
    st.ext["remote"] = "song|3|4821|n3"; M.remote_poll(c); assert st.cursor == pytest.approx(res.songs[2]["start"])
    st.ext["remote"] = "song|9|4821|n4"; assert tuple(M.remote_poll(c)) == ("song", "bad")
    st.ext["remote"] = "xyz||4821|n5"; assert tuple(M.remote_poll(c)) == ("xyz", "bad")
    st.ext["remote"] = "toggle||4821|n6"; assert tuple(M.remote_poll(None)) == ("toggle", "noconcert")
    assert M.remote_poll(c) is None


def test_lib_paths_ips_ports(concert, tmp_path):
    L, g = runtime(concert, ips=("10.0.0.5", "192.168.68.20"))
    M = lib(L)
    assert list(M.local_ips().values()) == ["10.0.0.5", "192.168.68.20"]
    assert tuple(M.web_port()) == (8090, True)
    assert tuple(M.parse_web_port("\n[REAPER]\nfoo=1\n")) == (8080, False)
    assert M.prompter_url("10.0.0.5", 8090) == "http://10.0.0.5:8090/prompteur.html"
    # Windows : ipconfig (sortie localisée), sans PowerShell ni console
    out = ("0\nConfiguration IP de Windows\r\n\r\n   Adresse IPv4. . . . . . . . . . . . . .: 192.168.1.42\r\n"
           "   Masque de sous-réseau. . . . . . . . . : 255.255.255.0\r\n   IPv4 Address. . . : 169.254.3.3\r\n"
           "   IPv4 Address. . . . . . . . . . . : 10.1.2.3(Preferred)\r\n")
    L2, g2 = runtime(concert, os_name="Win64", exec_fn=lambda cmd: out)
    M2 = lib(L2)
    assert list(M2.local_ips().values()) == ["192.168.1.42", "10.1.2.3"]
    assert list(g2.state.execs[1].values())[0] == "ipconfig"
    L3, g3 = runtime(concert, os_name="Other", exec_fn=lambda cmd: "0\n192.168.0.7 172.17.0.1 fe80::1\n")
    assert list(lib(L3).local_ips().values()) == ["192.168.0.7", "172.17.0.1"]
    # dossier des concerts : réglages, sinon <Documents>/REAPER Media/Concerts
    res = concert[0]
    del g.state.ext["concert_dir"]
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": "fr", "concert_dir": "/shows/here"}), encoding="utf-8")
    assert M.concert_dir() == "/shows/here"
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": "fr", "projects_dir": "/proj"}), encoding="utf-8")
    assert M.concert_dir() == "/proj/Concerts"
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(json.dumps({"language": "fr"}), encoding="utf-8")
    assert M.concert_dir().endswith("Documents/REAPER Media/Concerts")
    assert res is not None


def test_lib_run_cli_mac_and_windows(concert, tmp_path):
    inst = tmp_path / "ReaCue"
    (inst / ".venv" / "bin").mkdir(parents=True)
    (inst / ".venv" / "bin" / "python").write_text("")
    (inst / ".venv" / "Scripts").mkdir(parents=True)
    (inst / ".venv" / "Scripts" / "pythonw.exe").write_text("")
    L, g = runtime(concert)
    g.state.ext["install_dir"] = str(inst)
    M = lib(L)
    ok = M.run_cli("concert", "/a b/it's.setlist.json")
    assert ok is True or (isinstance(ok, tuple) and ok[0])
    sh = list(g.state.shell.values())[0]
    assert "-m reacue_mcp.cli concert --setlist '/a b/it'\\''s.setlist.json'" in sh and "nohup" in sh
    # This fake POSIX launch never spawned a worker; Windows uses a fresh simulated session.
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").unlink(missing_ok=True)
    calls = []
    L2, g2 = runtime(concert, os_name="Win64", exec_fn=lambda cmd: calls.append(cmd) or "0\n")
    Path(str(inst) + "\\.venv\\Scripts\\pythonw.exe").write_text("")   # chemin « Windows » simulé
    g2.state.ext["install_dir"] = str(inst)
    M2 = lib(L2)
    M2.run_cli("concert", r"C:\Users\x\Shows\My show.setlist.json")
    line, timeout = list(g2.state.execs[1].values())
    assert timeout == -1 and "pythonw.exe" in line and 'concert --setlist "C:\\Users\\x\\Shows\\My show.setlist.json"' in line


# ---------------------------------------------------------------------------------------- fenêtre
@pytest.mark.parametrize("lang", ["fr", "en"])
def test_window_detached(concert, lang):
    res = concert[0]
    L, g = runtime(concert, lang=lang)
    gx = window(L, g)
    st = g.state
    st.cursor = res.songs[1]["bar1"] + 1.0
    frame(L, g); frame(L, g)
    T = texts(g)
    assert "Second Demo" in T and ("MORCEAU 2 / 3" if lang == "fr" else "SONG 2 / 3") in T, T   # espace avant le n°
    nxt = "Ensuite : 3 · Third Demo" if lang == "fr" else "Next: 3 · Third Demo"
    assert any(t.startswith(nxt) for t in T), T
    assert any(("mesure" if lang == "fr" else "bar") in t and "BPM" in t for t in T), T
    # transport : libellés des boutons (fenêtre ReaCue, onglet Scène)
    lab = (lambda fr, en: fr if lang == "fr" else en)
    def press(label):
        xy = find_text(g, label); assert xy, (label, texts(g))
        frame(L, g, (xy[0] + 2, xy[1] - 12))
    press(lab("Lecture", "Play")); assert st.play == 1                  # Lecture
    st.pos = st.cursor
    frame(L, g)
    assert ("Pause" in texts(g)) and (("Lecture" if lang == "fr" else "Playing") in texts(g))
    press("Stop"); assert st.play == 1                                  # Stop : 1er appui = armé
    assert ("encore ?" if lang == "fr" else "again?") in texts(g)
    st.t += 0.5
    xy = find_text(g, "encore ?" if lang == "fr" else "again?"); frame(L, g, (xy[0] + 2, xy[1] - 12))
    assert st.play == 0                                                  # 2e appui : stop
    frame(L, g)
    press(lab("SUIVANT", "NEXT"))                                        # à l'arrêt : Suivant en un appui (capitales)
    assert st.cursor == pytest.approx(res.songs[2]["start"])
    st.cursor = res.songs[1]["bar1"] + 1.0; frame(L, g)
    xy = find_text(g, "Solo"); assert xy
    frame(L, g, (xy[0] + 5, xy[1] + 6))
    solo = [r for r in concert[1] if r[3] == "Second Demo · Solo"][0]
    assert st.cursor == pytest.approx(solo[1])
    # PIN modifiable
    xy = find_text(g, "PIN "); assert xy
    st.inputs = "1357"; frame(L, g, (xy[0] + 4, xy[1] + 4)); assert st.persist["remote_pin"] == "1357"
    # télécommande dans la boucle
    st.ext["remote"] = "toggle||1357|w1"; frame(L, g)
    assert st.play == 1 and st.ext["remote_ack"] == "w1|ok"
    assert any(("téléphone" if lang == "fr" else "phone") in t for t in texts(g))
    st.atexit(); assert st.ext["remote_alive"] == ""


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_window_qr_decodes(concert, lang):
    zxing = pytest.importorskip("zxingcpp")
    pytest.importorskip("PIL")
    L, g = runtime(concert, lang=lang)
    gx = window(L, g)
    g.state.cursor = 5.0
    frame(L, g); frame(L, g)
    xy = find_text(g, "QR"); assert xy
    frame(L, g, (xy[0] + 3, xy[1] + 3)); frame(L, g)
    img = render(g, gx.w, gx.h)
    got = [r.text for r in zxing.read_barcodes(img)]
    assert got == ["http://192.168.1.20:8090/prompteur.html"], got
    pin_line = "Code PIN de la Régie : " if lang == "fr" else "Stage control PIN code: "
    assert any(t.startswith(pin_line) for t in texts(g))
    assert ("Même Wi-Fi que l'ordinateur" if lang == "fr" else "Same Wi-Fi as the computer") in texts(g)


def test_window_docked_and_empty(concert, tmp_path):
    res = concert[0]
    L, g = runtime(concert)
    gx = window(L, g, dock=1, h=64)
    gx.w = 1200
    g.state.cursor = res.songs[1]["bar1"] + 1
    frame(L, g)
    assert any("2 / 3 · Second Demo" in t for t in texts(g))
    x0 = gx.w - 5 * 50 - 50 - 12
    frame(L, g, (x0 + 2 * 50 + 22, 32)); assert g.state.play == 1
    # arrêt automatique dans la boucle
    g.state.pos = res.songs[1]["stop"] - 0.2; frame(L, g)
    g.state.pos = res.songs[1]["stop"] + 0.05; frame(L, g)
    assert g.state.play == 0 and g.state.cursor == pytest.approx(res.songs[2]["start"])
    # sans concert : onglet Scène vide, concerts existants à ouvrir
    L2, g2 = runtime(concert, lang="en", proj=tmp_path / "other.RPP")
    window(L2, g2)
    frame(L2, g2); frame(L2, g2)
    T = texts(g2)
    assert "No concert or song open" in T and any("Concert test" in t for t in T), T
    st = g2.state
    st.ext["remote"] = f"toggle||{st.persist['remote_pin']}|z1"; frame(L2, g2)
    assert st.ext["remote_ack"] == "z1|noconcert"


@pytest.mark.parametrize("name", ["ReaCue_Morceau_suivant.lua", "ReaCue_Morceau_precedent.lua"])
def test_next_prev_actions(concert, tmp_path, name):
    res = concert[0]
    L, g = runtime(concert)
    g.state.cursor = res.songs[1]["bar1"] + 3
    L.execute(f"dofile([[{LUA_DIR / name}]])")
    want = res.songs[2]["start"] if "suivant" in name else res.songs[1]["start"]
    assert g.state.cursor == pytest.approx(want)
    L2, g2 = runtime(concert, lang="en", proj=tmp_path / "other.RPP")
    L2.execute(f"dofile([[{LUA_DIR / name}]])")
    assert "not a ReaCue concert" in g2.state.msgbox
