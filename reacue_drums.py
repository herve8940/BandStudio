"""Transcription de batterie pour ReaCue (ADTOF, en local) / Drum transcription for ReaCue (ADTOF, local).

Tourne dans l'environnement séparé .venv-drums (installé par install/install_drums_*), jamais dans le .venv
de ReaCue. Modèle : ADTOF « Frame_RNN » (M. Zehren, M. Alunno, P. Bientinesi ; poids CC BY-NC-SA 4.0), dans
son portage PyTorch ADTOF-pytorch (X. Riley) téléchargé par l'installateur dans
<ReaCue>/drums/ADTOF-pytorch (révision figée, poids de 16 Mo compris). Calcul sur CPU, quelques dizaines de
secondes pour un morceau.

    <python> reacue_drums.py analyze --input <stem batterie> --out <résultat.json> [--status <état.json>]
        -> {"engine": "adtof", "fps": 100, "classes": [...], "duration",
            "onsets": {"BD": [[t, p], …], "SD": …, "TT": …, "HH": …, "CY": …}, "seconds"}
           (t en secondes dans le temps du fichier, p = activation du modèle au pic, 0..1)
    <python> reacue_drums.py check [--lang fr|en]    # charge le modèle, teste sur une batterie synthétique,
                                                    # affiche la vitesse, « DRUMS_OK »

Classes ADTOF (5) : grosse caisse (BD), caisse claire (SD), toms (TT), charleston (HH), cymbales crash + ride
(CY). ReaCue précise ensuite par le signal : tom aigu / médium / basse, charley fermé / ouvert, crash / ride.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import types
from pathlib import Path

import reacue_performance

reacue_performance.configure()

import reacue_metal

reacue_metal.configure()

HERE = Path(__file__).resolve().parent
DRUMS_DIR = Path(os.environ.get("REACUE_DRUMS_DIR") or HERE / "drums")
REPO = DRUMS_DIR / "ADTOF-pytorch"
FPS = 100
CLASSES = ("BD", "SD", "TT", "HH", "CY")          # ordre des sorties du modèle (GM 35, 38, 47, 42, 49)
THRESHOLDS = (0.22, 0.24, 0.32, 0.22, 0.30)       # seuils publiés avec le modèle Frame_RNN
CHUNK = 6000                                       # trames (60 s) par passe : mémoire bornée
OVERLAP = 300                                      # recouvrement (3 s) : contexte pour les GRU


def _write_status(path: Path | None, state: str, **kw):
    if not path:
        return
    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- détection des pics (numpy)
def pick_peaks(act, threshold: float, fps: int = FPS, pre_avg: float = 0.1, post_avg: float = 0.01,
               pre_max: float = 0.02, post_max: float = 0.01, combine: float = 0.02) -> list[list[float]]:
    """Pics d'une activation (une classe) : [[t (s), activation au pic]].

    Même principe que le sélecteur de pics de madmom utilisé par ADTOF : activation moins sa moyenne
    glissante (100 ms avant, 10 ms après), maximum local sur ±20/10 ms, au-dessus du seuil ; pics à moins
    de 20 ms fusionnés (le plus fort gardé)."""
    import numpy as np
    x = np.asarray(act, dtype=np.float32).reshape(-1)
    if not len(x):
        return []
    a0, a1 = int(round(pre_avg * fps)), int(round(post_avg * fps))
    k = np.ones(a0 + a1 + 1, dtype=np.float32) / (a0 + a1 + 1)
    avg = np.convolve(np.pad(x, (a0, a1), mode="edge"), k, mode="valid")
    d = np.maximum(0.0, x - avg)
    m0, m1 = int(round(pre_max * fps)), int(round(post_max * fps))
    pad = np.pad(d, (m0, m1), mode="edge")
    mx = np.max(np.stack([pad[i:i + len(d)] for i in range(m0 + m1 + 1)]), axis=0)
    idx = np.nonzero((d >= mx) & (d >= threshold))[0]
    if not len(idx):
        return []
    comb = max(1, int(round(combine * fps)))
    groups, cur = [], [int(idx[0])]
    for i in idx[1:]:
        if i - cur[-1] <= comb:
            cur.append(int(i))
        else:
            groups.append(cur)
            cur = [int(i)]
    groups.append(cur)
    out = []
    for g in groups:
        best = max(g, key=lambda i: d[i])
        out.append([round(best / fps, 3), round(float(x[best]), 3)])
    return out


def onsets_from_activations(act, fps: int = FPS, thresholds=THRESHOLDS) -> dict:
    return {c: pick_peaks(act[:, k], thresholds[k], fps) for k, c in enumerate(CLASSES)}


# --------------------------------------------------------------------------- modèle
def load_adtof():
    """Module adtof_pytorch.model du dépôt figé (pretty_midi, inutile ici, est simulé)."""
    src = REPO / "src"
    if not (src / "adtof_pytorch" / "model.py").is_file():
        raise FileNotFoundError(f"ADTOF-pytorch introuvable / not found: {REPO}")
    sys.path.insert(0, str(src))
    if "pretty_midi" not in sys.modules:
        pm = types.ModuleType("pretty_midi")
        pm.PrettyMIDI = pm.Instrument = pm.Note = object       # annotations seulement
        sys.modules["pretty_midi"] = pm
    from adtof_pytorch import model as M  # noqa: E402
    return M


def weights_path() -> Path:
    return REPO / "src" / "adtof_pytorch" / "data" / "adtof_frame_rnn_pytorch_weights.pth"


def load_model():
    M = load_adtof()
    import torch
    reacue_performance.configure_torch(torch)
    net = M.create_frame_rnn_model(M.calculate_n_bins())
    w = weights_path()
    if not w.is_file():
        raise FileNotFoundError(f"poids ADTOF introuvables / ADTOF weights not found: {w}")
    M.load_pytorch_weights(net, str(w), strict=True)
    net.eval()
    return M, net


def activations(audio: str, M=None, net=None, status=None):
    """Activations (T, 5) à 100 trames/s, calculées par passes de 60 s qui se recouvrent."""
    import numpy as np
    import torch
    if net is None:
        M, net = load_model()
    x = M.load_audio_for_model(str(audio))           # [1, T, bins, 1]
    T = x.shape[1]
    out = np.zeros((T, len(CLASSES)), dtype=np.float32)
    with torch.no_grad():
        s = 0
        while s < T:
            _write_status(status,"running",step="Transcription des frappes",done=s,total=T)
            a = max(0, s - OVERLAP)
            b = min(T, s + CHUNK + OVERLAP)
            y = reacue_metal.forward(net, x[:, a:b]).numpy()[0]
            e = min(T, s + CHUNK)
            out[s:e] = y[s - a:e - a]
            s = e
            _write_status(status,"running",step="Transcription des frappes",done=s,total=T)
    return out


def analyze(audio: str, out: str, status: str | None = None) -> int:
    st = Path(status) if status else None
    audio = str(Path(audio).resolve())
    out = Path(out).resolve()
    t0 = time.time()
    try:
        if not Path(audio).is_file():
            raise FileNotFoundError(audio)
        _write_status(st, "running", step="chargement du modèle / loading model")
        M, net = load_model()
        _write_status(st, "running", step="transcription / transcribing")
        act = activations(audio, M, net, status=st)
        res = {"engine": "adtof", "fps": FPS, "classes": list(CLASSES), "duration": round(len(act) / FPS, 2),
               "onsets": onsets_from_activations(act), "seconds": round(time.time() - t0, 1)}
        tmp = Path(str(out) + ".tmp")
        tmp.write_text(json.dumps(res), encoding="utf-8")
        os.replace(tmp, out)
        _write_status(st, "done", seconds=res["seconds"])
        return 0
    except BaseException as e:                       # noqa: BLE001 - rapporté à ReaCue
        traceback.print_exc()
        _write_status(st, "error", message=f"{type(e).__name__}: {e}")
        return 1


# --------------------------------------------------------------------------- test d'installation
def synth_groove(sr: int = 44100, bpm: float = 120.0, bars: int = 4, seed: int = 0):
    """Batterie synthétique (rock : charley en croches, grosse caisse 1 et 3, caisse claire 2 et 4).
    Renvoie (signal, {classe: [temps]})."""
    import numpy as np
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    n = int((bars * 4 * beat + 1.0) * sr)
    y = np.zeros(n, dtype=np.float32)
    truth = {"BD": [], "SD": [], "HH": []}

    def add(t, sig):
        i = int(t * sr)
        seg = sig[: max(0, n - i)]
        y[i:i + len(seg)] += seg

    tt = np.arange(int(0.35 * sr)) / sr
    kick = (np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)).astype(np.float32)
    ts = np.arange(int(0.25 * sr)) / sr
    snare = (0.5 * np.sin(2 * np.pi * 190 * ts) * np.exp(-ts * 25)
             + 0.6 * rng.standard_normal(len(ts)) * np.exp(-ts * 18)).astype(np.float32)
    th = np.arange(int(0.06 * sr)) / sr
    noise = rng.standard_normal(len(th))
    hh = (np.diff(np.r_[0.0, np.diff(np.r_[0.0, noise])]) * 0.25 * np.exp(-th * 70)).astype(np.float32)
    for b in range(bars):
        for e in range(8):
            t = 0.5 + (b * 4 + e / 2) * beat
            add(t, hh)
            truth["HH"].append(round(t, 3))
            if e in (0, 4):
                add(t, kick)
                truth["BD"].append(round(t, 3))
            if e in (2, 6):
                add(t, snare)
                truth["SD"].append(round(t, 3))
    return y / (np.abs(y).max() + 1e-9) * 0.8, truth


def match_rate(found: list, truth: list, tol: float = 0.05) -> float:
    if not truth:
        return 1.0
    return sum(any(abs(f[0] - t) <= tol for f in found) for t in truth) / len(truth)


def check(lang: str = "fr") -> int:
    import tempfile
    import numpy as np
    import soundfile as sf

    def t(fr, en):
        return en if lang == "en" else fr
    M, net = load_model()
    print(t("  modèle ADTOF chargé", "  ADTOF model loaded"))
    y, truth = synth_groove(bars=8)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "drums.wav"
        sf.write(str(wav), y[:44100], 44100)
        activations(str(wav), M, net)               # 1er appel : compilation de librosa (non mesurée)
        sf.write(str(wav), y, 44100)
        t0 = time.time()
        act = activations(str(wav), M, net)
        dt = time.time() - t0
    on = onsets_from_activations(act)
    rates = {c: match_rate(on[c], truth[c]) for c in truth}
    print("  " + ", ".join(f"{c} {r:.0%}" for c, r in rates.items()))
    per_song = dt / (len(y) / 44100) * 240
    print(t(f"  vitesse : environ {per_song:.0f} s pour un morceau de 4 min",
            f"  speed: about {per_song:.0f} s for a 4-minute song"))
    if rates["BD"] < 0.5 or rates["SD"] < 0.5:
        print(t("  la batterie de test n'est pas reconnue", "  the test drums are not recognised"))
        return 1
    print("DRUMS_OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reacue_drums")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--input", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--status")
    c = sub.add_parser("check")
    c.add_argument("--lang", default="fr", choices=["fr", "en"])
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        return analyze(args.input, args.out, args.status)
    return check(args.lang)


if __name__ == "__main__":
    sys.exit(main())
