"""Paroles automatiques (reacue_mcp/lyrics_auto.py + reacue_transcribe.py) : nettoyage du texte de Whisper, découpe
en lignes, brouillon « paroles (auto).txt » (jamais écrasé, fichier de l'utilisateur prioritaire), moteur simulé,
sous-processus simulé, prompteur / grille PDF, installateurs. Textes entièrement fictifs (syllabes inventées).

La partie Whisper réelle (modèle) n'est jamais lancée ici ; les fonctions de reacue_transcribe.py sans torch
(activité vocale, regroupement, conversion des clés Hugging Face) sont testées directement."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from reacue_mcp import lyrics, lyrics_auto as LA, prompter
from reacue_mcp.analysis import Analysis, Section

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reacue_transcribe as RT  # noqa: E402  (aucune dépendance lourde au niveau du module)


def analysis(folder: Path):
    db = [1.0 + 2.0 * k for k in range(21)]                    # 120 BPM, 4/4, mesure 1 à 1 s
    voice = str(folder / "Demo-vocals.wav")
    return Analysis(file=voice, duration=45.0, bpm=120.0, beats_per_bar=4, denominator=4, tempo_stable=True,
                    tempo_cv=0.0, beats=[1.0 + 0.5 * k for k in range(81)], downbeats=db,
                    sections=[Section(0, 20, "Couplet 1", "A")], stems={"vocals": voice})


def seg(t, end, text, lp=-0.3, ns=0.05, words=True, p=0.8):
    toks = text.split()
    d = (end - t) / max(1, len(toks))
    ws = [{"w": w, "t": round(t + k * d, 3), "end": round(t + (k + 0.9) * d, 3), "p": p}
          for k, w in enumerate(toks)] if words else []
    return {"t": t, "end": end, "text": text, "avg_logprob": lp, "no_speech_prob": ns, "compression_ratio": 1.2,
            "words": ws}


SEGS = [seg(3.0, 6.0, "Zorblat quimpe vaxu."), seg(7.0, 9.5, "frimbel dostra klop"),
        seg(20.0, 23.0, "♪ Brasko lindu ♪")]


# --------------------------------------------------------------------------- nettoyage
def test_keep_segment_filters_hallucinations():
    assert LA.keep_segment(SEGS[0])
    assert not LA.keep_segment(seg(1, 3, "Sous-titres réalisés par la communauté d'Amara.org"))
    assert not LA.keep_segment(seg(1, 3, "Thanks for watching!"))
    assert not LA.keep_segment(seg(1, 3, "♪ ♪"))                               # aucune lettre
    assert not LA.keep_segment(seg(1, 3, "[Musique]"))
    assert not LA.keep_segment(seg(1, 3, "zorblat quimpe", lp=-1.5))          # très incertain
    assert not LA.keep_segment(seg(1, 3, "zorblat quimpe", lp=-0.9, ns=0.8))  # silence probable
    assert LA.keep_segment(seg(1, 3, "zorblat quimpe", lp=-0.5, ns=0.8))      # voix sûre malgré no_speech
    assert not LA.keep_segment(seg(1, 3, "zorblat quimpe", p=0.05))           # mots improbables
    assert not LA.keep_segment(seg(1, 1.5, "a b c d e f g h i j"))           # débit impossible


def test_collapse_repeats():
    toks = "la la la la la la la la".split()
    assert LA.collapse_repeats(toks) == ["la"] * 4
    toks = "vo ka vo ka vo ka vo ka vo ka vo ka zim".split()
    assert LA.collapse_repeats(toks) == "vo ka vo ka vo ka vo ka zim".split()
    toks = "brasko lindu brasko lindu".split()                      # 2 répétitions : gardées
    assert LA.collapse_repeats(toks) == toks


def test_segments_to_lines_split_and_clean():
    long = seg(30.0, 38.0, "zorblat quimpe vaxu frimbel, dostra klop brasko lindu tema voro sefi")
    gap = seg(40.0, 44.0, "tema voro sefi nalu", words=False)
    gap["words"] = [{"w": "tema", "t": 40.0, "end": 40.4, "p": 0.9}, {"w": "voro", "t": 40.5, "end": 40.9, "p": 0.9},
                    {"w": "sefi", "t": 42.2, "end": 42.6, "p": 0.9}, {"w": "nalu", "t": 42.7, "end": 43.1, "p": 0.9}]
    loop = [seg(50.0 + k, 50.8 + k, "Brasko lindu") for k in range(7)]
    lines = LA.segments_to_lines(SEGS + [long, gap] + loop + [seg(1, 2, "Merci d'avoir regardé")])
    texts = [x["text"] for x in lines]
    assert texts[:3] == ["Zorblat quimpe vaxu", "Frimbel dostra klop", "Brasko lindu"]   # point final, ♪ retirés
    # segment trop long : coupé (de préférence après la virgule) ; silence de 1,3 s : nouvelle ligne
    assert "Zorblat quimpe vaxu frimbel" in texts and "Dostra klop brasko lindu tema voro sefi" in texts
    assert "Tema voro" in texts and "Sefi nalu" in texts
    assert sum(1 for t in texts[-6:] if t == "Brasko lindu") <= LA.MAX_SAME_LINES
    assert all(lines[k]["t"] <= lines[k + 1]["t"] for k in range(len(lines) - 1))
    assert not any("Merci" in t for t in texts)


def test_format_draft_and_read_back(tmp_path, lang):
    lang("fr")
    lines = LA.segments_to_lines(SEGS)
    txt = LA.format_draft(lines, gap=4.0, model="large-v3-turbo", lang="fr")
    head = txt.splitlines()[:2]
    assert all(h.startswith("# ") for h in head) and "Whisper large-v3-turbo" in head[0] and "paroles.txt" in head[1]
    assert "\n\nBrasko lindu\n" in txt                                       # 10,5 s de silence : nouveau bloc
    p = tmp_path / "paroles (auto).txt"
    p.write_text(txt, encoding="utf-8")
    rl = lyrics.read_lyrics(p)
    assert [x["text"] for x in rl] == ["Zorblat quimpe vaxu", "Frimbel dostra klop", "Brasko lindu"]
    assert [x["block"] for x in rl] == [0, 0, 1] and rl[0]["line"] == 1      # commentaires non comptés
    lang("en")
    assert "lyrics.txt" in LA.format_draft(lines, model="m", lang="en").splitlines()[1]


def test_block_gap(tmp_path):
    a = analysis(tmp_path)
    assert LA.block_gap(a) == pytest.approx(4.0)                              # 2 mesures de 2 s
    a.downbeats = [k * 0.5 for k in range(30)]
    assert LA.block_gap(a) == LA.BLOCK_GAP_MIN


# --------------------------------------------------------------------------- recherche des fichiers
def test_user_file_has_priority_and_draft_is_found(tmp_path):
    f = tmp_path / "Demo-vocals.wav"
    (tmp_path / "paroles (auto).txt").write_text("# brouillon\nzorblat\n", encoding="utf-8")
    assert lyrics.find_lyrics_file([str(f)]) is None                         # le brouillon n'est pas « à soi »
    assert LA.find_auto_file([str(f)]) == tmp_path / "paroles (auto).txt"
    (tmp_path / "paroles.txt").write_text("quimpe\n", encoding="utf-8")
    assert lyrics.find_lyrics_file([str(f)]) == tmp_path / "paroles.txt"


def test_target_folder_for_separated_stems(tmp_path):
    st = tmp_path / "Demo-stems" / "htdemucs_6s"
    st.mkdir(parents=True)
    assert LA.target_folder([str(st / "vocals.wav")]) == tmp_path
    assert LA.target_folder([str(tmp_path / "x.wav")]) == tmp_path


def test_write_draft_never_overwrites(tmp_path):
    p = LA.write_draft(tmp_path, "# a\nzorblat\n")
    assert p == tmp_path / "paroles (auto).txt"
    p.write_text("corrigé à la main\n", encoding="utf-8")
    assert LA.write_draft(tmp_path, "# b\nquimpe\n") is None
    assert p.read_text(encoding="utf-8") == "corrigé à la main\n"


# --------------------------------------------------------------------------- composant installé ?
def fake_install(d: Path, model=True, package=True):
    from reacue_mcp import words
    py = words.words_python(d)
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("")
    (d / "reacue_transcribe.py").write_text("")
    if package:
        w = d / ".venv-words" / "lib" / "python3.12" / "site-packages" / "whisper"
        w.mkdir(parents=True, exist_ok=True)
        (w / "__init__.py").write_text("")
    if model:
        m = d / "words" / "whisper"
        m.mkdir(parents=True, exist_ok=True)
        (m / (LA.model_setting() + ".pt")).write_bytes(b"0" * 2000)
    return d


def test_missing_reason(tmp_path, monkeypatch):
    monkeypatch.delenv("REACUE_WORDS_DIR", raising=False)
    assert LA.missing_reason(tmp_path) == "venv"
    fake_install(tmp_path, model=False, package=False)
    assert LA.missing_reason(tmp_path) == "package"
    fake_install(tmp_path, model=False)
    assert LA.missing_reason(tmp_path) == "model"
    fake_install(tmp_path)
    assert LA.missing_reason(tmp_path) is None and LA.available(tmp_path)
    (tmp_path / "words" / "whisper" / (LA.model_setting() + ".pt")).unlink()
    (tmp_path / "words" / "whisper" / (LA.model_setting() + "-hf.pt")).write_bytes(b"0" * 2000)   # converti (repli HF)
    assert LA.available(tmp_path)


def test_setting(monkeypatch, tmp_path):
    from reacue_mcp.settings import load_settings
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"lyrics_auto": "bogus"}), encoding="utf-8")
    assert load_settings(p)["lyrics_auto"] == "auto"
    p.write_text(json.dumps({"lyrics_auto": "OFF"}), encoding="utf-8")
    assert load_settings(p)["lyrics_auto"] == "off"
    monkeypatch.setenv("REACUE_LYRICS_AUTO", "auto")
    assert LA.setting() == "auto"
    monkeypatch.setenv("REACUE_LYRICS_AUTO", "off")
    assert LA.setting() == "off"


# --------------------------------------------------------------------------- moteur simulé
@pytest.fixture
def engine(monkeypatch, tmp_path):
    """Whisper simulé : composant « installé » dans tmp_path/inst, run_engine renvoie SEGS."""
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "small")
    inst = fake_install(tmp_path / "inst")
    monkeypatch.setattr(LA, "ROOT", inst)
    monkeypatch.delenv("REACUE_WORDS_DIR", raising=False)
    monkeypatch.setenv("REACUE_LYRICS_AUTO", "auto")
    from reacue_mcp import words
    monkeypatch.setattr(words, "write_voice", lambda a, items, wav: Path(wav))
    calls = []
    state = {"segments": SEGS, "error": None}

    def run(wav, workdir, lang="auto", install_dir=None, **kw):
        calls.append(lang)
        if state["error"]:
            raise RuntimeError(state["error"])
        return {"engine": "whisper", "model": kw.get("model", LA.model_setting()), "language": "fr", "seconds": 1.0,
                "segments": state["segments"]}
    monkeypatch.setattr(LA, "run_engine", run)
    song = tmp_path / "song"
    song.mkdir()
    (song / "Demo-vocals.wav").write_bytes(b"RIFF")
    return calls, state, song


def test_ensure_creates_draft_once(engine, tmp_path):
    calls, state, song = engine
    a = analysis(song)
    memo = tmp_path / "memo.json"
    p = LA.ensure_auto_lyrics(a, None, cache=memo)
    assert p == song / "paroles (auto).txt" and len(calls) == 1 and calls[0] == "auto"
    assert LA.LAST_INFO["state"] == "created" and LA.LAST_INFO["lines"] == 3 and "3 lignes" in LA.LAST_INFO["message"]
    p.write_text("# corrigé\nquimpe zorblat\n", encoding="utf-8")            # l'utilisateur corrige sur place
    assert LA.ensure_auto_lyrics(a, None, cache=memo) == p and len(calls) == 1
    assert p.read_text(encoding="utf-8") == "# corrigé\nquimpe zorblat\n"
    assert LA.LAST_INFO["state"] == "existing"


def test_ensure_failure_is_remembered_and_never_raises(engine, tmp_path):
    calls, state, song = engine
    a = analysis(song)
    memo = tmp_path / "memo.json"
    state["error"] = "RuntimeError: boom"
    assert LA.ensure_auto_lyrics(a, None, cache=memo) is None
    assert LA.LAST_INFO["state"] == "error" and "boom" in LA.LAST_INFO["message"]
    assert LA.ensure_auto_lyrics(a, None, cache=memo) is None and len(calls) == 1      # pas de nouvel essai
    assert not (song / "paroles (auto).txt").exists()
    # morceau sans chant reconnu : rien d'écrit, mémorisé aussi
    state["error"] = None
    memo2 = tmp_path / "memo2.json"
    state["segments"] = [seg(1, 3, "Thanks for watching!")]
    assert LA.ensure_auto_lyrics(a, None, cache=memo2) is None and LA.LAST_INFO["state"] == "empty"
    assert LA.ensure_auto_lyrics(a, None, cache=memo2) is None and len(calls) == 2
    assert not (song / "paroles (auto).txt").exists()


def test_ensure_off_missing_no_voice(engine, monkeypatch, tmp_path):
    calls, state, song = engine
    a = analysis(song)
    monkeypatch.setenv("REACUE_LYRICS_AUTO", "off")
    assert LA.ensure_auto_lyrics(a, None, cache=tmp_path / "m.json") is None and LA.LAST_INFO["state"] == "off"
    monkeypatch.setenv("REACUE_LYRICS_AUTO", "auto")
    a2 = analysis(song)
    a2.stems = {}
    assert LA.ensure_auto_lyrics(a2, None, cache=tmp_path / "m.json") is None and LA.LAST_INFO["state"] == "no_voice"
    (LA.ROOT / "words" / "whisper" / (LA.model_setting() + ".pt")).unlink()
    assert LA.ensure_auto_lyrics(a, None, cache=tmp_path / "m.json") is None
    assert LA.LAST_INFO["state"] == "missing" and LA.LAST_INFO["missing"] == "model" and calls == []
    assert LA.LAST_INFO["selected_model"] in LA.LAST_INFO["message"]


def test_cached_lyrics_uses_draft_then_user_file(engine, tmp_path, monkeypatch):
    """Intégration : sans paroles.txt, le brouillon est créé puis calé comme un fichier normal ("auto": True) ;
    dès que paroles.txt existe, il est prioritaire."""
    calls, state, song = engine
    a = analysis(song)
    seen = []

    def fake_align(a, items, lines, anchors=None, **kw):
        seen.append([x["text"] for x in lines])
        return [{"i": x["i"], "line": x["line"], "t": 3.0 + 2 * k, "end": 4.5 + 2 * k, "bar": 2 + k, "beat": 0,
                 "pos": 0.0, "end_bar": 2 + k, "end_pos": 3.0, "text": x["text"], "confidence": 0.8, "copy": False}
                for k, x in enumerate(lines)]
    monkeypatch.setattr(lyrics, "align_lyrics", fake_align)
    out = lyrics.cached_lyrics(a, None, cache=tmp_path / "c.json")
    assert [o["text"] for o in out] == ["Zorblat quimpe vaxu", "Frimbel dostra klop", "Brasko lindu"]
    assert all(o.get("auto") for o in out) and (song / "paroles (auto).txt").exists()
    out2 = lyrics.cached_lyrics(a, None, cache=tmp_path / "c.json")          # cache : mêmes lignes, toujours auto
    assert out2 == out and len(calls) == 1
    (song / "paroles.txt").write_text("quimpe\nvaxu\n", encoding="utf-8")
    out3 = lyrics.cached_lyrics(a, None, cache=tmp_path / "c.json")
    assert [o["text"] for o in out3] == ["quimpe", "vaxu"] and not any(o.get("auto") for o in out3)
    assert len(calls) == 1


def test_auto_flag_reaches_prompter_and_sheet(tmp_path, lang):
    from reacue_mcp import sheet
    lang("fr")
    a = analysis(tmp_path)
    lyr = [{"i": 0, "line": 1, "t": 3.0, "end": 4.5, "bar": 2, "beat": 0, "pos": 0.0, "end_bar": 2,
            "end_pos": 3.0, "text": "zorblat quimpe", "confidence": 0.8, "copy": False, "auto": True}]
    timeline = {"bpm": 120.0, "tempo_mode": "constant", "count_in_bars": 2,
                "bar_times": [10.0 + 2.0 * k for k in range(23)]}
    song = prompter.build_song(a, {"file": a.file, "title": "Demo"}, timeline, None, {}, lyrics=lyr)
    assert song["lyrics"][0]["auto"] is True
    foot_auto = sheet.build_pdf(song, lang="fr")
    song2 = dict(song, lyrics=[dict(song["lyrics"][0], auto=False)])
    assert foot_auto != sheet.build_pdf(song2, lang="fr")


# --------------------------------------------------------------------------- sous-processus (faux moteur)
FAKE_SCRIPT = r'''
import json, sys
args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
if "boom" in args["--audio"]:
    json.dump({"state": "error", "message": "RuntimeError: boom"}, open(args["--status"], "w"))
    sys.exit(1)
json.dump({"engine": "whisper", "model": args["--model"], "language": "fr" if args["--lang"] == "auto" else args["--lang"],
           "segments": [{"t": 1.0, "end": 2.0, "text": "zorblat", "words": []}]}, open(args["--out"], "w"))
'''


def test_run_engine_subprocess(tmp_path):
    sc = tmp_path / "fake_transcribe.py"
    sc.write_text(FAKE_SCRIPT, encoding="utf-8")
    res = LA.run_engine(tmp_path / "v.wav", tmp_path / "work", "en", install_dir=tmp_path,
                        python=sys.executable, script=str(sc))
    assert res["language"] == "en" and res["model"] == LA.MODEL and len(res["segments"]) == 1
    with pytest.raises(RuntimeError, match="boom"):
        LA.run_engine(tmp_path / "boom.wav", tmp_path / "w2", install_dir=tmp_path, python=sys.executable,
                      script=str(sc))
    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        LA.run_engine(tmp_path / "v.wav", tmp_path / "w3", install_dir=tmp_path, timeout=0.5,
                      python=sys.executable, script=str(slow))


# --------------------------------------------------------------------------- reacue_transcribe.py (sans torch)
def test_voiced_regions_and_clips():
    sr = RT.SR
    t = np.arange(sr * 60) / sr
    y = np.zeros_like(t)
    for s, e in ((2, 6), (6.3, 12), (20, 26), (30, 62)):
        k = (t >= s) & (t < e)
        y[k] = 0.3 * np.sin(2 * np.pi * 200 * t[k])
    y = (y + 0.001 * np.random.default_rng(0).standard_normal(len(t))).astype(np.float32)
    reg = RT.voiced_regions(y)
    assert len(reg) == 3                                    # 0,3 s de silence : même zone
    assert reg[0][0] == pytest.approx(1.8, abs=0.05) and reg[0][1] == pytest.approx(12.2, abs=0.05)
    clips = RT.group_clips(reg)
    assert len(clips) == 3                                  # 8 s d'écart : fenêtres séparées ; 30 s : seule
    assert RT.group_clips([(0, 5), (6, 10), (11, 20), (21, 29), (30, 35)]) == [[(0, 5), (6, 10), (11, 20)],
                                                                                 [(21, 29), (30, 35)]]
    m = RT.masked(y, reg)
    assert np.abs(m[int(15 * sr):int(19 * sr)]).max() == 0 and np.abs(m[int(3 * sr):int(5 * sr)]).max() > 0.2
    assert RT.voiced_regions(np.zeros(100, dtype=np.float32)) == []


def test_hf_to_openai_keys():
    cfg = {"num_mel_bins": 128, "max_source_positions": 1500, "d_model": 1280, "encoder_attention_heads": 20,
           "encoder_layers": 32, "vocab_size": 51866, "max_target_positions": 448, "decoder_attention_heads": 20,
           "decoder_layers": 4}
    sd = {k: k for k in (
        "model.encoder.conv1.weight", "model.encoder.embed_positions.weight", "model.encoder.layer_norm.bias",
        "model.encoder.layers.3.self_attn.k_proj.weight", "model.encoder.layers.3.self_attn_layer_norm.weight",
        "model.encoder.layers.3.fc1.bias", "model.encoder.layers.3.fc2.weight",
        "model.encoder.layers.3.final_layer_norm.bias", "model.decoder.embed_tokens.weight",
        "model.decoder.embed_positions.weight", "model.decoder.layer_norm.weight",
        "model.decoder.layers.1.encoder_attn.q_proj.bias", "model.decoder.layers.1.encoder_attn_layer_norm.weight",
        "model.decoder.layers.1.self_attn.out_proj.weight", "proj_out.weight")}
    dims, out = RT.hf_to_openai(sd, cfg)
    assert dims == {"n_mels": 128, "n_audio_ctx": 1500, "n_audio_state": 1280, "n_audio_head": 20,
                    "n_audio_layer": 32, "n_vocab": 51866, "n_text_ctx": 448, "n_text_state": 1280,
                    "n_text_head": 20, "n_text_layer": 4}
    assert set(out) == {
        "encoder.conv1.weight", "encoder.positional_embedding", "encoder.ln_post.bias",
        "encoder.blocks.3.attn.key.weight", "encoder.blocks.3.attn_ln.weight", "encoder.blocks.3.mlp.0.bias",
        "encoder.blocks.3.mlp.2.weight", "encoder.blocks.3.mlp_ln.bias", "decoder.token_embedding.weight",
        "decoder.positional_embedding", "decoder.ln.weight", "decoder.blocks.1.cross_attn.query.bias",
        "decoder.blocks.1.cross_attn_ln.weight", "decoder.blocks.1.attn.out.weight"}


def test_model_file_and_load_never_downloads(tmp_path):
    assert RT.model_file("large-v3-turbo", tmp_path) is None
    (tmp_path / "large-v3-turbo-hf.pt").write_bytes(b"0" * 2000)
    assert RT.model_file("large-v3-turbo", tmp_path) == tmp_path / "large-v3-turbo-hf.pt"
    (tmp_path / "large-v3-turbo.pt").write_bytes(b"0" * 2000)
    assert RT.model_file("large-v3-turbo", tmp_path) == tmp_path / "large-v3-turbo.pt"   # officiel d'abord
    assert RT.DEFAULT_MODEL == LA.MODEL == "small"
    assert RT.DECODE["condition_on_previous_text"] is False and RT.DECODE["word_timestamps"] is True


@pytest.mark.skipif(not __import__("importlib").util.find_spec("whisper"), reason="openai-whisper absent")
def test_transcribe_with_random_tiny_model(tmp_path):
    """Chaîne complète avec un petit modèle Whisper aléatoire (seulement si openai-whisper est installé)."""
    import torch
    from whisper.model import ModelDimensions, Whisper
    td = dict(n_mels=80, n_audio_ctx=1500, n_audio_state=64, n_audio_head=2, n_audio_layer=1, n_vocab=51865,
              n_text_ctx=448, n_text_state=64, n_text_head=2, n_text_layer=1)
    torch.save({"dims": td, "model_state_dict": Whisper(ModelDimensions(**td)).state_dict()},
               str(tmp_path / "tiny-hf.pt"))
    model = RT.load("tiny", tmp_path)
    y = np.zeros(RT.SR * 6, dtype=np.float32)
    y[RT.SR:RT.SR * 3] = 0.3 * np.sin(np.arange(RT.SR * 2) * 0.08)
    res = RT.transcribe_array(model, y, "fr", decode={"beam_size": None, "best_of": None, "temperature": (0.0,),
                                                      "sample_len": 8})
    assert res["clips"] == 1 and res["language"] == "fr" and isinstance(res["segments"], list)


# --------------------------------------------------------------------------- outil (statistiques seulement)
def test_transcribe_tool_prints_only_stats(engine, tmp_path, capsys, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import transcribe_lyrics as TLY
    calls, state, song = engine
    a = analysis(song)
    sess = tmp_path / "sess.json"
    sess.write_text(json.dumps({"analysis": a.to_dict(), "item": {"file": a.file}}), encoding="utf-8")
    assert TLY.main(["--session", str(sess)]) == 0
    out = capsys.readouterr().out
    assert "lines              3" in out and "language           fr" in out
    for w in ("Zorblat", "quimpe", "vaxu", "Frimbel", "dostra", "klop", "Brasko", "lindu"):
        assert w.lower() not in out.lower()
    assert not (song / "paroles (auto).txt").exists()
    assert TLY.main(["--session", str(sess), "--write"]) == 0
    assert (song / "paroles (auto).txt").exists()
    out = capsys.readouterr().out
    assert "zorblat" not in out.lower()


# --------------------------------------------------------------------------- installation
def test_requirements_whisper():
    req = (ROOT / "requirements-words.txt").read_text(encoding="utf-8")
    for pin in ("numba==0.62.1", "llvmlite==0.45.1", "tiktoken==0.9.0", "more-itertools", "tqdm"):
        assert pin in req, pin
    w = (ROOT / "requirements-whisper.txt").read_text(encoding="utf-8")
    assert "openai-whisper==20250625" in w and "--no-deps" in w


def test_installers_whisper():
    sh = (ROOT / "install" / "install_words_mac.sh").read_text(encoding="utf-8")
    ps = (ROOT / "install" / "install_words_windows.ps1").read_bytes().decode("utf-8-sig")
    for txt in (sh, ps):
        assert "--no-deps -r requirements-whisper.txt" in txt and "reacue_transcribe.py" in txt
        assert "check --download" in txt and "REACUE_WHISPER" in txt and "MIT" in txt
    assert "WHISPER_OK" in (ROOT / "reacue_transcribe.py").read_text(encoding="utf-8")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/words/" in gi and "*.pt" in gi


def test_mac_installer_adds_whisper_to_existing_install(tmp_path):
    """Faux macOS, .venv-words déjà là : pas de nouveau venv ; paquets complétés, Whisper ajouté et testé."""
    import shutil
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_words_mac.sh", inst / "install")
    for f in ("requirements-words.txt", "requirements-whisper.txt"):
        shutil.copy(ROOT / f, inst)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls.txt"
    venv_py = inst / ".venv-words" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text(f'#!/bin/bash\necho py "$@" >> "{calls}"\n')
    venv_py.chmod(0o755)
    for name, body in (("uname", 'if [ "$1" = -m ]; then echo x86_64; else echo Darwin; fi'),
                       ("uv", f'echo uv "$@" >> "{calls}"')):
        f = bin_ / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", HOME=str(tmp_path), REACUE_WORDS_LANGS="fr")
    r = subprocess.run(["bash", str(inst / "install" / "install_words_mac.sh"), "fr"], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls.read_text()
    assert "uv venv" not in log
    assert "--only-binary :all: -r requirements-words.txt" in log
    assert "--no-deps -r requirements-whisper.txt" in log
    assert "py reacue_transcribe.py check --download --lang fr" in log
    assert "Paroles automatiques installées" in r.stdout
    calls.unlink()
    env["REACUE_WHISPER"] = "0"
    r = subprocess.run(["bash", str(inst / "install" / "install_words_mac.sh"), "en"], env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "requirements-whisper" not in calls.read_text()
    assert "reacue_transcribe" not in calls.read_text()


def test_no_real_lyrics_or_weights_in_repo():
    for p in ROOT.rglob("paroles (auto).txt"):
        assert ".venv" in str(p) or "words" in p.parts, p
    assert not list((ROOT / "reacue_mcp").glob("*.pt"))


def test_whisper_times_are_preserved_instead_of_reestimated(engine, monkeypatch, tmp_path):
    _, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    expected = LA.segments_to_lines(SEGS)
    assert LA.timing_path(path).exists()
    def must_not_realign(*args, **kwargs):
        raise AssertionError("Known Whisper timing must not be replaced by heuristic timing")
    monkeypatch.setattr(lyrics, "align_lyrics", must_not_realign)
    monkeypatch.setattr(lyrics, "_with_words", lambda a, items, res, cache: res)
    out = lyrics.cached_lyrics(a, None, path=path, cache=tmp_path / "lines.json")
    assert [(x["t"], x["end"]) for x in out] == [(x["t"], x["end"]) for x in expected]
    assert all(x["timing_source"] == "whisper" and x["anchored"] for x in out)


def test_old_auto_draft_gets_timing_once_without_overwriting(engine, tmp_path):
    calls, _, song = engine
    a = analysis(song)
    expected = LA.segments_to_lines(SEGS)
    path = LA.write_draft(song, LA.format_draft(expected))
    original = path.read_bytes()
    assert not LA.timing_path(path).exists()
    assert LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json") == path
    assert path.read_bytes() == original and len(calls) == 1
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is not None
    LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    assert len(calls) == 1


def test_edited_text_and_changed_audio_do_not_reuse_stale_timing(engine, tmp_path):
    _, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    original = path.read_text()
    path.write_text("# user correction\nCompletely different words\n")
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is None
    path.write_text(original)
    (song / "Demo-vocals.wav").write_bytes(b"different audio")
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is None


def test_timing_sidecar_invalidates_line_cache(engine, tmp_path):
    _, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    before = lyrics.lyrics_cache_key(a, None, path)
    data = LA.read_timing(path)
    data["lines"][0]["t"] += 0.2
    LA.timing_path(path).write_text(json.dumps(data))
    assert lyrics.lyrics_cache_key(a, None, path) != before


def test_manual_calage_takes_priority_over_preserved_auto_times(engine, monkeypatch, tmp_path):
    _, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    monkeypatch.setattr(lyrics, "_with_words", lambda a, items, res, cache: res)
    manual = {"anchors": {(1, 1): {"start": (2, 0.0), "end": (3, 0.0)}}, "off": set()}
    monkeypatch.setattr(lyrics, "read_calage", lambda p: manual)
    out = lyrics.cached_lyrics(a, None, path=path, cache=tmp_path / "lines.json")
    first = next(x for x in out if x["line"] == 1)
    assert first["t"] == 3.0 and first["end"] == 5.0


def test_mismatched_old_draft_is_kept_and_repair_not_repeated(engine, tmp_path):
    calls, _, song = engine
    a = analysis(song)
    path = LA.write_draft(song, "# previous edited draft\nDifferent words\n")
    original = path.read_bytes()
    LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    assert LA.read_timing(path)["matched"] is False
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is None
    LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    assert path.read_bytes() == original and len(calls) == 1


def test_voice_audio_replacement_invalidates_line_cache(engine, tmp_path):
    _, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None, cache=tmp_path / "memo.json")
    before = lyrics.lyrics_cache_key(a, None, path)
    (song / "Demo-vocals.wav").write_bytes(b"replacement voice audio")
    assert lyrics.lyrics_cache_key(a, None, path) != before


def test_transcription_failure_expires_and_repairs_old_draft(engine, monkeypatch, tmp_path):
    calls, state, song = engine
    a = analysis(song)
    memo = tmp_path / "memo.json"
    path = LA.write_draft(song, LA.format_draft(LA.segments_to_lines(SEGS)))
    original = path.read_bytes()
    clock = [10000.0]
    monkeypatch.setattr(LA.time, "time", lambda: clock[0])
    state["error"] = "Whisper timeout"
    assert LA.ensure_auto_lyrics(a, None, cache=memo) == path
    state["error"] = None
    LA.ensure_auto_lyrics(a, None, cache=memo)
    assert len(calls) == 1  # Refreshes must not repeatedly launch a failing model.
    clock[0] += LA.ERROR_RETRY_S + 1
    assert LA.ensure_auto_lyrics(a, None, cache=memo) == path
    assert len(calls) == 2 and path.read_bytes() == original
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is not None
    LA.ensure_auto_lyrics(a, None, cache=memo)
    assert len(calls) == 2


def test_legacy_error_without_timestamp_is_retried(engine, tmp_path):
    calls, _, song = engine
    a = analysis(song)
    memo = tmp_path / "memo.json"
    key = LA.memo_key(a, None, "auto")
    memo.write_text(json.dumps({key: {"state": "error", "error": "old timeout"}}))
    assert LA.ensure_auto_lyrics(a, None, cache=memo) is not None
    assert len(calls) == 1


def test_model_selection_follows_live_settings_and_environment(monkeypatch):
    import reacue_performance
    from reacue_mcp import settings
    config = {"lyrics_model": "small"}
    monkeypatch.delenv("REACUE_LYRICS_MODEL", raising=False)
    monkeypatch.setattr(settings, "load_settings", lambda: config)
    monkeypatch.setattr(reacue_performance, "settings", lambda: config)
    assert LA.model_setting() == RT.selected_model() == "small"
    config["lyrics_model"] = "large-v3-turbo"
    assert LA.model_setting() == RT.selected_model() == "large-v3-turbo"
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "medium")  # preserve existing environment overrides
    assert LA.model_setting() == RT.selected_model() == "medium"


def test_offline_load_passes_local_path_even_for_official_name(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / "small.pt"
    path.write_bytes(b"x" * 2000)
    calls = []
    model = SimpleNamespace(eval=lambda: None, set_alignment_heads=lambda heads: calls.append(heads))
    def load_model(name, **kw):
        assert name == str(path)  # a model name could trigger an automatic download
        calls.append(name)
        return model
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load_model,
                                                                _ALIGNMENT_HEADS={"small": b"heads"}))
    assert RT.load("small", tmp_path) is model
    assert calls == [str(path), b"heads"]


def test_model_and_language_changes_never_relabel_or_overwrite_draft(engine, tmp_path, monkeypatch):
    calls, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None)
    original = path.read_bytes()
    metadata = LA.timing_path(path).read_bytes()
    assert LA.read_timing(path)["model"] == "small"
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "large-v3-turbo")
    assert LA.ensure_auto_lyrics(a, None) == path
    assert len(calls) == 1 and path.read_bytes() == original
    assert LA.timing_path(path).read_bytes() == metadata
    assert LA.LAST_INFO["model"] == "small"
    assert LA.LAST_INFO["selected_model"] == "large-v3-turbo"
    assert "small" in LA.LAST_INFO["warning"] and "large-v3-turbo" in LA.LAST_INFO["warning"]
    assert "paroles (auto).txt" in LA.LAST_INFO["warning"]
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "small")
    monkeypatch.setenv("REACUE_WORDS_LANG", "en")
    assert LA.ensure_auto_lyrics(a, None) == path
    assert len(calls) == 1 and "langue en" in LA.LAST_INFO["warning"]


def test_success_cache_is_per_song_and_repairs_missing_sidecar(engine, tmp_path):
    calls, _, song = engine
    a = analysis(song)
    path = LA.ensure_auto_lyrics(a, None)
    assert (song / ".reacue" / "lyrics_auto.json").is_file()
    LA.timing_path(path).unlink()
    assert LA.ensure_auto_lyrics(a, None) == path and len(calls) == 1
    assert LA.LAST_INFO["cached"] is True
    assert LA.timed_draft(a, None, path, lyrics.read_lyrics(path)) is not None


def test_selected_model_missing_does_not_fall_back_to_other_weights(engine, monkeypatch):
    calls, _, song = engine
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "large-v3-turbo")
    assert LA.model_file() is None  # small is installed, turbo is not
    assert LA.ensure_auto_lyrics(analysis(song), None) is None
    assert calls == [] and LA.LAST_INFO["state"] == "missing"
    assert LA.LAST_INFO["model"] == "large-v3-turbo"
    assert "large-v3-turbo" in LA.LAST_INFO["message"]


def test_transcription_cache_separates_model_language_and_source(engine, monkeypatch):
    _, _, song = engine
    a = analysis(song)
    first = LA.memo_key(a, None, "auto")
    assert first != LA.memo_key(a, None, "fr")
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "large-v3-turbo")
    assert first != LA.memo_key(a, None, "auto")
    monkeypatch.setenv("REACUE_LYRICS_MODEL", "small")
    audio = Path(a.file)
    stat = audio.stat()
    os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 100))
    assert first != LA.memo_key(a, None, "auto")
