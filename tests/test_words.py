"""Paroles calées mot par mot (reacue_mcp/words.py + reacue_words.py) : langue, fenêtres, fusion, cache,
sous-processus simulé, conversion sur la timeline du prompteur. Paroles entièrement fictives.

La partie torch (conversion des poids, alignement forcé) n'est testée que si torch / torchaudio sont
importables (environnement .venv-words) ; sinon elle est sautée."""
import json
import sys
from pathlib import Path

import pytest

from reacue_mcp import lyrics, prompter, words
from reacue_mcp.analysis import Analysis, Section

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reacue_words as RW  # noqa: E402  (aucune dépendance lourde au niveau du module)


def analysis(tmp_path=None):
    db = [1.0 + 2.0 * k for k in range(21)]                    # 120 BPM, 4/4, mesure 1 à 1 s
    voice = str(tmp_path / "Demo-vocals.wav") if tmp_path else "/x/Demo-vocals.wav"
    return Analysis(file=voice, duration=45.0, bpm=120.0, beats_per_bar=4, denominator=4, tempo_stable=True,
                    tempo_cv=0.0, beats=[1.0 + 0.5 * k for k in range(81)], downbeats=db,
                    sections=[Section(0, 20, "Couplet 1", "A")], stems={"vocals": voice})


def line(i, t, end, text, **kw):
    a = analysis()
    bar, beat, pos = lyrics._bar_pos(a, t)
    eb, _, ep = lyrics._bar_pos(a, end)
    d = {"i": i, "line": i + 1, "t": t, "end": end, "bar": bar, "beat": beat, "pos": pos, "end_bar": eb,
         "end_pos": ep, "text": text, "confidence": 0.8, "copy": False}
    d.update(kw)
    return d


LYR = [line(0, 3.0, 6.0, "la lune danse encore"), line(1, 7.0, 9.5, "sur le toit — gris !"),
       line(2, 11.0, 13.0, "tra la la")]


def fake_result(lyr=LYR, score=0.6, shift=0.1):
    """Résultat simulé de reacue_words.py : mots répartis sur chaque ligne, décalés de `shift`."""
    out = []
    for i, o in enumerate(lyr):
        ws = o["text"].split()
        # comme reacue_words.tokenize : « — » et « ! » collés au mot précédent
        merged = []
        for w in ws:
            if not any(c.isalpha() for c in w) and merged:
                merged[-1] += " " + w
            else:
                merged.append(w)
        d = (o["end"] - o["t"] - 2 * shift) / len(merged)
        out.append({"id": i, "score": score, "words": [
            {"w": w, "t": round(o["t"] + shift + k * d, 3), "end": round(o["t"] + shift + (k + 0.9) * d, 3),
             "score": score} for k, w in enumerate(merged)]})
    return {"engine": "wav2vec2-ctc", "lang": "fr", "seconds": 1.0, "lines": out}


# --------------------------------------------------------------------------- langue
def test_detect_language():
    assert words.detect_language(["la lune danse encore", "je t'attends sur le toit"]) == "fr"
    assert words.detect_language(["the moon is dancing", "I wait for you on the roof"]) == "en"
    assert words.detect_language(["été à côté"]) == "fr"                    # lettres accentuées
    assert words.detect_language([]) == "fr"


def test_language_setting(monkeypatch):
    monkeypatch.setenv("REACUE_WORDS_LANG", "en")
    assert words.song_language(LYR) == "en"
    monkeypatch.setenv("REACUE_WORDS_LANG", "auto")
    assert words.song_language(LYR) == "fr"


def test_settings_validated(tmp_path):
    from reacue_mcp.settings import load_settings
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"words_engine": "bogus", "words_language": "EN"}), encoding="utf-8")
    s = load_settings(p)
    assert s["words_engine"] == "off" and s["words_language"] == "en"


# --------------------------------------------------------------------------- fenêtres
def test_make_jobs_padding():
    jobs = words.make_jobs(LYR)
    assert [j["id"] for j in jobs] == [0, 1, 2]
    assert jobs[0]["t0"] == pytest.approx(3.0 - words.PAD_MAX)            # rien avant : marge maximale
    assert jobs[0]["t1"] == pytest.approx(6.5)                              # moitié de l'écart (1 s)
    assert jobs[1]["t0"] == pytest.approx(6.5) and jobs[1]["t1"] == pytest.approx(9.5 + 0.75)
    # lignes collées : marge minimale ; ligne vide ignorée
    lyr = [line(0, 3.0, 5.0, "a b"), line(1, 5.0, 7.0, "c d"), line(2, 8.0, 9.0, "  ")]
    jobs = words.make_jobs(lyr)
    assert jobs[0]["t1"] == pytest.approx(5.0 + words.PAD_MIN) and len(jobs) == 2


# --------------------------------------------------------------------------- fusion
def test_merge_adds_words_and_tightens_lines():
    a = analysis()
    out, n = words.merge(a, LYR, fake_result())
    assert n == 3
    o = out[1]
    assert [w["w"] for w in o["words"]] == ["sur", "le", "toit —", "gris !"]
    assert " ".join(w["w"] for w in o["words"]).split() == o["text"].split()
    assert o["t"] == pytest.approx(7.1) and o["words"][0]["t"] == o["t"]
    assert o["end"] == o["words"][-1]["end"]
    assert (o["bar"], o["pos"]) == (4, pytest.approx(0.2))                   # 7,1 s = mesure 4 + 0,2 temps
    assert all(set(w) == {"w", "t", "end"} for w in o["words"])
    assert LYR[1]["t"] == 7.0 and "words" not in LYR[1]                       # entrée d'origine intacte


def test_merge_keeps_anchored_lines_and_rejects_bad_ones():
    a = analysis()
    lyr = [dict(LYR[0], anchored=True)] + LYR[1:]
    res = fake_result()
    res["lines"][1]["score"] = 0.01                                           # alignement improbable
    res["lines"][2]["words"][0]["w"] = "autre"                                # texte différent
    out, n = words.merge(a, lyr, res)
    assert n == 1
    assert out[0]["t"] == 3.0 and out[0]["words"][0]["t"] == pytest.approx(3.1)   # ancre exacte gardée
    assert "words" not in out[1] and "words" not in out[2]
    assert out[1]["t"] == 7.0
    # erreur dans une ligne, ligne absente, résultat vide : lignes inchangées
    out, n = words.merge(a, LYR, {"lines": [{"id": 0, "error": "x"}]})
    assert n == 0 and out == LYR
    assert words.merge(a, LYR, None)[1] == 0


def test_merge_monotonic_words():
    a = analysis()
    res = fake_result()
    ws = res["lines"][0]["words"]
    ws[2]["t"] = ws[1]["t"] - 0.3                                             # chevauchement : remis en ordre
    out, _ = words.merge(a, LYR, res)
    ts = [w["t"] for w in out[0]["words"]]
    assert ts == sorted(ts) and all(w["end"] > w["t"] for w in out[0]["words"])


# --------------------------------------------------------------------------- add_words (moteur simulé)
@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(words, "available", lambda d=None: True)
    monkeypatch.setattr(words, "write_voice", lambda a, items, wav: Path(wav))
    monkeypatch.setenv("REACUE_WORDS_ENGINE", "auto")
    monkeypatch.setenv("REACUE_WORDS_LANG", "auto")

    def run(wav, jobs, lang, workdir, install_dir=None, **kw):
        calls.append((jobs, lang))
        if calls and getattr(run, "fail", None):
            raise RuntimeError(run.fail)
        return fake_result()
    monkeypatch.setattr(words, "run_engine", run)
    return calls, run


def test_add_words_with_cache(fake_engine, tmp_path):
    calls, _ = fake_engine
    a = analysis()
    cache = tmp_path / "prompter_lyrics_words.json"
    out = words.add_words(a, None, LYR, cache=cache)
    assert all("words" in o for o in out) and len(calls) == 1 and calls[0][1] == "fr"
    assert words.LAST_INFO["lines"] == 3 and words.LAST_INFO["engine"] == "wav2vec2-ctc"
    assert "3/3" in words.LAST_INFO["message"]
    out2 = words.add_words(a, None, LYR, cache=cache)                          # résultat mémorisé
    assert out2 == out and len(calls) == 1 and words.LAST_INFO["cached"]
    lyr = [dict(LYR[0], text="la lune danse toujours")] + LYR[1:]             # texte changé : recalcul
    words.add_words(a, None, lyr, cache=cache)
    assert len(calls) == 2
    assert [job["id"] for job in calls[-1][0]] == [0]  # autres phrases réutilisées
    assert words.LAST_INFO["reused_lines"] == 2


def test_word_lines_survive_another_song(fake_engine, tmp_path):
    calls, _ = fake_engine
    a = analysis(tmp_path)
    cache = tmp_path / "words.json"
    words.add_words(a, None, LYR, cache=cache)
    first_key = json.loads(cache.read_text())["key"]
    other = analysis(tmp_path / "other")
    words.add_words(other, None, LYR, cache=cache)
    assert json.loads(cache.read_text())["key"] != first_key
    words.add_words(a, None, LYR, cache=cache)
    assert len(calls) == 2 and words.LAST_INFO["cached"]


def test_failed_words_retry_after_delay(fake_engine, tmp_path, monkeypatch):
    calls, run = fake_engine
    run.fail = "transient"
    cache = tmp_path / "words.json"
    words.add_words(analysis(), None, LYR, cache=cache)
    failed = json.loads(cache.read_text())
    failed["at"] = 0
    cache.write_text(json.dumps(failed))
    run.fail = None
    assert all(o.get("words") for o in words.add_words(analysis(), None, LYR, cache=cache))
    assert len(calls) == 2


def test_corrupt_cached_line_is_recomputed_without_losing_other_lines(fake_engine, tmp_path):
    calls, _ = fake_engine
    a, cache = analysis(tmp_path), tmp_path / "words.json"
    words.add_words(a, None, LYR, cache=cache)
    paths = words._line_paths(a, None, words.make_jobs(LYR), "fr", None, cache)
    broken = {"id": 0, "score": .9, "words": [{"w": "la"}]}
    paths[0].write_text(json.dumps(broken))
    stored = json.loads(cache.read_text())
    stored["result"]["lines"][0] = broken
    cache.write_text(json.dumps(stored))
    out = words.add_words(a, None, LYR, cache=cache)
    assert all(o.get("words") for o in out)
    assert len(calls) == 2 and [j["id"] for j in calls[-1][0]] == [0]


def test_partial_worker_failure_expires_per_line(fake_engine, tmp_path, monkeypatch):
    attempts = []
    clock = [1000.0]
    monkeypatch.setattr(words.time, "time", lambda: clock[0])
    def run(wav, jobs, *args, **kwargs):
        attempts.append(jobs)
        result = fake_result()
        if len(attempts) == 1:
            result["lines"][0] = {"id": 0, "error": "temporary"}
        return result
    monkeypatch.setattr(words, "run_engine", run)
    a, cache = analysis(tmp_path), tmp_path / "words.json"
    first = words.add_words(a, None, LYR, cache=cache)
    assert "words" not in first[0] and all(o.get("words") for o in first[1:])
    words.add_words(a, None, LYR, cache=cache)
    assert len(attempts) == 1
    clock[0] += words.RETRY_AFTER_S + 1
    result = words.add_words(a, None, LYR, cache=cache)
    assert all(o.get("words") for o in result)
    assert len(attempts) == 2 and [j["id"] for j in attempts[-1]] == [0]


def test_add_words_failure_falls_back_and_is_remembered(fake_engine, tmp_path):
    calls, run = fake_engine
    run.fail = "modèle introuvable"
    a = analysis()
    cache = tmp_path / "w.json"
    assert words.add_words(a, None, LYR, cache=cache) is LYR
    assert "modèle introuvable" in words.LAST_INFO["error"]
    assert "paroles calées par ligne" in words.LAST_INFO["message"] or "timed by line" in words.LAST_INFO["message"]
    assert words.add_words(a, None, LYR, cache=cache) is LYR and len(calls) == 1   # échec mémorisé


def test_add_words_off_or_missing(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(words, "run_engine", lambda *a, **k: called.append(1))
    monkeypatch.setenv("REACUE_WORDS_ENGINE", "off")
    monkeypatch.setattr(words, "available", lambda d=None: True)
    assert words.add_words(analysis(), None, LYR) is LYR
    monkeypatch.setenv("REACUE_WORDS_ENGINE", "auto")
    monkeypatch.setattr(words, "available", lambda d=None: False)
    assert words.add_words(analysis(), None, LYR) is LYR and words.LAST_INFO.get("missing")
    assert words.add_words(analysis(), None, []) == [] and not called


def test_available(tmp_path):
    assert not words.available(tmp_path)
    py = words.words_python(tmp_path)
    py.parent.mkdir(parents=True)
    py.write_text("")
    (tmp_path / "reacue_words.py").write_text("")
    assert words.available(tmp_path)
    assert words.words_python(tmp_path, windows=True).parts[-3:] == (".venv-words", "Scripts", "python.exe")


def test_cached_lyrics_gets_words(fake_engine, tmp_path):
    """Intégration : calage par ligne (ancres exactes : pas d'audio) puis mots ; cache des lignes inchangé."""
    calls, _ = fake_engine
    a = analysis(tmp_path)
    (tmp_path / "paroles.txt").write_text("la lune danse encore\nsur le toit — gris !\n", encoding="utf-8")
    (tmp_path / "paroles_calage.json").write_text(json.dumps({"1": "2:1-3:3", "2": "4:1-5:2"}), encoding="utf-8")
    cache = tmp_path / "prompter_lyrics.json"
    out = lyrics.cached_lyrics(a, None, cache=cache, path=tmp_path / "paroles.txt")
    assert [o["text"] for o in out] == ["la lune danse encore", "sur le toit — gris !"]
    assert all(o.get("words") for o in out) and len(calls) == 1
    assert "words" not in json.loads(cache.read_text(encoding="utf-8"))["lyrics"][0]
    assert (tmp_path / "prompter_lyrics_words.json").exists()
    assert out[0]["t"] == pytest.approx(3.0)                                 # ancre exacte : début gardé
    out2 = lyrics.cached_lyrics(a, None, cache=cache, path=tmp_path / "paroles.txt")
    assert out2 == out and len(calls) == 1


# --------------------------------------------------------------------------- sous-processus (faux moteur)
FAKE_SCRIPT = r'''
import json, sys
args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
jobs = json.load(open(args["--jobs"], encoding="utf-8"))
if any("boom" in j["text"] for j in jobs):
    json.dump({"state": "error", "message": "RuntimeError: boom"}, open(args["--status"], "w"))
    sys.exit(1)
lines = [{"id": j["id"], "score": 0.5, "words": [{"w": w, "t": j["t0"], "end": j["t1"], "score": 0.5}
          for w in j["text"].split()]} for j in jobs]
json.dump({"engine": "wav2vec2-ctc", "lang": args["--lang"], "lines": lines}, open(args["--out"], "w"))
'''


def test_run_engine_subprocess(tmp_path):
    sc = tmp_path / "fake_words.py"
    sc.write_text(FAKE_SCRIPT, encoding="utf-8")
    jobs = words.make_jobs(LYR)
    res = words.run_engine(tmp_path / "v.wav", jobs, "en", tmp_path / "work", install_dir=tmp_path,
                           python=sys.executable, script=str(sc))
    assert res["lang"] == "en" and [ln["id"] for ln in res["lines"]] == [0, 1, 2]
    with pytest.raises(RuntimeError, match="boom"):
        words.run_engine(tmp_path / "v.wav", [dict(jobs[0], text="boom")], "fr", tmp_path / "w2",
                         install_dir=tmp_path, python=sys.executable, script=str(sc))
    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        words.run_engine(tmp_path / "v.wav", jobs, "fr", tmp_path / "w3", install_dir=tmp_path, timeout=0.5,
                         python=sys.executable, script=str(slow))


# --------------------------------------------------------------------------- prompteur
TIMELINE = {"bpm": 120.0, "tempo_mode": "constant", "count_in_bars": 2,
            "bar_times": [10.0 + 2.0 * k for k in range(23)]}               # mesure 1 à 14 s (fichier : 1 s)


def test_lyrics_on_timeline_words():
    a = analysis()
    lyr, _ = words.merge(a, LYR, fake_result())
    out = prompter.lyrics_on_timeline(lyr, TIMELINE, 4, a.n_bars, downbeats=a.downbeats)
    for o, src in zip(out, lyr):
        assert o["t"] == pytest.approx(src["t"] + 13.0, abs=1e-3)           # fichier -> timeline : +13 s
        for w, sw in zip(o["words"], src["words"]):
            assert w["w"] == sw["w"]
            assert w["t"] == pytest.approx(sw["t"] + 13.0, abs=1e-3)
            assert w["end"] == pytest.approx(sw["end"] + 13.0, abs=1e-3)
            assert o["t"] <= w["t"] <= w["end"] <= o["end"] + 1e-6
    # sans la grille : proportionnel entre début et fin de la ligne (même résultat à tempo constant)
    out2 = prompter.lyrics_on_timeline(lyr, TIMELINE, 4, a.n_bars)
    assert [w["t"] for w in out2[1]["words"]] == pytest.approx([w["t"] for w in out[1]["words"]], abs=1e-3)
    # sans mots : format d'avant, aucun champ "words"
    out3 = prompter.lyrics_on_timeline(LYR, TIMELINE, 4, a.n_bars)
    assert all("words" not in o for o in out3)


def test_build_song_with_words():
    a = analysis()
    lyr, _ = words.merge(a, LYR, fake_result())
    song = prompter.build_song(a, {"file": a.file, "title": "Demo"}, TIMELINE, lyrics=lyr)
    assert song["lyrics"][0]["words"][0]["w"] == "la"
    from reacue_mcp import sheet
    bl = sheet.bar_lyrics(song)
    assert " ".join(bl[b] for b in sorted(bl)).split() == " ".join(o["text"] for o in LYR).split()


# --------------------------------------------------------------------------- reacue_words.py (sans torch)
VOCAB = {c: i for i, c in enumerate(["<pad>", "<s>", "</s>", "<unk>", "|", "'"] +
                                     list("abcdefghijklmnopqrstuvwxyzàâçéèêëîïôùûü"))}


def test_tokenize():
    ws = RW.tokenize("L’été — c'est 2 Œufs !", VOCAB)
    assert [w["w"] for w in ws] == ["L’été —", "c'est 2", "Œufs !"]
    assert ws[0]["ids"] == [VOCAB[c] for c in "l'été"]
    assert ws[2]["ids"] == [VOCAB[c] for c in "oeufs"]
    up = {k.upper(): v for k, v in VOCAB.items() if len(k) == 1}             # vocabulaire en majuscules
    assert RW.tokenize("Ça", up)[0]["ids"] == [up["Ç"], up["A"]]
    en = {c: i for i, c in enumerate(["<pad>", "|", "'"] + list("abcdefghijklmnopqrstuvwxyz"))}
    assert RW.tokenize("Été", en)[0]["ids"] == [en[c] for c in "ete"]      # accents retirés si inconnus
    assert RW.tokenize("— !", VOCAB) == []
    assert [w["w"] for w in RW.tokenize("« oui", VOCAB)] == ["« oui"]


def test_convert_state_dict_keys():
    sd = {"wav2vec2.feature_extractor.conv_layers.0.conv.weight": 1,
          "wav2vec2.feature_projection.projection.weight": 2,
          "wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0": 3,
          "wav2vec2.encoder.pos_conv_embed.conv.weight_v": 4,
          "wav2vec2.encoder.layers.0.attention.k_proj.weight": 5,
          "wav2vec2.masked_spec_embed": 6, "lm_head.weight": 7}
    out = RW.convert_state_dict(sd)
    assert out == {"feature_extractor.conv_layers.0.conv.weight": 1,
                   "encoder.feature_projection.projection.weight": 2,
                   "encoder.transformer.pos_conv_embed.conv.weight_g": 3,
                   "encoder.transformer.pos_conv_embed.conv.weight_v": 4,
                   "encoder.transformer.layers.0.attention.k_proj.weight": 5, "aux.weight": 7}
    cfg = {"feat_extract_norm": "layer", "conv_dim": [512] * 7, "conv_kernel": [10, 3, 3, 3, 3, 2, 2],
           "conv_stride": [5, 2, 2, 2, 2, 2, 2], "conv_bias": True, "hidden_size": 1024,
           "num_conv_pos_embeddings": 128, "num_conv_pos_embedding_groups": 16, "num_hidden_layers": 24,
           "num_attention_heads": 16, "intermediate_size": 4096, "do_stable_layer_norm": True, "vocab_size": 48}
    c = RW._hf_config(cfg)
    assert c["extractor_mode"] == "layer_norm" and c["encoder_layer_norm_first"] and c["aux_num_out"] == 48
    assert c["extractor_conv_layer_config"][0] == (512, 10, 5)


def test_models_consistent():
    assert RW.MODELS == words.MODELS
    for m in RW.MODELS.values():
        assert m.startswith("jonatasgrosman/wav2vec2-large-xlsr-53-")


# --------------------------------------------------------------------------- outil de comparaison
def test_compare_tool_never_prints_lyrics(monkeypatch, tmp_path, capsys):
    sys.path.insert(0, str(ROOT / "tools"))
    import compare_words as CW
    a = analysis(tmp_path)
    (tmp_path / "paroles.txt").write_text("zorblat quimpe vaxu\nfrimbel dostra — klop !\n", encoding="utf-8")
    (tmp_path / "paroles_calage.json").write_text(json.dumps({"1": "2:1-3:3", "2": "4:1-5:2"}), encoding="utf-8")
    sess = tmp_path / "sess.json"
    sess.write_text(json.dumps({"analysis": a.to_dict(), "item": {"file": a.file}}), encoding="utf-8")
    monkeypatch.setattr(words, "available", lambda d=None: True)
    monkeypatch.setattr(words, "write_voice", lambda a, items, wav: Path(wav))

    def run(wav, jobs, lang, workdir, install_dir=None, **kw):
        lyr = [{"t": j["t0"] + 0.2, "end": j["t1"] - 0.2, "text": j["text"]} for j in jobs]
        return fake_result(lyr)
    monkeypatch.setattr(words, "run_engine", run)
    assert CW.main(["--session", str(sess), "-v"]) == 0
    out = capsys.readouterr().out
    assert "2/2 lignes" in out and "mot  1" in out
    for w in ("zorblat", "quimpe", "vaxu", "frimbel", "dostra", "klop"):
        assert w not in out


# --------------------------------------------------------------------------- installation
def test_requirements_words_same_torch_as_stems():
    req = (ROOT / "requirements-words.txt").read_text(encoding="utf-8")
    stems = (ROOT / "requirements-stems.txt").read_text(encoding="utf-8")
    for pin in ('torch==2.2.2 ; sys_platform == "darwin" and platform_machine == "x86_64"',
                'torchaudio==2.2.2 ; sys_platform == "darwin" and platform_machine == "x86_64"',
                'numpy<2 ; sys_platform == "darwin" and platform_machine == "x86_64"',
                "torch>=2.5.1,<2.9", "torchaudio>=2.5.1,<2.9"):
        assert pin in req and pin in stems, pin
    assert not [ln for ln in req.splitlines() if ln.strip().startswith("transformers")]


def test_installers_words():
    import os
    import shutil
    import subprocess
    for f in ("install/install_words_mac.sh", "Install ReaCue Words.command"):
        assert subprocess.run(["bash", "-n", str(ROOT / f)]).returncode == 0, f
        assert os.access(ROOT / f, os.X_OK), f
    sh = (ROOT / "install" / "install_words_mac.sh").read_text(encoding="utf-8")
    ps = (ROOT / "install" / "install_words_windows.ps1").read_bytes()
    # Windows PowerShell 5.1 needs the BOM for accented text; LF is also valid.
    assert ps.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in ps.replace(b"\r\n", b"")
    bat = (ROOT / "Install ReaCue Words.bat").read_bytes()
    assert b"install_words_windows.ps1" in bat and b"\n" not in bat.replace(b"\r\n", b"")
    for txt in (sh, ps.decode("utf-8-sig")):
        assert "requirements-words.txt" in txt and ".venv-words" in txt and "--only-binary" in txt
        assert "reacue_words.py" in txt and " check " in txt and "Apache-2.0" in txt
        assert "THIRD_PARTY_NOTICES.md" in txt and "J'accepte" not in txt          # poids Apache-2.0 : pas d'accord
    assert "WORDS_OK" in (ROOT / "reacue_words.py").read_text(encoding="utf-8")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".venv-words/" in gi and "/words/" in gi
    pwsh = shutil.which("pwsh")
    if pwsh:
        cmd = ("$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{ROOT / 'install' / 'install_words_windows.ps1'}',[ref]$null,[ref]$e);$e.Count")
        r = subprocess.run([pwsh, "-NoProfile", "-Command", cmd], capture_output=True, text=True)
        assert r.stdout.strip() == "0", (r.stdout, r.stderr)


@pytest.mark.parametrize("words_engine, lyrics_model", [("off", "small"), ("auto", "large-v3-turbo")])
def test_mac_installer_sandbox(tmp_path, words_engine, lyrics_model):
    """Installer checks the selected model and downloads alignment only when enabled."""
    import os
    import shutil
    import subprocess
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_words_mac.sh", inst / "install")
    shutil.copy(ROOT / "requirements-words.txt", inst)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls.txt"
    venv_py = inst / ".venv-words" / "bin" / "python"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        f'#!/bin/bash\necho py "$@" >> "{calls}"\n'
        'if [ "$1" = -c ]; then\n'
        '  case "$2" in\n'
        '    *selected_model*) echo "$REACUE_LYRICS_MODEL" ;;\n'
        '    *) echo "$REACUE_WORDS_ENGINE" ;;\n'
        '  esac\n'
        'else\n  echo WORDS_OK\nfi\n'
    )
    for name, body in (("uname", 'if [ "$1" = -m ]; then echo x86_64; else echo Darwin; fi'),
                       ("uv", f'echo uv "$@" >> "{calls}"; if [ "$1" = venv ]; then mkdir -p "{venv_py.parent}"; '
                              f'cp "{fake_python}" "{venv_py}"; chmod +x "{venv_py}"; fi')):
        f = bin_ / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", HOME=str(tmp_path), REACUE_WORDS_LANGS="fr",
               REACUE_WORDS_ENGINE=words_engine, REACUE_LYRICS_MODEL=lyrics_model, REACUE_WHISPER="1")
    r = subprocess.run(["bash", str(inst / "install" / "install_words_mac.sh"), "en"], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls.read_text()
    assert "uv venv .venv-words --python 3.12" in log
    assert "--only-binary :all: -r requirements-words.txt" in log
    assert ("py reacue_words.py check --lang en --langs fr" in log) == (words_engine == "auto")
    assert f"py reacue_transcribe.py check --download --lang en --model {lyrics_model}" in log
    assert "Automatic lyrics installed" in r.stdout
    if words_engine == "off":
        assert "Word alignment disabled" in r.stdout


# --------------------------------------------------------------------------- reacue_words.py (avec torch)
def test_forced_align_with_torch():
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchaudio")
    ws = RW.tokenize("La — si !", VOCAB)
    T, C = 50, len(VOCAB)
    em = torch.full((1, T, C), -10.0)
    em[0, :, 0] = -0.1
    for f, ch in ((10, "l"), (11, "l"), (12, "a"), (13, "a"), (20, "|"), (30, "s"), (31, "i"), (32, "i")):
        em[0, f, :] = -10.0
        em[0, f, VOCAB[ch]] = -0.05
    em = torch.log_softmax(em, -1)
    out, score = RW.align_words(em, 0.02, ws, 0, VOCAB["|"], offset=1.0)
    assert [w["w"] for w in out] == ["La —", "si !"]
    assert out[0]["t"] == pytest.approx(1.2) and out[0]["end"] == pytest.approx(1.28)
    assert out[1]["t"] == pytest.approx(1.6) and score > 0.9
    with pytest.raises(ValueError):
        RW.align_words(em[:, :3], 0.02, ws, 0, VOCAB["|"])                 # trop court


def test_hf_weights_match_transformers(tmp_path):
    """Poids au format transformers -> modèle torchaudio : mêmes sorties (petit modèle aléatoire)."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchaudio")
    tr = pytest.importorskip("transformers")
    cfg = tr.Wav2Vec2Config(vocab_size=len(VOCAB), hidden_size=64, num_hidden_layers=2, num_attention_heads=4,
                            intermediate_size=128, conv_dim=(32,) * 7, feat_extract_norm="layer",
                            do_stable_layer_norm=True, conv_bias=True, num_conv_pos_embeddings=16,
                            num_conv_pos_embedding_groups=4, pad_token_id=0)
    torch.manual_seed(0)
    m = tr.Wav2Vec2ForCTC(cfg).eval()
    for safe in (True, False):
        d = tmp_path / ("safe" if safe else "bin")
        m.save_pretrained(d, safe_serialization=safe)
        (d / "vocab.json").write_text(json.dumps(VOCAB), encoding="utf-8")
        w = d / ("model.safetensors" if safe else "pytorch_model.bin")
        model, voc, blank, norm = RW.load_model("fr", {"config": d / "config.json", "vocab": d / "vocab.json",
                                                      "preproc": None, "weights": w})
        x = torch.randn(1, 16000)
        with torch.inference_mode():
            assert torch.allclose(m(x).logits, model(x)[0], atol=1e-5)
        assert blank == 0 and norm
        jobs = [{"id": 0, "t0": 0.0, "t1": 1.0, "text": "la si"}, {"id": 1, "t0": 0.9, "t1": 0.95, "text": "x"}]
        res = RW.align_jobs(model, voc, blank, norm, x[0], jobs)
        assert [w["w"] for w in res[0]["words"]] == ["la", "si"] and "error" in res[1]
