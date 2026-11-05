"""« + Nouveau morceau » (fenêtre ReaCue, Lua 5.4 via lupa, API REAPER simulée) et l'outil Python
`new_song` : titre proposé, collision de nom, copie (taille vérifiée), une piste par fichier, projet
enregistré dans <dossier des projets>/<Titre>/<Titre>.RPP, enregistrement automatique après une préparation,
liste des morceaux de l'onglet Concert. Noms de morceaux fictifs."""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("lupa")

import test_concert_lua as TL  # noqa: E402
import test_reacue_window as W  # noqa: E402
from reacue_mcp import newsong as NS  # noqa: E402

NEW = r"""
state.inserted, state.saved_ex, state.saves, state.titles_asked = {}, {}, 0, {}
reaper.GetUserFileNameForRead = function(fn, title, ext) if PICK then return true, PICK end return false, "" end
reaper.InsertMedia = function(file, mode)
  local tr = {name = ""}; table.insert(TRACKS, tr)
  table.insert(ITEMS, {track = #TRACKS, file = file}); table.insert(state.inserted, {file, mode}); return 1 end
reaper.GetSetMediaTrackInfo_String = function(tr, k, v, set) if set and k == "P_NAME" then tr.name = v end return true, tr.name end
reaper.SetOnlyTrackSelected = function(tr) state.selected = tr end
reaper.PreventUIRefresh = function() end
reaper.UpdateArrange = function() end
reaper.Main_SaveProjectEx = function(p, fn, opt) table.insert(state.saved_ex, fn); WRITE(fn) end
reaper.Main_SaveProject = function(p, force) state.saves = state.saves + 1 end
reaper.IsProjectDirty = function() return DIRTY or 0 end
reaper.GetUserInputs = function(t, n, cap, def)
  table.insert(state.titles_asked, def)
  if state.inputs_q and #state.inputs_q > 0 then return true, table.remove(state.inputs_q, 1) end
  if state.inputs then return true, state.inputs end
  return true, def end
local _cmd = reaper.Main_OnCommand
reaper.Main_OnCommand = function(c, f) _cmd(c, f); if c == 40859 then TRACKS, ITEMS, REGIONS = {}, {}, {} end end
local _open = reaper.Main_openProject
reaper.Main_openProject = function(p) _open(p); local f = p:gsub("^noprompt:", ""); PROJFILE = f end
"""

@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return TL.make_concert(tmp_path_factory.mktemp("newsong"))


STEMS = ["Demo Ballad Live-Bass-E minor-92bpm-441hz.wav", "Demo Ballad Live-Drums-E minor-92bpm-441hz.wav",
         "Demo Ballad Live-Vocals-E minor-92bpm-441hz.wav"]


def setup(concert, tmp_path, lang="fr"):
    projects = tmp_path / "projects"
    projects.mkdir()
    L, g = W.rt(concert, lang=lang, proj=tmp_path / "empty.RPP", tracks=False)
    (Path(g.RES) / "ReaCueMCP" / "reacue_settings.json").write_text(
        json.dumps({"language": lang, "projects_dir": str(projects)}), encoding="utf-8")
    L.execute(NEW)
    g.WRITE = lambda fn: Path(str(fn)).write_text("<REAPER_PROJECT\n>\n", encoding="utf-8")
    g.state.ext["concert_dir"] = str(tmp_path / "Shows")
    g.PROJFILE = ""
    return L, g, projects


def run_job(L, g, n=30):
    for _ in range(n):
        W.frame(L, g)
        if not any("Copie des fichiers" in t or "Copying the files" in t for t in TL.texts(g)):
            pass
        g.state.t = g.state.t + 0.1


def test_titles_python_and_lua(concert, tmp_path):
    cases = {
        "Luke Demo - La vigie _Clip officiel_-Bass-E minor-188bpm-441hz.wav": "Luke Demo - La vigie",
        "Band - Song Title _Official HD Remastered Video_-Gb minor-104bpm-441hz.mp3": "Band - Song Title",
        "Band - Other Song (Official Video).mp3": "Band - Other Song",
        "Demo Song-A minor-120bpm-drums.wav": "Demo Song",
        "simple.wav": "simple",
        "Song-consolidated.mp3": "Song",
        "Jean-Pierre - Mon titre.mp3": "Jean-Pierre - Mon titre",
    }
    L, g, _ = setup(concert, tmp_path)
    W.open_window(L, g)
    for src, want in cases.items():
        assert NS.clean_title(src) == want, src
    # même règle côté Lua (module de la fenêtre)
    N = L.execute(f"""
      local ctx = {{L = dofile([[{TL.LUA_DIR / 'ReaCue_concert_lib.lua'}]]), U = {{}}, T = function(k) return k end,
                   SEP = "/", tr = function(tbl, k) return tbl.fr[k] end}}
      return dofile([[{TL.LUA_DIR / 'ReaCue_newsong.lua'}]])(ctx)""")
    for src, want in cases.items():
        assert N.clean_title(src) == want, src
    assert N.stems_title("/x/Demo Ballad Live-E minor-92bpm-441hz", L.table_from([])) == "Demo Ballad Live"
    assert N.role_of("x-Lead Guitars-y.wav") == "lead_guitar" and N.role_of("piano.wav") == "keys"
    assert N.is_audio("a.MP3") and not N.is_audio("paroles.txt") and not N.is_audio(".hidden.wav")


def test_new_song_stems_folder_copy_project_and_collision(concert, tmp_path):
    L, g, projects = setup(concert, tmp_path)
    src = tmp_path / "Downloads" / "Demo Ballad Live-E minor-92bpm-441hz"
    src.mkdir(parents=True)
    for k, n in enumerate(STEMS):
        (src / n).write_bytes(os.urandom(3 * 1024 * 1024 + k))          # > 1 bloc de copie
    (src / "notes.txt").write_text("x", encoding="utf-8")
    gx = W.open_window(L, g)
    W.frame(L, g); W.frame(L, g)
    T = TL.texts(g)
    assert "+ Nouveau morceau" in T and "Concert" in T, T       # projet vide : onglet Concert, bouton présent
    W.press_text(L, g, "Morceau", exact=True); W.frame(L, g)
    T = TL.texts(g)
    assert "+ Nouveau morceau" in T and any("crée-en un avec" in t for t in T), T
    # stems : pas de js_ReaScriptAPI → message puis choix d'UN des fichiers du dossier
    g.state.menu = 2
    g.PICK = str(src / STEMS[0])
    W.press_text(L, g, "+ Nouveau morceau")
    assert "UN des fichiers" in g.state.msgbox
    assert list(g.state.titles_asked.values())[0] == "Demo Ballad Live"
    run_job(L, g)
    dst = projects / "Demo Ballad Live"
    for n in STEMS:
        assert (dst / n).stat().st_size == (src / n).stat().st_size
    assert not (dst / "notes.txt").exists()
    assert 40859 in list(g.state.cmds.values())                       # nouvel onglet de projet
    ins = [list(v.values()) for v in g.state.inserted.values()]
    assert [Path(i[0]).name for i in ins] == STEMS and all(i[1] == 1 for i in ins)
    names = [t.name for t in g.TRACKS.values()]
    assert names == ["Basse", "Batterie", "Chant"], names
    rpp = dst / "Demo Ballad Live.RPP"
    assert list(g.state.saved_ex.values()) == [str(rpp)] and rpp.exists()
    assert g.state.opened == "noprompt:" + str(rpp) and g.PROJFILE == str(rpp)
    W.frame(L, g)
    T = TL.texts(g)
    assert "Morceau" in T and any("Nouveau morceau « Demo Ballad Live »" in t for t in T), T
    assert "Analyser et préparer" in T and "Tout faire" in T, T
    assert any(t.startswith("Morceau créé. Tout préparer maintenant") for t in T), T      # « Tout faire » proposé
    # l'onglet Concert le liste (pas encore préparé)
    W.press_text(L, g, "Concert", exact=True); W.frame(L, g)
    T = TL.texts(g)
    assert "Demo Ballad Live" in T and any("à préparer" in t for t in T), T
    # même titre : jamais écrasé → avertissement et nouveau titre proposé
    g.state.titles_asked = L.table_from([])
    g.state.inputs_q = L.table_from(["Demo Ballad Live", "Demo Ballad Live (v2)"])
    W.press_text(L, g, "+ Nouveau morceau")
    assert "existe déjà" in g.state.msgbox
    run_job(L, g)
    assert (projects / "Demo Ballad Live (v2)" / "Demo Ballad Live (v2).RPP").exists()
    assert (dst / STEMS[0]).stat().st_size == (src / STEMS[0]).stat().st_size


def test_new_song_single_file_then_split_first_and_autosave(concert, tmp_path):
    L, g, projects = setup(concert, tmp_path)
    mp3 = tmp_path / "dl" / "Band - Demo Tune _Official Video_-C major-110bpm-441hz.mp3"
    mp3.parent.mkdir()
    mp3.write_bytes(b"ID3" + os.urandom(5000))
    inst = tmp_path / "inst"
    (inst / ".venv" / "bin").mkdir(parents=True)
    (inst / ".venv" / "bin" / "python").write_text("")
    g.state.ext["install_dir"] = str(inst)
    W.open_window(L, g)
    W.frame(L, g)
    g.state.menu = 1
    g.PICK = str(mp3)
    W.press_text(L, g, "+ Nouveau morceau")
    run_job(L, g)
    rpp = projects / "Band - Demo Tune" / "Band - Demo Tune.RPP"
    assert rpp.exists() and [t.name for t in g.TRACKS.values()] == ["Band - Demo Tune"]
    W.frame(L, g); W.frame(L, g)
    T = TL.texts(g)
    assert "Séparer les stems" in T and "Stems —" in T, T                 # grand bouton : séparer d'abord
    # préparation réussie depuis la fenêtre → projet du morceau enregistré automatiquement
    saves = g.state.saves
    W.press_text(L, g, "Analyser et préparer", exact=True)
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").write_text(
        json.dumps({"state": "done", "cmd": "prepare", "message": "ok"}), encoding="utf-8")
    W.frame(L, g)
    assert g.state.saves == saves + 1
    W.press_text(L, g, "OK", exact=True)
    W.frame(L, g)
    assert "Enregistré ✓" in TL.texts(g), TL.texts(g)
    # échec : pas d'enregistrement
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").unlink()
    W.press_text(L, g, "Analyser et préparer", exact=True)
    (Path(g.RES) / "ReaCueMCP" / "cli_status.json").write_text(
        json.dumps({"state": "error", "cmd": "prepare", "message": "boom"}), encoding="utf-8")
    W.frame(L, g)
    assert g.state.saves == saves + 1


def test_english_labels(concert, tmp_path):
    L, g, _ = setup(concert, tmp_path, lang="en")
    W.open_window(L, g)
    W.frame(L, g); W.press_text(L, g, "Song", exact=True); W.frame(L, g)
    T = TL.texts(g)
    assert "+ New song" in T and any("create one with" in t for t in T), T


@pytest.mark.parametrize("source", ["cli", "jobs"])
def test_new_song_refuses_active_worker_before_copy_or_project_creation(concert, tmp_path, source):
    L, g, projects = setup(concert, tmp_path)
    W.open_window(L, g)
    if source == "cli":
        L.execute('REACUE_CTX.R.active_job=function() return {state="running"} end')
    else:
        L.execute('REACUE_CTX.jobs.busy=function() return true end')
    assert g.REACUE_CTX.newsong.start("file") is False
    assert g.REACUE_CTX.job is None
    assert not list(projects.iterdir())
    assert not list(g.state.inserted.values()) and not list(g.state.saved_ex.values())
    assert not list(g.state.titles_asked.values())


def test_new_song_completion_does_not_claim_success_when_project_creation_refused(concert, tmp_path):
    L, g, _ = setup(concert, tmp_path)
    W.open_window(L, g)
    L.execute('REACUE_CTX.newsong.make_project=function() return false end')
    assert g.REACUE_CTX.newsong.complete("/new", "New song", L.table_from(["mix.wav"]), True) is False
    assert g.REACUE_CTX.last_new is None and g.REACUE_CTX.propose_all is None
    assert not list(g.state.saved_ex.values())


def test_python_new_song(tmp_path):
    root = tmp_path / "projects"
    src = tmp_path / "Demo Ballad Live-E minor-92bpm-441hz"
    src.mkdir()
    import numpy as np
    import soundfile as sf
    for n in STEMS:
        sf.write(src / n, np.zeros(44100 * 2, dtype="float32"), 44100)
    out = NS.new_song([str(src)], root=root, lang="fr")
    rpp = Path(out["project"])
    assert out["title"] == "Demo Ballad Live" and rpp == root / "Demo Ballad Live" / "Demo Ballad Live.RPP"
    txt = rpp.read_text(encoding="utf-8")
    assert txt.count("<TRACK") == 3 and 'NAME "Basse"' in txt and "LENGTH 2.000000" in txt
    assert str(root / "Demo Ballad Live" / STEMS[0]) in txt and out["next"] == "prepare"
    with pytest.raises(ValueError):
        NS.new_song([str(src)], root=root)
    mp3 = tmp_path / "Band - Song (Official Video).wav"
    sf.write(mp3, np.zeros(4410, dtype="float32"), 44100)
    o2 = NS.new_song([str(mp3)], root=root, lang="en")
    assert o2["title"] == "Band - Song" and o2["single_file"] and o2["next"].startswith("separate")
    assert 'NAME "Band - Song"' in Path(o2["project"]).read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        NS.new_song([str(tmp_path / "x.txt")] if (tmp_path / "x.txt").write_text("x") else [], root=root)
