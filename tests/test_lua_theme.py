"""Fenêtre ReaCue, apparence « Studio pro » : thème centralisé dans ReaCue_ui.lua (mêmes couleurs que ReaCue
Studio), polices monospace / condensée avec repli selon le système, majuscules accentuées, bords nets ; et la
commande télécommande « tctest » (bouton TEST 10 S des écrans Concert / Lumière de ReaCue Studio)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / "reaper"
WINDOW_FILES = ["ReaCue.lua", "ReaCue_assistant.lua", "ReaCue_flow.lua", "ReaCue_guide.lua", "ReaCue_newsong.lua"] + \
    sorted(p.name for p in LUA.glob("ReaCue_tab_*.lua"))


# --------------------------------------------------------------------------------------- statique
def test_colours_are_centralised_in_ui_theme():
    """aucune couleur RVB en dur ni arrondi dans la fenêtre : tout passe par U.<NOM> (ReaCue_ui.lua)"""
    for name in WINDOW_FILES:
        src = (LUA / name).read_text(encoding="utf-8")
        assert not re.search(r"\{\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\}", src), name
        assert "gfx.roundrect" not in src, name
        assert not re.search(r"gfx\.set\(\s*[\d.]+\s*,", src.replace("gfx.set(1, 1, 1, 1)", "").replace("gfx.set(0, 0, 0, 1)", "")), name
    ui = (LUA / "ReaCue_ui.lua").read_text(encoding="utf-8")
    assert "gfx.roundrect" not in ui


def test_theme_matches_studio_web_palette():
    ui = (LUA / "ReaCue_ui.lua").read_text(encoding="utf-8")
    theme = dict((k, "#%02X%02X%02X" % tuple(int(v, 16) for v in rgb))
                 for k, *rgb in re.findall(r"(\w+) = \{ 0x(\w\w), 0x(\w\w), 0x(\w\w) \}", ui))
    css = (ROOT / "reacue_mcp" / "web" / "reacue_studio" / "base.css").read_text(encoding="utf-8")
    css += (ROOT / "reacue_mcp" / "web" / "reacue_studio" / "studio-pro.css").read_text(encoding="utf-8")
    tokens = {k: v.upper() for k, v in re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", css)}
    pairs = {"bg": "bg", "panel": "panel", "inset": "inset", "edge": "edge", "raise": "raise", "ink": "ink",
             "mute": "mute", "dim": "dim", "sig": "sig", "led": "led", "lcd": "lcd", "smpte": "smpte", "red": "red"}
    for lua_k, css_k in pairs.items():
        assert theme[lua_k] == tokens[css_k], (lua_k, theme[lua_k], tokens[css_k])
    # valeurs demandées pour la fenêtre
    assert (theme["bg"], theme["panel"], theme["inset"], theme["edge"], theme["ink"], theme["mute"]) == \
        ("#151719", "#202326", "#101214", "#0C0D0F", "#E6E8EB", "#8A9099")
    assert (theme["sig"], theme["led"], theme["lcd"], theme["smpte"]) == ("#FF8737", "#30DF75", "#F2C230", "#8FD1FF")


# --------------------------------------------------------------------------------------- Lua
lupa = pytest.importorskip("lupa")

FAKE = r"""
reaper = { time_precise = function() return 0 end }
FONTW = {}
DRAW = {}
local font = { 14, 0, "" }
READY = true
gfx = { w = 500, h = 300, x = 0, y = 0 }
function gfx.setfont(i, face, size, flags) font = { size or 14, flags or 0, face } end
function gfx.measurestr(s)
  if not READY then return 0, 0 end
  return utf8.len(s) * font[1] * (FONTW[font[3] or ""] or 0.55), font[1]
end
function gfx.set() end
function gfx.drawstr(s) table.insert(DRAW, { s, font[3], font[1], font[2] }) end
function gfx.rect() end
function gfx.circle() end
function gfx.line() end
"""


def ui(is_windows=False, fonts=None, ready=True):
    L = lupa.LuaRuntime(unpack_returned_tuples=True)
    L.execute(FAKE)
    for k, v in (fonts or {}).items():
        L.execute(f'FONTW["{k}"] = {v}')
    L.execute(f"READY = {'true' if ready else 'false'}")
    U = L.execute(f"return dofile([[{LUA / 'ReaCue_ui.lua'}]])")
    U.init(is_windows)
    return L, U


@pytest.mark.parametrize("win,fonts,mono,cond", [
    (False, {"Menlo": 0.6, "Avenir Next Condensed": 0.5}, "Menlo", "Avenir Next Condensed"),
    (False, {"Monaco": 0.6, "Arial Narrow": 0.5}, "Monaco", "Arial Narrow"),
    (False, {}, "Courier New", "Arial"),                                           # repli
    (True, {"Consolas": 0.6, "Arial Narrow": 0.5}, "Consolas", "Arial Narrow"),
    (True, {"Bahnschrift SemiCondensed": 0.5}, "Courier New", "Bahnschrift SemiCondensed"),
    (True, {}, "Courier New", "Arial"),
])
def test_fonts_pick_first_installed_with_fallback(win, fonts, mono, cond):
    L, U = ui(win, fonts)
    assert U.face("mono") == mono and U.face("cond") == cond
    assert U.face("sans") == ("Arial" if win else "Helvetica")
    # le texte d'un afficheur LCD est dessiné dans la police monospace, un titre dans la condensée (en gras)
    U.lcd("Reste", "0:53", 0, 0, 120, 50)
    U.title("Comète", 0, 0, 30)
    d = [list(x.values()) for x in L.globals().DRAW.values()]
    assert ["RESTE", "Helvetica" if not win else "Arial"] == d[0][:2]
    assert d[1][:2] == ["0:53", mono]
    assert d[2][:2] == ["COMÈTE", cond] and d[2][3] == ord("b")


def test_fonts_not_cached_before_window_exists():
    L, U = ui(False, {"Menlo": 0.6}, ready=False)
    assert U.face("mono") == "Courier New"          # pas encore mesurable : repli provisoire
    L.execute("READY = true")
    assert U.face("mono") == "Menlo"                 # puis la vraie police une fois la fenêtre ouverte


def test_upper_handles_french_accents():
    _, U = ui()
    assert U.upper("élan à l'œuvre, déjà vu ça ? ïle ÿ") == "ÉLAN À L'ŒUVRE, DÉJÀ VU ÇA ? ÏLE Ÿ"
    assert U.upper("Pré-refrain 2") == "PRÉ-REFRAIN 2"
    assert U.upper("Paroles — à revoir → ✓") == "PAROLES — À REVOIR → ✓"


def test_paragraph_preserves_utf8_in_mac_locale():
    L, U = ui()
    text = "Les changements s'appliquent à la prochaine préparation."
    U.para(text, 0, 0, 900, 12, U.INK)
    assert [line[1] for line in L.globals().DRAW.values()] == [text]


def test_button_styles_use_theme():
    L, U = ui()
    th = {k: tuple(v.values()) for k, v in U.THEME.items()}
    fill, ink = U.style_cols("primary")
    assert tuple(fill.values()) == th["sig"] and tuple(ink.values()) == th["bg"]
    fill, ink = U.style_cols(None)
    assert tuple(fill.values()) == th["raise"] and tuple(ink.values()) == th["ink"]
    fill, _ = U.style_cols("armed")
    assert tuple(fill.values()) == th["lcd"]
    assert tuple(U.ACCENT.values()) == th["led"] and tuple(U.WARN.values()) == th["lcd"]


# ------------------------------------------------------------------- télécommande : TEST 10 S (tctest)
def test_remote_tctest_starts_and_stops_timecode_test(tmp_path_factory, tmp_path):
    import test_concert_lua as TL
    import test_lighting_tab as LT
    import test_reacue_window as W
    concert = TL.make_concert(tmp_path_factory.mktemp("tct"))
    L, g, _ = LT.song_rt(concert, tmp_path, gma3_ltc_output=7)
    LT.add_tc_tracks(L, ("LTC",))
    W.open_window(L, g)
    W.frame(L, g); W.frame(L, g)
    M, lib = LT.tab(L), TL.lib(L)
    st = g.state
    pin = lib.remote_pin()
    st.ext["remote"] = f"tctest||{pin}|t1"
    W.frame(L, g)
    assert st.ext["remote_ack"] == "t1|ok" and M.test_active()
    assert st.ext["tctest"] == "10"                                  # secondes restantes publiées
    assert LT.tracks(g)["TIMECODE LTC"].solo == 1
    st.t += 3.2
    W.frame(L, g)
    assert st.ext["tctest"] == "7"
    st.ext["remote"] = f"tctest||{pin}|t2"                           # 2e appui : arrêt, tout est rétabli
    W.frame(L, g)
    assert st.ext["remote_ack"] == "t2|ok" and not M.test_active() and st.ext["tctest"] == ""
    assert (LT.tracks(g)["TIMECODE LTC"].solo or 0) == 0
    # sans piste TIMECODE : refusé (« bad »), message dans la fenêtre
    L.execute('for i = #TRACKS, 1, -1 do if TRACKS[i].name:match("^TIMECODE") then table.remove(TRACKS, i) end end')
    st.ext["remote"] = f"tctest||{pin}|t3"
    W.frame(L, g)
    assert st.ext["remote_ack"] == "t3|bad" and not M.test_active()
    # mauvais PIN
    st.ext["remote"] = "tctest||0000|t4" if pin != "0000" else "tctest||1111|t4"
    W.frame(L, g)
    assert st.ext["remote_ack"] == "t4|badpin"
