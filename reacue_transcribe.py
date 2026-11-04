"""Paroles automatiques pour ReaCue : transcription du stem voix avec Whisper, en local.
Automatic lyrics for ReaCue: transcription of the vocal stem with Whisper, locally.

Tourne dans l'environnement séparé .venv-words (le même que les paroles mot par mot, installé par
install/install_words_*), jamais dans le .venv de ReaCue. Utilisé seulement quand le dossier du morceau n'a pas
de fichier de paroles : ReaCue (reacue_mcp/lyrics_auto.py) écrit alors un brouillon « paroles (auto).txt » à
partir des phrases renvoyées ici.

Modèle : openai-whisper (code MIT) « small » par défaut ou « large-v3-turbo » (poids MIT), dans <ReaCue>/words/whisper/
(téléchargé par l'installateur depuis le serveur d'OpenAI ; sinon converti depuis le dépôt Hugging Face
officiel openai/whisper-large-v3-turbo, même licence). Jamais téléchargé pendant une transcription.

Contre les hallucinations sur du chant :
  - détection d'activité vocale sur le stem (niveau relatif) : seules les zones chantées sont transcrites,
    le reste du signal est mis à zéro ; zones regroupées en fenêtres d'au plus ~28 s (une passe d'encodeur) ;
  - condition_on_previous_text=False (pas de boucle d'une fenêtre à l'autre), seuils no_speech / logprob /
    compression de Whisper, hallucination_silence_threshold (horodatage des mots) ;
  - le nettoyage (phrases parasites, répétitions en boucle, découpe en lignes) est fait côté ReaCue.

    <python> reacue_transcribe.py transcribe --audio <voix.wav> --out <résultat.json>
                                             [--lang auto|fr|en|…] [--model small|large-v3-turbo] [--status <état.json>]
        -> {"engine": "whisper", "model", "language", "language_prob", "seconds", "voiced_s",
            "segments": [{"t", "end", "text", "avg_logprob", "no_speech_prob", "compression_ratio",
                          "words": [{"w", "t", "end", "p"}]}]}
    <python> reacue_transcribe.py check [--download] [--lang fr|en] [--model small|large-v3-turbo]
        télécharge le modèle s'il manque (--download), le charge, fait un essai, affiche « WHISPER_OK ».
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

import reacue_performance

reacue_performance.configure()

HERE = Path(__file__).resolve().parent
WORDS_DIR = Path(os.environ.get("REACUE_WORDS_DIR") or HERE / "words")
WHISPER_DIR = WORDS_DIR / "whisper"
DEFAULT_MODEL = "small"
HF_REPOS = {"large-v3-turbo": "openai/whisper-large-v3-turbo", "large-v3": "openai/whisper-large-v3",
            "medium": "openai/whisper-medium", "small": "openai/whisper-small", "base": "openai/whisper-base",
            "tiny": "openai/whisper-tiny"}
SR = 16000
ENGINE = "whisper"


def selected_model() -> str:
    """Installer/CLI default follows the saved profile without importing the main package."""
    override = os.environ.get("REACUE_LYRICS_MODEL", "").strip()
    if override:
        return override
    value = reacue_performance.settings().get("lyrics_model", DEFAULT_MODEL)
    return value if value in ("small", "large-v3-turbo") else DEFAULT_MODEL

# détection d'activité vocale (trames de 20 ms)
VAD_HOP = 320
VAD_REL_DB = 24.0                # seuil = niveau fort (p95) − 24 dB…
VAD_FLOOR_DB = -50.0             # … et au moins −50 dBFS (fuites des autres instruments dans le stem)
VAD_MIN_GAP = 0.5                # silences plus courts : même zone
VAD_MIN_LEN = 0.25               # zones plus courtes : ignorées
VAD_PAD = 0.2                    # marge autour de chaque zone
CLIP_MAX = 28.0                  # fenêtre de transcription (Whisper lit 30 s à la fois)
CLIP_JOIN_GAP = 4.0              # zones séparées de plus : fenêtres différentes

DECODE = dict(temperature=(0.0, 0.2, 0.4, 0.6), compression_ratio_threshold=2.4, logprob_threshold=-1.0,
              no_speech_threshold=0.6, condition_on_previous_text=False, word_timestamps=True,
              hallucination_silence_threshold=2.0, beam_size=5, best_of=5)


# --------------------------------------------------------------------------- activité vocale
def voiced_regions(y, sr: int = SR) -> list[tuple[float, float]]:
    """Zones chantées du stem voix [(début s, fin s)] : niveau RMS au-dessus d'un seuil relatif."""
    import numpy as np
    y = np.asarray(y, dtype=np.float32)
    n = len(y) // VAD_HOP
    if n == 0:
        return []
    fr = y[:n * VAD_HOP].reshape(n, VAD_HOP)
    db = 10 * np.log10(np.mean(fr * fr, axis=1) + 1e-12)
    if n >= 5:                                       # lissage (médiane glissante sur 5 trames)
        pad = np.pad(db, 2, mode="edge")
        db = np.median(np.stack([pad[k:k + n] for k in range(5)]), axis=0)
    thr = max(float(np.percentile(db, 95)) - VAD_REL_DB, VAD_FLOOR_DB)
    act = db > thr
    hop_s = VAD_HOP / sr
    runs, i = [], 0
    while i < n:
        if act[i]:
            j = i
            while j < n and act[j]:
                j += 1
            runs.append([i * hop_s, j * hop_s])
            i = j
        else:
            i += 1
    out = []
    for s, e in runs:
        if out and s - out[-1][1] < VAD_MIN_GAP:
            out[-1][1] = e
        else:
            out.append([s, e])
    dur = len(y) / sr
    return [(max(0.0, s - VAD_PAD), min(dur, e + VAD_PAD)) for s, e in out if e - s >= VAD_MIN_LEN]


def group_clips(regions: list[tuple[float, float]], max_len: float = CLIP_MAX,
                join_gap: float = CLIP_JOIN_GAP) -> list[list[tuple[float, float]]]:
    """Zones regroupées en fenêtres de transcription (au plus max_len s, sauf zone plus longue seule)."""
    clips: list[list[tuple[float, float]]] = []
    for s, e in regions:
        if clips and s - clips[-1][-1][1] <= join_gap and e - clips[-1][0][0] <= max_len:
            clips[-1].append((s, e))
        else:
            clips.append([(s, e)])
    return clips


def masked(y, regions, sr: int = SR):
    """Signal mis à zéro hors des zones chantées (fondus de 20 ms)."""
    import numpy as np
    m = np.zeros(len(y), dtype=np.float32)
    f = int(0.02 * sr)
    ramp = np.linspace(0, 1, f, dtype=np.float32) if f > 1 else None
    for s, e in regions:
        a, b = int(s * sr), min(len(y), int(e * sr))
        if b <= a:
            continue
        m[a:b] = 1.0
        if ramp is not None and b - a > 2 * f:
            m[a:a + f] = ramp
            m[b - f:b] = ramp[::-1]
    return (np.asarray(y, dtype=np.float32) * m).astype(np.float32)


# --------------------------------------------------------------------------- modèle
def model_file(name: str = DEFAULT_MODEL, root: Path | None = None) -> Path | None:
    """Fichier du modèle déjà présent : officiel (<nom>.pt) ou converti depuis Hugging Face (<nom>-hf.pt)."""
    root = Path(root or WHISPER_DIR)
    for p in (root / f"{name}.pt", root / f"{name}-hf.pt"):
        if p.is_file() and p.stat().st_size > 1000:
            return p
    return None


def hf_to_openai(sd: dict, cfg: dict) -> tuple[dict, dict]:
    """Poids Hugging Face (WhisperForConditionalGeneration) -> (dims, state_dict) au format openai-whisper."""
    dims = {"n_mels": cfg["num_mel_bins"], "n_audio_ctx": cfg["max_source_positions"],
            "n_audio_state": cfg["d_model"], "n_audio_head": cfg["encoder_attention_heads"],
            "n_audio_layer": cfg["encoder_layers"], "n_vocab": cfg["vocab_size"],
            "n_text_ctx": cfg["max_target_positions"], "n_text_state": cfg["d_model"],
            "n_text_head": cfg["decoder_attention_heads"], "n_text_layer": cfg["decoder_layers"]}
    rep = [(".self_attn.q_proj.", ".attn.query."), (".self_attn.k_proj.", ".attn.key."),
           (".self_attn.v_proj.", ".attn.value."), (".self_attn.out_proj.", ".attn.out."),
           (".encoder_attn.q_proj.", ".cross_attn.query."), (".encoder_attn.k_proj.", ".cross_attn.key."),
           (".encoder_attn.v_proj.", ".cross_attn.value."), (".encoder_attn.out_proj.", ".cross_attn.out."),
           (".self_attn_layer_norm.", ".attn_ln."), (".encoder_attn_layer_norm.", ".cross_attn_ln."),
           (".fc1.", ".mlp.0."), (".fc2.", ".mlp.2."), (".final_layer_norm.", ".mlp_ln.")]
    out = {}
    for k, v in sd.items():
        if k.startswith("model."):
            k = k[len("model."):]
        if k.startswith("proj_out."):
            continue                                  # liée à embed_tokens
        if k == "encoder.embed_positions.weight":
            nk = "encoder.positional_embedding"
        elif k == "decoder.embed_positions.weight":
            nk = "decoder.positional_embedding"
        elif k == "decoder.embed_tokens.weight":
            nk = "decoder.token_embedding.weight"
        elif k.startswith("encoder.layer_norm."):
            nk = "encoder.ln_post." + k.split(".")[-1]
        elif k.startswith("decoder.layer_norm."):
            nk = "decoder.ln." + k.split(".")[-1]
        elif ".layers." in k:
            nk = k.replace(".layers.", ".blocks.")
            for a, b in rep:
                nk = nk.replace(a, b)
        else:
            nk = k                                    # encoder.conv1 / conv2
        out[nk] = v
    return dims, out


def convert_from_hf(name: str = DEFAULT_MODEL, root: Path | None = None) -> Path:
    """Repli si le serveur d'OpenAI ne répond pas : dépôt Hugging Face officiel, converti en <nom>-hf.pt."""
    import torch
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file
    root = Path(root or WHISPER_DIR)
    root.mkdir(parents=True, exist_ok=True)
    repo = HF_REPOS[name]
    cache = str(WORDS_DIR / "hf" / "hub")
    cfg = json.loads(Path(hf_hub_download(repo, "config.json", cache_dir=cache)).read_text(encoding="utf-8"))
    sd = load_file(hf_hub_download(repo, "model.safetensors", cache_dir=cache))
    dims, sd = hf_to_openai(sd, cfg)
    out = root / f"{name}-hf.pt"
    tmp = out.with_suffix(".tmp")
    torch.save({"dims": dims, "model_state_dict": {k: v.contiguous() for k, v in sd.items()}}, str(tmp))
    os.replace(tmp, out)
    return out


def download(name: str = DEFAULT_MODEL, root: Path | None = None) -> Path:
    """Télécharge le modèle s'il manque (serveur d'OpenAI, contrôle SHA-256 ; sinon Hugging Face)."""
    import whisper
    root = Path(root or WHISPER_DIR)
    have = model_file(name, root)
    if have:
        return have
    root.mkdir(parents=True, exist_ok=True)
    try:
        return Path(whisper._download(whisper._MODELS[name], str(root), False))
    except Exception as e:                           # noqa: BLE001 - repli Hugging Face
        print(f"  ! {type(e).__name__}: {e} -> Hugging Face ({HF_REPOS.get(name)})", flush=True)
        return convert_from_hf(name, root)


def load(name: str = DEFAULT_MODEL, root: Path | None = None, device: str | None = None):
    """Modèle Whisper en mode eval ; jamais de téléchargement ici (FileNotFoundError s'il manque)."""
    import torch
    import whisper
    root = Path(root or WHISPER_DIR)
    p = model_file(name, root)
    if p is None:
        raise FileNotFoundError(f"{root / (name + '.pt')}")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    # Passing a model name permits Whisper to redownload corrupt/missing cached weights.
    # A local path keeps inference strictly offline; installation/check owns downloads.
    model = whisper.load_model(str(p), device=device)
    if name in getattr(whisper, "_ALIGNMENT_HEADS", {}):
        try:
            model.set_alignment_heads(whisper._ALIGNMENT_HEADS[name])
        except RuntimeError:                          # dimensions différentes : têtes par défaut
            pass
    model.eval()
    return model


# --------------------------------------------------------------------------- transcription
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
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        import torch
        import torchaudio.functional as AF
        y = AF.resample(torch.from_numpy(np.ascontiguousarray(y)), sr, SR).numpy()
    return np.ascontiguousarray(y, dtype=np.float32)


def detect_language(model, y, clips, prefer=("fr", "en")) -> tuple[str, float]:
    """Langue chantée : moyenne des probabilités de Whisper sur les 3 plus longues fenêtres. Une autre langue
    que fr / en n'est retenue que si elle est nette (≥ 0,7) : le chant trompe souvent la détection."""
    import whisper
    probs: dict = {}
    longest = sorted(clips, key=lambda c: -(c[-1][1] - c[0][0]))[:3]
    for c in longest:
        a, b = int(c[0][0] * SR), int(c[-1][1] * SR)
        mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(y[a:b]), model.dims.n_mels).to(model.device)
        _, p = model.detect_language(mel)
        for k, v in p.items():
            probs[k] = probs.get(k, 0.0) + float(v) / len(longest)
    if not probs:
        return prefer[0], 0.0
    best = max(probs, key=probs.get)
    if best not in prefer and probs[best] < 0.7:
        best = max(prefer, key=lambda k: probs.get(k, 0.0))
    return best, round(probs.get(best, 0.0), 3)


def transcribe_array(model, y, lang: str = "auto", status: Path | None = None, decode: dict | None = None) -> dict:
    """Signal 16 kHz mono (numpy) -> résultat (voir l'en-tête du module)."""
    import torch
    import whisper
    t0 = time.time()
    regions = voiced_regions(y)
    clips = group_clips(regions)
    ym = masked(y, regions)
    opts = dict(DECODE)
    opts.update(reacue_performance.whisper_options())
    opts.update(decode or {})
    opts["fp16"] = bool(torch.cuda.is_available() and str(model.device).startswith("cuda"))
    if lang in (None, "", "auto"):
        _write_status(status, "running", step="langue / language")
        lang, lp = detect_language(model, ym, clips) if clips else ("fr", 0.0)
    else:
        lp = 1.0
    segs = []
    for k, c in enumerate(clips):
        _write_status(status, "running", step=f"{k + 1}/{len(clips)}", done=k, total=len(clips))
        a, b = int(c[0][0] * SR), min(len(ym), int(c[-1][1] * SR))
        if b - a < int(0.2 * SR):
            continue
        off = a / SR
        r = whisper.transcribe(model, ym[a:b], language=lang, task="transcribe", verbose=None, **opts)
        for s in r.get("segments") or []:
            ws = [{"w": w["word"].strip(), "t": round(off + float(w["start"]), 3),
                   "end": round(off + float(w["end"]), 3), "p": round(float(w.get("probability", 0.0)), 3)}
                  for w in s.get("words") or [] if str(w.get("word", "")).strip()]
            segs.append({"t": round(off + float(s["start"]), 3), "end": round(off + float(s["end"]), 3),
                         "text": str(s.get("text", "")).strip(),
                         "avg_logprob": round(float(s.get("avg_logprob", 0.0)), 3),
                         "no_speech_prob": round(float(s.get("no_speech_prob", 0.0)), 3),
                         "compression_ratio": round(float(s.get("compression_ratio", 0.0)), 3),
                         "words": ws})
    return {"engine": ENGINE, "language": lang, "language_prob": lp, "seconds": round(time.time() - t0, 1),
            "voiced_s": round(sum(e - s for s, e in regions), 1), "clips": len(clips), "segments": segs}


def transcribe(audio: str, out: str, lang: str = "auto", model_name: str = DEFAULT_MODEL,
               status: str | None = None) -> int:
    st = Path(status) if status else None
    out = Path(out).resolve()
    t0 = time.time()
    try:
        _write_status(st, "running", step="chargement du modèle / loading model")
        import torch
        reacue_performance.configure_torch(torch)
        model = load(model_name)
        y = _load_audio(audio)
        res = transcribe_array(model, y, lang, st)
        res.update({"model": model_name, "seconds": round(time.time() - t0, 1)})
        tmp = Path(str(out) + ".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, out)
        _write_status(st, "done", seconds=res["seconds"])
        return 0
    except BaseException as e:                       # noqa: BLE001 - rapporté à ReaCue
        traceback.print_exc()
        _write_status(st, "error", message=f"{type(e).__name__}: {e}")
        return 1


def check(lang: str = "fr", model_name: str = DEFAULT_MODEL, do_download: bool = False) -> int:
    def t(fr, en):
        return en if lang == "en" else fr
    try:
        import numpy as np
        import torch
        import whisper
    except Exception as e:                           # noqa: BLE001
        print(t("ÉCHEC : Whisper non importable : ", "FAILED: Whisper cannot be imported: ") + repr(e))
        return 1
    print(f"  python {sys.version.split()[0]} | torch {torch.__version__} | numpy {np.__version__} | "
          f"openai-whisper {getattr(whisper, '__version__', '?')}")
    if do_download and model_file(model_name) is None:
        print(t(f"  téléchargement du modèle Whisper {model_name}…",
                f"  downloading the Whisper {model_name} model…"), flush=True)
        download(model_name)
    t0 = time.time()
    model = load(model_name)
    print(t(f"  modèle prêt ({time.time() - t0:.0f} s) : {model_file(model_name)}",
            f"  model ready ({time.time() - t0:.0f} s): {model_file(model_name)}"), flush=True)
    # essai : 8 s de voyelles synthétiques (aucun texte attendu), mesure de la vitesse
    rng = np.random.default_rng(0)
    tt = np.arange(SR * 8) / SR
    y = (0.2 * np.sin(2 * np.pi * 220 * tt) * (np.sin(2 * np.pi * 0.5 * tt) > 0)
         + 0.01 * rng.standard_normal(len(tt))).astype(np.float32)
    t0 = time.time()
    res = transcribe_array(model, y, "fr" if lang == "fr" else "en")
    dt = time.time() - t0
    assert isinstance(res.get("segments"), list)
    # une passe d'encodeur par fenêtre ; un morceau ≈ 6 à 10 fenêtres
    per = dt / max(1, res["clips"])
    print(t(f"  vitesse : environ {per * 8 / 60:.1f} min pour un morceau",
            f"  speed: about {per * 8 / 60:.1f} min per song"))
    print("WHISPER_OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reacue_transcribe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("transcribe")
    a.add_argument("--audio", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--lang", default="auto")
    a.add_argument("--model", default=selected_model())
    a.add_argument("--status")
    c = sub.add_parser("check")
    c.add_argument("--lang", default="fr", choices=["fr", "en"])
    c.add_argument("--model", default=selected_model())
    c.add_argument("--download", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "transcribe":
        return transcribe(args.audio, args.out, args.lang, args.model, args.status)
    try:
        return check(args.lang, args.model, args.download)
    except Exception as e:                           # noqa: BLE001
        traceback.print_exc()
        print(("ÉCHEC : " if args.lang == "fr" else "FAILED: ") + repr(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
