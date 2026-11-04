"""Transcription de batterie par modèle (ADTOF, composant optionnel) : quantification sur la grille, triolets,
sous-classes par le signal (toms, charley ouvert, ride / crash), format du prompteur, lanceur reacue_drums.py
avec un faux ADTOF (aucun modèle téléchargé, torch simulé), cache, repli sur les règles, installateurs.
Batterie synthétique uniquement (tests/drum_synth.py)."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import drum_synth as DS
from reacue_mcp import drums as D
from reacue_mcp.analysis import SR, Analysis, Section

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reacue_drums as RD  # noqa: E402

TO_CLASS = {"BD": "BD", "SD": "SD", "T1": "TT", "T2": "TT", "FT": "TT", "HH": "HH", "HO": "HH", "RD": "CY", "CR": "CY"}


def truth_onsets(score, downbeats, steps, latency=0.0, jitter=0.0, seed=1):
    """Coups « parfaits » d'un modèle : {classe ADTOF: [[t, p]]}."""
    rng = np.random.default_rng(seed)
    out = {c: [] for c in RD.CLASSES}
    for b, hits in enumerate(score):
        bar = downbeats[b + 1] - downbeats[b]
        for lane, st in hits.items():
            for s in st:
                t = downbeats[b] + s * bar / steps + latency + (rng.uniform(-jitter, jitter) if jitter else 0.0)
                out[TO_CLASS[lane]].append([round(t, 3), 0.9])
    return {"onsets": {c: sorted(v) for c, v in out.items()}}


def analysis_for(score, secs, wav, downbeats, bpm=120.0):
    return Analysis(file=str(wav), duration=downbeats[-1] + 2, bpm=bpm, beats_per_bar=4, denominator=4,
                    tempo_stable=True, tempo_cv=0.0, beats=[], downbeats=downbeats,
                    sections=[Section(s, e, "A", n, 0.0) for s, e, n in secs], stems={"drums": str(wav)})


def exact(out, score):
    ok = tot = 0
    for e, truth in zip(out["bars"], score):
        h = e.get("hits") or {}
        for lane, st in truth.items():
            tot += len(st)
            ok += len(set(st) & set(h.get(lane, [])))
    return ok, tot


@pytest.fixture(scope="module")
def demo():
    score, secs = DS.demo_score()
    y, db = DS.render(score, sr=SR)
    return score, secs, y, db


# --------------------------------------------------------------------------- quantification
def test_quantize_variable_bars_and_wrap():
    db = [1.0, 3.0, 5.2, 7.0]                       # mesures de longueurs différentes (beatmap)
    t = [1.0, 1.5, 2.99, 3.0 + 2.2 * 0.5, 5.2 + 1.8 * 0.75, 0.97, 7.5, 0.5]
    bar, s, ok = D.quantize(t, db, 16)
    assert list(ok) == [True, True, True, True, True, True, False, False]
    assert [(int(b), int(x)) for b, x, o in zip(bar, s, ok) if o] == [(0, 0), (0, 4), (1, 0), (1, 8), (2, 12), (0, 0)]
    b, s, ok = D.quantize([], db, 16)
    assert len(b) == 0


def test_grid_offset_and_clip():
    db = [1.0 + 2.0 * k for k in range(9)]
    t = [d + 0.5 * k + 0.018 for d in db[:-1] for k in range(4)]
    assert abs(D.grid_offset(t, db, 4) - 0.018) < 1e-6
    assert D.grid_offset([x + 0.1 for x in t], db, 4) in (-0.04, 0.04)
    assert D.grid_offset(t[:2], db, 4) == 0.0


def test_choose_steps_straight_triplets_and_compound():
    db = [1.0 + 2.0 * k for k in range(9)]
    beat = 0.5
    straight = [d + i * beat / 4 for d in db[:-1] for i in range(16) if i % 2 or i % 4 == 2]
    shuffle = [d + b * beat + f * beat for d in db[:-1] for b in range(4) for f in (0, 2 / 3)]
    assert D.choose_steps(straight, db, 4, 4) == 16
    assert D.choose_steps(shuffle, db, 4, 4) == 12
    db3 = [1.0 + 1.5 * k for k in range(9)]                   # 3/4 en ternaire : 9 pas
    shuffle3 = [d + b * beat + f * beat for d in db3[:-1] for b in range(3) for f in (0, 2 / 3)]
    assert D.choose_steps(shuffle3, db3, 3, 4) == 9
    assert D.choose_steps(shuffle, db, 6, 8) == 12          # 6/8 : croches subdivisées, pas de choix
    assert D.choose_steps([d for d in db], db, 4, 4) == 16  # que des temps : rien ne départage


def test_tom_lanes_by_pitch():
    assert D._tom_lanes([200, 205, 140, 95, 92, 141]) == ["T1", "T1", "T2", "FT", "FT", "T2"]
    assert D._tom_lanes([180, 100, 182]) == ["T1", "FT", "T1"]
    assert D._tom_lanes([150, 152]) == ["T2", "T2"]          # une seule hauteur : seuils absolus
    assert D._tom_lanes([]) == []


def test_pick_peaks_madmom_like():
    act = np.zeros(300, np.float32)
    for i, v in ((50, 0.9), (52, 0.5), (120, 0.3), (200, 0.1), (250, 0.8)):
        act[i] = v
    p = RD.pick_peaks(act, 0.22)
    assert [x[0] for x in p] == [0.5, 1.2, 2.5] and p[0][1] == 0.9
    assert RD.pick_peaks(np.zeros(0), 0.2) == []
    on = RD.onsets_from_activations(np.stack([act] * 5, 1))
    assert set(on) == set(RD.CLASSES) and len(on["TT"]) == 2          # seuil des toms : 0,32


# --------------------------------------------------------------------------- coups du modèle -> format
def test_from_model_demo_song(demo):
    score, secs, y, db = demo
    a = analysis_for(score, secs, "/x/drums.wav", db)
    out = D.from_model(a, y, truth_onsets(score, db, 16))
    assert out["engine"] == "adtof" and out["steps"] == 16 and out["version"] == D.VERSION
    ok, tot = exact(out, score)
    assert ok >= 0.97 * tot, (ok, tot)
    b = out["bars"]
    for k in (5, 7, 9):                                      # charley ouvert sur le « et » de 4
        assert b[k]["hits"].get("HO") == [14], b[k]
    assert "HO" not in b[4]["hits"] and b[4]["hits"]["HH"] == ROCK_HH
    assert b[12]["crash"] and b[12]["hits"]["CR"] == [0] and "RD" in b[13]["hits"]
    assert b[11]["fill"] and b[19]["fill"]
    assert b[11]["hits"]["T1"] == [8, 9] and b[11]["hits"]["T2"] == [10, 11] and b[11]["hits"]["FT"] == [12, 13, 14, 15]
    pats = out["patterns"]
    assert len(pats) == 2 and pats["A"]["hits"]["HH"] == ROCK_HH and pats["B"]["hits"]["RD"] == ROCK_HH
    assert pats["A"]["name"].startswith("Groove A — intro")
    assert b[0]["pattern"] == "A" and b[13]["pattern"] == "B"
    assert set(out["lanes"]) == {"CR", "HH", "HO", "RD", "SD", "T1", "T2", "FT", "BD"}
    assert [l for l in D.LANES if l in out["lanes"]] == out["lanes"]       # ordre de D.LANES


ROCK_HH = [0, 2, 4, 6, 8, 10, 12, 14]


def test_from_model_latency_jitter_and_shift(demo):
    score, secs, y, db = demo
    a = analysis_for(score, secs, "/x/drums.wav", db)
    res = truth_onsets(score, db, 16, latency=0.025, jitter=0.012)
    out = D.from_model(a, y, res)
    assert 20 <= out["offset_ms"] <= 30
    ok, tot = exact(out, score)
    assert ok >= 0.95 * tot, (ok, tot)
    # stem décalé de 0,5 s par rapport à la référence : temps du stem + décalage
    res2 = {"onsets": {c: [[t - 0.5, p] for t, p in v] for c, v in res["onsets"].items()}}
    out2 = D.from_model(a, y, res2, shift=0.5)
    assert [e.get("hits") for e in out2["bars"]] == [e.get("hits") for e in out["bars"]]


def test_from_model_shuffle_triplets():
    groove = {"HH": [0, 2, 3, 5, 6, 8, 9, 11], "BD": [0, 6], "SD": [3, 9]}
    score = [dict(groove) for _ in range(8)]
    y, db = DS.render(score, steps=12, sr=SR)
    a = analysis_for(score, [(0, 8, "Couplet 1")], "/x/d.wav", db)
    out = D.from_model(a, y, truth_onsets(score, db, 12))
    assert out["steps"] == 12
    assert out["patterns"]["A"]["hits"] == groove
    assert all(e["pattern"] == "A" and not e["fill"] for e in out["bars"])


def test_from_model_rests_and_empty_classes():
    score = [dict(DS.ROCK) for _ in range(4)] + [{} for _ in range(2)] + [dict(DS.ROCK) for _ in range(2)]
    y, db = DS.render(score, sr=SR)
    a = analysis_for(score, [(0, 8, "Couplet 1")], "/x/d.wav", db)
    res = truth_onsets(score, db, 16)
    res["onsets"]["TT"] = []
    del res["onsets"]["CY"]
    out = D.from_model(a, y, res)
    assert [e.get("rest", False) for e in out["bars"]] == [False] * 4 + [True] * 2 + [False] * 2
    assert out["bars"][4] == {"bar": 5, "pattern": None, "rest": True}


def test_format_compatible_with_prompter_and_midi(demo, tmp_path):
    from reacue_mcp import prompter
    score, secs, y, db = demo
    a = analysis_for(score, secs, "/x/drums.wav", db)
    out = D.from_model(a, y, truth_onsets(score, db, 16))
    out = json.loads(json.dumps(out))                         # sérialisable, clés de pas en entiers
    assert set(out) >= {"steps", "lanes", "patterns", "bars", "offset_ms", "version", "engine"}
    for p in out["patterns"].values():
        assert set(p) == {"name", "hits", "accents"}
        assert all(isinstance(s, int) and 0 <= s < out["steps"] for v in p["hits"].values() for s in v)
    for i, e in enumerate(out["bars"]):
        assert e["bar"] == i + 1
        if not e.get("rest"):
            assert set(e) == {"bar", "pattern", "fill", "crash", "hits"}
            assert set(e["hits"]) <= set(D.LANES)
    timeline = {"bpm": 120.0, "tempo_mode": "constant", "count_in_bars": 2,
                "bar_times": [4.0 + 2.0 * k for k in range(a.n_bars + 3)]}
    song = prompter.build_song(a, {"file": "/x/drums.wav"}, timeline, None, {}, drums=out)
    assert song["drums"]["bars"] and song["drums"]["lanes"] == out["lanes"]
    mid = D.drums_to_midi(out, 120.0, tmp_path / "d.mid")
    data = Path(mid).read_bytes()
    assert data.startswith(b"MThd") and bytes([0x99, 46]) in data            # charley ouvert : GM 46
    out12 = {**out, "steps": 12, "bars": [{"bar": 1, "hits": {"HH": [0, 2, 3, 5]}}]}
    assert Path(D.drums_to_midi(out12, 100.0, tmp_path / "t.mid")).stat().st_size > 30


def test_rules_engine_unchanged_and_dist_with_open_hat():
    u = D._vec({"HH": {0: 1, 2: 1}, "BD": {0: 1}})
    v = D._vec({"HO": {0: 1, 2: 1}, "BD": {0: 1}})
    w = D._vec({"RD": {0: 1, 2: 1}, "BD": {0: 1}})
    assert D._dist(u, v) == pytest.approx(D._dist(u, w)) == pytest.approx(0.4 * 4)
    assert D._dist(u, u) == 0
    assert D._vec({"HH": {19: 1}}, 20).shape == (len(D.LANES), 20)       # 5/4 : 20 pas


# --------------------------------------------------------------------------- lanceur + faux ADTOF
FAKE_MODEL = r'''
import json, os, time
import numpy as np
import soundfile as sf
CL = ("BD", "SD", "TT", "HH", "CY")
ACT = None
class _Out:
    def __init__(self, a): self.a = a
    def cpu(self): return self
    def numpy(self): return self.a
class _X:
    def __init__(self, idx): self.idx = idx; self.shape = (1, len(idx), 84, 1)
    def __getitem__(self, k): return _X(self.idx[k[1]])
    def to(self, device): return self
class _Net:
    def to(self, device): return self
    def eval(self): return self
    def __call__(self, x):
        if os.environ.get("FAKE_FAIL"):
            raise MemoryError("out of memory")
        time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
        return _Out(ACT[x.idx][None])
def calculate_n_bins(): return 84
def create_frame_rnn_model(n): return _Net()
def load_pytorch_weights(net, path, strict=False):
    open(os.environ["FAKE_LOG"], "a").write("weights %s %s\n" % (os.path.basename(path), strict))
    return net
def load_audio_for_model(path):
    global ACT
    open(os.environ["FAKE_LOG"], "a").write("audio %s\n" % os.path.basename(path))
    T = int(sf.info(path).duration * 100) + 1
    ACT = np.zeros((T, 5), np.float32)
    on = json.load(open(os.environ["FAKE_ONSETS"]))["onsets"]
    for k, c in enumerate(CL):
        for t, p in on.get(c, []):
            i = int(round(t * 100))
            for d, v in zip(range(-2, 3), (0.3, 0.6, 0.9, 0.6, 0.3)):
                if 0 <= i + d < T:
                    ACT[i + d, k] = max(ACT[i + d, k], v)
    return _X(np.arange(T))
'''
FAKE_TORCH = '''
import contextlib
def set_num_threads(n): pass
def no_grad(): return contextlib.nullcontext()
def inference_mode(): return contextlib.nullcontext()
'''


def fake_install(tmp_path, onsets, monkeypatch, sleep=0, fail=False):
    inst = tmp_path / "ReaCue"
    pkg = inst / "drums" / "ADTOF-pytorch" / "src" / "adtof_pytorch"
    (pkg / "data").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "model.py").write_text(FAKE_MODEL, encoding="utf-8")
    (pkg / "data" / "adtof_frame_rnn_pytorch_weights.pth").write_bytes(b"fake")
    (pkg.parent / "torch.py").write_text(FAKE_TORCH, encoding="utf-8")
    shutil.copy(ROOT / "reacue_drums.py", inst / "reacue_drums.py")
    shutil.copy(ROOT / "reacue_metal.py", inst / "reacue_metal.py")
    shutil.copy(ROOT / "reacue_performance.py", inst / "reacue_performance.py")
    py = D.drums_python(inst)
    py.parent.mkdir(parents=True)
    if os.name == "nt":
        shutil.copy(sys.executable, py)
    else:
        py.symlink_to(sys.executable)
    (tmp_path / "onsets.json").write_text(json.dumps(onsets), encoding="utf-8")
    monkeypatch.setenv("FAKE_ONSETS", str(tmp_path / "onsets.json"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "fake.log"))
    monkeypatch.setenv("FAKE_SLEEP", str(sleep))
    monkeypatch.delenv("REACUE_DRUMS_DIR", raising=False)
    if fail:
        monkeypatch.setenv("FAKE_FAIL", "1")
    else:
        monkeypatch.delenv("FAKE_FAIL", raising=False)
    return inst


@pytest.fixture
def song(tmp_path, demo):
    score, secs, y, db = demo
    wav = tmp_path / "media" / "Demo-drums.wav"
    wav.parent.mkdir()
    sf.write(str(wav), y, SR)
    return score, secs, db, wav


def test_launcher_analyze_and_check(tmp_path, monkeypatch, song):
    score, secs, db, wav = song
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch)
    out, st = tmp_path / "r.json", tmp_path / "st.json"
    r = subprocess.run([str(D.drums_python(inst)), str(inst / "reacue_drums.py"), "analyze", "--input", str(wav),
                        "--out", str(out), "--status", str(st)], capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["engine"] == "adtof" and res["fps"] == 100 and set(res["onsets"]) == set(RD.CLASSES)
    want = truth_onsets(score, db, 16)["onsets"]
    for c in ("BD", "SD", "HH"):
        assert RD.match_rate(res["onsets"][c], [t for t, _ in want[c]], 0.015) == 1.0, c
    assert json.loads(st.read_text(encoding="utf-8"))["state"] == "done"
    assert "weights adtof_frame_rnn_pytorch_weights.pth True" in (tmp_path / "fake.log").read_text()
    # fichier absent : état « error »
    r = subprocess.run([str(D.drums_python(inst)), str(inst / "reacue_drums.py"), "analyze",
                        "--input", str(tmp_path / "none.wav"), "--out", str(out), "--status", str(st)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and json.loads(st.read_text(encoding="utf-8"))["state"] == "error"
    # check : batterie synthétique du lanceur, reconnue par le faux modèle
    y, truth = RD.synth_groove(bars=8)
    (tmp_path / "onsets.json").write_text(json.dumps({"onsets": {c: [[t, 0.9] for t in v] for c, v in truth.items()}}))
    r = subprocess.run([str(D.drums_python(inst)), str(inst / "reacue_drums.py"), "check", "--lang", "en"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "DRUMS_OK" in r.stdout and "speed" in r.stdout, r.stdout + r.stderr


def test_launcher_chunks_cover_whole_song(tmp_path, monkeypatch, song):
    score, secs, db, wav = song
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch)
    monkeypatch.setattr(RD, "CHUNK", 700)
    monkeypatch.setattr(RD, "OVERLAP", 50)
    monkeypatch.setattr(RD, "REPO", inst / "drums" / "ADTOF-pytorch")
    for m in ("adtof_pytorch", "adtof_pytorch.model", "torch"):
        monkeypatch.delitem(sys.modules, m, raising=False)
    monkeypatch.syspath_prepend(str(inst / "drums" / "ADTOF-pytorch" / "src"))
    try:
        act = RD.activations(str(wav))
        on = RD.onsets_from_activations(act)
    finally:
        for m in ("adtof_pytorch", "adtof_pytorch.model", "torch"):
            sys.modules.pop(m, None)
    want = truth_onsets(score, db, 16)["onsets"]
    assert len(on["BD"]) == len(want["BD"]) and len(on["CY"]) == len(want["CY"])


def test_detect_drums_model_cache_and_invalidation(tmp_path, monkeypatch, song):
    score, secs, db, wav = song
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch)
    a = analysis_for(score, secs, wav, db)
    out = D.detect_drums(a, None, engine="auto", install_dir=inst)
    assert out["engine"] == "adtof" and out["model_cached"] is False and "warning" not in out
    ok, tot = exact(out, score)
    assert ok >= 0.95 * tot
    cache = wav.parent / ".reacue" / "Demo-drums_drums_adtof.json"
    c = json.loads(cache.read_text(encoding="utf-8"))
    assert c["rev"] == D.ADTOF_REV and c["key"] == D.model_cache_key(wav)
    # 2e fois (autre grille, mêmes coups) : le modèle n'est pas relancé
    (tmp_path / "fake.log").write_text("")
    a2 = analysis_for(score, [(0, 12, "Couplet 1"), (12, 20, "Refrain 1")], wav, db)
    out2 = D.detect_drums(a2, None, engine="auto", install_dir=inst)
    assert out2["model_cached"] is True and (tmp_path / "fake.log").read_text() == ""
    # stem modifié : relancé
    time.sleep(1.1)
    sf.write(str(wav), np.zeros(SR * 3, np.float32), SR)
    out3 = D.detect_drums(a, None, engine="auto", install_dir=inst)
    assert out3["model_cached"] is False and "audio Demo-drums.wav" in (tmp_path / "fake.log").read_text()


def test_detect_drums_fallbacks(tmp_path, monkeypatch, song):
    score, secs, db, wav = song
    a = analysis_for(score, secs, wav, db)
    # non installé : règles, sans avertissement
    out = D.detect_drums(a, None, engine="auto", install_dir=tmp_path / "none")
    assert out["engine"] == "reacue" and "warning" not in out
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch, fail=True)
    # réglage « reacue » : modèle pas lancé
    out = D.detect_drums(a, None, engine="reacue", install_dir=inst)
    assert out["engine"] == "reacue" and not (tmp_path / "fake.log").exists()
    # échec du modèle : règles + avertissement
    out = D.detect_drums(a, None, engine="auto", install_dir=inst)
    assert out["engine"] == "reacue" and "MemoryError" in out["warning"] and "méthode ReaCue" in out["warning"]
    assert out["bars"] and out["steps"] == 16


def test_run_model_timeout(tmp_path, monkeypatch, song):
    score, secs, db, wav = song
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch, sleep=30)
    with pytest.raises(RuntimeError, match="ADTOF"):
        D.run_model(str(wav), tmp_path / "o" / "r.json", inst, timeout=2)


def test_engine_setting_and_cache_key(tmp_path, monkeypatch, bridge_dir):
    from reacue_mcp import settings as S
    assert D.engine_setting() == "reacue"                    # tests : jamais le vrai modèle
    monkeypatch.delenv("REACUE_DRUMS_ENGINE")
    p = bridge_dir / "reacue_settings.json"
    try:
        p.write_text(json.dumps({"drums_engine": "REACUE"}), encoding="utf-8")
        assert D.engine_setting() == "reacue" and S.load_settings()["drums_engine"] == "reacue"
        p.write_text(json.dumps({"drums_engine": "bogus"}), encoding="utf-8")
        assert D.engine_setting() == "adtof" and S.load_settings()["drums_engine"] == "adtof"
    finally:
        p.unlink(missing_ok=True)
    assert S.DEFAULTS["drums_engine"] == "adtof"
    # clé du cache du prompteur : dépend de la présence du modèle
    wav = tmp_path / "d-drums.wav"
    sf.write(str(wav), np.zeros(SR, np.float32), SR)
    a = analysis_for([{}], [(0, 1, "Intro")], wav, [0.0, 2.0])
    k1 = D.drums_cache_key(a, None)
    monkeypatch.setattr(D, "available", lambda *x: True)
    assert D.drums_cache_key(a, None) != k1


def test_compare_tool_with_fake_model(tmp_path, monkeypatch, song, capsys):
    score, secs, db, wav = song
    inst = fake_install(tmp_path, truth_onsets(score, db, 16), monkeypatch)
    from reacue_mcp import analysis as A
    monkeypatch.setattr(D, "ROOT", inst)
    monkeypatch.setattr(A, "analyze", lambda path, **k: analysis_for(score, secs, wav, db))
    sys.path.insert(0, str(ROOT / "tools"))
    import compare_drums
    assert compare_drums.main([str(wav), "--bars"]) == 0
    out = capsys.readouterr().out
    assert "AVANT (règles)" in out and "APRÈS (ADTOF)" in out and "moteur adtof" in out
    assert "=== accord" in out and "HO " in out and "mesure 20" in out
    monkeypatch.setattr(D, "ROOT", tmp_path / "none")
    assert compare_drums.main([str(wav)]) == 0
    assert "composant non installé" in capsys.readouterr().out


# --------------------------------------------------------------------------- installateurs, licences
def test_pinned_revision_and_requirements():
    for f in ("install/install_drums_mac.sh", "install/install_drums_windows.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8-sig")
        assert D.ADTOF_REV in txt and "xavriley/ADTOF-pytorch" in txt and "requirements-drums.txt" in txt, f
        assert "reacue_drums.py" in txt and " check " in txt and "J'accepte" in txt and "CC BY-NC-SA 4.0" in txt
    req = (ROOT / "requirements-drums.txt").read_text(encoding="utf-8")
    assert 'torch==2.2.2 ; sys_platform == "darwin" and platform_machine == "x86_64"' in req
    assert "numpy<2" in req and "torch>=2.5.1,<2.9" in req and "tensorflow" not in req.lower()
    stems = (ROOT / "requirements-stems.txt").read_text(encoding="utf-8")
    for line in re.findall(r"^torch==.*$", req, re.M):
        assert line in stems                                   # mêmes PyTorch que Demucs (cache partagé)
    assert "DRUMS_OK" in (ROOT / "reacue_drums.py").read_text(encoding="utf-8")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".venv-drums/" in gi and "/drums/" in gi


def test_installer_files_syntax_and_encoding():
    for f in ("install/install_drums_mac.sh", "Install ReaCue Drums.command"):
        assert subprocess.run(["bash", "-n", str(ROOT / f)]).returncode == 0, f
        assert os.access(ROOT / f, os.X_OK), f
    ps = (ROOT / "install" / "install_drums_windows.ps1").read_bytes()
    assert ps.startswith(b"\xef\xbb\xbf") and b"\r\n" in ps and b"\n" not in ps.replace(b"\r\n", b"")
    bat = (ROOT / "Install ReaCue Drums.bat").read_bytes()
    assert b"\r\n" in bat and b"install_drums_windows.ps1" in bat
    pwsh = shutil.which("pwsh")
    if pwsh:
        cmd = ("$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{ROOT / 'install' / 'install_drums_windows.ps1'}',[ref]$null,[ref]$e);$e.Count")
        r = subprocess.run([pwsh, "-NoProfile", "-Command", cmd], capture_output=True, text=True)
        assert r.stdout.strip() == "0", (r.stdout, r.stderr)


def _mac_sandbox(tmp_path):
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_drums_mac.sh", inst / "install")
    shutil.copy(ROOT / "requirements-drums.txt", inst)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls.txt"
    for name, body in (("uname", 'if [ "$1" = -m ]; then echo x86_64; else echo Darwin; fi'),
                       ("uv", f'echo uv "$@" >> "{calls}"; exit 1'),
                       ("curl", f'echo curl "$@" >> "{calls}"; exit 22'),
                       ("git", "exit 1")):
        f = bin_ / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", HOME=str(tmp_path))
    env.pop("REACUE_DRUMS_ACCEPT", None)
    return inst, env, calls


def test_mac_installer_licence_acceptance(tmp_path):
    inst, env, calls = _mac_sandbox(tmp_path)
    sh = str(inst / "install" / "install_drums_mac.sh")
    r = subprocess.run(["bash", sh, "fr"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CC BY-NC-SA 4.0" in r.stdout and "NON COMMERCIAL" in r.stdout and "rien n'a été installé" in r.stdout
    assert not calls.exists() and not (inst / "drums" / ".licenses_accepted").exists()
    env["REACUE_DRUMS_ACCEPT"] = "yes"
    r = subprocess.run(["bash", sh, "en"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    marker = inst / "drums" / ".licenses_accepted"
    assert marker.exists() and marker.read_text().splitlines()[0].startswith("adtof-weights-ccbyncsa4")
    assert "Licences accepted" in r.stdout and "curl" in calls.read_text() and D.ADTOF_REV in calls.read_text()
    assert r.returncode == 1                                     # faux curl : échec attendu, après l'accord
    # mémorisé : plus de question
    env.pop("REACUE_DRUMS_ACCEPT")
    calls.unlink()
    r = subprocess.run(["bash", sh, "fr"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert "tape exactement" not in r.stdout and calls.exists()


@pytest.mark.skipif(not shutil.which("pwsh"), reason="pwsh absent")
def test_windows_installer_refuses_then_env_accepts(tmp_path):
    pwsh = shutil.which("pwsh")
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_drums_windows.ps1", inst / "install")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "uv").write_text("#!/bin/bash\nexit 1\n")
    (bin_ / "uv").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin:{os.path.dirname(pwsh)}", USERPROFILE=str(tmp_path),
               TEMP=str(tmp_path))
    env.pop("REACUE_DRUMS_ACCEPT", None)
    ps1 = str(inst / "install" / "install_drums_windows.ps1")
    r = subprocess.run([pwsh, "-NoProfile", "-File", ps1, "-Lang", "fr"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 3 and "CC BY-NC-SA 4.0" in r.stdout, r.stdout + r.stderr
    env["REACUE_DRUMS_ACCEPT"] = "yes"
    r = subprocess.run([pwsh, "-NoProfile", "-File", ps1, "-Lang", "en"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    assert (inst / "drums" / ".licenses_accepted").exists(), r.stdout + r.stderr
    assert "Licences accepted" in r.stdout and r.returncode != 3


def test_notices_mention_adtof():
    txt = " ".join((ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").split())
    for needle in ("ADTOF", "CC BY-NC-SA 4.0", "ADTOF-pytorch", "Zehren", D.ADTOF_REV[:7]):
        assert needle in txt, needle
    for doc in ("LISEZMOI.md", "README.md"):
        assert "ADTOF" in (ROOT / doc).read_text(encoding="utf-8"), doc


def test_prompter_page_knows_open_hihat():
    html = (ROOT / "reacue_mcp" / "web" / "prompteur.html").read_text(encoding="utf-8")
    assert '"HO"' in html and "Charley ouv." in html and "Open hi-hat" in html and "i.cy.op" in html


def test_advanced_preserves_raw_notes_and_sparse_hits(tmp_path):
    db = [0., 2., 4.]
    a = analysis_for([{}, {}], [(0, 2, 'A')], tmp_path/'drums.wav', db)
    result = {'notes': [{'t': .123, 'end': .223, 'pitch': 46, 'velocity': 47},
                        {'t': 2.13, 'end': 2.23, 'pitch': 56, 'velocity': 113}]}
    out = D.from_advanced(a, result)
    assert out['engine'] == 'adt-str'
    assert out['raw_notes'] == result['notes']
    assert 'HO' in out['lanes']
    assert any(e.get('hits', {}).get('HO') for e in out['bars'])
    path = tmp_path/'real.mid'
    D.drums_to_midi(out, 120, path)
    data = path.read_bytes()
    assert bytes([0x99, 46, 47]) in data
    assert bytes([0x99, 56, 113]) in data  # Percussion outside the simplified UI survives.
    # First note starts at 118 ticks, preserving .123 s rather than snapping to a grid.
    assert b'\x76\x99\x2e\x2f' in data


def test_advanced_failure_uses_adtof_and_reports_warning(monkeypatch):
    a = type('A', (), {})()
    monkeypatch.setattr(D, '_drum_source', lambda *x: ('drums.wav', 0))
    monkeypatch.setattr(D, '_load_placed', lambda *x: [])
    monkeypatch.setattr(D, 'advanced_available', lambda *x: True)
    def fail(*x):
        raise RuntimeError('unsupported operation')
    monkeypatch.setattr(D, 'advanced_onsets', fail)
    monkeypatch.setattr(D, 'available', lambda *x: True)
    monkeypatch.setattr(D, 'model_onsets', lambda *x: ({}, True))
    monkeypatch.setattr(D, 'from_model', lambda *x: {'engine': 'adtof'})
    out = D.detect_drums(a, engine='adt-str')
    assert out['engine'] == 'adtof' and 'unsupported operation' in out['warning']


def test_advanced_setting_and_cache_identity(monkeypatch, tmp_path):
    a = analysis_for([{}, {}], [(0, 2, 'A')], tmp_path/'drums.wav', [0.,2.,4.])
    monkeypatch.setenv('REACUE_DRUMS_ENGINE', 'adt-str')
    assert D.engine_setting() == 'adt-str'
    first = D.drums_cache_key(a, None)
    monkeypatch.setenv('REACUE_DRUMS_ENGINE', 'reacue')
    assert D.drums_cache_key(a, None) != first


def test_advanced_empty_result_is_valid(tmp_path):
    a = analysis_for([{}, {}], [(0, 2, 'A')], tmp_path/'drums.wav', [0.,2.,4.])
    out = D.from_advanced(a, {'notes': []})
    assert out['raw_notes'] == [] and len(out['bars']) == 2


def test_advanced_subprocess_cache_preserves_extra_percussion(tmp_path, monkeypatch):
    source = tmp_path/'drums.wav'
    source.write_bytes(b'audio')
    calls = []
    raw = {'engine': 'adt-str', 'onsets': {},
           'notes': [{'t': .1, 'end': .2, 'pitch': 56, 'velocity': 70}]}
    def run(*args, **kwargs):
        calls.append(kwargs)
        return dict(raw)
    monkeypatch.setattr(D, 'run_model', run)
    first, cached = D.advanced_onsets(source, tmp_path)
    second, cached2 = D.advanced_onsets(source, tmp_path)
    assert not cached and cached2 and first['notes'] == second['notes'] == raw['notes']
    assert len(calls) == 1 and calls[0]['script'].endswith('reacue_adt.py')
    source.write_bytes(b'different audio')
    D.advanced_onsets(source, tmp_path)
    assert len(calls) == 2
