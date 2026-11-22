"""Paroles calées mot par mot pour ReaCue (alignement forcé, en local) / Word-level lyrics timing for ReaCue.

Tourne dans l'environnement séparé .venv-words (installé par install/install_words_*), jamais dans le .venv de
ReaCue. Le texte des paroles est connu (fichier de l'utilisateur) et chaque ligne est déjà calée par ReaCue :
ce script ne fait que placer les mots à l'intérieur de chaque ligne, par alignement forcé CTC
(torchaudio.functional.forced_align) sur le stem voix, avec un modèle wav2vec2 XLSR-53 affiné par langue :
  fr : jonatasgrosman/wav2vec2-large-xlsr-53-french   (Apache-2.0)
  en : jonatasgrosman/wav2vec2-large-xlsr-53-english  (Apache-2.0)
Les poids (Hugging Face, ~1,3 Go par langue) sont convertis à la volée vers torchaudio.models.wav2vec2_model :
pas de dépendance à transformers. Modèles dans <ReaCue>/words/hf (HF_HOME) ; un cache Hugging Face déjà présent
sur la machine (~/.cache/huggingface) est utilisé tel quel s'il contient le modèle.

    <python> reacue_words.py align --audio <voix 16 kHz mono.wav> --jobs <lignes.json> --out <résultat.json>
                                   --lang fr|en [--status <état.json>]
        lignes.json : [{"id", "t0", "t1", "text"}] (secondes dans le fichier audio)
        -> {"engine": "wav2vec2-ctc", "model", "lang", "seconds",
            "lines": [{"id", "score", "words": [{"w", "t", "end", "score"}]} | {"id", "error"}]}
    <python> reacue_words.py check [--lang fr|en] [--langs fr,en]   # télécharge, teste, « WORDS_OK »

Inférence wav2vec2 sur Metal/MPS si disponible sur Mac, sinon CPU ; alignement CTC sur CPU.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import unicodedata
from pathlib import Path

import reacue_performance

reacue_performance.configure()

import reacue_metal

reacue_metal.configure()

HERE = Path(__file__).resolve().parent
WORDS_DIR = Path(os.environ.get("REACUE_WORDS_DIR") or HERE / "words")
SR = 16000
ENGINE = "wav2vec2-ctc"
MODELS = {
    "fr": "jonatasgrosman/wav2vec2-large-xlsr-53-french",
    "en": "jonatasgrosman/wav2vec2-large-xlsr-53-english",
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
}
REVISION = os.environ.get("REACUE_WORDS_REVISION") or "main"
WEIGHTS = ("model.safetensors", "pytorch_model.bin")
MAX_SEG_S = 40.0                 # ligne plus longue (calage par ligne douteux) : non traitée
CHAR_SUBST = {"’": "'", "‘": "'", "ʼ": "'", "`": "'", "œ": "oe", "æ": "ae", "ß": "ss", "Œ": "oe", "Æ": "ae"}


# --------------------------------------------------------------------------- texte -> jetons
def _char_tokens(ch: str, vocab: dict) -> list[int]:
    """Un caractère -> identifiants du vocabulaire (minuscule, sinon majuscule, sinon sans accent)."""
    for c in (ch.lower(), ch.upper()):
        if c in vocab:
            return [vocab[c]]
    sub = CHAR_SUBST.get(ch) or CHAR_SUBST.get(ch.lower())
    if sub:
        out = []
        for c in sub:
            out += _char_tokens(c, vocab)
        return out
    base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
    if base and base != ch:
        out = []
        for c in base:
            out += _char_tokens(c, vocab)
        return out
    return []


def tokenize(text: str, vocab: dict) -> list[dict]:
    """Ligne -> [{"w": mot affiché, "ids": [jetons]}]. Les morceaux sans lettre connue du modèle
    (« — », « ! », chiffres) sont collés au mot précédent (ou suivant) : « ".join(w) » == le texte."""
    words = []
    pending = ""
    for piece in str(text).split():
        ids = []
        for ch in unicodedata.normalize("NFC", piece):
            ids += _char_tokens(ch, vocab)
        if not ids:
            if words:
                words[-1]["w"] += " " + piece
            else:
                pending = (pending + " " + piece).strip()
            continue
        if pending:
            piece, pending = pending + " " + piece, ""
        words.append({"w": piece, "ids": ids})
    if pending and words:
        words[-1]["w"] += " " + pending
    return words


# --------------------------------------------------------------------------- modèle
def _cache_dirs() -> list[Path]:
    """Caches Hugging Face où chercher un modèle déjà téléchargé (le premier est celui de ReaCue)."""
    out = [WORDS_DIR / "hf" / "hub"]
    for env, sub in (("HF_HUB_CACHE", ""), ("HF_HOME", "hub")):
        if os.environ.get(env):
            out.append(Path(os.environ[env]) / sub if sub else Path(os.environ[env]))
    out.append(Path.home() / ".cache" / "huggingface" / "hub")
    seen, res = set(), []
    for d in out:
        if str(d) not in seen:
            seen.add(str(d))
            res.append(d)
    return res


def model_files(lang: str, download: bool = True) -> dict:
    """{"config", "vocab", "preproc" (ou None), "weights"} : chemins locaux du modèle de la langue.
    Un dossier <ReaCue>/words/models/<langue>/ (config.json, vocab.json, poids) est prioritaire : modèle
    copié à la main (machine sans internet) ou autre modèle wav2vec2 CTC de même format."""
    local = WORDS_DIR / "models" / lang
    if (local / "config.json").is_file() and (local / "vocab.json").is_file():
        for w in WEIGHTS:
            if (local / w).is_file():
                pre = local / "preprocessor_config.json"
                return {"config": str(local / "config.json"), "vocab": str(local / "vocab.json"),
                        "preproc": str(pre) if pre.is_file() else None, "weights": str(local / w)}
    from huggingface_hub import hf_hub_download
    repo = MODELS[lang]

    def get(name, required=True):
        for d in _cache_dirs():
            try:
                return hf_hub_download(repo, name, revision=REVISION, cache_dir=str(d), local_files_only=True)
            except Exception:                        # noqa: BLE001 - absent de ce cache
                continue
        if not download:
            if required:
                raise FileNotFoundError(f"{repo}/{name}")
            return None
        try:
            return hf_hub_download(repo, name, revision=REVISION, cache_dir=str(_cache_dirs()[0]))
        except Exception:                            # noqa: BLE001
            if required:
                raise
            return None
    out = {"config": get("config.json"), "vocab": get("vocab.json"),
           "preproc": get("preprocessor_config.json", required=False)}
    for w in WEIGHTS:
        p = get(w, required=False)
        if p:
            out["weights"] = p
            break
    else:
        raise FileNotFoundError(f"{repo}: {' / '.join(WEIGHTS)}")
    return out


def _hf_config(cfg: dict) -> dict:
    """config.json (transformers Wav2Vec2Config) -> arguments de torchaudio.models.wav2vec2_model
    (même correspondance que torchaudio.models.wav2vec2.utils.import_huggingface_model)."""
    return {
        "extractor_mode": f"{cfg.get('feat_extract_norm', 'group')}_norm",
        "extractor_conv_layer_config": list(zip(cfg["conv_dim"], cfg["conv_kernel"], cfg["conv_stride"])),
        "extractor_conv_bias": bool(cfg.get("conv_bias", False)),
        "encoder_embed_dim": cfg["hidden_size"],
        "encoder_projection_dropout": 0.0,
        "encoder_pos_conv_kernel": cfg["num_conv_pos_embeddings"],
        "encoder_pos_conv_groups": cfg["num_conv_pos_embedding_groups"],
        "encoder_num_layers": cfg["num_hidden_layers"],
        "encoder_num_heads": cfg["num_attention_heads"],
        "encoder_attention_dropout": 0.0,
        "encoder_ff_interm_features": cfg["intermediate_size"],
        "encoder_ff_interm_dropout": 0.0,
        "encoder_dropout": 0.0,
        "encoder_layer_norm_first": bool(cfg.get("do_stable_layer_norm", False)),
        "encoder_layer_drop": 0.0,
        "aux_num_out": cfg["vocab_size"],
    }


def convert_state_dict(sd: dict) -> dict:
    """Clés Wav2Vec2ForCTC (transformers) -> clés de torchaudio Wav2Vec2Model."""
    out = {}
    for k, v in sd.items():
        if k.startswith("wav2vec2.feature_extractor."):
            nk = "feature_extractor." + k[len("wav2vec2.feature_extractor."):]
        elif k.startswith("wav2vec2.feature_projection."):
            nk = "encoder.feature_projection." + k[len("wav2vec2.feature_projection."):]
        elif k.startswith("wav2vec2.encoder."):
            nk = "encoder.transformer." + k[len("wav2vec2.encoder."):]
        elif k.startswith("lm_head."):
            nk = "aux." + k[len("lm_head."):]
        else:
            continue                                  # masked_spec_embed, adapter… : inutiles ici
        # normalisation de poids de pos_conv : ancien format (weight_g/weight_v) ou paramétrisation récente
        nk = nk.replace("conv.parametrizations.weight.original0", "conv.weight_g")
        nk = nk.replace("conv.parametrizations.weight.original1", "conv.weight_v")
        out[nk] = v
    return out


def load_model(lang: str, files: dict | None = None):
    """-> (modèle torchaudio en mode eval, vocabulaire {caractère: id}, id du blanc, normaliser ?)."""
    import torch
    from torchaudio.models import wav2vec2_model
    files = files or model_files(lang)
    cfg = json.loads(Path(files["config"]).read_text(encoding="utf-8"))
    vocab = json.loads(Path(files["vocab"]).read_text(encoding="utf-8"))
    if vocab and all(isinstance(v, dict) for v in vocab.values()):     # vocabulaire par langue
        vocab = next(iter(vocab.values()))
    pre = {}
    if files.get("preproc"):
        pre = json.loads(Path(files["preproc"]).read_text(encoding="utf-8"))
    w = str(files["weights"])
    if w.endswith(".safetensors"):
        from safetensors.torch import load_file
        sd = load_file(w)
    else:
        sd = torch.load(w, map_location="cpu", weights_only=True)
    model = wav2vec2_model(**_hf_config(cfg))
    missing, unexpected = model.load_state_dict(convert_state_dict(sd), strict=False)
    if missing:
        raise RuntimeError(f"poids incomplets / incomplete weights: {missing[:5]}")
    model.eval()
    blank = vocab.get("<pad>", cfg.get("pad_token_id", 0))
    return model, vocab, int(blank), bool(pre.get("do_normalize", True))


# --------------------------------------------------------------------------- alignement
def emissions(model, wav, normalize: bool = True):
    """Signal 16 kHz (tensor 1-D) -> log-probabilités (1, T, C) et durée d'une trame (s)."""
    import torch
    x = wav.float()
    if normalize:
        x = (x - x.mean()) / torch.sqrt(x.var() + 1e-7)
    logits, _ = reacue_metal.forward(model, x.unsqueeze(0))
    em = torch.log_softmax(logits.float(), dim=-1)
    return em, len(wav) / SR / max(1, em.shape[1])


def align_words(em, frame_s: float, words: list[dict], blank: int, delim: int | None = None,
                offset: float = 0.0) -> tuple[list[dict], float]:
    """Alignement forcé des mots d'une ligne sur ses log-probabilités.
    Renvoie ([{"w", "t", "end", "score"}], score moyen 0..1) ; ValueError si impossible."""
    import torch
    import torchaudio.functional as AF
    targets, owner = [], []
    for i, w in enumerate(words):
        if i and delim is not None:
            targets.append(delim)
            owner.append(-1)
        for t in w["ids"]:
            targets.append(t)
            owner.append(i)
    if not targets:
        raise ValueError("aucun jeton / no token")
    T = em.shape[1]
    reps = sum(1 for a, b in zip(targets, targets[1:]) if a == b)
    if T < len(targets) + reps:
        raise ValueError("segment trop court / segment too short")
    tg = torch.tensor([targets], dtype=torch.int32)
    labels, scores = AF.forced_align(em, tg, blank=blank)
    spans = AF.merge_tokens(labels[0], scores[0].exp())
    if len(spans) != len(targets):
        raise ValueError("alignement incohérent / inconsistent alignment")
    out = []
    for i, w in enumerate(words):
        sp = [s for s, o in zip(spans, owner) if o == i]
        sc = sum(float(s.score) * (s.end - s.start) for s in sp) / max(1, sum(s.end - s.start for s in sp))
        out.append({"w": w["w"], "t": round(offset + sp[0].start * frame_s, 3),
                    "end": round(offset + sp[-1].end * frame_s, 3), "score": round(sc, 3)})
    allsp = [s for s, o in zip(spans, owner) if o >= 0]
    mean = sum(float(s.score) * (s.end - s.start) for s in allsp) / max(1, sum(s.end - s.start for s in allsp))
    return out, round(mean, 3)


def _write_status(path: Path | None, state: str, **kw):
    if not path:
        return
    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _load_audio(path: str):
    import numpy as np
    import soundfile as sf
    import torch
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        import torchaudio.functional as AF
        return AF.resample(torch.from_numpy(np.ascontiguousarray(y)), sr, SR)
    return torch.from_numpy(np.ascontiguousarray(y))


def align_jobs(model, vocab: dict, blank: int, normalize: bool, wav, jobs: list[dict], status=None) -> list[dict]:
    delim = vocab.get("|")
    res = []
    n = len(jobs)
    for k, j in enumerate(jobs):
        if status and k % 5 == 0:
            _write_status(status, "running", step=f"{k}/{n}")
        try:
            t0, t1 = max(0.0, float(j["t0"])), float(j["t1"])
            if t1 - t0 > MAX_SEG_S or t1 - t0 < 0.2:
                raise ValueError("durée hors limites / duration out of range")
            a, b = int(round(t0 * SR)), min(len(wav), int(round(t1 * SR)))
            if b - a < int(0.2 * SR):
                raise ValueError("hors du fichier / outside the file")
            words = tokenize(j["text"], vocab)
            em, fs = emissions(model, wav[a:b], normalize)
            ws, sc = align_words(em, fs, words, blank, delim, offset=a / SR)
            res.append({"id": j["id"], "score": sc, "words": ws})
        except Exception as e:                       # noqa: BLE001 - ligne laissée sans mots
            res.append({"id": j.get("id"), "error": f"{type(e).__name__}: {e}"})
    return res


def align(audio: str, jobs_path: str, out: str, lang: str = "fr", status: str | None = None) -> int:
    st = Path(status) if status else None
    out = Path(out).resolve()
    t0 = time.time()
    try:
        jobs = json.loads(Path(jobs_path).read_text(encoding="utf-8"))
        lang = lang if lang in MODELS else "fr"
        _write_status(st, "running", step="chargement du modèle / loading model")
        import torch
        reacue_performance.configure_torch(torch)
        model, vocab, blank, norm = load_model(lang)
        wav = _load_audio(audio)
        _write_status(st, "running", step="alignement / aligning")
        lines = align_jobs(model, vocab, blank, norm, wav, jobs, st)
        res = {"engine": ENGINE, "model": MODELS[lang], "revision": REVISION, "lang": lang,
               "seconds": round(time.time() - t0, 1), "lines": lines}
        tmp = Path(str(out) + ".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, out)
        _write_status(st, "done", seconds=res["seconds"])
        return 0
    except BaseException as e:                       # noqa: BLE001 - rapporté à ReaCue
        traceback.print_exc()
        _write_status(st, "error", message=f"{type(e).__name__}: {e}")
        return 1


def check(lang: str = "fr", langs: str = "fr,en") -> int:
    def t(fr, en):
        return en if lang == "en" else fr
    try:
        import numpy as np
        import torch
        import torchaudio
        from torchaudio.functional import forced_align  # noqa: F401
    except Exception as e:                           # noqa: BLE001
        print(t("ÉCHEC : PyTorch / torchaudio non importable : ", "FAILED: PyTorch / torchaudio cannot be imported: ")
              + repr(e))
        return 1
    print(f"  python {sys.version.split()[0]} | torch {torch.__version__} | torchaudio {torchaudio.__version__} | "
          f"numpy {np.__version__} | preferred device: {reacue_metal.device(torch)}")
    for lg in [x.strip() for x in langs.split(",") if x.strip() in MODELS]:
        print(t(f"  modèle {lg} : {MODELS[lg]} (environ 1,3 Go la première fois)…",
                f"  {lg} model: {MODELS[lg]} (about 1.3 GB the first time)…"), flush=True)
        t0 = time.time()
        model, vocab, blank, norm = load_model(lg)
        print(t(f"  modèle prêt ({time.time() - t0:.0f} s)", f"  model ready ({time.time() - t0:.0f} s)"), flush=True)
        x = torch.from_numpy((np.random.default_rng(0).standard_normal(SR * 10) * 0.05).astype(np.float32))
        t0 = time.time()
        em, fs = emissions(model, x, norm)
        ws, _ = align_words(em, fs, tokenize("la la la la", vocab), blank, vocab.get("|"))
        dt = time.time() - t0
        assert len(ws) == 4 and all(w["end"] >= w["t"] for w in ws)
        # un morceau de 4 min ≈ 2 min 30 de chant (fenêtres des lignes)
        print(t(f"  vitesse : environ {dt / 10 * 150 / 60:.1f} min pour un morceau",
                f"  speed: about {dt / 10 * 150 / 60:.1f} min per song"))
    print("WORDS_OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reacue_words")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("align")
    a.add_argument("--audio", required=True)
    a.add_argument("--jobs", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--lang", default="fr", choices=sorted(MODELS))
    a.add_argument("--status")
    c = sub.add_parser("check")
    c.add_argument("--lang", default="fr", choices=["fr", "en"])
    c.add_argument("--langs", default="fr,en")
    args = ap.parse_args(argv)
    if args.cmd == "align":
        return align(args.audio, args.jobs, args.out, args.lang, args.status)
    try:
        return check(args.lang, args.langs)
    except Exception as e:                           # noqa: BLE001
        traceback.print_exc()
        print(("ÉCHEC : " if args.lang == "fr" else "FAILED: ") + repr(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
