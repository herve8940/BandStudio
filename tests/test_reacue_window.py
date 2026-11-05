"""Fenêtre « ReaCue » en 4 onglets (Morceau, Concert, Scène, Réglages) et instruments (mute / solo / joué en
live) : Lua 5.4 via lupa, API REAPER simulée (tests/test_concert_lua.py), concert et morceaux de démonstration
fictifs construits par le vrai code Python. Captures de la documentation : tests/test_doc_screenshots.py."""
import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("lupa")

import test_concert_lua as TL  # noqa: E402
from reacue_mcp import concert as C  # noqa: E402

LUA_DIR = TL.LUA_DIR
SHOTS = Path(os.environ.get("REACUE_SHOTS", "")) if os.environ.get("REACUE_SHOTS") else None

EXTRA = r"""
state.marker_ops, state.undo, state.menu, state.menus = {}, 0, 0, {}
reaper.SetProjectMarker4 = function(p, idx, isrgn, pos, rend, name, color, flags)
  local r = REGIONS[idx]; if r then r[2] = pos; r[3] = rend; r[4] = name end
  table.insert(state.marker_ops, {"set", idx, pos, rend, name}); return true end
reaper.AddProjectMarker2 = function(p, isrgn, pos, rend, name, want, color)
  table.insert(REGIONS, {true, pos, rend, name, color}); table.insert(state.marker_ops, {"add", pos, rend, name}); return #REGIONS end
reaper.DeleteProjectMarker = function(p, idx, isrgn) table.remove(REGIONS, idx); table.insert(state.marker_ops, {"del", idx}); return true end
reaper.Undo_BeginBlock = function() state.undo = state.undo + 1 end
reaper.Undo_EndBlock = function() end
reaper.UpdateTimeline = function() end
reaper.GetProjectLength = function() return PROJLEN or 0 end
reaper.TimeMap2_GetDividedBpmAtTime = function(p, t) return BPM or 120 end
reaper.EnumerateFiles = function(dir, i) return LISTFILES(dir, i) end
reaper.EnumerateSubdirectories = function(dir, i) return LISTDIRS(dir, i) end
reaper.get_action_context = function() return false, ACTION or "" end
reaper.RecursiveCreateDirectory = function(d) MKDIR(d); return 1 end
reaper.GetMediaItem_Track = function(it) return TRACKS[it.track] end
state.projext, state.saves = {}, 0
reaper.GetProjExtState = function(p, s, k) local v = state.projext[k]; return v and 1 or 0, v or "" end
reaper.SetProjExtState = function(p, s, k, v) state.projext[k] = v; return 1 end
reaper.Main_SaveProject = function() state.saves = state.saves + 1 end
reaper.AddRemoveReaScript = function(add, sec, f, commit) state.added_script = f; return 55555 end
local _gfx = gfx
gfx = setmetatable({}, {__index = function(t, k)
  if k == "showmenu" then return function(s) table.insert(state.menus, s); return state.menu end end
  if k == "line" then return function(x1, y1, x2, y2) table.insert(state.ops, {"line", x1, y1, x2, y2,
    state.color[1], state.color[2], state.color[3], state.color[4]}) end end
  return _gfx[k] end, __newindex = function(t, k, v) _gfx[k] = v end})
"""


def lister(kind):
    def f(d, i):
        try:
            p = Path(str(d))
            names = sorted(x.name for x in p.iterdir() if (x.is_dir() if kind == "dirs" else x.is_file()))
        except OSError:
            return None
        return names[i] if i < len(names) else None
    return f


@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return TL.make_concert(tmp_path_factory.mktemp("win"))


def rt(concert, lang="fr", proj=None, tracks=True, heartbeat=True):
    L, g = TL.runtime(concert, lang=lang, proj=proj)
    L.execute(EXTRA)
    g.LISTFILES = lister("files")
    g.LISTDIRS = lister("dirs")
    g.MKDIR = lambda d: os.makedirs(str(d), exist_ok=True)
    rdir = Path(g.RES)
    (rdir / "reaper_www_root").mkdir(exist_ok=True)
    if heartbeat:
        (rdir / "ReaCueMCP" / "heartbeat.txt").write_text(str(int(time.time())), encoding="utf-8")
    if tracks:
        L.execute("""TRACKS = { {name="Chant"}, {name="Batterie"}, {name="Basse"}, {name="Guitares"},
                                {name="CUES"}, {name="VOIX"}, {name="CLICK", main=0, sends={2}} }; NOUT = 4""")
    return L, g


def open_window(L, g, script="ReaCue.lua"):
    g.ACTION = str(LUA_DIR / script)
    L.execute(f"dofile([[{LUA_DIR / script}]])")
    return L.globals().gfx


def frame(L, g, click=None, hold=None):
    TL.frame(L, g, click)


def press_text(L, g, label, dy=3, exact=False):
    for up in (False, True):                   # 2e passage : libellé en capitales (thème Studio pro)
        want = label.upper() if up else label
        for o in g.state.ops.values():
            o = list(o.values())
            got = o[3].upper() if up and o[0] == "text" else o[3]
            if o[0] == "text" and ((got == want) if exact else (want in got)):
                TL.frame(L, g, (o[1] + 3, o[2] + dy))
                return True
    raise AssertionError((label, TL.texts(g)))


def click_release(L, g, x, y):
    """appui puis relâchement (boutons à appui long)"""
    gx = L.globals().gfx
    gx.mouse_x, gx.mouse_y, gx.mouse_cap = x, y, 1
    g.state.deferred()
    gx.mouse_cap = 0
    L.execute("state.ops = {}")
    g.state.deferred()


def text_xy(g, label):
    xy = TL.find_text(g, label)
    assert xy, (label, TL.texts(g))
    return xy


def mutes(g):
    return {t.name: t.mute or 0 for t in g.TRACKS.values() if t.name not in ("CUES", "VOIX", "CLICK")}


@pytest.mark.parametrize("cached", [True, False])
def test_stems_import_refusal_is_reported_to_flow(concert, cached):
    L, g = rt(concert)
    open_window(L, g)
    g.cached = cached
    L.execute('''
      local ctx = REACUE_CTX
      ctx.S.start = function() return {ready = cached} end
      ctx.S.poll = function() return "ready" end
      ctx.S.finish = function() return nil, "source item is no longer in this project" end
      results = {}
      started = ctx.start_stems(function(state, message)
        results[#results + 1] = {state, message}
      end, true)
    ''')
    assert g.started
    if not cached:
        frame(L, g)
    assert len(g.results) == 1
    assert list(g.results[1].values()) == ["error", "source item is no longer in this project"]
    assert g.REACUE_CTX.job is None


# ------------------------------------------------------------------------------- instruments (lib)
def test_mix_profile_exceptions_solo_hearall_and_rehearsal(concert, tmp_path):
    res = concert[0]
    C.set_live_profile(res.setlist, live=["Batterie", "guitars"], exceptions={"Second Demo": {"drums": "stem"}},
                       replace_exceptions=True)
    L, g = rt(concert)
    M = TL.lib(L)
    c = M.load_concert()
    st = g.state
    st.cursor = res.songs[0]["bar1"] + 1
    assert M.mix_tick(c, 1000.0)
    assert mutes(g) == {"Chant": 0, "Batterie": 1, "Basse": 0, "Guitares": 1}
    assert st.ext["mix"].startswith("vocals=1,drums=0L,bass=1,guitars=0L;;0;1"), st.ext["mix"]
    # morceau 2 : exception (batterie en stem)
    st.cursor = res.songs[1]["bar1"] + 1
    M.mix_tick(c, 1000.1)
    assert mutes(g)["Batterie"] == 0 and mutes(g)["Guitares"] == 1
    # choix manuels : mute, solo, tout entendre ; effacés en changeant de morceau
    assert M.mix_toggle(c, "Basse") and mutes(g)["Basse"] == 1
    assert M.mix_solo(c, "Chant") and mutes(g) == {"Chant": 0, "Batterie": 1, "Basse": 1, "Guitares": 1}
    assert M.mix_solo(c, "vocals") and mutes(g)["Basse"] == 1          # solo off : choix manuel gardé
    M.mix_hear_all(c, True); assert set(mutes(g).values()) == {0}
    M.mix_hear_all(c, False); assert mutes(g) == {"Chant": 0, "Batterie": 0, "Basse": 0, "Guitares": 1}
    M.mix_toggle(c, "Basse")
    st.cursor = res.songs[2]["bar1"] + 1
    M.mix_tick(c, 1000.2)
    assert mutes(g) == {"Chant": 0, "Batterie": 1, "Basse": 0, "Guitares": 1}
    # télécommande (PIN)
    pin = M.remote_pin()
    st.ext["remote"] = f"mute|Chant|{pin}|m1"; assert tuple(M.remote_poll(c)) == ("mute", "ok") and mutes(g)["Chant"] == 1
    st.ext["remote"] = f"solo|bass|{pin}|m2"; M.remote_poll(c); assert mutes(g)["Basse"] == 0 and mutes(g)["Chant"] == 1
    st.ext["remote"] = f"hearall|1|{pin}|m3"; M.remote_poll(c); assert set(mutes(g).values()) == {0}
    st.ext["remote"] = f"mute|tuba|{pin}|m4"; assert tuple(M.remote_poll(c)) == ("mute", "bad")
    st.ext["remote"] = f"hearall|0|{pin}|m5"; M.remote_poll(c)
    # profil modifié par Claude (setlist) : relu et appliqué sans reconstruire
    C.set_live_profile(res.setlist, live=["vocals"])
    M.mix_tick(c, 1010.0)
    assert mutes(g) == {"Chant": 1, "Batterie": 0, "Basse": 0, "Guitares": 0}
    # édition depuis la fenêtre : écrite dans la setlist, lisible par Python
    assert M.live_toggle(c, "Basse")
    d = json.loads(res.setlist.read_text(encoding="utf-8"))
    assert d["live"] == ["vocals", "bass"] and mutes(g)["Basse"] == 1
    assert M.live_exc_cycle(c, 1, "bass")
    d = json.loads(res.setlist.read_text(encoding="utf-8"))
    assert d["live_exceptions"]["Demo Song"] == {"bass": "stem"} and d["songs"] and d["name"] == "Concert test"
    assert C.load_setlist(res.setlist)["live"] == ["vocals", "bass"]
    # Vérifier : ligne d'information
    lst = {x.id: x for x in M.run_checks(c).values()}
    assert lst["mix"].status == "info" and "Chant" in lst["mix"].detail
    # répétition : la mesure de décompte coupe tout, un mute changé pendant ce temps est rétabli correctement
    secs = M.song_sections(c, 3)
    M.loop_set(c, secs[1], secs[1])
    assert set(mutes(g).values()) == {1}
    M.mix_toggle(c, "Chant")                     # pendant la mesure de décompte
    assert mutes(g)["Chant"] == 1
    st.play = 1
    M.loop_tick(secs[1].start - 0.5, secs[1].start)
    assert mutes(g)["Chant"] == 0 and mutes(g)["Batterie"] == 0
    M.set_rehearsal(False)
    C.set_live_profile(res.setlist, live=[], exceptions={}, replace_exceptions=True)


# ---------------------------------------------------------------------------------- fenêtre / onglets
@pytest.mark.parametrize("lang", ["fr", "en"])
def test_window_tabs_auto_and_handoff(concert, tmp_path, lang):
    L, g = rt(concert, lang=lang)
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    names = ["Morceau", "Concert", "Scène", "Réglages"] if lang == "fr" else ["Song", "Concert", "Stage", "Settings"]
    for n in names:
        assert n in T, T
    # projet concert : onglet Scène choisi tout seul
    assert ("Précédent" if lang == "fr" else "Previous") in T and ("MORCEAU 1 / 3" if lang == "fr" else "SONG 1 / 3") in T
    assert ("Batterie" if lang == "fr" else "Drums") in T                 # rangée Instruments
    press_text(L, g, names[3], exact=True); frame(L, g)
    assert ("Modèles" if lang == "fr" else "Models") in TL.texts(g)
    press_text(L, g, "Live et système" if lang == "fr" else "Live and system", exact=True); frame(L, g)
    assert ("Langue" if lang == "fr" else "Language") in TL.texts(g)
    press_text(L, g, names[1], exact=True); frame(L, g)
    assert ("Concerts existants" if lang == "fr" else "Existing concerts") in TL.texts(g)
    assert g.state.persist["tab"] == "concert"
    # une 2e action ReaCue (« ReaCue - Concert ») ne rouvre pas de fenêtre : elle demande l'onglet Scène
    g.state.t += 0.2
    frame(L, g)
    assert g.state.ext["win_alive"] != ""
    g.ACTION = str(LUA_DIR / "ReaCue_Concert.lua")
    before = len(list(g.state.ops.values()))
    L.execute(f"REACUE_START_TAB = nil; dofile([[{LUA_DIR / 'ReaCue_Concert.lua'}]])")
    assert g.state.ext["win_goto"] == "stage"
    frame(L, g)
    assert ("Précédent" if lang == "fr" else "Previous") in TL.texts(g) and before >= 0
    g.state.atexit()
    assert g.state.ext["win_alive"] == "" and g.state.ext["remote_alive"] == ""


def test_stage_instruments_click_long_press_and_live_view(concert):
    res = concert[0]
    C.set_live_profile(res.setlist, live=["drums"], exceptions={}, replace_exceptions=True)
    L, g = rt(concert)
    open_window(L, g)
    st = g.state
    st.cursor = res.songs[1]["bar1"] + 1
    frame(L, g); frame(L, g)
    assert mutes(g)["Batterie"] == 1 and "coupé" in TL.texts(g)
    # clic court : mute de la basse (à l'arrêt : un seul appui)
    x, y = text_xy(g, "Basse")
    click_release(L, g, x + 3, y + 3)
    assert mutes(g)["Basse"] == 1
    # appui long : solo
    gx = L.globals().gfx
    gx.mouse_x, gx.mouse_y, gx.mouse_cap = x + 3, y + 3, 1
    st.deferred(); st.t += 0.7; st.deferred()
    gx.mouse_cap = 0; st.deferred()
    assert mutes(g) == {"Chant": 1, "Batterie": 1, "Basse": 0, "Guitares": 1}
    # pendant la lecture (hors répétition) : double appui
    L.execute("state.ops = {}"); st.deferred()
    press_text(L, g, "Tout entendre")
    assert set(mutes(g).values()) == {0}
    st.play = 1; st.pos = st.cursor
    L.execute("state.ops = {}"); st.deferred()
    x, y = text_xy(g, "Chant")
    click_release(L, g, x + 3, y + 3)
    frame(L, g)
    assert mutes(g)["Chant"] == 0 and "encore ?" in TL.texts(g)
    st.t += 0.3
    click_release(L, g, x + 3, y + 3)
    assert mutes(g)["Chant"] == 1
    st.play = 0
    # vue « Joué en live » : cases et exceptions par morceau
    L.execute("state.ops = {}"); st.deferred()
    press_text(L, g, "Joué en live")
    frame(L, g)
    T = TL.texts(g)
    assert "Exceptions par morceau  ·  clic : stem / live / profil" in T and "2. Second Demo" in T, T
    press_text(L, g, "Basse", exact=True)
    assert json.loads(res.setlist.read_text(encoding="utf-8"))["live"] == ["drums", "bass"]
    C.set_live_profile(res.setlist, live=[], exceptions={}, replace_exceptions=True)


def song_runtime(concert, tmp_path, lang="fr"):
    """Projet d'un morceau seul (démo) : régions à 120 BPM, stems dans un dossier, paroles."""
    res = concert[0]
    d = tmp_path / "Song One"
    d.mkdir(exist_ok=True)
    files = []
    for name in ("Song One-A minor-120bpm-vocals.wav", "Song One-A minor-120bpm-drums.wav"):
        (d / name).write_bytes(b"RIFF")
        files.append(d / name)
    (d / "paroles.txt").write_text("[Couplet]\nligne un\nligne deux\n\nligne trois\n", encoding="utf-8")
    proj = tmp_path / "Song One.RPP"
    proj.write_text("<REAPER_PROJECT\n>\n", encoding="utf-8")
    L, g = rt(concert, lang=lang, proj=proj, tracks=False)
    L.execute(f"""
      TRACKS = {{ {{name="Chant"}}, {{name="Batterie"}}, {{name="CLICK"}} }}
      ITEMS = {{ {{track=1, file=[[{files[0]}]]}}, {{track=2, file=[[{files[1]}]]}} }}
      BARS = {{}}; for k = 0, 40 do BARS[k + 1] = 4.0 + k * 2.0 end
      REGIONS = {{ {{true, 4.0, 12.0, "Intro", 0x5A7FA8}}, {{true, 12.0, 30.0, "Couplet 1", 0x3E9E7A}}, {{true, 30.0, 46.0, "Refrain 1", 0xC2554F}} }}
      PROJLEN = 46; BPM = 120
    """)
    return L, g, res


def status(g, **kw):
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").write_text(json.dumps(kw), encoding="utf-8")


def clear_status(g):
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").unlink(missing_ok=True)


def install(g, tmp_path, structure=False, stems=False):
    inst = tmp_path / "inst"
    (inst / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (inst / ".venv" / "bin" / "python").write_text("")
    if structure:
        (inst / ".venv-structure" / "bin").mkdir(parents=True, exist_ok=True)
        (inst / ".venv-structure" / "bin" / "python").write_text("")
        (inst / "reacue_structure.py").write_text("")
    if stems:
        (inst / ".venv-demucs" / "bin").mkdir(parents=True, exist_ok=True)
        (inst / ".venv-demucs" / "bin" / "python").write_text("")
    g.state.ext["install_dir"] = str(inst)
    return inst


def test_song_tab_prepare_structure_lyrics_and_add_to_concert(concert, tmp_path):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path, structure=True)
    g.state.projext["structure_engine"] = "songformer"
    g.state.projext["doubts"] = "16:moved"
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Song One" in T and "Morceau" in T
    assert any("21 mesures · Am" in t for t in T), T
    # grand bouton : morceau prêt ; pastilles d'état
    assert "Prêt ✓" in T and "Tout faire" in T and "Re-préparer" in T and "Réanalyser depuis zéro" in T
    assert "Mettre à jour les téléphones" in T, T
    for p in ("Stems ✓", "Structure : SongFormer ✓", "120 BPM", "Paroles : 3 lignes", "Accords —", "Prompteur —"):
        assert p in T, (p, T)
    assert "Intro" in T and "Couplet 1" in T and any("4 mes." in t for t in T)
    # longueurs inhabituelles signalées (Couplet 1 : 9 mesures) ; ligne d'aide au survol
    assert any("9 mes." in t for t in T)
    x, y = text_xy(g, "Tout faire")
    gx.mouse_x, gx.mouse_y = x + 2, y + 2
    frame(L, g)
    assert any(t.startswith("Tout faire : séparer les stems si besoin") for t in TL.texts(g)), TL.texts(g)
    gx.mouse_x, gx.mouse_y = 0, 0
    # Re-préparer : CLI en arrière-plan, progression, puis résultat ; moteur et doutes mémorisés
    press_text(L, g, "Re-préparer", exact=True)
    sh = list(g.state.shell.values())[-1]
    assert "-m reacue_mcp.cli prepare" in sh and "--reanalyse" not in sh, sh
    frame(L, g)
    assert any(t.startswith("Préparation du morceau en cours…") for t in TL.texts(g)), TL.texts(g)
    status(g, state="done", cmd="prepare", message="Morceau préparé : 3 sections", engine="reacue", doubts="9:unsure")
    frame(L, g)
    assert "Terminé" in TL.texts(g) and "Morceau préparé : 3 sections" in TL.texts(g)
    assert g.state.projext["structure_engine"] == "reacue" and g.state.projext["doubts"] == "9:unsure"
    press_text(L, g, "OK", exact=True)
    assert "Structure : ReaCue ✓" in TL.texts(g)
    # Réanalyser depuis zéro : confirmation puis --reanalyse ; erreur expliquée (cause + solution + bouton)
    clear_status(g)
    press_text(L, g, "Réanalyser depuis zéro", exact=True)
    assert "prepare --reanalyse" in list(g.state.shell.values())[-1]
    status(g, state="error", cmd="prepare", message="Fichier audio introuvable : /x/y.wav (hors ligne)")
    frame(L, g)
    T = TL.texts(g)
    assert "Un fichier audio est hors ligne ou introuvable." in T and "Corriger" in T, T
    press_text(L, g, "Corriger", exact=True)
    assert 40101 in list(g.state.cmds.values())
    # structure : renommer (liste), déplacer, supprimer, ajouter
    g.state.inputs = "Pont"
    x, y = [o for o in (list(v.values()) for v in g.state.ops.values()) if o[0] == "text" and o[3] == "Couplet 1"][-1][1:3]
    rows = [o for o in (list(v.values()) for v in g.state.ops.values()) if o[0] == "text" and o[3] == "Nom"]
    ren = [r for r in rows if abs(r[2] - y) < 8][0]
    TL.frame(L, g, (ren[1] + 2, ren[2] + 3))
    assert g.REGIONS[2][4] == "Pont"
    frame(L, g)
    T = TL.texts(g)
    assert any("Structure modifiée" in t for t in T) and "Appliquer les modifications" in T, T
    assert "Structure : manuelle ✓" in T
    # déplacer le début du Refrain d'une mesure plus tôt : la fin du Pont suit
    xr, yr = [o for o in (list(v.values()) for v in g.state.ops.values()) if o[0] == "text" and o[3] == "Refrain 1"][-1][1:3]
    tri = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "tri"]
    left = [t_ for t_ in tri if abs(t_[2] - (yr + 9)) < 14]
    lx = min(t_[1] for t_ in left)
    TL.frame(L, g, (lx, yr + 9))
    assert g.REGIONS[3][2] == pytest.approx(28.0) and g.REGIONS[2][3] == pytest.approx(28.0)
    # ajouter une section au curseur (mesure qui commence à 20 s)
    g.state.cursor = 21.0
    g.state.inputs = "Pré-refrain"
    frame(L, g)
    press_text(L, g, "+ Section au curseur")
    added = [r for r in g.REGIONS.values() if r[4] == "Pré-refrain"]
    assert added and added[0][2] == pytest.approx(20.0) and g.REGIONS[2][3] == pytest.approx(20.0)
    # Appliquer (grand bouton) = préparer en gardant les régions
    clear_status(g)
    frame(L, g)
    press_text(L, g, "Appliquer les modifications", exact=True)
    sh = list(g.state.shell.values())[-1]
    assert "reacue_mcp.cli prepare" in sh and "--reanalyse" not in sh
    # ajouter à un nouveau concert
    status(g, state="done", cmd="prepare", message="ok")
    frame(L, g); press_text(L, g, "OK", exact=True)
    g.state.menu = 1
    g.state.inputs = "Samedi"
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    press_text(L, g, "Ajouter à un concert")
    sl = json.loads((tmp_path / "Shows" / "Samedi.setlist.json").read_text(encoding="utf-8"))
    assert sl["name"] == "Samedi" and sl["songs"] == [{"project": str(tmp_path / "Song One.RPP"), "title": "Song One"}]
    assert sl["live"] == [] and sl["live_exceptions"] == {}
    # concert « fictif » : l'onglet Scène pilote le morceau seul (transport, sections, répétition)
    frame(L, g); press_text(L, g, "OK", exact=True)
    press_text(L, g, "Scène", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Morceau seul" in T and "Début" in T and "Précédent" not in T and "Intro" in T, T


def band_box(g, name):
    """case de la bande de structure (texte en 11 gras, couleur sombre)"""
    for o in g.state.ops.values():
        o = list(o.values())
        if o[0] == "text" and o[3] == name and o[4] == 11:
            return o[1], o[2]
    raise AssertionError((name, TL.texts(g)))


def test_structure_band_edit_merge_split_undo_redo(concert, tmp_path):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path, structure=True)
    g.state.projext["structure_engine"] = "songformer"
    g.state.projext["doubts"] = "5:moved"
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    names = lambda: [r[4] for r in sorted(g.REGIONS.values(), key=lambda r: r[2])]
    # bande : orange = à vérifier (Couplet 1 : 9 mesures, frontière déplacée)
    x, y = band_box(g, "Couplet 1")
    gx.mouse_x, gx.mouse_y = x + 2, y + 2
    frame(L, g)
    T = TL.texts(g)
    i = [k for k, t in enumerate(T) if t.startswith("Couplet 1 · m. 5 · 9 mes.")][-1]
    help_ = " ".join(T[i:i + 2])
    assert "longueur inhabituelle" in help_ and "frontière déplacée" in help_, T
    # clic sur une case : choisie + écoute
    TL.frame(L, g, (x + 2, y + 2)); frame(L, g)
    assert g.state.play == 1 and g.state.cursor == pytest.approx(12.0)
    assert "Couplet 1 · m. 5 · 9 mes." in TL.texts(g) and "Fusionner →" in TL.texts(g)
    # fusionner avec la suivante
    press_text(L, g, "Fusionner →", exact=True)
    assert names() == ["Intro", "Couplet 1"] and sorted(g.REGIONS.values(), key=lambda r: r[2])[1][3] == pytest.approx(46.0)
    frame(L, g)
    # couper en deux (au milieu, sur une mesure)
    g.state.inputs = "Refrain"
    press_text(L, g, "Couper en deux", exact=True)
    regs = sorted(g.REGIONS.values(), key=lambda r: r[2])
    assert names() == ["Intro", "Couplet 1", "Refrain"] and regs[2][2] == pytest.approx(28.0)
    frame(L, g)
    # annuler deux fois, rétablir une fois
    press_text(L, g, "Annuler", exact=True); frame(L, g)
    assert names() == ["Intro", "Couplet 1"]
    press_text(L, g, "Annuler", exact=True); frame(L, g)
    assert names() == ["Intro", "Couplet 1", "Refrain 1"]
    regs = sorted(g.REGIONS.values(), key=lambda r: r[2])
    assert [round(r[2]) for r in regs] == [4, 12, 30]
    press_text(L, g, "Rétablir", exact=True); frame(L, g)
    assert names() == ["Intro", "Couplet 1"]
    # supprimer depuis les outils de la section choisie
    x, y = band_box(g, "Intro")
    TL.frame(L, g, (x + 2, y + 2)); frame(L, g)
    press_text(L, g, "Supprimer", exact=True)
    assert names() == ["Couplet 1"]


def test_song_contextual_button_states(concert, tmp_path):
    """« Séparer les stems » (un seul fichier) → « Analyser et préparer » → « Prêt ✓ »"""
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path)
    mp3 = tmp_path / "Song One" / "Song One.mp3"
    mp3.write_bytes(b"ID3")
    L.execute(f"""TRACKS = {{ {{name="Song One"}} }}; ITEMS = {{ {{track=1, file=[[{mp3}]]}} }}; REGIONS = {{}}""")
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Séparer les stems" in T and "Tout faire" in T and "Stems —" in T and "Structure —" in T, T
    # stems séparés, pas encore préparé
    L.execute(f"""TRACKS = {{ {{name="Chant"}}, {{name="Batterie"}} }}
      ITEMS = {{ {{track=1, file=[[{tmp_path / 'Song One' / 'Song One-A minor-120bpm-vocals.wav'}]]}},
                {{track=2, file=[[{tmp_path / 'Song One' / 'Song One-A minor-120bpm-drums.wav'}]]}} }}""")
    g.state.t += 3; frame(L, g)
    T = TL.texts(g)
    assert "Analyser et préparer" in T and "Séparer les stems" not in T and "Stems ✓" in T, T
    # préparé
    L.execute("""TRACKS[3] = {name="CLICK"}; REGIONS = { {true, 4.0, 12.0, "Intro", 0}, {true, 12.0, 28.0, "Couplet 1", 0} }""")
    g.state.t += 3; frame(L, g)
    T = TL.texts(g)
    assert "Prêt ✓" in T and "Re-préparer" in T, T
    press_text(L, g, "Prêt ✓", exact=True); frame(L, g)
    assert g.state.persist["tab"] == "stage"


def test_do_everything_success_failure_resume(concert, tmp_path):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path)
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    press_text(L, g, "Tout faire", exact=True)
    # étape 1 (stems) : déjà fait (stems présents) ; étape 2 : analyser et préparer
    assert "-m reacue_mcp.cli prepare" in list(g.state.shell.values())[-1]
    frame(L, g)
    T = TL.texts(g)
    assert "Séparer les stems" in T and "déjà fait" in T and "Mettre à jour les téléphones" in T, T
    assert "Arrêter" in T
    g.state.t += 12
    frame(L, g)
    status(g, state="done", cmd="prepare", message="Morceau préparé", engine="songformer", doubts="")
    frame(L, g)
    assert "reacue_mcp.cli publish" in list(g.state.shell.values())[-1]
    # échec de la mise à jour des téléphones : pont arrêté → explication + bouton
    status(g, state="error", cmd="publish", message="Le pont ReaCue ne tourne pas dans REAPER.")
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Arrêté à l'étape « Mettre à jour les téléphones »" in T and "Reprendre" in T, T
    assert "Démarrer le pont" in T, T
    # reprendre : relance seulement l'étape en échec, puis enregistre
    clear_status(g)
    n_saves = g.state.saves
    press_text(L, g, "Reprendre", exact=True)
    assert "reacue_mcp.cli publish" in list(g.state.shell.values())[-1]
    status(g, state="done", cmd="publish", message="ok")
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert any(t.startswith("Morceau prêt ✓") for t in T) and g.state.saves == n_saves + 1, T
    assert g.state.projext["structure_engine"] == "songformer"
    press_text(L, g, "Fermer", exact=True); frame(L, g)
    assert "Prêt ✓" in TL.texts(g)
    # annuler : s'arrête après l'étape en cours
    clear_status(g)
    press_text(L, g, "Tout faire", exact=True)
    frame(L, g)
    press_text(L, g, "Arrêter", exact=True)
    status(g, state="done", cmd="prepare", message="ok")
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "annulé" in T and "Reprendre" in T, T


def test_new_song_proposes_do_everything(concert, tmp_path):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path)
    open_window(L, g)
    frame(L, g)
    # simule la fin de « + Nouveau morceau »
    L.execute("REACUE_CTX.propose_all = REACUE_CTX.proj_key")
    frame(L, g)
    T = TL.texts(g)
    assert any(t.startswith("Morceau créé. Tout préparer maintenant") for t in T) and "Plus tard" in T, T
    press_text(L, g, "Plus tard", exact=True); frame(L, g)
    assert not any(t.startswith("Morceau créé.") for t in TL.texts(g))


def test_assistant_first_launch_and_settings_simple_advanced(concert, tmp_path):
    L, g = rt(concert, proj=tmp_path / "x.RPP", tracks=False)
    g.state.ext["assistant_seen"] = ""
    install(g, tmp_path, stems=True)
    sp = Path(g.RES) / "ReaCueMCP" / "reacue_settings.json"
    L.execute("local ge = os.getenv; os.getenv = function(k) if k == 'HOME' then return '/Users/demo' end return ge(k) end")
    gx = open_window(L, g)
    frame(L, g)
    T = TL.texts(g)
    assert "Bienvenue dans ReaCue" in T and "Analyse de structure (SongFormer)  ·  facultatif" in T, T
    assert "Installer" in T and "Créer" in T and "Pont ReaCue (dans REAPER)" in T, T
    assert any("/Users/demo/Documents" in t for t in T), T            # dossier par défaut absent
    # dossier des projets absent : « Créer »
    sp.write_text(json.dumps({"language": "fr", "projects_dir": str(tmp_path / "Projets")}), encoding="utf-8")
    press_text(L, g, "Revérifier", exact=True); frame(L, g)
    press_text(L, g, "Créer", exact=True)
    assert (tmp_path / "Projets").is_dir()
    # SongFormer : « Installer » ouvre l'installateur
    press_text(L, g, "Installer", exact=True)
    assert any("Install ReaCue Structure" in c or str(tmp_path / "inst") in c for c in g.state.shell.values())
    press_text(L, g, "Terminer", exact=True)
    assert g.state.persist["assistant_seen"] == "1"
    sp.write_text(json.dumps({"language": "fr"}), encoding="utf-8")       # captures : dossiers par défaut
    g.state.ext["concert_dir"] = ""
    # Réglages simples / avancés
    press_text(L, g, "Réglages", exact=True); frame(L, g)
    assert "Détection de structure" in TL.texts(g)
    press_text(L, g, "Live et système", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Décompte avant le morceau" in T and "Licences" in T, T
    assert "Volume du click" not in T and "Code PIN de la Régie" not in T and "Dossier des projets" not in T
    press_text(L, g, "Réglages avancés", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Volume du click" in T and "Code PIN de la Régie" in T and "Dossier des projets" in T and "Débit du décompte" in T, T
    assert g.state.persist["settings_adv"] == "1"
    press_text(L, g, "Réglages simples", exact=True); frame(L, g)
    # « Vérifier l'installation » rouvre l'assistant
    press_text(L, g, "Vérifier l'installation", exact=True); frame(L, g)
    assert "Vérifier l'installation" in TL.texts(g) and "Revérifier" in TL.texts(g)


def test_concert_batch_prepare(concert, tmp_path):
    res = concert[0]
    projects = tmp_path / "projects"
    projects.mkdir()
    for name, ready in (("Alpha", True), ("Bravo", False), ("Charlie", False)):
        body = '<REAPER_PROJECT\n  MARKER 1 0 "Intro" 1\n  <TRACK\n    NAME CLICK\n  >\n>\n' if ready else "<REAPER_PROJECT\n>\n"
        (projects / f"{name}.RPP").write_text(body, encoding="utf-8")
    L, g = rt(concert, proj=tmp_path / "empty.RPP", tracks=False)
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": "fr", "projects_dir": str(projects)}), encoding="utf-8")
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    install(g, tmp_path)
    gx = open_window(L, g)
    press_text(L, g, "Concert", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Préparer tous les morceaux non préparés (2)" in T, T
    # les projets ouverts par le lot : chacun « préparé » par la CLI simulée
    L.execute(f"""
      local mo = reaper.Main_openProject
      reaper.Main_openProject = function(p) mo(p); PROJFILE = p:gsub("^noprompt:", "")
        TRACKS = {{ {{name="Chant"}}, {{name="Batterie"}} }}
        ITEMS = {{ {{track=1, file="/x/a-vocals.wav"}}, {{track=2, file="/x/a-drums.wav"}} }}
      end""")
    press_text(L, g, "Préparer tous les morceaux non préparés", exact=False)
    assert g.state.opened == "noprompt:" + str(projects / "Bravo.RPP") and 40859 in list(g.state.cmds.values())
    frame(L, g)
    T = TL.texts(g)
    assert "Préparation en lot  ·  1 / 2" in T and "Bravo" in T and "Charlie" in T and "Arrêter" in T, T
    assert "Concert" in T and g.state.persist["tab"] == "concert"
    for cmd in ("prepare", "publish"):
        status(g, state="done", cmd=cmd, message="ok", engine="songformer")
        frame(L, g)
    g.state.t += 1; frame(L, g)
    # 1er morceau fini : enregistré, onglet refermé, 2e ouvert
    assert 40860 in list(g.state.cmds.values()) and g.state.opened == "noprompt:" + str(projects / "Charlie.RPP")
    press_text(L, g, "Arrêter", exact=True)
    for cmd in ("prepare", "publish"):
        status(g, state="done", cmd=cmd, message="ok")
        frame(L, g)
    g.state.t += 1; frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Lot terminé : 2 prêt(s), 0 en échec" in T, T


def test_concert_tab_compose_build_open(concert, tmp_path):
    res = concert[0]
    projects = res.rpp.parent.parent / "projects"
    L, g = rt(concert, proj=tmp_path / "empty.RPP", tracks=False)
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": "fr", "projects_dir": str(projects)}), encoding="utf-8")
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    inst = tmp_path / "inst"
    (inst / ".venv" / "bin").mkdir(parents=True)
    (inst / ".venv" / "bin" / "python").write_text("")
    g.state.ext["install_dir"] = str(inst)
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Concert" in T and any(t.upper().startswith("MORCEAUX (") for t in T), T
    assert "Demo Song" in T and "Second Demo" in T and any("✓" in t for t in T), T
    plus = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "rect"]

    def add(name):
        x, y = text_xy(g, name)
        TL.frame(L, g, (x + int((L.globals().gfx.w - 44) / 2) - 20, y + 4))       # bouton « + » au bout de la ligne
        frame(L, g)
    add("Second Demo"); add("Demo Song")
    T = TL.texts(g)
    assert "1. Second Demo" in T and "2. Demo Song" in T, T
    # monter « Demo Song »
    x, y = text_xy(g, "2. Demo Song")
    tri = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "tri" and abs(list(o.values())[2] - (y + 8)) < 14]
    up = min(tri, key=lambda t_: t_[1])
    TL.frame(L, g, (up[1] + 1, y + 8)); frame(L, g)
    assert "1. Demo Song" in TL.texts(g)
    g.state.inputs = "Samedi"
    press_text(L, g, "Renommer"); frame(L, g)
    press_text(L, g, "Construire", exact=True)
    sl = tmp_path / "Shows" / "Samedi.setlist.json"
    d = json.loads(sl.read_text(encoding="utf-8"))
    assert [s["title"] for s in d["songs"]] == ["Demo Song", "Second Demo"] and d["name"] == "Samedi"
    sh = list(g.state.shell.values())[-1]
    assert f"concert --setlist '{sl}'" in sh, sh
    frame(L, g)
    assert any("Construction du concert" in t for t in TL.texts(g))
    # la CLI a construit : ouverture dans un nouvel onglet
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").write_text(json.dumps({"state": "done", "cmd": "concert", "message": "ok"}), encoding="utf-8")
    frame(L, g)
    assert g.state.opened == str(tmp_path / "Shows" / "Samedi.RPP") and 40859 in list(g.state.cmds.values())
    # le profil « joué en live » réglé dans la fenêtre est gardé quand on reconstruit
    d["live"] = ["drums"]
    sl.write_text(json.dumps(d), encoding="utf-8")
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").unlink()
    frame(L, g)
    press_text(L, g, "Construire", exact=True)
    assert json.loads(sl.read_text(encoding="utf-8"))["live"] == ["drums"]


def test_settings_tab_writes_json(concert, tmp_path):
    L, g = rt(concert, proj=tmp_path / "x.RPP", tracks=False)
    sp = Path(g.RES) / "ReaCueMCP" / "reacue_settings.json"
    sp.write_text(json.dumps({"language": "fr", "custom_key": 7}), encoding="utf-8")
    # capture : dossiers par défaut d'un utilisateur fictif
    g.state.ext["concert_dir"] = ""
    L.execute("local ge = os.getenv; os.getenv = function(k) if k == 'HOME' then return '/Users/demo' end return ge(k) end")
    gx = open_window(L, g)
    frame(L, g)
    press_text(L, g, "Réglages", exact=True); frame(L, g)
    # La séparation reste accessible en vue simple, avant toute préparation.
    g.state.menu = 1
    press_text(L, g, "4 stems · équilibré", exact=False); frame(L, g)
    assert json.loads(sp.read_text(encoding="utf-8"))["stems_model"] == "htdemucs"
    press_text(L, g, "Live et système", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Langue" in T and "Décompte avant le morceau" in T and "2 mes." in T, T
    # décompte 2 → 3 mesures
    x, y = text_xy(g, "2 mes.")
    tri = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "tri" and abs(list(o.values())[2] - (y + 7)) < 14]
    right = max(tri, key=lambda t_: t_[1])
    TL.frame(L, g, (right[1], y + 7))
    d = json.loads(sp.read_text(encoding="utf-8"))
    assert d["count_in_bars"] == 3 and d["custom_key"] == 7
    frame(L, g)
    press_text(L, g, "Réglages avancés", exact=True); frame(L, g)
    press_text(L, g, "fixe", exact=True)
    assert json.loads(sp.read_text(encoding="utf-8"))["tempo_mode"] == "constant"
    # sortie click + voix : menu (aucune, 1/2, 3/4)
    L.execute("NOUT = 4")
    g.state.menu = 3
    frame(L, g)
    press_text(L, g, "sortie principale", exact=True)
    assert json.loads(sp.read_text(encoding="utf-8"))["click_hw_output"] == 2
    frame(L, g)
    press_text(L, g, "English", exact=True)
    assert json.loads(sp.read_text(encoding="utf-8"))["language"] == "en"
    frame(L, g)
    assert "Language" in TL.texts(g) and "Settings" in TL.texts(g)
    from reacue_mcp import settings as S
    assert S.DEFAULTS.keys() >= {"count_in_bars", "tempo_mode", "stems_model", "click_hw_output"}


def test_json_roundtrip_lua(concert):
    L, g = rt(concert)
    R = L.execute(f"return dofile([[{LUA_DIR / 'ReaCue_run.lua'}]])")
    src = json.dumps({"name": "Gig é \"q\"", "songs": [{"project": "/a/b.RPP", "title": "B"}], "live": [],
                      "live_exceptions": {}, "gap_s": 4, "n": 0.5, "t": True, "z": None})
    d = R.json_decode(src)
    out = json.loads(R.json_encode(d, "  ", L.table_from(["name", "gap_s", "songs", "live", "live_exceptions"])))
    want = json.loads(src)
    want.pop("z")
    assert out == want
    assert R.json_decode("{bad") is None


def test_window_english_views(concert, tmp_path):
    """Les 4 onglets en anglais (captures *_en.png de la documentation)."""
    L, g, res = song_runtime(concert, tmp_path, lang="en")
    projects = res.rpp.parent.parent / "projects"
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": "en", "projects_dir": str(projects)}), encoding="utf-8")
    g.state.ext["concert_dir"] = ""
    L.execute("local ge = os.getenv; os.getenv = function(k) if k == 'HOME' then return '/Users/demo' end return ge(k) end")
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Song One" in T and "Ready ✓" in T and "Do everything" in T and "Update the phones" in T, T
    assert "Lyrics: 3 lines" in T and any("bars" in t for t in T), T
    press_text(L, g, "Concert", exact=True); frame(L, g)
    for name in ("Second Demo", "Demo Song"):
        x, y = text_xy(g, name)
        TL.frame(L, g, (x + int((L.globals().gfx.w - 44) / 2) - 20, y + 4)); frame(L, g)
    T = TL.texts(g)
    assert "1. Second Demo" in T and "Build" in T, T
    press_text(L, g, "Settings", exact=True); frame(L, g)
    press_text(L, g, "Live and system", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Language" in T and "Count-in before the song" in T and "Spoken count-in" in T, T
    press_text(L, g, "Stage", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Single song" in T or any("Single song" in t for t in T), T


def test_stage_english_view(concert):
    L, g = rt(concert, lang="en")
    gx = open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Instruments (stems)  ·  long press = solo" in T or any(t.startswith("Instruments") for t in T), T
    assert "Hear everything" in T and "Played live…" in T, T


def test_english_new_views(concert, tmp_path):
    """Assistant, « Tout faire », aide, réglages avancés et erreurs expliquées en anglais."""
    L, g, res = song_runtime(concert, tmp_path, lang="en")
    g.state.ext["assistant_seen"] = ""
    install(g, tmp_path)
    gx = open_window(L, g)
    frame(L, g)
    T = TL.texts(g)
    assert "Welcome to ReaCue" in T and "Structure analysis (SongFormer)  ·  optional" in T and "Finish" in T, T
    press_text(L, g, "Finish", exact=True)
    gx.mouse_x, gx.mouse_y = 0, 0
    frame(L, g)
    T = TL.texts(g)
    assert "Ready ✓" in T and "Prepare again" in T and "Re-analyse from scratch" in T and "Stems ✓" in T, T
    assert any(t.startswith("Hover a button") for t in T), T
    press_text(L, g, "Do everything", exact=True); frame(L, g)
    assert any(t.startswith("Analyse and prepare") for t in TL.texts(g)) and "already done" in TL.texts(g)
    status(g, state="error", cmd="prepare", message="The ReaCue bridge is not running in REAPER.")
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert "Stopped at step “Analyse and prepare”" in T and "Start the bridge" in T and "Resume" in T, T
    press_text(L, g, "Start the bridge", exact=True)
    assert g.state.added_script.endswith("ReaCue_Bridge.lua") and 55555 in list(g.state.cmds.values())
    press_text(L, g, "Settings", exact=True); frame(L, g)
    press_text(L, g, "Live and system", exact=True); frame(L, g)
    press_text(L, g, "Advanced settings", exact=True); frame(L, g)
    T = TL.texts(g)
    assert "Click volume" in T and "Count speed" in T and "Simple settings" in T and "Check the installation" in T, T


@pytest.mark.parametrize("title, ok", [
    ("Song One-A minor-120bpm", True),              # stems : début commun des noms (serveur, _common_title)
    ("Song One-A minor-120bpm-vocals", True),       # un seul fichier : son nom
    ("Song One", True),                             # titre plus court, suivi d'un séparateur
    ("Song Two", False), ("Song On", False),        # autre morceau / coupé au milieu d'un mot
])
def test_published_pills_match_stem_titles(concert, tmp_path, title, ok):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path, structure=True)
    song = {"version": 1, "title": title, "chords": [{"bar": 1, "chords": []}],
            "drums": {"steps": 16, "bars": []}}
    (Path(g.RES) / "reaper_www_root" / "reacue_song.json").write_text(json.dumps(song), encoding="utf-8")
    open_window(L, g)
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    want = ("Accords ✓", "Batterie ✓", "Prompteur publié ✓") if ok else ("Accords —", "Batterie —", "Prompteur —")
    for p in want:
        assert p in T, (title, p, T)


def test_sheet_pill_opens_pdf_or_publishes(concert, tmp_path):
    L, g, res = song_runtime(concert, tmp_path)
    install(g, tmp_path, structure=True)
    www = Path(g.RES) / "reaper_www_root" / "reacue_song.json"
    www.write_text(json.dumps({"version": 1, "title": "Song One-A minor-120bpm"}), encoding="utf-8")
    open_window(L, g)
    frame(L, g); frame(L, g)
    assert "Grille PDF —" in TL.texts(g)
    # pas encore de grille : clic = mettre à jour les téléphones (qui écrit la grille)
    press_text(L, g, "Grille PDF —", exact=True)
    assert "-m reacue_mcp.cli publish" in list(g.state.shell.values())[-1]
    status(g, state="done", cmd="publish", message="ok")
    frame(L, g); press_text(L, g, "OK", exact=True)
    pdf = tmp_path / "Song One" / "Grille - Song One-A minor-120bpm.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    g.state.t = g.state.t + 3                      # relecture du dossier (toutes les 2 s)
    frame(L, g); frame(L, g)
    assert "Grille PDF ✓" in TL.texts(g), TL.texts(g)
    n = len(g.state.shell)
    press_text(L, g, "Grille PDF ✓", exact=True)
    cmds = list(g.state.shell.values())[n:]
    assert any(str(pdf) in c for c in cmds), cmds


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_lyrics_pill_auto_draft(concert, tmp_path, lang):
    """Paroles venues du brouillon automatique (Whisper) : pastille orange « auto (N lignes) », aide au survol,
    clic = ouvrir le fichier ; le fichier de l'utilisateur reste prioritaire. Texte fictif."""
    L, g, res = song_runtime(concert, tmp_path, lang=lang)
    install(g, tmp_path, structure=True)
    d = tmp_path / "Song One"
    (d / "paroles.txt").unlink()
    auto = d / "paroles (auto).txt"
    auto.write_text("# Brouillon automatique\n# à corriger\n\nZorblat quimpe\nVaxu frimbel\n\nDostra klop\n",
                    encoding="utf-8")
    open_window(L, g)
    frame(L, g); frame(L, g)
    lab = "Paroles : auto (3 lignes)" if lang == "fr" else "Lyrics: auto (3 lines)"
    T = TL.texts(g)
    assert lab in T, T
    x, y = text_xy(g, lab)
    # pastille d'avertissement : texte et voyant de la couleur U.WARN du thème (jaune LCD)
    warn = [int(v) for v in L.eval("REACUE_CTX.U.WARN").values()]
    txt = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "text" and list(o.values())[3] == lab]
    assert txt and [round(c * 255) for c in txt[0][6:9]] == warn, txt
    dots = [list(o.values()) for o in g.state.ops.values() if list(o.values())[0] == "circle"]
    assert any(abs(o[2] - (y + 6)) < 8 and o[1] < x and [round(c * 255) for c in o[4:7]] == warn for o in dots), dots
    gx = L.globals().gfx
    gx.mouse_x, gx.mouse_y = x + 2, y + 2
    frame(L, g)
    tip = ("Paroles transcrites automatiquement (Whisper)" if lang == "fr"
           else "Lyrics transcribed automatically (Whisper)")
    assert any(t.startswith(tip) for t in TL.texts(g)), TL.texts(g)
    gx.mouse_x, gx.mouse_y = 0, 0
    n = len(g.state.shell)
    press_text(L, g, lab, exact=True)
    cmds = list(g.state.shell.values())[n:]
    assert any(str(auto) in c for c in cmds), cmds
    # le fichier de l'utilisateur est prioritaire
    (d / "paroles.txt").write_text("ligne un\nligne deux\n", encoding="utf-8")
    g.state.t = g.state.t + 3
    frame(L, g); frame(L, g)
    T = TL.texts(g)
    assert ("Paroles : 2 lignes" if lang == "fr" else "Lyrics: 2 lines") in T and lab not in T, T


def test_performance_controls_keep_other_settings(concert, tmp_path):
    L, g = rt(concert, proj=tmp_path / "performance.RPP", tracks=False)
    sp = Path(g.RES) / "ReaCueMCP" / "reacue_settings.json"
    sp.write_text(json.dumps({"language": "fr", "custom_key": 7, "stems_model": "htdemucs_6s"}))
    open_window(L, g)
    frame(L, g)
    press_text(L, g, "Réglages", exact=True)
    frame(L, g)
    press_text(L, g, "Live et système", exact=True); frame(L, g)
    press_text(L, g, "Réglages avancés", exact=True)
    frame(L, g)
    press_text(L, g, "Rapide", exact=True)
    frame(L, g)
    assert any("QUALITÉ" in text.upper() for text in TL.texts(g)), (sp.read_text(), TL.texts(g))
    press_text(L, g, "4", exact=True)
    data = json.loads(sp.read_text())
    assert data["performance_profile"] == "fast" and data["cpu_threads"] == 4
    assert data["stems_model"] == "htdemucs_6s" and data["custom_key"] == 7
    frame(L, g)
    press_text(L, g, "Standard", exact=True)
    assert json.loads(sp.read_text())["performance_profile"] == "standard"


def test_native_studio_header_and_narrow_docking(concert, tmp_path):
    L, g, _ = song_runtime(concert, tmp_path)
    gx = open_window(L, g)
    frame(L, g)
    assert gx.w == 920
    assert "TEMPS" in TL.texts(g) and "TEMPO" in TL.texts(g)
    # Readouts must reflect REAPER's cursor and playback, without sending commands.
    before = len(g.state.cmds)
    g.state.cursor = 75
    frame(L, g)
    assert "1:15" in TL.texts(g)
    assert len(g.state.cmds) == before
    gx.w = 560
    frame(L, g)
    assert "REACUE" in TL.texts(g) and "Song One" in TL.texts(g)
    assert "TEMPO" not in TL.texts(g)  # Preserve the project title instead of squeezing LCDs.
