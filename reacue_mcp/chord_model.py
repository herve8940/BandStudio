"""Accords par modèle entraîné (composant optionnel) / Chord recognition with a trained model (optional).

Le modèle de Jiang et al. (ISMIR 2019, music-x-lab, licence MIT, poids compris) tourne dans l'environnement
séparé .venv-chords (installé par install/install_chords_*), jamais dans le .venv de ReaCue : ce module-ci
ne dépend pas de torch, il écrit l'audio harmonique (stems sans voix ni batterie, sinon le mix), lance
`reacue_chords.py` en sous-processus avec les temps de la grille de ReaCue, lit ses segments (cache par
morceau) ; chords.chords_from_segments les cale ensuite sur les mesures.

Réglage `chords_engine` : "auto" (défaut : le modèle s'il est installé, sinon la détection de ReaCue) |
"reacue" (détection de ReaCue seule) ; la variable d'environnement REACUE_CHORDS_ENGINE l'emporte (tests).
Tout échec retombe sur la détection de ReaCue (chords.detect_chords) : le prompteur n'est jamais bloqué.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # dossier d'installation de ReaCue
ENGINE = "jiang2019"
# révision figée du dépôt téléchargé par install/install_chords_* (même valeur là-bas)
MODEL_REPO = "music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition"
MODEL_REV = "481f4ce703f8822b99f4037e9104ba1760e21ea3"
CACHE_VERSION = 1
TIMEOUT_S = 600                  # 10 min (CPU lent, 1er lancement) ; au-delà, détection de ReaCue
RETRY_AFTER_S = 3600             # après un échec, pas de nouvel essai sur le même audio pendant 1 h
VOCAB = "submission"             # dictionnaire d'accords du HMM (celui de l'article, recommandé)

PROGRESS = None                  # callback(message) facultatif
LAST = {}                        # dernier résultat (moteur utilisé, message) : diagnostic, fenêtre, CLI


# --------------------------------------------------------------------------- #
# Composant installé ?
# --------------------------------------------------------------------------- #
def chords_python(install_dir: Path | None = None, windows: bool | None = None) -> Path:
    d = Path(install_dir or ROOT)
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        return d / ".venv-chords" / "Scripts" / "python.exe"
    return d / ".venv-chords" / "bin" / "python"


def available(install_dir: Path | None = None) -> bool:
    d = Path(install_dir or ROOT)
    m = d / "chords" / "model"
    return (chords_python(d).exists() and (d / "reacue_chords.py").is_file()
            and (m / "chordnet_ismir_naive.py").is_file() and (m / "cache_data").is_dir())


def engine_setting() -> str:
    env = os.environ.get("REACUE_CHORDS_ENGINE", "").lower()
    if env in ("auto", "reacue", "off"):
        return env
    try:
        from .settings import load_settings
        v = str(load_settings().get("chords_engine") or "auto").lower()
    except Exception:
        v = "auto"
    return v if v in ("auto", "reacue", "off") else "auto"


def wanted(install_dir: Path | None = None) -> bool:
    """Le modèle sera-t-il essayé ? (réglage « auto » et composant installé)"""
    return engine_setting() == "auto" and available(install_dir)


# --------------------------------------------------------------------------- #
# Audio harmonique, temps, clés de cache
# --------------------------------------------------------------------------- #
def harmonic_sources(srcs: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """Stems utiles aux accords : tout sauf la voix et la batterie (basse comprise : elle donne les
    renversements). Mode MP3 (un seul fichier) : le mix tel quel."""
    if len(srcs) <= 1:
        return list(srcs)
    keep = [s for s in srcs if re.sub(r"_\d+$", "", s[0]) not in ("vocals", "drums")]
    return keep or list(srcs)


def write_mix(srcs: list[tuple[str, str, float]], n: int, wav: Path, sr: int = 22050) -> Path:
    """Somme des sources (décalées dans le temps du stem de référence) -> WAV mono 22 050 Hz."""
    import numpy as np
    import soundfile as sf
    from .chords import _load
    mix = np.zeros(n, dtype=np.float32)
    for _, f, sh in srcs:
        y = _load(f, sh, n)
        mix[:len(y)] += y[:n]
    peak = float(np.abs(mix).max()) or 1.0
    wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav), (mix / peak * 0.9).astype(np.float32), sr, subtype="PCM_16")
    return wav


def beats_payload(a) -> dict:
    """Temps de la grille de ReaCue (temps du stem de référence) pour le décodage du modèle."""
    from .chords import _beat_frames
    tb, _ = _beat_frames(a)
    return {"beats": [round(float(t), 4) for t in tb], "downbeats": [round(float(t), 4) for t in a.downbeats],
            "beats_per_bar": int(a.beats_per_bar)}


def audio_key(srcs: list[tuple[str, str, float]]) -> str:
    """Clé de l'audio analysé (fichiers, tailles, dates, décalages, révision du modèle)."""
    h = hashlib.sha1(f"{ENGINE}:{MODEL_REV}:{CACHE_VERSION}".encode())
    for role, f, sh in sorted(srcs, key=lambda s: str(s[1])):
        p = Path(f)
        try:
            st = p.stat()
            h.update(f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}|{round(float(sh), 4)}".encode())
        except OSError:
            h.update(f"{f}|missing".encode())
    return h.hexdigest()


def grid_key(beats: dict) -> str:
    return hashlib.sha1(json.dumps([beats["beats"], beats["beats_per_bar"], VOCAB]).encode()).hexdigest()


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", str(name)).strip(" .") or "song"


def cache_paths(ref_file: str) -> tuple[Path, Path]:
    """(segments JSON, probabilités npz) dans <dossier du morceau>/.reacue/."""
    d = Path(ref_file).parent / ".reacue"
    stem = _safe(Path(ref_file).stem)
    return d / f"{stem}_chords_model.json", d / f"{stem}_chords_probs.npz"


def _read_json(p: Path) -> dict | None:
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(p: Path, d: dict):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _progress(msg: str):
    if PROGRESS:
        try:
            PROGRESS(msg)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Sous-processus
# --------------------------------------------------------------------------- #
def run_engine(audio: str, out_json: Path, beats: dict | None = None, probs: Path | None = None,
               key: str | None = None, install_dir: Path | None = None, timeout: float = TIMEOUT_S,
               python: str | None = None, script: str | None = None) -> dict:
    """Lance reacue_chords.py analyze ; renvoie le résultat (dict) ou lève RuntimeError."""
    from .i18n import t
    d = Path(install_dir or ROOT).resolve()
    py = python or str(chords_python(d))
    sc = script or str(d / "reacue_chords.py")
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    status = out_json.with_name(out_json.stem + "_status.json")
    for p in (out_json, status):
        try:
            p.unlink()
        except OSError:
            pass
    cmd = [py, sc, "analyze", "--input", str(audio), "--out", str(out_json), "--status", str(status),
           "--vocab", VOCAB]
    if beats:
        bf = out_json.with_name(out_json.stem + "_beats.json")
        bf.write_text(json.dumps(beats), encoding="utf-8")
        cmd += ["--beats", str(bf)]
    if probs:
        cmd += ["--probs", str(probs)]
    if key:
        cmd += ["--key", key]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    t0 = time.time()
    log = out_json.with_name(out_json.stem + ".log")
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(d), **kw)
        last = 0.0
        while proc.poll() is None:
            el = time.time() - t0
            if el > timeout:
                proc.kill()
                raise RuntimeError(t("chords_model_timeout", min=max(1, int(timeout // 60))))
            if el - last >= 5:
                last = el
                _progress(t("chords_model_running", s=int(el)))
            time.sleep(0.2)
    try:
        res = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        res = None
    if proc.returncode != 0 or not isinstance(res, dict) or not isinstance(res.get("segments"), list):
        msg = ""
        try:
            msg = json.loads(status.read_text(encoding="utf-8")).get("message") or ""
        except (OSError, ValueError):
            pass
        raise RuntimeError(msg or f"exit {proc.returncode} ({log})")
    return res


def model_segments(a, srcs: list[tuple[str, str, float]], install_dir: Path | None = None,
                   timeout: float = TIMEOUT_S) -> tuple[list[dict], dict]:
    """Segments du modèle [{start, end, label (Harte), confidence}] dans le temps du stem de référence.
    srcs : chords._sources(a, items). Cache : segments par (audio, grille) ; probabilités du réseau par
    audio (un changement de grille ne relance que le décodage). Lève RuntimeError en cas d'échec."""
    from .i18n import t
    hs = harmonic_sources(srcs)
    ref = srcs[0][1] if len(srcs) == 1 else next((f for _, f, sh in srcs if abs(sh) < 1e-9), srcs[0][1])
    akey = audio_key(hs)
    beats = beats_payload(a)
    gkey = grid_key(beats)
    seg_path, probs_path = cache_paths(ref)
    c = _read_json(seg_path)
    if c and c.get("audio") == akey:
        if c.get("grid") == gkey and isinstance(c.get("segments"), list):
            return c["segments"], {"engine": ENGINE, "cached": True, "seconds": c.get("seconds")}
        if c.get("error") and time.time() - float(c.get("time") or 0) < RETRY_AFTER_S:
            raise RuntimeError(c["error"])
    t0 = time.time()
    _progress(t("chords_model_running", s=0))
    try:
        with tempfile.TemporaryDirectory(prefix="reacue_chords_") as tmp:
            audio = Path(tmp) / "harmonic.wav"
            if _probs_ok(probs_path, akey):
                audio = Path(hs[0][1])                   # probabilités en cache : l'audio n'est pas relu
            else:
                n = int((float(a.downbeats[-1]) + 2.0) * 22050)
                write_mix(hs, n, audio)
            out = run_engine(str(audio), Path(tmp) / "result.json", beats, probs_path, akey, install_dir, timeout)
    except Exception as e:
        _write_json(seg_path, {"audio": akey, "error": str(e), "time": time.time()})
        raise
    secs = round(time.time() - t0)
    _write_json(seg_path, {"audio": akey, "grid": gkey, "engine": ENGINE, "rev": MODEL_REV,
                           "segments": out["segments"], "seconds": secs})
    return out["segments"], {"engine": ENGINE, "cached": False, "seconds": secs}


def _probs_ok(path: Path, key: str) -> bool:
    try:
        import numpy as np
        with np.load(str(path), allow_pickle=False) as z:
            return str(z["key"]) == key
    except Exception:
        return False
