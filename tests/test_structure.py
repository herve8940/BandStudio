"""Analyse de structure SongFormer (composant optionnel) : calage sur la grille, noms, cache, repli sur la
détection de ReaCue, lanceur reacue_structure.py avec un faux SongFormer, installateurs, réglage Lua.
Aucun modèle n'est téléchargé : SongFormer et torch sont simulés."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from reacue_mcp import structure as ST
from reacue_mcp.analysis import Analysis, Section

ROOT = Path(__file__).resolve().parents[1]
BAR = 2.0                                   # 120 bpm en 4/4


def grid(n_bars, t0=1.0):
    return [t0 + BAR * i for i in range(n_bars + 1)]


def seg(a, b, label, t0=1.0):
    """segment en mesures (0-based) -> secondes, comme SongFormer"""
    return {"start": t0 + BAR * a, "end": t0 + BAR * b, "label": label}


# --------------------------------------------------------------------------- calage et noms
def test_snap_exact_and_names_groups():
    db = grid(64)
    segs = [seg(0, 8, "intro"), seg(8, 24, "verse"), seg(24, 40, "chorus"), seg(40, 56, "verse"),
            seg(56, 64, "outro")]
    out = ST.sections_from_segments(segs, db)
    assert [(s["start_bar"], s["name"], s["label"]) for s in out] == [
        (1, "Intro", "A"), (9, "Couplet 1", "B"), (25, "Refrain 1", "C"), (41, "Couplet 2", "B"), (57, "Outro", "D")]


def test_snap_nearest_bar_and_phrase_preference():
    db = grid(48)
    # 8.4 -> 8 (le plus proche) ; 23.2 -> 24 (carrure de 4 depuis 8, à <= 1 mesure) ; 34.6 -> 35 (32 et 36 trop loin)
    segs = [seg(0, 8.4, "intro"), seg(8.4, 23.2, "verse"), seg(23.2, 34.6, "chorus"), seg(34.6, 48, "bridge")]
    sn = ST.snap_segments(segs, db)
    assert [(s["start_bar"], s["end_bar"]) for s in sn] == [(0, 8), (8, 24), (24, 35), (35, 48)]
    # 4-carrure préférée seulement à <= 1 mesure : 23.1 -> 24 (16 mesures depuis 8), 22.8 -> 23
    sn = ST.snap_segments([seg(0, 8, "intro"), seg(8, 23.1, "verse"), seg(23.1, 48, "chorus")], db)
    assert [s["start_bar"] for s in sn] == [0, 8, 24]
    sn = ST.snap_segments([seg(0, 8, "intro"), seg(8, 22.8, "verse"), seg(22.8, 48, "chorus")], db)
    assert [s["start_bar"] for s in sn] == [0, 8, 23]


def test_silence_ends_ignored_short_merged_first_last_bounds():
    db = grid(40)
    segs = [seg(-1, 0.3, "silence"), seg(0.3, 8, "intro"), seg(8, 9, "inst"), seg(9, 24, "verse"),
            seg(24, 39.5, "chorus"), seg(39.5, 41, "silence")]
    sn = ST.snap_segments(segs, db)
    assert sn[0]["start_bar"] == 0 and sn[-1]["end_bar"] == 40
    assert all(s["label"] != "silence" for s in sn)
    assert all(s["end_bar"] - s["start_bar"] >= ST.MIN_BARS for s in sn)
    assert [s["label"] for s in sn] == ["intro", "verse", "chorus"]


def test_same_label_consecutive_merged_when_short():
    db = grid(40)
    sn = ST.snap_segments([seg(0, 4, "intro"), seg(4, 12, "verse"), seg(12, 16, "verse"), seg(16, 40, "chorus")], db)
    assert [(s["start_bar"], s["label"]) for s in sn] == [(0, "intro"), (4, "verse"), (16, "chorus")]
    # trop long (> 16 mesures) : deux couplets distincts
    sn = ST.snap_segments([seg(0, 16, "verse"), seg(16, 32, "verse"), seg(32, 40, "outro")], db)
    assert len(sn) == 3


def test_numbering_unknown_label_and_empty():
    db = grid(32)
    out = ST.sections_from_segments([seg(0, 8, "intro"), seg(8, 16, "weird"), seg(16, 24, "inst"),
                                     seg(24, 32, "inst")], db)
    names = [s["name"] for s in out]
    assert names[0] == "Intro" and names[1] == "Section"
    assert ST.sections_from_segments([seg(0, 32, "silence")], db) == []
    assert ST.sections_from_segments([], db) == []


def test_solo_from_guitar_and_voice():
    db = grid(32)
    segs = [seg(0, 8, "verse"), seg(8, 16, "inst"), seg(16, 24, "chorus"), seg(24, 32, "inst")]
    g = [-20.0] * 32
    g[8:16] = [-10.0] * 8                   # guitare lead nettement plus forte, voix muette
    voc = [0.8] * 32
    voc[8:16] = [0.0] * 8
    voc[24:32] = [0.0] * 8
    out = ST.sections_from_segments(segs, db, {"guitar_db": g, "lead": True, "vocal": voc})
    assert [s["name"] for s in out] == ["Couplet 1", "Solo", "Refrain 1", "Instrumental"]
    # voix présente : pas de solo
    out = ST.sections_from_segments(segs, db, {"guitar_db": g, "lead": True, "vocal": [0.8] * 32})
    assert "Solo" not in [s["name"] for s in out]


def test_names_localized_in_english():
    from reacue_mcp.analysis import resection
    from reacue_mcp.i18n import set_lang
    from reacue_mcp import server
    a = make_analysis(Path("/x/a.wav"), 32)
    a = resection(a, ST.sections_from_segments([seg(0, 8, "intro"), seg(8, 16, "pre-chorus"),
                                                seg(16, 24, "inst"), seg(24, 32, "chorus")], a.downbeats))
    try:
        set_lang("en")
        server.localize_analysis(a)
        assert [s.name for s in a.sections] == ["Intro", "Pre-chorus 1", "Instrumental", "Chorus 1"]
    finally:
        set_lang("fr")


# --------------------------------------------------------------------------- moteur simulé
FAKE_APP = r'''
import json, os, time
def download_all(use_mirror=False):
    open(os.environ["FAKE_LOG"], "a").write("download\n")
def initialize_models(model_name, checkpoint, config_path):
    open(os.environ["FAKE_LOG"], "a").write(f"init {model_name} {checkpoint} {config_path}\n")
def process_audio(path, win_size, hop_size):
    open(os.environ["FAKE_LOG"], "a").write(f"process {os.path.basename(path)} {win_size} {hop_size}\n")
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    if os.environ.get("FAKE_FAIL"):
        raise MemoryError("out of memory")
    return None, json.load(open(os.environ["FAKE_SEGMENTS"]))
def rule_post_processing(msa):
    return msa
def format_as_segments(msa):
    return msa
'''


def fake_install(tmp_path, segments, monkeypatch, sleep=0, fail=False):
    """Dossier d'installation de ReaCue avec .venv-structure (python actuel) et un faux SongFormer."""
    inst = tmp_path / "ReaCue"
    sf = inst / "structure" / "SongFormer"
    sf.mkdir(parents=True)
    (sf / "app.py").write_text(FAKE_APP, encoding="utf-8")
    (sf / "torch.py").write_text("def set_num_threads(n): pass\n__version__ = 'fake'\n", encoding="utf-8")
    shutil.copy(ROOT / "reacue_structure.py", inst / "reacue_structure.py")
    shutil.copy(ROOT / "reacue_metal.py", inst / "reacue_metal.py")
    shutil.copy(ROOT / "reacue_performance.py", inst / "reacue_performance.py")
    py = ST.structure_python(inst)
    py.parent.mkdir(parents=True)
    if os.name == "nt":
        shutil.copy(sys.executable, py)
    else:
        py.symlink_to(sys.executable)
    (tmp_path / "segments.json").write_text(json.dumps(segments), encoding="utf-8")
    monkeypatch.setenv("FAKE_SEGMENTS", str(tmp_path / "segments.json"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv("FAKE_SLEEP", str(sleep))
    monkeypatch.delenv("REACUE_STRUCTURE_DIR", raising=False)
    if fail:
        monkeypatch.setenv("FAKE_FAIL", "1")
    else:
        monkeypatch.delenv("FAKE_FAIL", raising=False)
    return inst


def make_analysis(audio: Path, n_bars=40):
    db = grid(n_bars)
    return Analysis(file=str(audio), duration=db[-1] + 1, bpm=120.0, beats_per_bar=4, denominator=4,
                    tempo_stable=True, tempo_cv=0.0, beats=[], downbeats=db,
                    sections=[Section(0, n_bars, "A", "Couplet", 0.0)])


SEGS = [seg(0, 8, "intro"), seg(8, 24, "verse"), seg(24, 40, "chorus")]


def test_launcher_analyze_and_window(tmp_path, monkeypatch):
    inst = fake_install(tmp_path, SEGS, monkeypatch)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF")
    out, st = tmp_path / "r.json", tmp_path / "st.json"
    r = subprocess.run([str(ST.structure_python(inst)), str(inst / "reacue_structure.py"), "analyze",
                        "--input", str(audio), "--out", str(out), "--status", str(st), "--window", "120"],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["engine"] == "songformer" and res["window_s"] == 120 and len(res["segments"]) == 3
    assert json.loads(st.read_text(encoding="utf-8"))["state"] == "done"
    log = (tmp_path / "fake.log").read_text()
    assert "init SongFormer SongFormer.safetensors SongFormer.yaml" in log and "process song.wav 120 120" in log
    # fichier absent : état « error »
    r = subprocess.run([str(ST.structure_python(inst)), str(inst / "reacue_structure.py"), "analyze",
                        "--input", str(tmp_path / "none.wav"), "--out", str(out), "--status", str(st)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and json.loads(st.read_text(encoding="utf-8"))["state"] == "error"


def test_choose_window_from_ram():
    sys.path.insert(0, str(ROOT))
    import reacue_structure as RS
    assert RS.choose_window("auto", 16) == 420
    assert RS.choose_window("auto", 8) == 120
    assert RS.choose_window("300", 8) == 300 and RS.choose_window("5", 64) == 30
    assert RS.ram_gb() > 0


def test_apply_engine_runs_caches_and_invalidates(tmp_path, monkeypatch):
    inst = fake_install(tmp_path, SEGS, monkeypatch)
    audio = tmp_path / "media" / "Mon morceau.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"RIFF0000")
    steps = []
    monkeypatch.setattr(ST, "PROGRESS", steps.append)
    a, info = ST.apply_engine(make_analysis(audio), None, "Mon morceau", install_dir=inst, engine="auto")
    assert info["engine"] == "songformer" and info["cached"] is False, info
    assert [s.name for s in a.sections] == ["Intro", "Couplet 1", "Refrain 1"]
    assert [s.start_bar for s in a.sections] == [0, 8, 24] and a.sections[-1].end_bar == 40
    assert steps and "Analyse de structure" in steps[0]
    cache = audio.parent / ".reacue" / "Mon morceau_structure.json"
    assert json.loads(cache.read_text(encoding="utf-8"))["rev"] == ST.SONGFORMER_REV
    # 2e fois : cache (le moteur n'est pas relancé)
    (tmp_path / "fake.log").write_text("")
    a, info = ST.apply_engine(make_analysis(audio), None, "Mon morceau", install_dir=inst, engine="auto")
    assert info["cached"] is True and (tmp_path / "fake.log").read_text() == ""
    assert "mémorisé" in info["message"]
    # audio modifié : cache invalidé
    time.sleep(1.1)
    audio.write_bytes(b"RIFF00001111")
    a, info = ST.apply_engine(make_analysis(audio), None, "Mon morceau", install_dir=inst, engine="auto")
    assert info["cached"] is False and "process" in (tmp_path / "fake.log").read_text()


def test_apply_engine_fallbacks(tmp_path, monkeypatch):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    # non installé : détection de ReaCue, sans avertissement
    a, info = ST.apply_engine(make_analysis(audio), install_dir=tmp_path / "none", engine="auto")
    assert info == {"engine": "reacue", "missing": True} and not a.warnings and a.sections[0].name == "Couplet"
    inst = fake_install(tmp_path, SEGS, monkeypatch, fail=True)
    # réglage « reacue » : SongFormer pas lancé
    a, info = ST.apply_engine(make_analysis(audio), install_dir=inst, engine="reacue")
    assert info["engine"] == "reacue" and not (tmp_path / "fake.log").exists()
    # échec du moteur : avertissement + structure de ReaCue conservée
    a, info = ST.apply_engine(make_analysis(audio), install_dir=inst, engine="auto")
    assert info["engine"] == "reacue" and "MemoryError" in info["error"]
    assert a.sections[0].name == "Couplet" and "→ structure ReaCue utilisée" in a.warnings[-1] and info["fallback"]


def test_apply_engine_empty_result_falls_back(tmp_path, monkeypatch):
    inst = fake_install(tmp_path, [seg(0, 40, "silence")], monkeypatch)
    audio = tmp_path / "b.wav"
    audio.write_bytes(b"RIFF")
    a, info = ST.apply_engine(make_analysis(audio), install_dir=inst, engine="auto")
    assert info["engine"] == "reacue" and a.sections[0].name == "Couplet" and a.warnings


def test_run_engine_timeout_and_progress(tmp_path, monkeypatch):
    inst = fake_install(tmp_path, SEGS, monkeypatch, sleep=30)
    audio = tmp_path / "c.wav"
    audio.write_bytes(b"RIFF")
    with pytest.raises(RuntimeError, match="SongFormer"):
        ST.run_engine(str(audio), tmp_path / "o" / "r.json", inst, timeout=2)


def test_engine_setting(tmp_path, monkeypatch):
    from reacue_mcp import settings as S
    assert ST.engine_setting() == "reacue"              # tests : jamais le vrai SongFormer
    monkeypatch.delenv("REACUE_STRUCTURE_ENGINE")
    assert S.DEFAULTS["structure_engine"] == "auto"
    monkeypatch.setattr("reacue_mcp.settings.load_settings", lambda: {"structure_engine": "reacue"})
    assert ST.engine_setting() == "reacue"
    monkeypatch.setattr("reacue_mcp.settings.load_settings", lambda: {"structure_engine": "bogus"})
    assert ST.engine_setting() == "auto"


def test_write_mix_aligns_stems(tmp_path):
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    sr = 22050
    a = np.zeros(sr * 2, dtype=np.float32)
    a[sr // 2] = 1.0                         # clic à 0,5 s dans le stem de référence
    b = np.zeros(sr * 2, dtype=np.float32)
    b[0] = 1.0                               # clic au début d'un stem posé 1 s plus tard
    sf.write(str(tmp_path / "a.wav"), a, sr)
    sf.write(str(tmp_path / "b.wav"), b, sr)
    out = ST._write_mix([{"file": str(tmp_path / "a.wav"), "shift": 0.0},
                         {"file": str(tmp_path / "b.wav"), "shift": 1.0}], tmp_path / "m.wav")
    y, _ = sf.read(str(out))
    peaks = sorted(int(i) for i in np.argsort(np.abs(y))[-2:])
    assert abs(peaks[0] - sr // 2) < 5 and abs(peaks[1] - sr) < 5


# --------------------------------------------------------------------------- installation
def test_pinned_revisions_consistent():
    for f in ("install/install_structure_mac.sh", "install/install_structure_windows.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8-sig")
        for rev in (ST.SONGFORMER_REV, ST.MUQ_REV, ST.MUSICFM_REV):
            assert rev in txt, (f, rev)
        assert "--no-deps" in txt and "requirements-structure.txt" in txt
    assert "STRUCTURE_OK" in (ROOT / "reacue_structure.py").read_text(encoding="utf-8")


def test_requirements_structure_pins():
    req = (ROOT / "requirements-structure.txt").read_text(encoding="utf-8")
    assert 'torch==2.2.2 ; sys_platform == "darwin" and platform_machine == "x86_64"' in req
    assert re.search(r"numpy<2", req)
    from packaging.requirements import Requirement
    torch_reqs = [Requirement(line) for line in req.splitlines() if line.startswith("torch")]
    intel = {"sys_platform": "darwin", "platform_machine": "x86_64"}
    windows = {"sys_platform": "win32", "platform_machine": "AMD64"}
    assert all("2.2.2" in r.specifier for r in torch_reqs if r.name in ("torch", "torchaudio") and r.marker.evaluate(intel))
    for r in torch_reqs:
        if r.name in ("torch", "torchaudio") and r.marker.evaluate(windows):
            assert "2.4.1" in r.specifier and "2.4.0" not in r.specifier and "2.9" not in r.specifier
    assert not any(p.suffix in (".safetensors", ".ckpt", ".pt", ".bin") for p in ROOT.rglob("*")
                   if ".venv" not in p.parts and "structure" not in p.parts[:len(ROOT.parts) + 1])


def test_installer_scripts_syntax():
    for f in ("install/install_structure_mac.sh", "install/install_mac.sh", "Install ReaCue Structure.command"):
        assert subprocess.run(["bash", "-n", str(ROOT / f)]).returncode == 0, f
    assert os.access(ROOT / "Install ReaCue Structure.command", os.X_OK)
    assert os.access(ROOT / "install" / "install_structure_mac.sh", os.X_OK)
    ps = (ROOT / "install" / "install_structure_windows.ps1").read_bytes()
    assert ps.startswith(b"\xef\xbb\xbf") and b"\r\n" in ps
    bat = (ROOT / "Install ReaCue Structure.bat").read_bytes()
    assert b"\r\n" in bat and b"install_structure_windows.ps1" in bat
    for f in ("install/install_mac.sh", "install/install_windows.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8-sig")
        assert "install_structure_" in txt
        steps = [(int(n), int(total)) for n, total in re.findall(r"== (\d+)/(\d+)", txt)]
        assert steps and len({total for _, total in steps}) == 1
        assert {n for n, _ in steps} == set(range(1, steps[0][1] + 1))
        # SongFormer proposé par défaut (réponse vide = oui), « J'accepte » reste exigé par install_structure_*
        assert "[O/n]" in txt and "[Y/n]" in txt and "[o/N] ' \\\n                  '  Install structure" not in txt
        assert "J'accepte" in txt
    sh = (ROOT / "install" / "install_mac.sh").read_text(encoding="utf-8")
    structure_block = sh.split('if [ "$STRUCT" = ask ]; then', 1)[1].split('if [ "$STRUCT" = yes ]; then', 1)[0]
    assert 'case "$(echo "${A:-o}"' in structure_block
    ps1 = (ROOT / "install" / "install_windows.ps1").read_text(encoding="utf-8-sig")
    assert 'StartsWith("n")) { "no" } else { "yes" }' in ps1
    # modèles déjà téléchargés réutilisés avant le test (qui télécharge le reste)
    for f in ("install/install_structure_mac.sh", "install/install_structure_windows.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8-sig")
        assert "reacue_structure.py\") reuse" in txt or "reacue_structure.py reuse" in txt, f
        assert txt.index(" reuse ") < txt.index(" check ")
    pwsh = shutil.which("pwsh")
    if pwsh:
        for f in ("install/install_structure_windows.ps1", "install/install_windows.ps1"):
            cmd = ("$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
                   f"'{ROOT / f}',[ref]$null,[ref]$e);$e.Count")
            r = subprocess.run([pwsh, "-NoProfile", "-Command", cmd], capture_output=True, text=True)
            assert r.stdout.strip() == "0", (f, r.stdout, r.stderr)


def test_gitignore_excludes_models():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".venv-structure/" in gi and "/structure/" in gi


def test_setup_status_and_purge(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / "install"))
    import reacue_setup as S
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: tmp_path / "none.json")
    assert S.SETTINGS_DEFAULTS["structure_engine"] == "auto"
    assert S.structure_python(Path("C:/R"), "win32") == Path("C:/R/.venv-structure/Scripts/python.exe")
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    inst = tmp_path / "ReaCue"
    (inst / "reaper").mkdir(parents=True)
    for f in S.SCRIPT_FILES:
        (inst / "reaper" / f).write_bytes((ROOT / "reaper" / f).read_bytes())
    (inst / ".venv-structure" / "bin").mkdir(parents=True)
    (inst / ".venv-structure" / "bin" / "python").write_text("")
    (inst / "structure" / "hf").mkdir(parents=True)
    args = ["install", "--lang", "fr", "--install-dir", str(inst), "--reaper-dir", str(reaper), "--mcp", "no",
            "--reaper-running", "no"]
    S.main(args)
    capsys.readouterr()
    S.main(["status", "--reaper-dir", str(reaper)])
    assert json.loads(capsys.readouterr().out)["structure"] is True
    S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"])
    assert (inst / "structure").exists() and "Analyse de structure conservée" in capsys.readouterr().out
    S.main(args)
    S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no", "--purge"])
    assert not (inst / "structure").exists() and not (inst / ".venv-structure").exists()


# --------------------------------------------------------------------------- banc d'essai
def test_struct_eval_songformer_sections(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import struct_eval as E
    db = grid(40)
    secs = E.sf_sections(SEGS, db, 40)
    assert [(s.start_bar, s.end_bar, s.name) for s in secs] == [(0, 8, "Intro"), (8, 24, "Couplet 1"),
                                                                (24, 40, "Refrain 1")]
    sc = E.score([(1, "Intro"), (9, "Verse 1"), (25, "Chorus 1")], 40, secs)
    assert sc["F0"] == 1.0 and sc["name_bars"] == 1.0
    song = tmp_path / "Song"
    (song / ".reacue").mkdir(parents=True)
    (song / ".reacue" / "Song_structure.json").write_text(json.dumps({"segments": SEGS}), encoding="utf-8")
    p = E.sf_result_path({"path": str(song / "a.mp3")})
    assert p and E.sf_segments(p) == SEGS
    (tmp_path / "x.json").write_text(json.dumps(SEGS), encoding="utf-8")
    assert E.sf_segments(E.sf_result_path({"songformer": str(tmp_path / "x.json")})) == SEGS
    assert E.sf_result_path({"path": str(tmp_path / "nothing" / "a.mp3")}) is None


# --------------------------------------------------------------------------- REAPER (Lua)
def test_lua_settings_structure_and_installed(tmp_path):
    pytest.importorskip("lupa")
    import test_reacue_window as W
    concert = W.TL.make_concert(tmp_path / "c")
    L, g = W.rt(concert, proj=tmp_path / "x.RPP", tracks=False)
    sp = Path(g.RES) / "ReaCueMCP" / "reacue_settings.json"
    sp.write_text(json.dumps({"language": "fr"}), encoding="utf-8")
    inst = tmp_path / "inst"
    (inst / ".venv-structure" / "bin").mkdir(parents=True)
    L.globals().reaper.SetExtState("ReaCue", "install_dir", str(inst), True)
    W.open_window(L, g)
    W.frame(L, g)
    W.press_text(L, g, "Réglages", exact=True)
    W.frame(L, g)
    T = W.TL.texts(g)
    assert "Détection de structure" in T and any("SongFormer non installé" in x for x in T), T
    W.press_text(L, g, "ReaCue seul", exact=True)
    assert json.loads(sp.read_text(encoding="utf-8"))["structure_engine"] == "reacue"
    R = L.execute(f"return dofile([[{W.LUA_DIR / 'ReaCue_run.lua'}]])")
    assert not R.structure_installed(str(inst), False)
    (inst / ".venv-structure" / "bin" / "python").write_text("")
    (inst / "reacue_structure.py").write_text("")
    assert R.structure_installed(str(inst), False)
    W.frame(L, g)
    assert "SongFormer installé" in W.TL.texts(g), W.TL.texts(g)


# --------------------------------------------------------------------------- cas réel
# Cas réel (une chanson française, titre non cité) : 105,12 BPM, mesure 1 à 0,6668 s dans le fichier ; segments bruts de SongFormer
# (Mac 16 Go, fenêtre 420 s). Frontières attendues exactement aux mesures 9/17/25/33/41/49/57/73.
REAL105_BAR = 4 * 60 / 105.12
REAL105_DB = [0.6668 + REAL105_BAR * i for i in range(85)]
REAL105 = [(0.0, 18.72, "intro"), (18.72, 37.08, "verse"), (37.08, 55.32, "verse"), (55.32, 73.56, "inst"),
        (73.56, 91.80, "verse"), (91.80, 110.04, "bridge"), (110.04, 128.41, "chorus"),
        (128.41, 164.89, "inst"), (164.89, 190.93, "outro"), (190.93, 192.01, "silence")]


def test_real_case_105_bpm():
    segs = [{"start": a, "end": b, "label": l} for a, b, l in REAL105]
    out = ST.sections_from_segments(segs, REAL105_DB)
    assert [s["start_bar"] for s in out] == [1, 9, 17, 25, 33, 41, 49, 57, 73]
    assert [s["name"] for s in out] == ["Intro", "Couplet 1", "Couplet 2", "Instrumental", "Couplet 3", "Pont",
                                        "Refrain 1", "Instrumental", "Outro"]
    # mêmes groupes (lettres) pour les couplets et les deux instrumentaux
    lab = {s["name"]: s["label"] for s in out}
    assert lab["Couplet 1"] == lab["Couplet 2"] == lab["Couplet 3"] and out[3]["label"] == out[7]["label"]
    # avec stems : guitare lead nettement au-dessus et voix absente sur le 2e instrumental -> Solo
    g = [-30.0] * 84
    for i in range(56, 72):
        g[i] = -12.0
    voc = [0.8] * 84
    for i in list(range(24, 32)) + list(range(56, 72)):
        voc[i] = 0.0
    out = ST.sections_from_segments(segs, REAL105_DB, {"guitar_db": g, "lead": True, "vocal": voc})
    assert out[7]["name"] == "Solo" and out[3]["name"] == "Instrumental"


# --------------------------------------------------------------------------- réutilisation des modèles
def _rs():
    sys.path.insert(0, str(ROOT))
    import reacue_structure as RS
    return RS


def _fake_labo(home: Path, corrupt=False):
    ck = home / "Documents" / "ReaCue-labo" / "SongFormer" / "src" / "SongFormer" / "ckpts"
    (ck / "MusicFM").mkdir(parents=True)
    import hashlib
    files = {"SongFormer.safetensors": b"songformer-weights", "MusicFM/pretrained_msd.pt": b"musicfm-pt",
             "MusicFM/msd_stats.json": b'{"m": 1}'}
    lines = []
    for rel, data in files.items():
        (ck / rel).write_bytes(data)
        lines.append(f"{hashlib.md5(data).hexdigest()}    {rel}")
    if corrupt:
        (ck / "SongFormer.safetensors").write_bytes(b"truncated")
    (ck / "md5sum.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    hub = home / ".cache" / "huggingface" / "hub"
    for repo in ("models--OpenMuQ--MuQ-large-msd-iter", "models--facebook--wav2vec2-conformer-rope-large-960h-ft"):
        blob = hub / repo / "blobs" / "abc123"
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b"weights-" + repo.encode())
        snap = hub / repo / "snapshots" / "rev1"
        snap.mkdir(parents=True)
        (hub / repo / "refs").mkdir()
        (hub / repo / "refs" / "main").write_text("rev1")
        if os.name == "nt":
            shutil.copy(blob, snap / "model.bin")
        else:
            (snap / "model.bin").symlink_to(Path("..") / ".." / "blobs" / "abc123")
    return ck, hub


def test_reuse_models_from_labo_and_hf_cache(tmp_path, monkeypatch):
    RS = _rs()
    for v in ("HF_HOME", "HF_HUB_CACHE", "XDG_CACHE_HOME", "USERPROFILE", "REACUE_REUSE_DIRS", "REACUE_HF_SOURCE"):
        monkeypatch.delenv(v, raising=False)
    home = tmp_path / "home"
    ck, hub = _fake_labo(home)
    struct = tmp_path / "ReaCue" / "structure"
    logs = []
    res = RS.reuse(struct_dir=struct, home=home, log=logs.append)
    dest = RS.ckpts_dir(struct)
    assert sorted(res["ckpts"]) == sorted(RS.CKPTS) and sorted(res["hf"]) == sorted(RS.HF_REPOS)
    assert (dest / "SongFormer.safetensors").read_bytes() == b"songformer-weights"
    assert (dest / "MusicFM" / "msd_stats.json").is_file()
    m = struct / "hf" / "hub" / "models--OpenMuQ--MuQ-large-msd-iter" / "snapshots" / "rev1" / "model.bin"
    assert m.read_bytes().startswith(b"weights-")           # lien relatif conservé et résolu
    assert any("ReaCue-labo" in x for x in logs)
    # sources intactes (jamais déplacées ni supprimées)
    assert (ck / "SongFormer.safetensors").read_bytes() == b"songformer-weights" and (hub / RS.HF_REPOS[0]).is_dir()
    # 2e passage : rien à faire
    res = RS.reuse(struct_dir=struct, home=home, log=logs.append)
    assert res["ckpts"] == [] and res["hf"] == []


def test_reuse_rejects_bad_md5_and_incomplete_cache(tmp_path, monkeypatch):
    RS = _rs()
    for v in ("HF_HOME", "HF_HUB_CACHE", "XDG_CACHE_HOME", "USERPROFILE", "REACUE_REUSE_DIRS", "REACUE_HF_SOURCE"):
        monkeypatch.delenv(v, raising=False)
    home = tmp_path / "home"
    ck, hub = _fake_labo(home, corrupt=True)
    # snapshot vide (téléchargement interrompu) : pas copié
    (hub / RS.HF_REPOS[1] / "snapshots" / "rev1" / "model.bin").unlink()
    struct = tmp_path / "ReaCue" / "structure"
    res = RS.reuse(struct_dir=struct, home=home, log=lambda *_: None)
    assert "SongFormer.safetensors" not in res["ckpts"] and "MusicFM/pretrained_msd.pt" in res["ckpts"]
    assert not (RS.ckpts_dir(struct) / "SongFormer.safetensors").exists()
    assert res["hf"] == [RS.HF_REPOS[0]] and any(r == "md5" for _, r in res["skipped"])


def test_reuse_from_windows_profile_and_cli(tmp_path, monkeypatch):
    RS = _rs()
    for v in ("HF_HOME", "HF_HUB_CACHE", "XDG_CACHE_HOME", "REACUE_REUSE_DIRS", "REACUE_HF_SOURCE"):
        monkeypatch.delenv(v, raising=False)
    prof = tmp_path / "Users" / "musicien"
    _fake_labo(prof)
    monkeypatch.setenv("USERPROFILE", str(prof))
    assert prof / ".cache" / "huggingface" / "hub" in RS.hf_sources(home=tmp_path / "vide")
    # sous-commande « reuse » : jamais bloquante (code 0), même sans rien à réutiliser
    inst = tmp_path / "ReaCue"
    inst.mkdir()
    shutil.copy(ROOT / "reacue_structure.py", inst / "reacue_structure.py")
    shutil.copy(ROOT / "reacue_metal.py", inst / "reacue_metal.py")
    shutil.copy(ROOT / "reacue_performance.py", inst / "reacue_performance.py")
    env = {**os.environ, "HOME": str(tmp_path / "vide"), "USERPROFILE": str(tmp_path / "vide")}
    env.pop("HF_HOME", None)
    r = subprocess.run([sys.executable, str(inst / "reacue_structure.py"), "reuse", "--lang", "en"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "no already-downloaded model" in r.stdout, r.stdout + r.stderr


def test_doubts_moved_and_unsure():
    db = grid(48)
    segs = [seg(0, 8, "intro"), seg(8.45, 23.2, "verse"), seg(23.2, 34.6, "chorus"), seg(34.6, 48, "bridge")]
    secs = ST.sections_from_segments(segs, db)
    d = {x["start_bar"]: x["reason"] for x in ST.doubts(segs, db, secs)}
    # 8,45 -> 9 (0-based 8) : entre deux mesures ; 23,2 -> 24 (carrure) : déplacée ; 34,6 -> 35 : entre deux
    assert d == {9: "unsure", 25: "moved", 36: "unsure"}, d
    # cas réel : aucune frontière douteuse
    real = [{"start": a, "end": b, "label": l} for a, b, l in REAL105]
    assert ST.doubts(real, REAL105_DB, ST.sections_from_segments(real, REAL105_DB)) == []
