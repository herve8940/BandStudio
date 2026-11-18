"""Reconnaissance d'accords pour ReaCue (modèle entraîné, en local) / Chord recognition for ReaCue (trained model, local).

Tourne dans l'environnement séparé .venv-chords (installé par install/install_chords_*), jamais dans le .venv
de ReaCue. Utilise le modèle « Large-Vocabulary Chord Transcription via Chord Structure Decomposition »
(Junyan Jiang, Ke Chen, Wei Li, Gus Xia — ISMIR 2019 ; dépôt music-x-lab/ISMIR2019-Large-Vocabulary-Chord-
Recognition, licence MIT, poids inclus dans le dépôt) téléchargé par l'installateur dans <ReaCue>/chords/model
(révision figée). Ensemble de 5 réseaux CNN + LSTM bidirectionnel qui prédisent séparément triade, basse, 7e,
9e, 11e et 13e ; décodage HMM du dépôt, calé sur les temps de ReaCue (les accords ne changent que sur un temps,
plus facilement sur le 1er et le 3e).

    <python> reacue_chords.py analyze --input <audio> --out <résultat.json> [--status <état.json>]
                                      [--beats <temps.json>] [--vocab submission|extended|ismir2017]
                                      [--probs <cache.npz> [--key <clé de l'audio>]]
        temps.json : {"beats": [s…], "downbeats": [s…], "beats_per_bar": 4} (facultatif)
        -> {"engine": "jiang2019", "segments": [{"start", "end", "label", "confidence"}], "seconds": …}
           label au format Harte (« C:maj », « A:min/b3 », « G:7 », « N »)
    <python> reacue_chords.py check [--lang fr|en]       # test sur un audio synthétique, « CHORDS_OK »

--probs : probabilités du réseau mises en cache (npz) ; si le fichier existe et correspond au même audio,
le réseau n'est pas relancé (seul le décodage, rapide, suit la grille de ReaCue).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
import types
from pathlib import Path

import reacue_performance

reacue_performance.configure()

HERE = Path(__file__).resolve().parent
CHORDS_DIR = Path(os.environ.get("REACUE_CHORDS_DIR") or HERE / "chords")
REPO = CHORDS_DIR / "model"
ENGINE = "jiang2019"
SR, HOP = 22050, 512
N_MODELS = 5
MODEL_NAME = "joint_chord_net_ismir_naive_v1.0_reweight(0.0,10.0)_s%d.best"
# pénalités de changement d'accord du HMM (log-probabilité) : temps 1, temps 3 (mesure paire), autres temps
PEN_DOWNBEAT, PEN_HALF, PEN_BEAT = 15.0, 45.0, 100.0


def _write_status(path: Path | None, state: str, **kw):
    if not path:
        return
    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _stub_modules():
    """Modules importés par le paquet `mir` du dépôt mais inutiles en inférence (entraînement, lecture
    de fichiers) : remplacés par des modules vides pour ne pas installer h5py, pydub, joblib…"""
    for name in ("h5py", "pydub", "pydub.utils", "joblib", "pretty_midi"):
        if name in sys.modules:
            continue
        try:
            __import__(name)
            continue
        except Exception:
            pass
        m = types.ModuleType(name)
        m.__getattr__ = lambda n, _name=name: (_ for _ in ()).throw(AttributeError(f"{_name}.{n}")) \
            if n.startswith("__") else (lambda *a, **k: None)
        sys.modules[name] = m
    if "pydub" in sys.modules and "pydub.utils" in sys.modules:
        setattr(sys.modules["pydub"], "utils", sys.modules["pydub.utils"])


def load_repo():
    """Importe le modèle et le décodeur du dépôt ; renvoie (ChordNet, XHMMDecoder)."""
    if not (REPO / "chordnet_ismir_naive.py").is_file():
        raise FileNotFoundError(f"modèle d'accords introuvable / chord model not found: {REPO}")
    import numpy as np
    for alias, typ in (("int", int), ("float", float), ("bool", bool)):   # code écrit pour numpy < 1.24
        if alias not in np.__dict__:
            setattr(np, alias, typ)
    os.chdir(REPO)                       # mir.common.WORKING_PATH = dossier courant (cache_data/)
    sys.path.insert(0, str(REPO))
    _stub_modules()
    from chordnet_ismir_naive import ChordNet          # noqa: E402
    from extractors.xhmm_ismir import XHMMDecoder      # noqa: E402
    return ChordNet, XHMMDecoder


def file_key(audio: str) -> str:
    p = Path(audio)
    st = p.stat()
    return hashlib.sha1(f"{ENGINE}|{p.resolve()}|{st.st_size}|{int(st.st_mtime)}|{N_MODELS}".encode()).hexdigest()


def cqt(audio: str):
    """CQT hybride du dépôt (CQTV2) : 288 cases, 36 par octave depuis F#0, hop 512 à 22050 Hz."""
    import librosa
    import numpy as np
    y, _ = librosa.load(audio, sr=SR, mono=True)
    C = librosa.hybrid_cqt(y, sr=SR, bins_per_octave=36, fmin=librosa.note_to_hz("F#0"), n_bins=288,
                           tuning=None, hop_length=HOP).T
    return np.abs(C).astype(np.float32)


def probabilities(audio: str, ChordNet, status=None):
    """Moyenne des 5 réseaux : liste de 6 tableaux (triade, basse, 7e, 9e, 11e, 13e) par trame."""
    import numpy as np
    import torch
    _write_status(status, 'running', step='Préparation harmonique')
    feat = cqt(audio)
    x = torch.tensor(feat, dtype=torch.float32)
    probs = []
    for i in range(N_MODELS):
        _write_status(status, "running", step=f"Réseau {i + 1} sur {N_MODELS}", done=i, total=N_MODELS)
        net = ChordNet(None)
        net.use_gpu = False
        sd = torch.load(str(REPO / "cache_data" / (MODEL_NAME % i + ".sdict")), map_location="cpu")
        net.load_state_dict(sd["net"])
        net.eval()
        with torch.no_grad():
            probs.append([np.asarray(p, dtype=np.float32) for p in net.inference(x)])
        _write_status(status, "running", step=f"Réseau {i + 1} sur {N_MODELS}", done=i+1, total=N_MODELS)
    return [np.mean([p[k] for p in probs], axis=0) for k in range(len(probs[0]))]


def beat_array(n_frames: int, beats: dict | None):
    """Trames où un changement d'accord est permis (format du décodeur du dépôt) :
    0 = pas de changement, 2 = temps 1, 3 = temps du milieu (mesure paire), 4 = autre temps ; sans grille :
    1 partout (changement possible à chaque trame)."""
    import numpy as np
    arr = np.ones(n_frames, dtype=np.int8)
    if not beats or len(beats.get("beats") or []) < 2:
        return arr
    dt = HOP / SR
    bt = [float(t) for t in beats["beats"]]
    db = {int(round(float(t) / dt)) for t in beats.get("downbeats") or []}
    m = int(beats.get("beats_per_bar") or 4)
    fr = [int(round(t / dt)) for t in bt]
    arr[:] = 0
    for f in fr:
        if 0 <= f < n_frames:
            arr[f] = 4
    # temps 1 : les mesures ; temps du milieu : m/2 temps après le temps 1 (mesure paire)
    db_sorted = sorted(db)
    for f in db_sorted:
        if 0 <= f < n_frames:
            arr[f] = 2
    if m % 2 == 0 and m >= 4:
        idx = {f: k for k, f in enumerate(fr)}
        for f in db_sorted:
            k = idx.get(f)
            if k is not None and k + m // 2 < len(fr) and 0 <= fr[k + m // 2] < n_frames:
                arr[fr[k + m // 2]] = 3
    # avant le premier temps / après le dernier : changement possible partout (intro libre, fin)
    lo = min((f for f in fr if f >= 0), default=0)
    hi = max((f for f in fr if f < n_frames), default=n_frames - 1)
    arr[:max(0, lo)] = 1
    arr[hi + 1:] = 1
    return arr


def decode(probs, XHMMDecoder, beats: dict | None = None, vocab: str = "submission") -> list[dict]:
    """Décodage HMM -> segments [{start, end, label, confidence}] (secondes, labels Harte)."""
    import numpy as np
    hmm = XHMMDecoder(diff_trans_penalty=30.0, beat_trans_penalty=(PEN_DOWNBEAT, PEN_HALF, PEN_BEAT),
                      template_file=str(REPO / "data" / f"{vocab}_chord_list.txt"))
    names, logp = hmm.get_chord_tag_obs(probs)
    n = logp.shape[0]
    tags = hmm.decode(probs, beat_array(n, beats))
    # confiance : probabilité (normalisée sur le vocabulaire) de la « famille » de l'accord retenu (même
    # fondamentale, même couleur majeure / mineure / diminuée / sus, enrichissements et renversements
    # confondus : c'est ce que le musicien lit), moyennée sur le segment
    lp = logp - logp.max(1, keepdims=True)
    post = np.exp(lp)
    post /= post.sum(1, keepdims=True)
    groups = {}
    for i, nm in enumerate(names):
        groups.setdefault(family(nm), []).append(i)
    fpost = {f: post[:, idx].sum(1) for f, idx in groups.items()}
    dt = HOP / SR
    segs, start = [], 0
    for i in range(n):
        if i + 1 == n or tags[i + 1] != tags[i]:
            c = float(fpost[family(tags[i])][start:i + 1].mean())
            segs.append({"start": round(start * dt, 4), "end": round((i + 1) * dt, 4), "label": tags[i],
                         "confidence": round(min(1.0, c), 3)})
            start = i + 1
    return segs


def family(label: str) -> tuple:
    """« A:min7/b7 » -> ("A", "min") ; familles : maj, min, dim, aug, sus ; « N » -> ("N", "")."""
    if ":" not in label:
        return (label, "")
    root, q = label.split(":", 1)
    q = q.split("/")[0]
    if q.startswith("sus"):
        return (root, "sus")
    if q.startswith(("dim", "hdim")):
        return (root, "dim")
    if q.startswith("aug"):
        return (root, "aug")
    if q.startswith("min"):
        return (root, "min")
    return (root, "maj")


def analyze(audio: str, out: str, status: str | None = None, beats_file: str | None = None,
            vocab: str = "submission", probs_cache: str | None = None, key: str | None = None) -> int:
    # chemins absolus avant load_repo (qui change de dossier courant)
    st = Path(status).resolve() if status else None
    audio = str(Path(audio).resolve())
    out = Path(out).resolve()
    pc = Path(probs_cache).resolve() if probs_cache else None
    t0 = time.time()
    try:
        if not Path(audio).is_file():
            raise FileNotFoundError(audio)
        beats = json.loads(Path(beats_file).read_text(encoding="utf-8")) if beats_file else None
        _write_status(st, "running", step="chargement du modèle / loading the model")
        ChordNet, XHMMDecoder = load_repo()
        import numpy as np
        import torch
        reacue_performance.configure_torch(torch)
        key = key or file_key(audio)
        probs = None
        if pc and pc.is_file():
            try:
                z = np.load(str(pc), allow_pickle=False)
                if str(z["key"]) == key:
                    probs = [z[f"p{k}"] for k in range(6)]
            except Exception:                        # noqa: BLE001 - cache illisible : on recalcule
                probs = None
        cached = probs is not None
        if probs is None:
            _write_status(st, "running", step="analyse / analysing")
            probs = probabilities(audio, ChordNet, st)
            if pc:
                try:
                    pc.parent.mkdir(parents=True, exist_ok=True)
                    tmp = pc.with_name(pc.stem + ".tmp.npz")
                    np.savez_compressed(str(tmp), key=np.array(key), **{f"p{k}": p for k, p in enumerate(probs)})
                    os.replace(tmp, pc)
                except OSError:
                    pass
        _write_status(st, "running", step="décodage / decoding")
        segs = decode(probs, XHMMDecoder, beats, vocab)
        res = {"engine": ENGINE, "vocab": vocab, "segments": segs, "probs_cached": cached,
               "seconds": round(time.time() - t0, 1)}
        tmp = Path(str(out) + ".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, out)
        _write_status(st, "done", seconds=res["seconds"])
        return 0
    except BaseException as e:                       # noqa: BLE001 - rapporté à ReaCue
        traceback.print_exc()
        _write_status(st, "error", message=f"{type(e).__name__}: {e}")
        return 1


# --------------------------------------------------------------------------- audio synthétique (test)
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "Ab": 8,
        "A": 9, "Bb": 10, "B": 11}
QUAL = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10),
        "sus4": (0, 5, 7), "sus2": (0, 2, 7), "dim": (0, 3, 6), "aug": (0, 4, 8)}


def synth(chords: list[str], bpm: float = 100.0, beats_per_chord: int = 4, sr: int = SR, seed: int = 0):
    """Audio d'accords synthétiques (« C:maj », « A:min/b3 »…) : piano à harmoniques + basse.
    Renvoie (signal, temps des temps)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    dur = beat * beats_per_chord
    n = int(sr * dur * len(chords)) + sr
    y = np.zeros(n, dtype=np.float32)
    t = np.arange(int(sr * beat)) / sr

    def tone(midi, amp, decay):
        f = 440.0 * 2 ** ((midi - 69) / 12)
        s = sum((0.6 ** (h - 1)) * np.sin(2 * np.pi * f * h * t + rng.uniform(0, 6.28)) for h in range(1, 7))
        return (amp * s * np.exp(-t * decay)).astype(np.float32)
    for i, c in enumerate(chords):
        root, _, rest = c.partition(":")
        q, _, inv = rest.partition("/")
        r = NOTE[root]
        ivs = QUAL[q]
        bass = r
        if inv:
            deg = {"3": 4, "b3": 3, "5": 7, "b7": 10, "7": 11, "2": 2, "4": 5}[inv]
            bass = (r + deg) % 12
        for b in range(beats_per_chord):
            i0 = int(sr * (i * dur + b * beat))
            for iv in ivs:
                y[i0:i0 + len(t)] += tone(60 + (r + iv) % 12 - (12 if (r + iv) % 12 > 7 else 0), 0.12, 2.5)
            y[i0:i0 + len(t)] += tone(36 + bass, 0.25, 1.5)
    y /= max(1e-6, float(np.abs(y).max())) / 0.8
    beats = [round(k * beat, 4) for k in range(len(chords) * beats_per_chord + 1)]
    return y, beats


def check(lang: str = "fr") -> int:
    def t(fr, en):
        return en if lang == "en" else fr
    try:
        ChordNet, XHMMDecoder = load_repo()
        import numpy as np
        import torch
        import soundfile as sf
    except Exception as e:                           # noqa: BLE001
        print(t("ÉCHEC : le modèle d'accords n'est pas importable : ",
                "FAILED: the chord model cannot be imported: ") + repr(e))
        return 1
    print(f"  python {sys.version.split()[0]} | torch {torch.__version__} | numpy {np.__version__}")
    prog = ["C:maj", "A:min", "F:maj", "G:7", "D:min7", "G:maj", "C:maj/3", "F:maj"]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "test.wav"
        y, beats = synth(prog)
        sf.write(str(wav), y, SR)
        warm = Path(tmp) / "warm.wav"                 # 1er appel : compilation (numba), hors chronométrage
        sf.write(str(warm), y[:SR * 3], SR)
        probabilities(str(warm), ChordNet)
        t0 = time.time()
        probs = probabilities(str(wav), ChordNet)
        el = time.time() - t0
        segs = decode(probs, XHMMDecoder, {"beats": beats, "downbeats": beats[::4], "beats_per_bar": 4})
    dur = len(y) / SR
    got = []
    for k, want in enumerate(prog):
        mid = (k + 0.5) * dur / len(prog)
        lab = next((s["label"] for s in segs if s["start"] <= mid < s["end"]), "?")
        got.append(lab)
    ok = sum(g.split("/")[0].split(":")[0] == w.split("/")[0].split(":")[0] for g, w in zip(got, prog))
    print(t("  attendu : ", "  expected: ") + " ".join(prog))
    print(t("  reconnu : ", "  found:    ") + " ".join(got))
    print(t(f"  vitesse : environ {el / dur * 240:.0f} s pour un morceau de 4 min",
            f"  speed: about {el / dur * 240:.0f} s for a 4-minute song"))
    if ok < len(prog) - 2:
        print(t("ÉCHEC : le modèle ne reconnaît pas l'audio de test.", "FAILED: the model does not recognise the test audio."))
        return 1
    print("CHORDS_OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reacue_chords")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--input", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--status")
    a.add_argument("--beats")
    a.add_argument("--vocab", default="submission", choices=["submission", "extended", "ismir2017"])
    a.add_argument("--probs")
    a.add_argument("--key", help="clé de l'audio pour le cache --probs (défaut : fichier, taille, date)")
    c = sub.add_parser("check")
    c.add_argument("--lang", default="fr", choices=["fr", "en"])
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        return analyze(args.input, args.out, args.status, args.beats, args.vocab, args.probs, args.key)
    return check(args.lang)


if __name__ == "__main__":
    sys.exit(main())
