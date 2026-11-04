"""Paroles automatiques (composant optionnel) / Automatic lyrics (optional component).

Quand le dossier du morceau n'a pas de fichier de paroles (paroles.txt, lyrics.txt… : lyrics.find_lyrics_file),
ReaCue transcrit le stem voix avec Whisper (openai-whisper, code et poids MIT, modèle « small » ou « large-v3-turbo ») et écrit
un brouillon « paroles (auto).txt » dans le dossier du morceau et conserve les temps de Whisper dans un
fichier .timing.json adjacent. Les temps restent valides pour la même source voix et le même texte ;
les corrections manuelles restent prioritaires. Sans temps valides, le calage par ligne est utilisé.

Règles :
  - le fichier de l'utilisateur (paroles.txt…) est toujours prioritaire ; le brouillon n'est jamais écrasé : il
    n'est créé qu'une fois et l'utilisateur peut le corriger sur place (ou le renommer en paroles.txt) ;
  - une ligne = une phrase chantée (segments de Whisper, recoupés s'ils sont trop longs) ; ligne vide entre deux
    blocs séparés par un long silence ; en tête, des lignes de commentaire « # … » (ignorées par read_lyrics) ;
  - Whisper tourne dans l'environnement séparé .venv-words (reacue_transcribe.py, sous-processus) : ce module ne
    dépend pas de torch ; tout échec (absent, erreur, délai) = comportement d'avant (pas de paroles), jamais
    bloquant ; un échec ou un morceau sans chant est mémorisé (pas de nouvel essai à chaque publication).

Réglage `lyrics_auto` : "auto" (défaut : brouillon si Whisper est installé) | "off" ; variable d'environnement
REACUE_LYRICS_AUTO (prioritaire, tests). Langue : réglage `words_language` ("auto" = détectée par Whisper).
Aucun texte de paroles n'est jamais écrit ailleurs que dans le dossier du morceau de l'utilisateur.
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

from .lyrics import AUTO_NAME, lyric_dirs

ROOT = Path(__file__).resolve().parent.parent          # dossier d'installation de ReaCue
ENGINE = "whisper"
MODEL = "small"  # compatibility/default; resolve the active setting at each call
CACHE_VERSION = 3
ERROR_RETRY_S = 300  # Retry transient failures after five minutes; do not retry on every refresh.
TIMEOUT_S = 1200                 # 20 min (Mac Intel, CPU : 3 à 6 min attendues) ; au-delà : pas de paroles
SR = 16000

# nettoyage du texte de Whisper
MIN_LOGPROB = -1.2               # segment très incertain : retiré
NO_SPEECH = 0.6                  # « pas de voix » probable…
NO_SPEECH_LOGPROB = -0.7         # … et texte incertain : retiré
MIN_WORD_PROB = 0.2              # probabilité moyenne des mots sous laquelle le segment est retiré
MAX_WORDS_PER_S = 8.0            # débit impossible : texte inventé
MAX_REPEAT = 4                   # « la la la la » : au plus 4 répétitions consécutives d'un même motif
MAX_SAME_LINES = 4               # même ligne plus de 4 fois de suite : boucle de Whisper
# découpe en lignes
MAX_LINE_WORDS = 9
MAX_LINE_S = 6.5
SPLIT_GAP_S = 0.8                # silence dans un segment : nouvelle ligne
BLOCK_GAP_MIN, BLOCK_GAP_MAX = 2.5, 6.0     # ligne vide : silence de 2 mesures (bornes en secondes)

PROGRESS = None                  # callback(message) facultatif
LAST_INFO: dict = {}             # dernier passage (créé, existant, absent, erreur…) : pour l'affichage


# --------------------------------------------------------------------------- #
# Composant installé ? Réglages
# --------------------------------------------------------------------------- #
def setting() -> str:
    v = os.environ.get("REACUE_LYRICS_AUTO", "").lower()
    if v in ("auto", "off"):
        return v
    try:
        from .settings import load_settings
        v = str(load_settings().get("lyrics_auto") or "auto").lower()
    except Exception:
        v = "auto"
    return v if v in ("auto", "off") else "auto"


def model_setting() -> str:
    """Resolve on every call so a running MCP server follows profile changes."""
    override = os.environ.get("REACUE_LYRICS_MODEL", "").strip()
    if override:
        return override
    from .settings import load_settings
    value = str(load_settings().get("lyrics_model") or MODEL)
    return value if value in ("small", "large-v3-turbo") else MODEL


def _message(fr: str, en: str) -> str:
    from .i18n import get_lang
    return en if get_lang() == "en" else fr


def _words_dir(install_dir: Path | None = None) -> Path:
    return Path(os.environ.get("REACUE_WORDS_DIR") or Path(install_dir or ROOT) / "words")


def model_file(install_dir: Path | None = None, model: str | None = None) -> Path | None:
    """Poids présents (<ReaCue>/words/whisper/<modèle>.pt, ou <modèle>-hf.pt converti), sinon None."""
    d = _words_dir(install_dir) / "whisper"
    m = model or model_setting()
    for p in (d / f"{m}.pt", d / f"{m}-hf.pt"):
        try:
            if p.is_file() and p.stat().st_size > 1000:
                return p
        except OSError:
            continue
    return None


def _whisper_package(install_dir: Path | None = None) -> bool:
    venv = Path(install_dir or ROOT) / ".venv-words"
    pats = ("lib/python3*/site-packages/whisper/__init__.py", "Lib/site-packages/whisper/__init__.py")
    return any(any(venv.glob(p)) for p in pats)


def missing_reason(install_dir: Path | None = None) -> str | None:
    """None si Whisper est prêt ; sinon "venv" | "script" | "package" | "model"."""
    from . import words
    d = Path(install_dir or ROOT)
    if not words.words_python(d).exists():
        return "venv"
    if not (d / "reacue_transcribe.py").is_file():
        return "script"
    if not _whisper_package(d):
        return "package"
    if model_file(d) is None:
        return "model"
    return None


def available(install_dir: Path | None = None) -> bool:
    return missing_reason(install_dir) is None


# --------------------------------------------------------------------------- #
# Où est / où écrire le brouillon
# --------------------------------------------------------------------------- #
def is_auto_file(path) -> bool:
    return bool(path) and Path(str(path)).name.lower() == AUTO_NAME.lower()


def target_folder(files: list[str]) -> Path | None:
    """Dossier du morceau (comme la grille PDF, sheet.song_folder), s'il fait partie des dossiers où ReaCue
    (et la fenêtre REAPER) cherchent les paroles ; sinon le dossier du premier fichier."""
    from .sheet import song_folder
    dirs = lyric_dirs(files)
    sf = song_folder([str(f) for f in files or []])
    if sf is not None and sf in dirs:
        return sf
    return dirs[0] if dirs else None


def find_auto_file(files: list[str]) -> Path | None:
    for d in lyric_dirs(files):
        try:
            for f in sorted(d.iterdir()):
                if f.is_file() and f.name.lower() == AUTO_NAME.lower():
                    return f
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Nettoyage du texte de Whisper -> lignes
# --------------------------------------------------------------------------- #
_HALLU = re.compile(r"sous-?titr|amara\.org|merci d'avoir regard|merci de (?:votre|nous avoir)|"
                    r"thanks? (?:you )?for watching|abonnez-vous|subscribe|www\.|https?:|\.com\b", re.I)
_NOISE = re.compile(r"[\[(*][^\])*]*(?:musique|music|applaudissements|applause|rires|laugh|instrumental|"
                    r"silence|chant|singing|bruit|noise)[^\])*]*[\])*]", re.I)
_SYMBOLS = re.compile(r"[♪♫♬🎵🎶]+")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", t))


def clean_text(text: str) -> str:
    t = _SYMBOLS.sub(" ", str(text))
    t = _NOISE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—")
    return t


def collapse_repeats(tokens: list, key=None, max_repeat: int = MAX_REPEAT, max_n: int = 6) -> list:
    """Motifs (1 à max_n éléments) répétés plus de max_repeat fois de suite -> max_repeat fois."""
    key = key or (lambda x: _norm(x))
    k = [key(x) for x in tokens]
    out, ko = [], []
    i = 0
    while i < len(tokens):
        done = False
        for n in range(1, max_n + 1):
            pat = k[i:i + n]
            if len(pat) < n or not any(pat):
                break
            r = 1
            while k[i + r * n:i + (r + 1) * n] == pat:
                r += 1
            if r > max_repeat:
                for j in range(max_repeat * n):
                    out.append(tokens[i + j])
                    ko.append(k[i + j])
                i += r * n
                done = True
                break
        if not done:
            out.append(tokens[i])
            ko.append(k[i])
            i += 1
    return out


def _seg_words(s: dict) -> list[dict]:
    """Mots horodatés du segment (texte nettoyé) ; à défaut, mots du texte répartis sur sa durée."""
    ws = []
    for w in s.get("words") or []:
        txt = clean_text(w.get("w", ""))
        if txt:
            ws.append({"w": txt, "t": float(w.get("t", s["t"])), "end": float(w.get("end", s["end"])),
                       "p": float(w.get("p", 1.0))})
    if ws:
        return ws
    toks = clean_text(s.get("text", "")).split()
    if not toks:
        return []
    t0, t1 = float(s["t"]), max(float(s["end"]), float(s["t"]) + 0.1)
    d = (t1 - t0) / len(toks)
    return [{"w": w, "t": t0 + k * d, "end": t0 + (k + 1) * d, "p": 1.0} for k, w in enumerate(toks)]


def keep_segment(s: dict) -> bool:
    """Filtre anti-hallucination d'un segment de Whisper."""
    text = clean_text(s.get("text", ""))
    if not re.search(r"[^\W\d_]", text):
        return False
    if _HALLU.search(text):
        return False
    lp = float(s.get("avg_logprob", 0.0))
    if lp < MIN_LOGPROB:
        return False
    if float(s.get("no_speech_prob", 0.0)) > NO_SPEECH and lp < NO_SPEECH_LOGPROB:
        return False
    ws = s.get("words") or []
    if ws and sum(float(w.get("p", 1.0)) for w in ws) / len(ws) < MIN_WORD_PROB:
        return False
    dur = max(0.05, float(s["end"]) - float(s["t"]))
    if len(text.split()) / dur > MAX_WORDS_PER_S and len(text.split()) > 3:
        return False
    return True


def _split(ws: list[dict]) -> list[list[dict]]:
    """Découpe récursive d'une suite de mots en lignes chantées (silences, ponctuation, longueur)."""
    n = len(ws)
    if n <= 1:
        return [ws] if ws else []
    gaps = [ws[i]["t"] - ws[i - 1]["end"] for i in range(1, n)]
    big = [i + 1 for i, g in enumerate(gaps) if g >= SPLIT_GAP_S]
    if big:
        out, a = [], 0
        for b in big + [n]:
            out += _split(ws[a:b])
            a = b
        return out
    if n <= MAX_LINE_WORDS and ws[-1]["end"] - ws[0]["t"] <= MAX_LINE_S:
        return [ws]
    if n < 4:
        return [ws]
    best, bi = None, None
    for i in range(2, n - 1):                 # au moins 2 mots de chaque côté
        g = max(0.0, ws[i]["t"] - ws[i - 1]["end"])
        punct = 0.6 if re.search(r"[,;:.!?…]$", ws[i - 1]["w"]) else 0.0
        cap = 0.2 if ws[i]["w"][:1].isupper() else 0.0
        sc = 2.0 * g + punct + cap - 0.8 * abs(i / n - 0.5)
        if best is None or sc > best:
            best, bi = sc, i
    return _split(ws[:bi]) + _split(ws[bi:])


def _line_text(ws: list[dict]) -> str:
    t = " ".join(w["w"] for w in ws)
    t = re.sub(r"\s+([,;:.!?…])", r"\1", t)
    t = re.sub(r"[.,;:]+$", "", t).strip()
    return t[:1].upper() + t[1:] if t else t


def segments_to_lines(segments: list[dict]) -> list[dict]:
    """Segments de Whisper -> lignes [{"t", "end", "text"}] nettoyées (voir les constantes)."""
    lines = []
    for s in sorted(segments or [], key=lambda x: float(x.get("t", 0.0))):
        if not keep_segment(s):
            continue
        ws = collapse_repeats(_seg_words(s), key=lambda w: _norm(w["w"]))
        for part in _split(ws):
            txt = _line_text(part)
            if re.search(r"[^\W\d_]", txt):
                lines.append({"t": round(part[0]["t"], 3), "end": round(part[-1]["end"], 3), "text": txt})
    out, run = [], 0
    for ln in lines:                             # même ligne en boucle : au plus MAX_SAME_LINES de suite
        if out and _norm(ln["text"]) == _norm(out[-1]["text"]):
            run += 1
            if run >= MAX_SAME_LINES:
                continue
        else:
            run = 0
        out.append(ln)
    return out


def block_gap(a) -> float:
    """Silence qui sépare deux blocs : 2 mesures, entre BLOCK_GAP_MIN et BLOCK_GAP_MAX secondes."""
    try:
        db = [float(x) for x in a.downbeats]
        bar = (db[-1] - db[0]) / max(1, len(db) - 1)
    except Exception:
        bar = 2.0
    return min(BLOCK_GAP_MAX, max(BLOCK_GAP_MIN, 2 * bar))


def format_draft(lines: list[dict], gap: float = 4.0, model: str = MODEL, lang: str = "?") -> str:
    """Texte du brouillon : commentaires « # » en tête, une ligne par phrase, ligne vide entre les blocs."""
    from .i18n import t
    out = ["# " + t("lyrics_auto_header1", model=model, code=lang), "# " + t("lyrics_auto_header2"), ""]
    prev = None
    for ln in lines:
        if prev is not None and float(ln["t"]) - float(prev["end"]) > gap:
            out.append("")
        out.append(ln["text"])
        prev = ln
    return "\n".join(out).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# Lancement de Whisper (sous-processus)
# --------------------------------------------------------------------------- #
def _progress(msg: str):
    if PROGRESS:
        try:
            PROGRESS(msg)
        except Exception:
            pass


def run_engine(wav: Path, workdir: Path, lang: str = "auto", install_dir: Path | None = None,
               timeout: float = TIMEOUT_S, python: str | None = None, script: str | None = None,
               model: str | None = None) -> dict:
    """Lance reacue_transcribe.py transcribe ; renvoie le résultat (dict) ou lève RuntimeError."""
    from . import words
    from .i18n import t
    d = Path(install_dir or ROOT)
    py = python or str(words.words_python(d))
    sc = script or str(d / "reacue_transcribe.py")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out_p, status = workdir / "transcript.json", workdir / "transcribe_status.json"
    for p in (out_p, status):
        try:
            p.unlink()
        except OSError:
            pass
    cmd = [py, sc, "transcribe", "--audio", str(wav), "--out", str(out_p), "--lang", lang, "--model", model or model_setting(),
           "--status", str(status)]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    t0 = time.time()
    log = workdir / "transcribe.log"
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(d), **kw)
        last = 0.0
        while proc.poll() is None:
            el = time.time() - t0
            if el > timeout:
                proc.kill()
                raise RuntimeError(t("lyrics_auto_timeout", min=max(1, int(timeout // 60))))
            if el - last >= 5:
                last = el
                step = ""
                try:
                    step = json.loads(status.read_text(encoding="utf-8")).get("step") or ""
                except (OSError, ValueError):
                    pass
                _progress(t("lyrics_auto_running", s=int(el)) + (f" · {step}" if step else ""))
            time.sleep(0.2)
    try:
        res = json.loads(out_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        res = None
    if proc.returncode != 0 or not isinstance(res, dict) or not isinstance(res.get("segments"), list):
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


def _install_stamp(install_dir: Path | None = None) -> str:
    d = Path(install_dir or ROOT)
    out = []
    for p in (d / "reacue_transcribe.py", d / ".venv-words" / "pyvenv.cfg", model_file(d)):
        try:
            out.append(str(int(Path(p).stat().st_mtime)))
        except (OSError, TypeError):
            out.append("-")
    return ":".join(out)


def memo_key(a, items: list[dict] | None, lang: str, install_dir: Path | None = None) -> str:
    from .lyrics import _voice_source
    src = _voice_source(a, items)
    h = hashlib.sha1(f"{ENGINE}:{model_setting()}:{CACHE_VERSION}:{lang}:{_install_stamp(install_dir)}".encode())
    import reacue_performance
    if reacue_performance.profile() == "fast":
        h.update(b":fast")
    if src:
        p = Path(src[0])
        try:
            st = p.stat()
            h.update(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{float(src[1]):.6f}".encode())
        except OSError:
            h.update(f"{p}|missing".encode())
    return h.hexdigest()


def _memo_read(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _memo_write(path: Path | None, key: str, value: dict):
    if not path:
        return
    d = _memo_read(path)
    d[key] = value
    if len(d) > 100:                                    # les plus anciens d'abord (ordre d'insertion)
        d = dict(list(d.items())[-100:])
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(path).with_name(Path(path).name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def write_draft(folder: Path, text: str) -> Path | None:
    """Crée le brouillon ; ne remplace jamais un fichier existant (None s'il existe déjà)."""
    p = Path(folder) / AUTO_NAME
    try:
        with open(p, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except FileExistsError:
        return None
    return p



def timing_path(path):
    return Path(path).with_suffix(".timing.json")


def source_stamp(a, items):
    from .lyrics import _voice_source
    src = _voice_source(a, items)
    if not src:
        return None
    p = Path(src[0])
    st = p.stat()
    return [str(p.resolve()), st.st_size, st.st_mtime_ns, round(float(src[1]), 6)]


def read_timing(path):
    try:
        data = json.loads(timing_path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_timing(a, items, path, lines, model=None, language="auto", key=None):
    from .lyrics import read_lyrics
    texts = [x["text"] for x in read_lyrics(path)]
    matches = [_norm(x) for x in texts] == [_norm(x["text"]) for x in lines]
    data = {"version": 2, "source": source_stamp(a, items), "texts": texts,
            "lines": lines if matches else [], "matched": matches,
            "model": model or model_setting(), "language": language, "key": key}
    target = timing_path(path)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


def timed_draft(a, items, path, lines):
    """Use Whisper times only for unchanged text and the same placed vocal source."""
    from .lyrics import _entry
    data = read_timing(path)
    try:
        if data.get("source") != source_stamp(a, items):
            return None
        if data.get("texts") != [x["text"] for x in lines]:
            return None
        timed = data.get("lines") or []
        if len(timed) != len(lines) or any(x.get("repeat", 1) != 1 for x in lines):
            return None
        out, last = [], -1.0
        for line, row in zip(lines, timed):
            t0, t1 = float(row["t"]), float(row["end"])
            if not (math.isfinite(t0) and math.isfinite(t1) and 0 <= t0 < t1 and t0 >= last):
                return None
            if _norm(line["text"]) != _norm(row["text"]):
                return None
            entry = _entry(a, line, t0, t1, 1, conf=0.5)
            entry["timing_source"] = "whisper"
            out.append(entry)
            last = t0
        return out or None
    except (OSError, TypeError, ValueError, KeyError):
        return None


def ensure_auto_lyrics(a, items: list[dict] | None, files: list[str] | None = None, cache=None,
                       install_dir: Path | None = None) -> Path | None:
    """Brouillon de paroles du morceau : existant, ou créé par Whisper si possible ; None sinon.
    À n'appeler que s'il n'y a pas de fichier de paroles de l'utilisateur. Ne lève jamais d'exception."""
    from .i18n import t
    LAST_INFO.clear()
    have = None
    try:
        from . import words
        selected = model_setting()
        lang = words.language_setting()
        LAST_INFO["selected_model"] = selected
        if files is None:
            files = [d["file"] for d in items] if items else [a.file] + list((a.stems or {}).values())
        have = find_auto_file(files)
        if have:
            timing = read_timing(have)
            previous = timing.get("model")
            if not previous:
                # Old drafts identify their generator in the comment header, if available.
                header = "\n".join(x for x in have.read_text(encoding="utf-8-sig").splitlines()[:5]
                                   if x.startswith("#"))
                match = re.search(r"\bWhisper\s+([\w.-]+)", header)
                previous = match.group(1) if match else None
            different = (previous and previous != selected) or (
                lang != "auto" and timing.get("language") not in (None, "auto", lang))
            if different or timing.get("source") == source_stamp(a, items):
                LAST_INFO.update({"state": "existing", "file": str(have), "model": previous})
                if different or not previous:
                    old = previous or "?"
                    warning = _message(
                        f"Brouillon existant conservé (Whisper {old}, langue {timing.get('language', '?')}) ; "
                        f"modèle demandé : {selected}, langue {lang}. Pour une nouvelle transcription, "
                        "sauvegardez le brouillon hors du dossier du morceau, retirez « paroles (auto).txt », "
                        "puis republiez. Un fichier paroles.txt personnel reste prioritaire.",
                        f"Existing draft kept (Whisper {old}, language {timing.get('language', '?')}); "
                        f"requested model: {selected}, language {lang}. To transcribe again, back up the draft "
                        "outside the song folder, remove 'paroles (auto).txt', then republish. "
                        "A personal lyrics.txt file keeps priority.")
                    LAST_INFO.update({"warning": warning, "message": warning})
                return have
        if setting() != "auto":
            LAST_INFO["state"] = "off"
            return have
        why = missing_reason(install_dir)
        if why:
            message = _message(
                f"Whisper {selected} indisponible ({why}) : lancez Install ReaCue Words pour installer "
                "le modèle sélectionné. Aucun téléchargement pendant la préparation.",
                f"Whisper {selected} unavailable ({why}): run Install ReaCue Words to install "
                "the selected model. Preparation never downloads models.")
            LAST_INFO.update({"state": "missing", "missing": why, "model": selected,
                              "message": message, "warning": message})
            return have
        from .lyrics import _voice_source
        if not _voice_source(a, items):
            LAST_INFO.update({"state": "no_voice"})
            return have
        folder = have.parent if have else target_folder(files)
        if folder is None or not folder.is_dir():
            LAST_INFO.update({"state": "no_folder"})
            return have
        if cache is None:
            cache = folder / ".reacue" / "lyrics_auto.json"
        key = memo_key(a, items, lang, install_dir)
        memo = _memo_read(cache).get(key)
        if memo and memo.get("state") != "success" and (memo.get("state") != "error" or
                     time.time() - float(memo.get("failed_at", 0)) < ERROR_RETRY_S):
            LAST_INFO.update({"state": memo.get("state", "error"), **memo, "cached": True})
            return have
        t0 = time.time()
        cached = bool(memo and memo.get("state") == "success" and isinstance(memo.get("result"), dict))
        if cached:
            res = memo["result"]
        else:
            _progress(t("lyrics_auto_running", s=0))
            with tempfile.TemporaryDirectory(prefix="reacue_whisper_") as tmp:
                wav = words.write_voice(a, items, Path(tmp) / "voice16k.wav")
                try:
                    res = run_engine(wav, Path(tmp), lang, install_dir, model=selected)
                except Exception as e:
                    _memo_write(cache, key, {"state": "error", "error": str(e), "failed_at": time.time()})
                    raise
        lines = segments_to_lines(res.get("segments") or [])
        info = {"lang": res.get("language") or lang, "lines": len(lines),
                "words": sum(len(x["text"].split()) for x in lines), "seconds": round(time.time() - t0, 1),
                "model": res.get("model") or selected, "cached": cached}
        if not lines:
            _memo_write(cache, key, {"state": "empty", **info})
            LAST_INFO.update({"state": "empty", **info, "message": t("lyrics_auto_empty")})
            return have
        if not cached:
            _memo_write(cache, key, {"state": "success", "result": res})
        text = format_draft(lines, block_gap(a), info["model"], info["lang"])
        p = have or write_draft(folder, text)
        if p is None:                                    # créé entre-temps : on garde celui-là
            p = folder / AUTO_NAME
        try:
            save_timing(a, items, p, lines, model=info["model"], language=info["lang"], key=key)
        except (OSError, ValueError):
            pass  # Preserve the draft if a read-only folder prevents storing timing.
        LAST_INFO.update({"state": "existing" if have else "created", "file": str(p), **info,
                          "message": t("lyrics_auto_created", name=AUTO_NAME, n=info["lines"], code=info["lang"])})
        return p
    except Exception as e:                               # noqa: BLE001 - pas de paroles, comme avant
        LAST_INFO.update({"state": "error", "error": str(e), "message": t("lyrics_auto_failed", e=e)})
        return have
