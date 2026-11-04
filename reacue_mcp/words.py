"""Paroles calées mot par mot (composant optionnel) / Word-by-word lyrics timing (optional component).

Le calage par ligne de lyrics.py (librosa / numpy) reste l'ancrage : il dit où chaque ligne est chantée (reprises,
chœurs, lignes non chantées compris). Ce module place ensuite les MOTS à l'intérieur de chaque ligne par
alignement forcé CTC (wav2vec2 XLSR-53 affiné en français ou en anglais, Apache-2.0) sur le stem voix. Le modèle
tourne dans l'environnement séparé .venv-words (installé par install/install_words_*), jamais dans le .venv de
ReaCue : ce module ne dépend pas de torch, il lance `reacue_words.py` en sous-processus et lit son résultat
(avec cache).

Résultat : chaque entrée de paroles reçoit un champ facultatif `words: [{"w", "t", "end"}]` (temps du fichier
de référence, comme "t" / "end" de la ligne) ; la concaténation des "w" (séparés par une espace) redonne le texte
de la ligne. Une ligne non calée automatiquement (ancre exacte de paroles_calage.json) garde son début et sa fin ;
sinon ils sont resserrés sur le premier et le dernier mot.

Réglages : `words_engine` "off" (défaut : lignes seules) | "auto" (mot par mot si installé) ;
`words_language` "auto" (déduite du texte) | "fr" | "en". Variables d'environnement REACUE_WORDS_ENGINE et
REACUE_WORDS_LANG (prioritaires, tests). Tout échec garde le calage par ligne : jamais bloquant.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # dossier d'installation de ReaCue
ENGINE = "wav2vec2-ctc"
MODELS = {                                             # mêmes valeurs que reacue_words.py
    "fr": "jonatasgrosman/wav2vec2-large-xlsr-53-french",
    "en": "jonatasgrosman/wav2vec2-large-xlsr-53-english",
}
CACHE_VERSION = 2
RETRY_AFTER_S = 300
TIMEOUT_S = 900                  # 15 min (CPU lent, 1er lancement) ; au-delà, paroles par ligne
SR = 16000
PAD_MIN, PAD_MAX = 0.15, 0.8     # marge (s) autour de chaque ligne : moitié de l'écart avec la voisine
MIN_LINE_SCORE = 0.12            # probabilité moyenne des lettres sous laquelle les mots sont ignorés
MAX_SHIFT_S = 1.0                # resserrement de la ligne sur ses mots : au plus 1 s de chaque côté

PROGRESS = None                  # callback(message) facultatif
LAST_INFO: dict = {}             # dernier passage (moteur, langue, lignes calées, erreur…) : pour l'affichage


# --------------------------------------------------------------------------- #
# Composant installé ? Réglages
# --------------------------------------------------------------------------- #
def words_python(install_dir: Path | None = None, windows: bool | None = None) -> Path:
    d = Path(install_dir or ROOT)
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        return d / ".venv-words" / "Scripts" / "python.exe"
    return d / ".venv-words" / "bin" / "python"


def available(install_dir: Path | None = None) -> bool:
    d = Path(install_dir or ROOT)
    return words_python(d).exists() and (d / "reacue_words.py").is_file()


def _setting(key: str, env: str, allowed: tuple, default: str) -> str:
    v = os.environ.get(env, "").lower()
    if v in allowed:
        return v
    try:
        from .settings import load_settings
        v = str(load_settings().get(key) or default).lower()
    except Exception:
        v = default
    return v if v in allowed else default


def engine_setting() -> str:
    return _setting("words_engine", "REACUE_WORDS_ENGINE", ("auto", "off"), "off")


def language_setting() -> str:
    return _setting("words_language", "REACUE_WORDS_LANG", ("auto", "fr", "en"), "auto")


# --------------------------------------------------------------------------- #
# Langue chantée, déduite du texte
# --------------------------------------------------------------------------- #
_FR = set("""le la les un une des du de et est je tu il elle nous vous ils elles que qui quoi pas ne mon ma mes ton
ta tes sa ses dans pour sur avec au aux ce cette ces c'est j'ai suis sont tout tous toute comme mais ou où plus
moi toi lui leur leurs y en encore jamais toujours rien quand alors été être avoir fait cœur coeur nuit jour
amour vie ciel très bien sans entre vers chez notre votre nos vos aussi même là oui non""".split())
_EN = set("""the and is are was were i you he she we they them that this these those to of in for with my your
his her our their me him it its be been being not no all what when where why how love heart night day life
never always nothing just don't can't won't i'm you're it's there here from have has had do does did will would
could should baby oh yeah into out up down so but or if like know want feel one only time way away""".split())
_FR_CHARS = set("éèêëàâçîïôûùœ")


def detect_language(texts: list[str]) -> str:
    """« fr » ou « en » selon les mots outils et les lettres accentuées (français par défaut)."""
    fr = en = 0.0
    for t in texts:
        low = unicodedata.normalize("NFC", str(t)).lower().replace("’", "'")
        for w in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", low):
            if w in _FR or w.split("'")[0] + "'" in ("j'", "l'", "d'", "qu'", "n'", "s'", "m'", "t'", "c'"):
                fr += 1
            if w in _EN:
                en += 1
        fr += 0.5 * sum(1 for c in low if c in _FR_CHARS)
    return "en" if en > fr else "fr"


def song_language(lyrics: list[dict]) -> str:
    v = language_setting()
    return v if v in MODELS else detect_language([o.get("text", "") for o in lyrics or []])


# --------------------------------------------------------------------------- #
# Fenêtres d'alignement (une par ligne calée)
# --------------------------------------------------------------------------- #
def make_jobs(lyrics: list[dict]) -> list[dict]:
    """[{"id": index dans lyrics, "t0", "t1", "text"}] : chaque ligne avec une marge égale à la moitié de
    l'écart avec ses voisines (entre PAD_MIN et PAD_MAX)."""
    order = sorted(range(len(lyrics)), key=lambda i: float(lyrics[i]["t"]))
    jobs = []
    for n, i in enumerate(order):
        o = lyrics[i]
        t, e = float(o["t"]), float(o.get("end", o["t"]))
        if not str(o.get("text") or "").strip() or e <= t:
            continue
        prev_e = float(lyrics[order[n - 1]].get("end", 0.0)) if n else t - 2 * PAD_MAX
        next_t = float(lyrics[order[n + 1]]["t"]) if n + 1 < len(order) else e + 2 * PAD_MAX
        pb = min(PAD_MAX, max(PAD_MIN, (t - prev_e) / 2))
        pa = min(PAD_MAX, max(PAD_MIN, (next_t - e) / 2))
        jobs.append({"id": i, "t0": round(max(0.0, t - pb), 3), "t1": round(e + pa, 3), "text": o["text"]})
    return jobs


# --------------------------------------------------------------------------- #
# Fusion du résultat dans les paroles
# --------------------------------------------------------------------------- #
def merge(a, lyrics: list[dict], result: dict, min_score: float | None = None) -> tuple[list[dict], int]:
    """Ajoute "words" aux lignes bien alignées (copie) ; resserre début / fin des lignes non ancrées.
    Renvoie (paroles, nombre de lignes calées mot par mot)."""
    from .lyrics import _bar_pos
    min_score = MIN_LINE_SCORE if min_score is None else min_score
    by_id = {}
    for ln in (result or {}).get("lines") or []:
        if isinstance(ln, dict) and "id" in ln:
            by_id[ln["id"]] = ln
    out, n_ok = [], 0
    for i, o in enumerate(lyrics):
        o = dict(o)
        r = by_id.get(i)
        ws = r.get("words") if r else None
        if (not ws or r.get("error") or float(r.get("score", 0.0)) < min_score
                or " ".join(w.get("w", "") for w in ws).split() != str(o.get("text", "")).split()):
            o.pop("words", None)
            out.append(o)
            continue
        words, last = [], None
        for w in ws:
            t0 = float(w["t"])
            t1 = max(float(w.get("end", t0)), t0 + 0.02)
            if last is not None and t0 < last:
                t0 = last
                t1 = max(t1, t0 + 0.02)
            words.append({"w": w["w"], "t": round(t0, 3), "end": round(t1, 3)})
            last = t1
        o["words"] = words
        if not o.get("anchored"):
            t0 = max(words[0]["t"], float(o["t"]) - MAX_SHIFT_S)
            t1 = min(words[-1]["end"], float(o["end"]) + MAX_SHIFT_S)
            if t1 > t0 + 0.1:
                o["t"], o["end"] = round(t0, 3), round(t1, 3)
                o["bar"], o["beat"], o["pos"] = _bar_pos(a, t0)
                o["end_bar"], _, o["end_pos"] = _bar_pos(a, t1)
        out.append(o)
        n_ok += 1
    out.sort(key=lambda x: float(x["t"]))
    return out, n_ok


# --------------------------------------------------------------------------- #
# Lancement du modèle (sous-processus) avec cache
# --------------------------------------------------------------------------- #
def _progress(msg: str):
    if PROGRESS:
        try:
            PROGRESS(msg)
        except Exception:
            pass


def run_engine(wav: Path, jobs: list[dict], lang: str, workdir: Path, install_dir: Path | None = None,
               timeout: float = TIMEOUT_S, python: str | None = None, script: str | None = None) -> dict:
    """Lance reacue_words.py align ; renvoie le résultat (dict) ou lève RuntimeError."""
    from .i18n import t
    d = Path(install_dir or ROOT)
    py = python or str(words_python(d))
    sc = script or str(d / "reacue_words.py")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    jobs_p, out_p, status = workdir / "jobs.json", workdir / "words.json", workdir / "words_status.json"
    jobs_p.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    for p in (out_p, status):
        try:
            p.unlink()
        except OSError:
            pass
    cmd = [py, sc, "align", "--audio", str(wav), "--jobs", str(jobs_p), "--out", str(out_p), "--lang", lang,
           "--status", str(status)]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    t0 = time.time()
    log = workdir / "words.log"
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(d), **kw)
        last = 0.0
        while proc.poll() is None:
            el = time.time() - t0
            if el > timeout:
                proc.kill()
                proc.wait()
                raise RuntimeError(t("words_timeout", min=max(1, int(timeout // 60))))
            if el - last >= 5:
                last = el
                step = ""
                try:
                    step = json.loads(status.read_text(encoding="utf-8")).get("step") or ""
                except (OSError, ValueError):
                    pass
                _progress(t("words_running", s=int(el)) + (f" · {step}" if step else ""))
            time.sleep(0.2)
    try:
        res = json.loads(out_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        res = None
    if proc.returncode != 0 or not isinstance(res, dict) or not isinstance(res.get("lines"), list):
        msg = ""
        try:
            msg = json.loads(status.read_text(encoding="utf-8")).get("message") or ""
        except (OSError, ValueError):
            pass
        if not msg:
            try:
                msg = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1][:300]
            except (OSError, IndexError):
                msg = ""
        raise RuntimeError(msg or f"exit {proc.returncode}")
    return res


def write_voice(a, items: list[dict] | None, wav: Path) -> Path:
    """Stem voix placé dans le temps du fichier de référence (comme lyrics.align_lyrics) -> WAV 16 kHz mono."""
    import librosa
    import soundfile as sf
    from .analysis import _place
    from .lyrics import _voice_source
    from .i18n import t
    src = _voice_source(a, items)
    if not src:
        raise ValueError(t("no_voice_stem"))
    y = librosa.load(src[0], sr=SR, mono=True)[0]
    n = int((float(a.downbeats[-1]) + 2.0) * SR)
    y = _place(y, src[1], SR, max(n, len(y) + max(0, int(round(src[1] * SR)))))
    wav = Path(wav)
    wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav), y, SR, subtype="PCM_16")
    return wav


def _install_stamp(install_dir: Path | None = None) -> str:
    """Date du script et de l'environnement : une réinstallation invalide le cache (échecs compris)."""
    d = Path(install_dir or ROOT)
    out = []
    for p in (d / "reacue_words.py", d / ".venv-words" / "pyvenv.cfg"):
        try:
            out.append(str(p.stat().st_mtime_ns))
        except OSError:
            out.append("-")
    return ":".join(out)


def cache_key(a, items: list[dict] | None, jobs: list[dict], lang: str, install_dir: Path | None = None) -> str:
    from .lyrics import _voice_source
    src = _voice_source(a, items)
    h = hashlib.sha1()
    h.update(f"{ENGINE}:{MODELS.get(lang)}:{CACHE_VERSION}:{lang}:{_install_stamp(install_dir)}".encode())
    if src:
        p = Path(src[0])
        try:
            st = p.stat()
            h.update(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{round(src[1], 4)}".encode())
        except OSError:
            h.update(f"{p}|missing".encode())
    h.update(json.dumps(jobs, ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()


def _line_paths(a, items, jobs, lang, install_dir, cache):
    """Cache par source et phrase : un autre morceau n'évince pas les lignes déjà alignées."""
    if cache is None:
        return {}
    base = cache_key(a, items, [], lang, install_dir)
    folder = Path(cache).parent / "word_lines" / base
    paths = {}
    for job in jobs:
        # L'identifiant est une position d'affichage ; l'audio, le texte et la
        # fenêtre de normalisation définissent le résultat acoustique.
        data = {k: v for k, v in job.items() if k != "id"}
        key = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        paths[job["id"]] = folder / (key + ".json")
    return paths


def _valid_cached_line(line):
    """Reject truncated cache records; transient per-line errors expire as well."""
    if not isinstance(line, dict):
        return False
    try:
        if line.get("error"):
            return float(line.get("retry_at", 0)) > time.time()
        if not math.isfinite(float(line.get("score", 0))):
            return False
        ws = line.get("words")
        return isinstance(ws, list) and all(
            isinstance(w, dict) and isinstance(w.get("w"), str)
            and math.isfinite(float(w["t"])) and math.isfinite(float(w["end"]))
            and float(w["end"]) >= float(w["t"]) for w in ws)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def add_words(a, items: list[dict] | None, lyrics: list[dict] | None, cache=None,
              install_dir: Path | None = None, engine: str | None = None) -> list[dict] | None:
    """Paroles calées par ligne -> mêmes paroles avec "words" (si le composant est installé et réussit).
    Ne lève jamais d'exception : en cas d'échec, les paroles sont rendues telles quelles (LAST_INFO["error"])."""
    from .i18n import t
    LAST_INFO.clear()
    LAST_INFO["engine"] = "lines"
    if not lyrics:
        return lyrics
    engine = engine or engine_setting()
    if engine != "auto":
        return lyrics
    if not available(install_dir):
        LAST_INFO["missing"] = True
        return lyrics
    try:
        lang = song_language(lyrics)
        jobs = make_jobs(lyrics)
        if not jobs:
            return lyrics
        key = cache_key(a, items, jobs, lang, install_dir)
        cpath = Path(cache) if cache else None
        res = None
        if cpath:
            try:
                c = json.loads(cpath.read_text(encoding="utf-8"))
                if isinstance(c, dict) and c.get("key") == key:
                    if c.get("error") and time.time() - float(c.get("at", 0)) < RETRY_AFTER_S:
                        raise RuntimeError(c["error"])
                    candidate = c.get("result")
                    if (isinstance(candidate, dict) and isinstance(candidate.get("lines"), list)
                            and {line.get("id") for line in candidate["lines"] if isinstance(line, dict)} == {j["id"] for j in jobs}
                            and all(_valid_cached_line(line) for line in candidate["lines"])):
                        res = candidate
            except (OSError, ValueError, TypeError):
                pass
        cached = res is not None
        if res is None:
            paths = _line_paths(a, items, jobs, lang, install_dir, cpath)
            reused, pending = [], []
            for job in jobs:
                try:
                    line = json.loads(paths[job["id"]].read_text(encoding="utf-8"))
                    if not _valid_cached_line(line):
                        raise ValueError("invalid cached line")
                    reused.append(dict(line, id=job["id"]))
                except (KeyError, OSError, ValueError):
                    pending.append(job)
            res = {"engine": ENGINE, "lang": lang, "lines": []}
            if pending:
                _progress(t("words_running", s=0))
                with tempfile.TemporaryDirectory(prefix="reacue_words_") as tmp:
                    wav = write_voice(a, items, Path(tmp) / "voice16k.wav")
                    try:
                        res = run_engine(wav, pending, lang, Path(tmp), install_dir)
                    except Exception as e:
                        if cpath:
                            _write_cache(cpath, {"key": key, "error": str(e), "at": time.time()})
                        raise
                by_id = {line.get("id"): line for line in res.get("lines", []) if isinstance(line, dict)}
                fresh = []
                for job in pending:
                    line = by_id.get(job["id"])
                    if not _valid_cached_line(line):
                        line = {"id": job["id"], "error": (line or {}).get("error") or "Invalid alignment result",
                                "retry_at": time.time() + RETRY_AFTER_S}
                    fresh.append(line)
                res["lines"] = fresh
                for line in res["lines"]:
                    if line["id"] in paths:
                        _write_cache(paths[line["id"]], line)
            cached = not pending
            res["lines"] = reused + res["lines"]
            LAST_INFO["reused_lines"] = len(reused)
            if cpath:
                _write_cache(cpath, {"key": key, "result": res})
        out, n = merge(a, lyrics, res)
        LAST_INFO.update({"engine": ENGINE, "lang": lang, "lines": n, "total": len(lyrics), "cached": cached,
                          "seconds": res.get("seconds"),
                          "message": t("words_used", n=n, total=len(lyrics), model=lang)})
        return out
    except Exception as e:                                   # noqa: BLE001 - le calage par ligne reste
        LAST_INFO.update({"engine": "lines", "error": str(e), "message": t("words_failed", e=e)})
        return lyrics


def _write_cache(path: Path, data: dict):
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
