"""Captures de la documentation : chaque vue de la fenêtre ReaCue, en français et en anglais.

Contenu entièrement fictif (concert et morceaux de démonstration construits par le vrai code Python,
adresse 192.168.1.20, PIN 1234). Sans REACUE_SHOTS, le test vérifie seulement que chaque vue s'affiche
sans texte coupé (U.fit, lignes de U.para en trop) ni texte qui déborde de la fenêtre. Avec REACUE_SHOTS=<dossier>,
il écrit window_<vue>_<langue>.png (rendu ×2) :

    REACUE_SHOTS=docs/images python -m pytest -q tests/test_doc_screenshots.py
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("lupa")
pytest.importorskip("PIL")

import test_concert_lua as TL  # noqa: E402
import test_reacue_window as W  # noqa: E402
from reacue_mcp import concert as C  # noqa: E402

SCALE = 2
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

LBL = {
    "fr": {"live": "Joué en live…", "structure_box": "Couplet 1"},
    "en": {"live": "Played live…", "structure_box": "Verse 1"},
}


# ------------------------------------------------------------------------------------- rendu PNG ×2
MONO = {"IBM Plex Mono", "Menlo", "Monaco", "Consolas", "Lucida Console", "Courier New"}
COND = {"Barlow Condensed", "Avenir Next Condensed", "Helvetica Neue Condensed Bold", "Arial Narrow", "Bahnschrift SemiCondensed"}


def _font(cache, size, bold, face=None):
    """police du rendu : DejaVu Sans (texte), Sans Mono (afficheurs), Sans Condensed Bold (titres condensés)"""
    from PIL import ImageFont
    kind = "mono" if face in MONO else ("cond" if face in COND else "sans")
    k = (size, bold, kind)
    if k not in cache:
        name = {"sans": "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                "mono": "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
                "cond": "DejaVuSansCondensed-Bold.ttf"}[kind]
        try:
            cache[k] = ImageFont.truetype(FONT_DIR + name, int(round(size * 0.9 * SCALE)))
        except OSError:
            # Some Linux images omit DejaVu Condensed; retain the requested text size.
            alternate = "/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf" if kind == "cond" else FONT_DIR + "DejaVuSans.ttf"
            try:
                cache[k] = ImageFont.truetype(alternate, int(round(size * 0.9 * SCALE)))
            except OSError:
                # A real font keeps accents and requested sizes when verifying on macOS.
                mac = {"sans": "Arial Bold.ttf" if bold else "Arial.ttf",
                       "mono": "Courier New Bold.ttf" if bold else "Courier New.ttf",
                       "cond": "Arial Narrow Bold.ttf"}[kind]
                try:
                    cache[k] = ImageFont.truetype("/System/Library/Fonts/Supplemental/" + mac,
                                                  int(round(size * 0.9 * SCALE)))
                except OSError:
                    cache[k] = ImageFont.load_default()
    return cache[k]


def render(g, w, h):
    from PIL import Image, ImageDraw
    S = SCALE
    img = Image.new("RGB", (int(w * S), int(h * S)), (0x16, 0x18, 0x1B))
    d = ImageDraw.Draw(img, "RGBA")
    fonts = {}
    col = lambda r, gg, b, a: (int(r * 255), int(gg * 255), int(b * 255), int(255 * (a if a is not None else 1)))
    for o in g.state.ops.values():
        o = list(o.values())
        k = o[0]
        if k == "rect":
            x, y, ww, hh, r, gg, b, a, fill = o[1:10]
            if ww > 0 and hh > 0:
                d.rectangle([x * S, y * S, (x + ww) * S - 1, (y + hh) * S - 1], fill=col(r, gg, b, a) if fill else None,
                            outline=None if fill else col(r, gg, b, a), width=1 if fill else S)
        elif k == "rrect":
            x, y, ww, hh, r, gg, b, a = o[1:9]
            d.rounded_rectangle([x * S, y * S, (x + ww) * S, (y + hh) * S], radius=6 * S, outline=col(r, gg, b, a), width=S)
        elif k == "circle":
            x, y, rad, r, gg, b, a = o[1:8]
            d.ellipse([(x - rad) * S, (y - rad) * S, (x + rad) * S, (y + rad) * S], fill=col(r, gg, b, a))
        elif k == "tri":
            p = [v * S for v in o[1:7]]
            r, gg, b, a = o[7:11]
            d.polygon([(p[0], p[1]), (p[2], p[3]), (p[4], p[5])], fill=col(r, gg, b, a))
        elif k == "line":
            x1, y1, x2, y2, r, gg, b, a = o[1:9]
            d.line([(x1 * S, y1 * S), (x2 * S, y2 * S)], fill=col(r, gg, b, a), width=2 * S)
        elif k == "text":
            x, y, s, size, flags, r, gg, b, a = o[1:10]
            face = o[10] if len(o) > 10 else None
            d.text((x * S, y * S), s, font=_font(fonts, size, flags == ord("b"), face), fill=col(r, gg, b, a))
    return img


# ------------------------------------------------------------------------------- contrôle du texte
FIT = "REACUE_CTX.U.on_cut = function(s) table.insert(state.cut, tostring(s)) end"


def watch(L):
    L.execute("state.cut = {}")
    L.execute(FIT)


def check_text(g, w):
    """aucun libellé coupé par U.fit ; aucun texte qui sort de la fenêtre (police du rendu)"""
    cut = list(g.state.cut.values())
    assert not cut, f"textes coupés : {cut}"
    fonts, over = {}, []
    for o in g.state.ops.values():
        o = list(o.values())
        if o[0] == "text" and o[3].strip():
            x, s, size, flags = o[1], o[3], o[4], o[5]
            face = o[10] if len(o) > 10 else None
            tw = _font(fonts, size, flags == ord("b"), face).getlength(s) / SCALE
            if x + tw > w + 1:
                over.append((s, round(x + tw - w)))
    assert not over, f"textes qui débordent : {over}"


def snap(L, g, name, lang):
    gx = L.globals().gfx
    L.execute("state.cut = {}; state.ops = {}")
    g.state.deferred()
    check_text(g, gx.w)
    if W.SHOTS:
        W.SHOTS.mkdir(parents=True, exist_ok=True)
        render(g, gx.w, gx.h).save(W.SHOTS / f"window_{name}_{lang}.png")
    return TL.texts(g)


@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return TL.make_concert(tmp_path_factory.mktemp("doc"))


def with_version(inst):
    """installation fictive : numéro de version lu par l'onglet Réglages"""
    from reacue_mcp import __version__
    (inst / "reacue_mcp").mkdir(exist_ok=True)
    (inst / "reacue_mcp" / "__init__.py").write_text(f'__version__ = "{__version__}"\n', encoding="utf-8")


def demo_home(L):
    L.execute("local ge = os.getenv; os.getenv = function(k) if k == 'HOME' then return '/Users/demo' end return ge(k) end")


def en_regions(L, lang):
    """morceau anglais : régions nommées en anglais (comme les créerait ReaCue en anglais)"""
    if lang == "en":
        L.execute('''for _, r in pairs(REGIONS) do
          r[4] = ({["Couplet 1"] = "Verse 1", ["Refrain 1"] = "Chorus 1"})[r[4]] or r[4] end''')


def en_concert_regions(L, lang):
    if lang == "en":
        L.execute('''local tr = { {"Pré%-refrain", "Pre-chorus"}, {"Couplet", "Verse"}, {"Refrain", "Chorus"}, {"Pont", "Bridge"} }
          for _, r in pairs(REGIONS) do for _, p in ipairs(tr) do r[4] = r[4]:gsub(p[1], p[2]) end end''')


def open_(L, g):
    gx = W.open_window(L, g)
    watch(L)
    W.frame(L, g); W.frame(L, g)
    return gx


# ------------------------------------------------------------------------------------------ vues
LANGS = ["fr", "en"]


@pytest.mark.parametrize("lang", LANGS)
def test_song_doall_newsong(concert, tmp_path, lang):
    L, g, res = W.song_runtime(concert, tmp_path, lang=lang)
    en_regions(L, lang)
    W.install(g, tmp_path, structure=True)
    g.state.projext["structure_engine"] = "songformer"
    g.state.projext["doubts"] = "16:moved"
    open_(L, g)
    T = snap(L, g, "song", lang)
    assert "Song One" in T and ("Prêt ✓" if lang == "fr" else "Ready ✓") in T, T
    # morceau tout juste créé par « + Nouveau morceau » : proposition de tout préparer
    L.execute("REACUE_CTX.propose_all = REACUE_CTX.proj_key")
    T = snap(L, g, "newsong", lang)
    assert any(t.startswith("Morceau créé." if lang == "fr" else "Song created.") for t in T), T
    L.execute("REACUE_CTX.propose_all = nil")
    # « Tout faire » en cours
    W.clear_status(g)
    L.execute("REACUE_CTX.tabs.song.do_all()")
    W.frame(L, g)
    g.state.t += 12
    T = snap(L, g, "doall", lang)
    assert ("Arrêter" if lang == "fr" else "Stop") in T, T


@pytest.mark.parametrize("lang", LANGS)
def test_structure_edit(concert, tmp_path, lang):
    L, g, res = W.song_runtime(concert, tmp_path, lang=lang)
    en_regions(L, lang)
    W.install(g, tmp_path, structure=True)
    g.state.projext["structure_engine"] = "songformer"
    g.state.projext["doubts"] = "5:moved"
    open_(L, g)
    x, y = W.band_box(g, LBL[lang]["structure_box"])
    TL.frame(L, g, (x + 2, y + 2)); W.frame(L, g)
    T = snap(L, g, "structure", lang)
    assert ("Fusionner →" if lang == "fr" else "Merge →") in T, T


@pytest.mark.parametrize("lang", LANGS)
def test_stage_live_check_qr(concert, lang):
    res = concert[0]
    C.set_live_profile(res.setlist, live=["drums"], exceptions={}, replace_exceptions=True)
    try:
        L, g = W.rt(concert, lang=lang)
        g.state.ext["remote_pin"] = "1234"
        en_concert_regions(L, lang)
        g.state.cursor = res.songs[1]["bar1"] + 1
        open_(L, g)
        T = snap(L, g, "stage", lang)
        assert ("MORCEAU 2 / 3" if lang == "fr" else "SONG 2 / 3") in T, T
        W.press_text(L, g, LBL[lang]["live"], exact=True)
        T = snap(L, g, "live", lang)
        assert "2. Second Demo" in T, T
        L.execute("REACUE_CTX.overlay = nil")
        L.execute("REACUE_CTX.open_check()")
        W.frame(L, g)
        T = snap(L, g, "check", lang)
        assert ("Contrôle avant concert" if lang == "fr" else "Pre-show check") in T, T
        L.execute("REACUE_CTX.overlay = nil")
        L.execute("REACUE_CTX.open_qr()")
        T = snap(L, g, "qr", lang)
        assert "http://192.168.1.20:8090/prompteur.html" in T and any("1234" in t for t in T), T
    finally:
        C.set_live_profile(res.setlist, live=[], exceptions={}, replace_exceptions=True)


@pytest.mark.parametrize("lang", LANGS)
def test_concert_compose(concert, tmp_path, lang):
    res = concert[0]
    projects = res.rpp.parent.parent / "projects"
    L, g = W.rt(concert, lang=lang, proj=tmp_path / "empty.RPP", tracks=False)
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": lang, "projects_dir": str(projects)}), encoding="utf-8")
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    W.install(g, tmp_path)
    open_(L, g)
    L.execute('REACUE_CTX.goto_tab("concert")'); W.frame(L, g)
    for name in ("Second Demo", "Demo Song"):
        x, y = W.text_xy(g, name)
        TL.frame(L, g, (x + int((L.globals().gfx.w - 44) / 2) - 20, y + 4)); W.frame(L, g)
    g.state.inputs = "Samedi" if lang == "fr" else "Saturday"
    W.press_text(L, g, "Renommer" if lang == "fr" else "Rename"); W.frame(L, g)
    T = snap(L, g, "concert", lang)
    assert "1. Second Demo" in T, T


@pytest.mark.parametrize("lang", LANGS)
def test_concert_batch(concert, tmp_path, lang):
    projects = tmp_path / "projects"
    projects.mkdir()
    for name, ready in (("Alpha", True), ("Bravo", False), ("Charlie", False)):
        body = '<REAPER_PROJECT\n  MARKER 1 0 "Intro" 1\n  <TRACK\n    NAME CLICK\n  >\n>\n' if ready else "<REAPER_PROJECT\n>\n"
        (projects / f"{name}.RPP").write_text(body, encoding="utf-8")
    L, g = W.rt(concert, lang=lang, proj=tmp_path / "empty.RPP", tracks=False)
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": lang, "projects_dir": str(projects)}), encoding="utf-8")
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    W.install(g, tmp_path)
    open_(L, g)
    L.execute('REACUE_CTX.goto_tab("concert")'); W.frame(L, g)
    L.execute("""
      local mo = reaper.Main_openProject
      reaper.Main_openProject = function(p) mo(p); PROJFILE = p:gsub("^noprompt:", "")
        TRACKS = { {name="Chant"}, {name="Batterie"} }
        ITEMS = { {track=1, file="/x/a-vocals.wav"}, {track=2, file="/x/a-drums.wav"} }
      end""")
    W.press_text(L, g, "Préparer tous les morceaux" if lang == "fr" else "Prepare all")
    g.state.t += 20
    T = snap(L, g, "batch", lang)
    assert "Bravo" in T and "Charlie" in T, T


@pytest.mark.parametrize("lang", LANGS)
def test_assistant_and_settings(concert, tmp_path, lang):
    L, g = W.rt(concert, lang=lang, proj=tmp_path / "x.RPP", tracks=False)
    g.state.ext["assistant_seen"] = ""
    g.state.ext["concert_dir"] = ""
    g.state.ext["remote_pin"] = "1234"
    with_version(W.install(g, tmp_path, stems=True))
    demo_home(L)
    open_(L, g)
    T = snap(L, g, "assistant", lang)
    assert ("Bienvenue dans ReaCue" if lang == "fr" else "Welcome to ReaCue") in T, T
    W.press_text(L, g, "Terminer" if lang == "fr" else "Finish", exact=True)
    L.execute('REACUE_CTX.goto_tab("settings")'); W.frame(L, g)
    T = snap(L, g, "settings_models", lang)
    assert ("Essentiel" if lang == "fr" else "Essential") in T, T
    assert g.REACUE_CTX.layout_h < 800
    L.execute('REACUE_CTX.tabs.settings.set_page("live")'); W.frame(L, g)
    L.execute("REACUE_CTX.tabs.settings.set_advanced(false)"); W.frame(L, g)
    T = snap(L, g, "settings", lang)
    assert ("Langue" if lang == "fr" else "Language") in T, T
    L.execute("REACUE_CTX.tabs.settings.set_advanced(true)"); W.frame(L, g)
    T = snap(L, g, "settings_advanced", lang)
    assert ("Volume du click" if lang == "fr" else "Click volume") in T, T


@pytest.mark.parametrize("lang", LANGS)
def test_lighting_tab(concert, tmp_path, lang):
    """onglet Lumière : cues exportés (morceau fictif), cue en cours, sorties fictives, pistes TIMECODE"""
    import test_lighting_tab as LT
    L, g, res = LT.song_rt(concert, tmp_path, lang=lang, gma3_ltc_output=7, gma3_mtc_output="IAC Driver Bus 1",
                           gma3_tc_start="01:00:00:00", gma3_tc_slot=1)
    en_regions(L, lang)
    if lang == "en":
        www = Path(g.RES) / "reaper_www_root" / "reacue_song.json"
        d = json.loads(www.read_text(encoding="utf-8"))
        for q in d["lighting"]["cues"]:
            q["name"] = {"Couplet 1": "Verse 1", "Refrain 1": "Chorus 1"}.get(q["name"], q["name"])
        www.write_text(json.dumps(d), encoding="utf-8")
    LT.add_tc_tracks(L, ("LTC", "MTC"))
    W.install(g, tmp_path, structure=True)
    open_(L, g)
    L.execute('REACUE_CTX.goto_tab("lighting")')
    g.state.play, g.state.pos = 1, 13.0
    W.frame(L, g)
    T = snap(L, g, "lighting", lang)
    assert "01:00:13:00" in T and ("Envoyer 10 s de test" if lang == "fr" else "Send a 10 s test") in T, T
    g.state.play = 0
