"""Mode concert : plusieurs morceaux déjà préparés, enchaînés dans UN projet REAPER.

    build_concert("Concert test", ["Demo Song", "Another Song", "third song"])

Chaque morceau est repris de son propre projet .RPP (lecture seule, rien n'est réanalysé) : stems,
carte de tempo, régions (structure validée), marqueurs « → Section », pistes CUES / VOIX / CLICK.
Le concert est écrit dans le dossier des concerts (réglage `concert_dir`, défaut
<Documents>/REAPER Media/Concerts) :

    <nom>.RPP              le projet (une piste par instrument, une couleur par morceau)
    <nom>.setlist.json     l'ordre des morceaux (réutilisable pour reconstruire)
    <nom>.concert.lua      les temps de chaque morceau, lus par l'action « ReaCue - Concert »
    <nom>.prompteur.json   le prompteur des musiciens pour tout le concert

    grandMA3/<nom>/        export lumière (lighting.py) : une Sequence par morceau, un Timecode, la conduite

Entre deux morceaux : un blanc d'un nombre entier de mesures (la grille reste juste) ; l'action
« ReaCue - Concert » arrête la lecture à la fin de chaque morceau et place le curseur au début du
suivant : Espace relance. Réglages du placement : `gma3_song_gap` (blanc minimum, remplace celui de la
setlist) et `gma3_song_slot` (créneau rond : chaque morceau démarre au prochain multiple, le blanc est
rallongé d'un nombre entier de mesures à un tempo ajusté). Le placement réel est écrit dans le projet,
le .concert.lua, le prompteur et le timecode grandMA3 : tout coïncide.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import zlib
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import Analysis, Section, assign_roles, classify_stem, reference_index
from .bridge import BRIDGE_DIR, to_lua
from .i18n import get_lang, t as _t

GENERATED = ("CLICK", "CUES", "VOIX", "VOICE", "TIMECODE LTC", "TIMECODE MTC")  # timecode : recréé, jamais copié


def documents_dir() -> Path:
    """Dossier Documents de l'utilisateur (macOS, Windows, Linux)."""
    if os.name == "nt" and os.environ.get("USERPROFILE"):
        return Path(os.environ["USERPROFILE"]) / "Documents"
    return Path.home() / "Documents"


def _setting(key: str):
    try:
        from .settings import load_settings
        v = load_settings().get(key)
    except Exception:
        v = None
    return Path(str(v)).expanduser() if v else None


def media_dir() -> Path:
    """Dossier des projets des morceaux (recherche par nom) : réglage `projects_dir`,
    variable REACUE_MEDIA_DIR, sinon <Documents>/REAPER Media."""
    env = os.environ.get("REACUE_MEDIA_DIR")
    return (_setting("projects_dir") or (Path(env).expanduser() if env else None)
            or documents_dir() / "REAPER Media")


def concert_dir() -> Path:
    """Dossier des concerts : réglage `concert_dir`, sinon <dossier des projets>/Concerts."""
    return _setting("concert_dir") or media_dir() / "Concerts"

MAX_TAIL = 8.0            # secondes d'audio gardées après la dernière mesure (résonance, larsen…)

# pistes communes du concert : (rôle, nom FR, nom EN, couleur RVB) dans l'ordre d'affichage
ROLE_TRACKS_I18N = [
    ("vocals", "Chant", "Vocals", (212, 83, 126)),
    ("drums", "Batterie", "Drums", (186, 117, 23)),
    ("bass", "Basse", "Bass", (24, 95, 165)),
    ("guitars", "Guitares", "Guitars", (99, 153, 34)),
    ("lead_guitar", "Guitare solo", "Lead guitar", (15, 110, 86)),
    ("keys", "Claviers", "Keys", (127, 119, 221)),
    ("other", "Autres", "Other", (136, 135, 128)),
    ("mix", "Mix", "Mix", (95, 94, 90)),
]


def role_tracks(lang: str | None = None) -> list[tuple]:
    """(rôle, nom de piste, couleur) dans la langue des réglages."""
    en = (lang or get_lang()) == "en"
    return [(r, e if en else f, c) for r, f, e, c in ROLE_TRACKS_I18N]


ROLE_TRACKS = role_tracks("fr")
TRACK_NAME = {r: n for r, n, _ in ROLE_TRACKS}
# une couleur par morceau (items audio), distinctes des couleurs de sections
SONG_COLORS = [(127, 119, 221), (29, 158, 117), (216, 90, 48), (212, 83, 126), (186, 117, 23),
               (55, 138, 221), (99, 153, 34), (136, 135, 128)]
KEYS_WORDS = ("piano", "keys", "key ", "clavier", "synth", "orgue", "organ", "rhodes")


# --------------------------------------------------------------------------- #
# Lecture / écriture du format RPP (texte, blocs < … >)
# --------------------------------------------------------------------------- #
class Node:
    __slots__ = ("header", "children")

    def __init__(self, header: str, children=None):
        self.header = header                  # ligne d'ouverture sans le « < »
        self.children: list = children if children is not None else []

    @property
    def tag(self) -> str:
        return self.header.split(" ", 1)[0]

    def lines(self, tag: str) -> list[str]:
        return [c for c in self.children if isinstance(c, str) and (c == tag or c.startswith(tag + " "))]

    def first(self, tag: str) -> str | None:
        L = self.lines(tag)
        return L[0] if L else None

    def blocks(self, tag: str) -> list["Node"]:
        return [c for c in self.children if isinstance(c, Node) and c.tag == tag]

    def set_line(self, tag: str, value: str):
        for i, c in enumerate(self.children):
            if isinstance(c, str) and (c == tag or c.startswith(tag + " ")):
                self.children[i] = value
                return
        self.children.insert(0, value)

    def drop(self, tag: str):
        self.children = [c for c in self.children
                         if not (isinstance(c, str) and (c == tag or c.startswith(tag + " ")))]

    def copy(self) -> "Node":
        return Node(self.header, [c.copy() if isinstance(c, Node) else c for c in self.children])


def parse_rpp(text: str) -> Node:
    root, stack = None, []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("<"):
            n = Node(s[1:])
            if stack:
                stack[-1].children.append(n)
            else:
                root = n
            stack.append(n)
        elif s == ">":
            if stack:
                stack.pop()
        elif stack:
            stack[-1].children.append(s)
    if root is None:
        raise ValueError(_t("concert_rpp_unreadable"))
    return root


def dump_rpp(node: Node, indent: int = 0) -> str:
    pad = "  " * indent
    out = [f"{pad}<{node.header}"]
    for c in node.children:
        if isinstance(c, Node):
            out.append(dump_rpp(c, indent + 1))
        else:
            out.append(f"{pad}  {c}")
    out.append(f"{pad}>")
    return "\n".join(out)


def tokens(line: str) -> list[str]:
    """Découpe une ligne RPP (chaînes entre "…", '…' ou `…`)."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c.isspace():
            i += 1
            continue
        if c in "\"'`":
            j = line.find(c, i + 1)
            j = n if j < 0 else j
            out.append(line[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and not line[j].isspace():
                j += 1
            out.append(line[i:j])
            i = j
    return out


def q(s: str) -> str:
    """Chaîne RPP entre guillemets (choisit un délimiteur absent du texte)."""
    s = str(s)
    if s and not any(ch.isspace() for ch in s) and not any(ch in s for ch in "\"'`"):
        return s
    for d in ('"', "'", "`"):
        if d not in s:
            return f"{d}{s}{d}"
    return '"' + s.replace('"', "'") + '"'


def guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


def native_color(rgb) -> int:
    """Couleur REAPER (macOS : 0xRRGGBB) avec le drapeau « couleur personnalisée »."""
    r, g, b = (int(x) for x in rgb)
    if os.name == "nt":
        return (b << 16 | g << 8 | r) | 0x1000000
    return (r << 16 | g << 8 | b) | 0x1000000


# --------------------------------------------------------------------------- #
# Un morceau lu dans son projet
# --------------------------------------------------------------------------- #
@dataclass
class SongSrc:
    path: Path
    title: str
    audio: list[dict] = field(default_factory=list)      # {node, track, vol, mute, file, position, length, offset, rate, guid, role}
    gen: dict = field(default_factory=dict)                # nom de piste générée -> (en-tête Node, [items Node])
    pts: list[list[str]] = field(default_factory=list)     # lignes PT (jetons)
    regions: list[dict] = field(default_factory=list)      # {start, end, name, color}
    markers: list[dict] = field(default_factory=list)      # {pos, name, color}
    bar_lines: list[float] = field(default_factory=list)   # temps des barres de mesure (timeline du morceau)
    i0: int = 0                                            # index de la mesure 1 dans bar_lines
    ci: int = 0                                            # mesures de count-in
    n_bars: int = 0
    sections: list[Section] = field(default_factory=list)
    beats_per_bar: int = 4
    denominator: int = 4
    stop: float = 0.0                                      # fin de l'audio gardé (timeline du morceau)
    next_start: float = 0.0                                # début du morceau suivant (barre de mesure)
    warnings: list[str] = field(default_factory=list)

    @property
    def bar1(self) -> float:
        return self.bar_lines[self.i0]

    @property
    def song_end(self) -> float:
        return self.bar_lines[self.i0 + self.n_bars]

    @property
    def count_in_pos(self) -> float:
        return self.bar_lines[self.i0 - self.ci]

    @property
    def bpm(self) -> float:
        return float(self.pts[0][2]) if self.pts else 120.0

    @property
    def beatmap(self) -> bool:
        """Tempo variable (un marqueur par mesure) dans le morceau."""
        return len({round(float(p[2]), 3) for p in self.pts if float(p[1]) < self.song_end - 1e-3}) > 1


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _title_from(path: Path) -> str:
    t = re.sub(r"[-_ ]?consolidated$", "", path.stem, flags=re.I).strip()
    return t[:1].upper() + t[1:]


def find_project(name: str, search: list[Path] | None = None) -> Path:
    """Chemin d'un projet .RPP à partir d'un chemin ou d'un nom (« Demo Song », « another song »)."""
    p = Path(str(name)).expanduser()
    if p.suffix.lower() == ".rpp" and p.exists():
        return p.resolve()
    if p.exists() and p.is_file():
        return p.resolve()
    want = _norm(Path(str(name)).stem if str(name).lower().endswith(".rpp") else name)
    roots = search or [media_dir(), documents_dir()]
    cdir = concert_dir()
    cands = []
    for r in roots:
        if not r.exists():
            continue
        for depth_glob in ("*.RPP", "*.rpp", "*/*.RPP", "*/*.rpp"):
            for f in r.glob(depth_glob):
                if cdir in f.parents or "backup" in str(f).lower():
                    continue
                if _norm(f.stem) == want and f.resolve() not in cands:
                    cands.append(f.resolve())
    if not cands:
        for r in roots:
            if not r.exists():
                continue
            for f in list(r.glob("*.RPP")) + list(r.glob("*.rpp")):
                if want and want in _norm(f.stem) and f.resolve() not in cands:
                    cands.append(f.resolve())
    if not cands:
        raise FileNotFoundError(_t("concert_project_missing", name=name, dirs=", ".join(str(r) for r in roots)))
    # préférence : dossier des projets, puis non consolidé
    md = media_dir()
    cands.sort(key=lambda f: (md not in f.parents, "consolidated" in f.stem.lower(), len(str(f))))
    return cands[0]


def _role(file: str, n_audio: int) -> str:
    r = classify_stem(file)
    if r == "other":
        low = Path(file).stem.lower()
        if any(w in low for w in KEYS_WORDS):
            return "keys"
        if n_audio == 1:
            return "mix"
    return r


def compute_bar_lines(pts: list[list[str]], t_end: float, default=(4, 4)) -> tuple[list[float], int, int]:
    """Barres de mesure de la carte de tempo (marqueurs « carrés »), de 0 à t_end."""
    num, den = default
    first_sig = None
    lines: list[float] = []
    P = sorted(((float(p[1]), float(p[2]), p) for p in pts), key=lambda x: x[0])
    if not P or P[0][0] > 1e-6:
        P.insert(0, (0.0, P[0][1] if P else 120.0, None))
    nxt = 0.0
    prev_len = None
    for k, (t, bpm, raw) in enumerate(P):
        seg_end = P[k + 1][0] if k + 1 < len(P) else t_end
        if raw is not None and len(raw) > 4 and raw[4].lstrip("-").isdigit() and int(raw[4]) > 0:
            packed = int(raw[4])
            num, den = packed & 0xFFFF, (packed >> 16) & 0xFFFF or 4
            if first_sig is None:
                first_sig = (num, den)
            nxt = t                                   # changement de mesure : nouvelle mesure ici
        elif prev_len is not None:
            frac = (nxt - t) / prev_len               # reste de la mesure en cours, en mesures
            nxt = t if abs(frac) < 1e-6 else t + frac * (60.0 / bpm * num * 4.0 / den)
        bar_len = 60.0 / max(bpm, 1e-6) * num * 4.0 / den
        while nxt < seg_end - 1e-6:
            if not lines or nxt > lines[-1] + 1e-6:
                lines.append(round(nxt, 6))
            nxt += bar_len
        prev_len = bar_len
    lines.append(round(nxt, 6))
    sig = first_sig or (num, den)
    return lines, sig[0], sig[1]


def _nearest(lines: list[float], t: float) -> int:
    import bisect
    i = bisect.bisect_left(lines, t)
    if i <= 0:
        return 0
    if i >= len(lines):
        return len(lines) - 1
    return i if abs(lines[i] - t) < abs(lines[i - 1] - t) else i - 1


def _abs_file(node: Node, base: Path):
    for c in node.children:
        if isinstance(c, Node):
            _abs_file(c, base)
    for i, c in enumerate(node.children):
        if isinstance(c, str) and c.startswith("FILE "):
            tk = tokens(c)
            if len(tk) >= 2:
                f = Path(tk[1])
                if not f.is_absolute():
                    f = (base / f)
                rest = " ".join(tk[2:])
                node.children[i] = f"FILE {q(str(f))}" + (f" {rest}" if rest else "")


def _source_file(node: Node) -> str | None:
    for c in node.children:
        if isinstance(c, Node):
            if c.tag == "SOURCE":
                if c.header.split()[1:2] == ["CLICK"]:
                    return None
                f = c.first("FILE")
                if f:
                    return tokens(f)[1]
                r = _source_file(c)
                if r:
                    return r
    return None


def _num(line: str | None, idx: int = 1, default: float = 0.0) -> float:
    if not line:
        return default
    tk = tokens(line)
    try:
        return float(tk[idx])
    except (IndexError, ValueError):
        return default


def load_song(path: Path, title: str | None = None) -> SongSrc:
    path = Path(path)
    root = parse_rpp(path.read_text(encoding="utf-8", errors="replace"))
    s = SongSrc(path=path, title=title or _title_from(path))
    base = path.parent

    # pistes ----------------------------------------------------------------
    raw_audio = []
    for tr in root.blocks("TRACK"):
        tk = tokens(tr.first("NAME") or "NAME ''")
        name = tk[1] if len(tk) > 1 else ""
        items = tr.blocks("ITEM")
        if name.upper() in GENERATED:
            head = Node(tr.header, [c for c in tr.children if not (isinstance(c, Node) and c.tag == "ITEM")])
            s.gen[name.upper()] = (head, [it.copy() for it in items])
            continue
        vol = _num(tr.first("VOLPAN"), 1, 1.0)
        mute = int(_num(tr.first("MUTESOLO"), 1, 0)) == 1
        for it in items:
            f = _source_file(it)
            if not f:
                continue
            fp = Path(f)
            if not fp.is_absolute():
                fp = base / fp
            raw_audio.append({
                "node": it.copy(), "track": name, "vol": vol, "mute": mute or int(_num(it.first("MUTE"), 1, 0)) == 1,
                "file": str(fp), "position": _num(it.first("POSITION")), "length": _num(it.first("LENGTH")),
                "offset": _num(it.first("SOFFS")), "rate": _num(it.first("PLAYRATE"), 1, 1.0) or 1.0,
                "guid": tokens(it.first("GUID") or "GUID x")[1] if it.first("GUID") else "",
            })
    for d in raw_audio:
        d["role"] = _role(d["file"], len(raw_audio))
    s.audio = raw_audio
    if not s.audio:
        s.warnings.append(_t("concert_no_audio", title=s.title))

    # tempo -------------------------------------------------------------------
    env = root.blocks("TEMPOENVEX")
    s.pts = [tokens(p) for p in (env[0].lines("PT") if env else [])]
    head_tempo = tokens(root.first("TEMPO") or "TEMPO 120 4 4")
    if not s.pts:
        bpm = float(head_tempo[1])
        num, den = int(head_tempo[2]), int(head_tempo[3])
        s.pts = [["PT", "0", f"{bpm}", "1", str(num | den << 16), "0", "1"]]
    elif float(s.pts[0][1]) > 1e-6:
        s.pts.insert(0, ["PT", "0", head_tempo[1], "1", str(int(head_tempo[2]) | int(head_tempo[3]) << 16), "0", "1"])

    # régions et marqueurs ----------------------------------------------------
    pending = {}
    for line in root.lines("MARKER"):
        tk = tokens(line)
        if len(tk) < 5:
            continue
        idx, pos, name, flags = tk[1], float(tk[2]), tk[3], int(tk[4]) if tk[4].lstrip("-").isdigit() else 0
        color = int(tk[5]) if len(tk) > 5 and tk[5].lstrip("-").isdigit() else 0
        if flags & 1:
            if len(tk) > 5 or idx not in pending:
                pending[idx] = {"start": pos, "name": name, "color": color}
            else:
                r = pending.pop(idx)
                r["end"] = pos
                s.regions.append(r)
        else:
            s.markers.append({"pos": pos, "name": name, "color": color})
    s.regions.sort(key=lambda r: r["start"])

    t_audio_end = max([d["position"] + d["length"] for d in s.audio] or [0.0])
    t_reg_end = max([r["end"] for r in s.regions] or [t_audio_end])
    s.bar_lines, s.beats_per_bar, s.denominator = compute_bar_lines(s.pts, max(t_audio_end, t_reg_end) + 120.0)

    # mesure 1, count-in, fin -------------------------------------------------
    if s.regions:
        i0 = _nearest(s.bar_lines, s.regions[0]["start"])
        i_end = _nearest(s.bar_lines, s.regions[-1]["end"])
        if abs(s.bar_lines[i0] - s.regions[0]["start"]) > 0.05:
            s.warnings.append(_t("concert_region_off_grid", title=s.title))
    else:
        s.warnings.append(_t("concert_no_regions", title=s.title))
        i0 = 0
        i_end = max(1, _nearest(s.bar_lines, t_audio_end))
    cm = next((m for m in s.markers if m["name"].lower().startswith(("count-in", "décompte", "decompte"))), None)
    ci = i0 - _nearest(s.bar_lines, cm["pos"]) if cm else min(2, i0)
    s.i0, s.ci, s.n_bars = i0, max(0, ci), max(1, i_end - i0)

    # sections (mesures, 0 = 1re mesure du morceau) ----------------------------
    letters = {}
    for r in s.regions:
        st = _nearest(s.bar_lines, r["start"]) - i0
        en = _nearest(s.bar_lines, r["end"]) - i0
        if en <= st:
            continue
        base_name = re.sub(r"\s+\d+$", "", r["name"]).strip().lower()
        lab = letters.setdefault(base_name, chr(ord("A") + len(letters) % 26))
        s.sections.append(Section(st, en, lab, r["name"], 0.0))
    if not s.sections:
        s.sections = [Section(0, s.n_bars, "A", s.title, 0.0)]
    return s


def _plan_song_span(s: SongSrc, gap_s: float):
    """Fin de l'audio gardé et début du morceau suivant (barre de mesure), timeline du morceau."""
    audio_end = max([d["position"] + d["length"] for d in s.audio if not d["mute"]] or [s.song_end])
    s.stop = round(max(s.song_end, min(audio_end, s.song_end + MAX_TAIL)) + 0.25, 6)
    target = s.stop + max(0.0, gap_s)
    k = s.i0 + s.n_bars
    while k < len(s.bar_lines) - 1 and s.bar_lines[k] < target - 1e-6:
        k += 1
    s.next_start = s.bar_lines[k]


def concert_layout(settings: dict | None = None, gap_s: float = 4.0, stored: dict | None = None) -> dict:
    """Placement des morceaux : {"gap_s": blanc minimum (s), "slot_s": créneau rond (s, 0 = aucun)}.

    gap_s : argument / setlist (4 s par défaut) ; le réglage `gma3_song_gap` le remplace s'il est donné.
    `gma3_song_slot` > 0 : chaque morceau commence au prochain multiple du créneau (morceau 1 à 0).
    stored : placement enregistré dans la setlist à la construction (relu par la phase lente, pour que le
    prompteur garde les temps du projet même si les réglages ont changé entre-temps)."""
    if stored:
        return {"gap_s": max(0.0, float(stored.get("gap_s", gap_s))), "slot_s": max(0.0, float(stored.get("slot_s") or 0))}
    try:
        from .lighting import config
        cfg = config(settings)
    except Exception:
        cfg = {"gap_s": None, "slot_s": 0.0}
    gap = float(gap_s) if cfg.get("gap_s") is None else float(cfg["gap_s"])
    return {"gap_s": max(0.0, gap), "slot_s": max(0.0, float(cfg.get("slot_s") or 0.0))}


MAX_FILL_BPM = 900.0      # tempo maximal du blanc ajusté (REAPER : 960)


def _fill_to(s: SongSrc, start: float, target: float) -> tuple[float, int] | None:
    """Tempo du blanc pour que la barre de mesure `start` (temps du concert, fin du morceau s) tombe, en
    un nombre entier de mesures, sur `target` (début du morceau suivant) : (bpm, mesures) ; None si
    rien à faire. La grille reste juste : le morceau suivant commence sur une barre de mesure."""
    d = target - start
    if d < 1e-6:
        return None
    j = min(max(1, s.i0 + s.n_bars), len(s.bar_lines) - 1)
    bar = max(1e-3, s.bar_lines[j] - s.bar_lines[j - 1])
    n = max(1, int(round(d / bar)))
    bpm = 60.0 * s.beats_per_bar * 4.0 / s.denominator * n / d
    return (bpm, n) if bpm <= MAX_FILL_BPM else None


def place_songs(srcs: list[SongSrc], slot_s: float = 0.0) -> list[dict]:
    """Début de chaque morceau sur la timeline du concert (après _plan_song_span) :
    [{"shift", "next", "fill": (bpm, mesures) | None}]. Sans créneau : à la suite (comportement d'origine) ;
    avec créneau : au prochain multiple de slot_s, le blanc étant rallongé d'un nombre entier de mesures."""
    out, pos = [], 0.0
    for k, s in enumerate(srcs):
        shift = pos
        nxt = shift + s.next_start
        fill = None
        if slot_s > 0 and k + 1 < len(srcs):
            target = math.ceil((nxt - 1e-6) / slot_s) * slot_s
            while True:
                fill = _fill_to(s, nxt, target)
                if fill is not None or target - nxt < 1e-6:
                    break
                target += slot_s                  # blanc trop court pour un tempo raisonnable : créneau suivant
            nxt = target
        out.append({"shift": round(shift, 6), "next": round(nxt, 6), "fill": fill})
        pos = nxt
    return out


# --------------------------------------------------------------------------- #
# Construction du projet concert
# --------------------------------------------------------------------------- #
def _item_for_concert(node: Node, shift: float, stop: float, base: Path, color=None, vol=1.0, mute=False,
                      fade_out=True) -> Node | None:
    it = node.copy()
    pos = _num(it.first("POSITION"))
    ln = _num(it.first("LENGTH"))
    if pos >= stop - 1e-6:
        return None
    trimmed = pos + ln > stop + 1e-6
    if trimmed:
        ln = stop - pos
    it.set_line("POSITION", f"POSITION {round(pos + shift, 6)}")
    it.set_line("LENGTH", f"LENGTH {round(ln, 6)}")
    if trimmed and fade_out:
        it.set_line("FADEOUT", "FADEOUT 1 0.5 0 1 0 0 0")
    it.drop("IID")
    it.drop("SEL")
    it.set_line("IGUID", f"IGUID {guid()}")
    if it.first("GUID"):
        it.set_line("GUID", f"GUID {guid()}")
    for take in it.blocks("TAKE"):            # prises multiples : GUID uniques aussi
        if take.first("GUID"):
            take.set_line("GUID", f"GUID {guid()}")
    if color is not None:
        it.drop("COLOR")
        it.children.insert(1, f"COLOR {native_color(color)} B")
    if abs(vol - 1.0) > 1e-9:
        vp = it.first("VOLPAN")
        tk = tokens(vp) if vp else ["VOLPAN", "1", "0", "1", "-1"]
        try:
            tk[1] = repr(round(float(tk[1]) * vol, 8))
        except (IndexError, ValueError):
            pass
        it.set_line("VOLPAN", " ".join(tk))
    if mute:
        it.set_line("MUTE", "MUTE 1 0")
    _abs_file(it, base)
    return it


def _track(name: str, color, items: list[Node], head: Node | None = None) -> Node:
    g = guid()
    if head is not None:
        tr = head.copy()
        tr.header = f"TRACK {g}"
        tr.set_line("NAME", f"NAME {q(name)}")
        tr.set_line("TRACKID", f"TRACKID {g}")
        tr.drop("SEL")
    else:
        tr = Node(f"TRACK {g}", [
            f"NAME {q(name)}",
            f"PEAKCOL {native_color(color) if color else 16576}",
            "BEAT -1", "AUTOMODE 0", "VOLPAN 1 0 -1 -1 1", "MUTESOLO 0 0 0", "IPHASE 0",
            "PLAYOFFS 0 1", "ISBUS 0 0", "SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0",
            "SEL 0", "REC 0 0 1 0 0 0 0 0", "VU 64", "TRACKHEIGHT 0 0 0 0 0 0 0",
            "NCHAN 2", "FX 1", f"TRACKID {g}", "PERF 0", "MAINSEND 1 0",
        ])
    if color and head is not None:
        tr.set_line("PEAKCOL", f"PEAKCOL {native_color(color)}")
    tr.children.extend(items)
    return tr


def _slug(name: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]+", "-", str(name)).strip(" .")
    return s or "Concert"


@dataclass
class ConcertResult:
    name: str
    rpp: Path
    setlist: Path
    sidecar: Path
    prompter: Path
    songs: list[dict]
    warnings: list[str]
    song_srcs: list[SongSrc] = field(default_factory=list, repr=False)
    live: list[str] = field(default_factory=list)
    live_exceptions: dict = field(default_factory=dict)
    lighting: dict | None = None

    def summary(self) -> dict:
        out = {"concert": self.name, "projet": str(self.rpp), "setlist": str(self.setlist),
               "morceaux": [{"#": d["n"], "titre": d["title"], "debut_s": round(d["start"], 2),
                             "bpm": d["bpm"], "mesures": d["bars"], "sections": d["sections"],
                             "fin_s": round(d["stop"], 2)} for d in self.songs],
               "duree_s": round(self.songs[-1]["stop"], 1) if self.songs else 0,
               "warnings": self.warnings}
        out.update(live_summary(self.live, self.live_exceptions))
        if self.lighting:
            out["grandma3"] = {"dossier": self.lighting.get("dir"), "cues": self.lighting.get("cues")}
        return out


def _fingerprint(path) -> dict:
    """Empreinte du projet d'un morceau au moment de la construction (taille + Adler-32 du fichier), relue
    par le contrôle « Vérifier » de la fenêtre Concert pour savoir si le morceau a changé depuis."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return {}
    return {"project_size": len(data), "project_sum": zlib.adler32(data) & 0xFFFFFFFF}


def build_concert(name: str, songs: list, gap_s: float = 4.0, out_dir: Path | None = None,
                  publish: bool = True, live=None, live_exceptions=None) -> ConcertResult:
    """Écrit le projet concert (et ses fichiers compagnons) ; phase rapide, sans analyse audio.

    live : instruments joués en vrai par le groupe (leurs stems sont coupés) ; live_exceptions :
    exceptions par morceau ({"Titre": {"bass": "stem"}}). None = profil déjà enregistré dans la
    setlist du concert (reconstruction), sinon aucun."""
    if not songs:
        raise ValueError(_t("concert_empty"))
    out_dir = Path(out_dir or concert_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(name)
    warnings: list[str] = []
    srcs: list[SongSrc] = []
    entries = []
    layout = concert_layout(gap_s=gap_s)
    for e in songs:
        if isinstance(e, dict):
            proj, title = e.get("project") or e.get("path") or e.get("name"), e.get("title")
        else:
            proj, title = e, None
        p = find_project(str(proj))
        s = load_song(p, title)
        _plan_song_span(s, layout["gap_s"])
        warnings += s.warnings
        srcs.append(s)
        entries.append({"project": str(p), "title": s.title})
    places = place_songs(srcs, layout["slot_s"])

    # pistes communes : rôles utilisés, dans l'ordre fixe ; doublons dans un morceau -> « Nom 2 »
    lanes: dict[str, list[Node]] = {}
    lane_color: dict[str, tuple] = {}
    order: list[str] = []

    def lane(name_, color):
        if name_ not in lanes:
            lanes[name_] = []
            lane_color[name_] = color
            order.append(name_)
        return lanes[name_]

    gen_items = {"CUES": [], "VOIX": [], "CLICK": []}
    gen_heads: dict[str, Node] = {}
    gen_names: dict[str, str] = {}
    song_markers, regions, cue_markers, pts_out, sidecar_songs = [], [], [], [], []
    tracks_l = role_tracks()
    track_name = {r: n for r, n, _ in tracks_l}
    role_rank = {r: i for i, (r, _, _) in enumerate(tracks_l)}
    for k, s in enumerate(srcs):
        shift, nxt_abs = places[k]["shift"], places[k]["next"]
        col = SONG_COLORS[k % len(SONG_COLORS)]
        used: dict[str, int] = {}
        for d in sorted(s.audio, key=lambda d: role_rank.get(d["role"], 99)):
            base_name = track_name.get(d["role"], track_name["other"])
            used[base_name] = used.get(base_name, 0) + 1
            tname = base_name if used[base_name] == 1 else f"{base_name} {used[base_name]}"
            rc = next((c for r, n, c in tracks_l if n == base_name), (136, 135, 128))
            it = _item_for_concert(d["node"], shift, s.stop, s.path.parent, color=col, vol=d["vol"], mute=d["mute"])
            if it is not None:
                lane(tname, rc).append(it)
        for gname in ("CUES", "VOIX", "CLICK"):
            src_name = gname if gname in s.gen else ("VOICE" if gname == "VOIX" and "VOICE" in s.gen else None)
            if not src_name:
                continue
            head, items = s.gen[src_name]
            gen_heads.setdefault(gname, head)
            gen_names.setdefault(gname, src_name)
            for it in items:
                n = _item_for_concert(it, shift, s.stop, s.path.parent, fade_out=False)
                if n is not None:
                    gen_items[gname].append(n)
        # tempo : marqueurs du morceau jusqu'au début du suivant, décalés
        for p in s.pts:
            t = float(p[1])
            if t >= s.next_start - 1e-6:
                continue
            q_ = list(p)
            q_[1] = f"{t + shift:.12f}"
            pts_out.append(q_)
        if places[k]["fill"]:                     # créneau rond : blanc rallongé, mesures entières
            pts_out.append(["PT", f"{s.next_start + shift:.12f}", f"{places[k]['fill'][0]:.10f}", "1"])
        # régions et marqueurs
        for sec_r in s.regions:
            regions.append({"start": sec_r["start"] + shift, "end": sec_r["end"] + shift,
                            "name": f"{s.title} · {sec_r['name']}", "color": sec_r["color"]})
        for m in s.markers:
            if m["name"].lower().startswith(("count-in", "décompte", "decompte")) or m["pos"] >= s.stop:
                continue
            cue_markers.append({"pos": m["pos"] + shift, "name": m["name"], "color": m["color"]})
        song_markers.append({"pos": shift, "name": f"{k + 1} · {s.title}", "color": native_color(col)})
        song_markers.append({"pos": s.stop + shift, "name": "■", "color": native_color((226, 75, 74))})
        sidecar_songs.append({
            "n": k + 1, "title": s.title, "project": str(s.path),
            "start": round(shift, 6), "countin": round(s.count_in_pos + shift, 6),
            "bar1": round(s.bar1 + shift, 6), "song_end": round(s.song_end + shift, 6),
            "stop": round(s.stop + shift, 6), "next": nxt_abs,
            "bpm": round(s.bpm, 2), "beatmap": bool(s.beatmap),
            "sig": f"{s.beats_per_bar}/{s.denominator}", "bars": s.n_bars,
            "sections": len(s.sections), "color": list(col),
            **_fingerprint(s.path),
        })

    # projet ------------------------------------------------------------------
    first = srcs[0]
    root = Node('REAPER_PROJECT 0.1 "7.0" 0 0', [
        "RIPPLE 0 0", "AUTOXFADE 129", "PANLAW 1", "PROJOFFS 0 0 0", "MAXPROJLEN 0 0",
        "GRID 3199 8 1 8 1 0 0 0", "TIMEMODE 1 5 -1 30 0 0 -1 0", "PANMODE 3", "CURSOR 0",
        "ZOOM 2 0 0", "VZOOMEX 6 0", "LOOP 0", 'RECORD_PATH "Media" ""',
        "TIMELOCKMODE 1", "TEMPOENVLOCKMODE 1", "ITEMMIX 1", "SAMPLERATE 44100 0 0", "LOCK 1",
        f"TEMPO {first.bpm} {first.beats_per_bar} {first.denominator} 0",
        "PLAYRATE 1 0 0.25 4", "SELECTION 0 0", "SELECTION2 0 0",
        "MASTER_VOLUME 1 0 -1 -1 1", "MASTER_NCH 2 2", f"MASTER_TRACKID {guid()}",
    ])
    env = Node("TEMPOENVEX", [f"EGUID {guid()}", "ACT 0 -1", "VIS 1 0 1", "LANEHEIGHT 0 0", "ARM 0",
                              "DEFSHAPE 1 -1 -1"] + [" ".join(q(x) if i == 0 else (q(x) if x == "" or " " in x else x)
                                                            for i, x in enumerate(p)) for p in pts_out])
    root.children.append(env)
    root.children += ["RULERHEIGHT 110 110",
                      f'RULERLANE 1 0 {q(_t("concert_lane_songs"))} 0 -1 0',
                      'RULERLANE 2 4 "" 0 -1 0',
                      'RULERLANE 3 8 "" 0 -1 0']
    for i, m in enumerate(song_markers, 1):
        root.children.append(f"MARKER {i} {m['pos']:.6f} {q(m['name'])} 0 {m['color']} 1 B {guid()} 0 1")
    nm = len(song_markers)
    for i, m in enumerate(sorted(cue_markers, key=lambda x: x["pos"]), nm + 1):
        root.children.append(f"MARKER {i} {m['pos']:.6f} {q(m['name'])} 0 {m['color']} 1 B {guid()} 0 3")
    for i, r in enumerate(regions, 1):
        root.children.append(f"MARKER {i} {r['start']:.6f} {q(r['name'])} 1 {r['color']} 1 B {guid()} 0 2")
        root.children.append(f"MARKER {i} {r['end']:.6f} \"\" 1")
    def _rank(t):
        b, _, n = t.rpartition(" ")
        base, num = (b, int(n)) if n.isdigit() and b else (t, 1)
        return (next((i for i, (_, nm, _) in enumerate(tracks_l) if nm == base), 99), num)
    for tname in sorted(order, key=_rank):
        root.children.append(_track(tname, lane_color[tname], sorted(lanes[tname], key=lambda n: _num(n.first("POSITION")))))
    for gname in ("CUES", "VOIX", "CLICK"):
        if gen_items[gname]:
            root.children.append(_track(gen_names.get(gname, gname), None, gen_items[gname], gen_heads.get(gname)))
    # timecode pour la console lumière : UNE piste par sortie sur toute la durée du concert (pas une copie
    # de celles des morceaux) ; temps envoyé = temps du concert + gma3_tc_start, comme le Timecode XML
    try:
        from . import timecode as TC
        tc_cfg = TC.config()
        if tc_cfg["enabled"]:
            tc_nodes, tc_warn = TC.concert_tracks([s.gen for s in srcs], sidecar_songs[-1]["stop"] + TC.TAIL_S, tc_cfg)
            root.children += tc_nodes
            warnings += tc_warn
    except Exception as e:                    # le timecode ne bloque jamais le concert
        warnings.append(_t("gma3_failed", e=e))

    rpp = out_dir / f"{slug}.RPP"
    setlist = out_dir / f"{slug}.setlist.json"
    sidecar = out_dir / f"{slug}.concert.lua"
    prompter_file = out_dir / f"{slug}.prompteur.json"
    # profil « joué en live » : donné, sinon celui déjà enregistré dans la setlist (reconstruction)
    old = {}
    if setlist.exists() and (live is None or live_exceptions is None):
        try:
            old = json.loads(setlist.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    titles = [e["title"] for e in entries]
    live_l = norm_live(old.get("live") if live is None else live)
    exc = norm_exceptions(old.get("live_exceptions") if live_exceptions is None else live_exceptions, titles, live_l)
    tmp = rpp.with_suffix(".rpp-tmp")
    tmp.write_text(dump_rpp(root) + "\n", encoding="utf-8")
    os.replace(tmp, rpp)
    sl = {"name": name, "gap_s": gap_s, "songs": entries, "live": live_l, "live_exceptions": exc}
    if layout["slot_s"] > 0 or abs(layout["gap_s"] - float(gap_s)) > 1e-9:
        sl["layout"] = layout                 # placement réel (réglages gma3_song_gap / gma3_song_slot)
    _write_json(setlist, sl)
    side = {"version": 2, "name": name, "rpp": str(rpp), "setlist": str(setlist), "prompter": str(prompter_file),
            "built": int(time.time()), "songs": sidecar_songs}
    sidecar.write_text("-- ReaCue : données du concert (lues par ReaCue_Concert.lua) / concert data\nreturn " + to_lua(side) + "\n",
                       encoding="utf-8")
    res = ConcertResult(name, rpp, setlist, sidecar, prompter_file, sidecar_songs, warnings, srcs, live_l, exc)
    # prompteur : structure tout de suite ; accords, paroles, batterie ensuite (concert_extras)
    try:
        song_json = concert_prompter(res, extras=False)
    except Exception as e:                    # le prompteur ne bloque jamais le concert
        song_json = None
        res.warnings.append(_t("concert_prompter_failed", e=e))
    if song_json is not None:
        # avant la publication : les liens de l'onglet Lumière existent (dossier web seulement si publié)
        export_lighting(res, song_json, www=None if publish else False)
        try:
            write_prompter(res, song_json, publish=publish)
        except Exception as e:
            res.warnings.append(_t("concert_prompter_failed", e=e))
    return res


def export_lighting(res: ConcertResult, data: dict, www=None) -> dict | None:
    """Export grandMA3 du concert (jamais bloquant : un échec devient un avertissement)."""
    from . import lighting, prompter
    try:
        out = lighting.export_concert(res.name, data, res.rpp.parent,
                                      prompter.WWW_DIR if www is None else (www or None))
        res.lighting = out
        return out
    except Exception as e:
        res.warnings.append(_t("gma3_failed", e=e))
        return None


# --------------------------------------------------------------------------- #
# Prompteur du concert
# --------------------------------------------------------------------------- #
def song_analysis(s: SongSrc) -> tuple[Analysis, dict, list[dict] | None]:
    """Analyse reconstruite à partir du projet (grille et structure validées), dans le temps du fichier
    de référence, + item de référence et items (stems) comme prepare_song les fournit."""
    aud = [d for d in s.audio]
    files = [d["file"] for d in aud]
    items = [{"file": d["file"], "position": d["position"], "offset": d["offset"], "rate": d["rate"],
              "guid": d["guid"], "track": d["track"]} for d in aud]
    ref = items[reference_index(files)] if items else {"file": "", "position": 0.0, "offset": 0.0, "rate": 1.0}

    def ft(t):
        return round((t - ref["position"]) * (ref["rate"] or 1.0) + ref["offset"], 4)
    db = [ft(t) for t in s.bar_lines[s.i0:s.i0 + s.n_bars + 1]]
    m = s.beats_per_bar
    beats = []
    for a_, b_ in zip(db[:-1], db[1:]):
        beats += [round(a_ + (b_ - a_) * j / m, 4) for j in range(m)]
    beats.append(db[-1])
    roles = assign_roles(files)
    a = Analysis(file=ref["file"], duration=round(max([d["length"] * d["rate"] for d in aud] or [0.0]), 3),
                 bpm=round(s.bpm, 3), beats_per_bar=m, denominator=s.denominator,
                 tempo_stable=not s.beatmap, tempo_cv=0.0, beats=beats, downbeats=db,
                 sections=[Section(x.start_bar, x.end_bar, x.label, x.name, 0.0) for x in s.sections],
                 stems={r: f for r, f in zip(roles, files)} if len(files) > 1 else {})
    item = dict(ref, title=s.title)
    return a, item, (items if len(items) > 1 else None)


def _cache_dir(s: SongSrc, a: Analysis) -> Path:
    base = Path(a.file).parent if a.file else s.path.parent
    d = base / ".reacue"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        d = BRIDGE_DIR / "concert_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d


def concert_prompter(res: ConcertResult, extras: bool = True, log=None) -> dict:
    from . import prompter
    songs_out = []
    for k, (s, side) in enumerate(zip(res.song_srcs, res.songs)):
        a, item, items = song_analysis(s)
        shift = side["start"]
        timeline = {
            "bpm": round(s.bpm, 3), "tempo_mode": "beatmap" if s.beatmap else "constant",
            "count_in_bars": s.ci,
            "bar_times": [round(t + shift, 4) for t in s.bar_lines[s.i0 - s.ci:s.i0 + s.n_bars + 1]],
        }
        act, grid, words, kit, warns = {}, None, None, None, []
        if extras and s.audio:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", _norm(s.path.stem)) or "song"
            cd = _cache_dir(s, a)
            names = [d["file"] for d in s.audio]
            steps = (
                ("activity", lambda: prompter.stem_activity(a, items, cache=cd / f"{slug}_activity.json")),
                ("chords", lambda: __import__("reacue_mcp.chords", fromlist=["x"]).cached_chords(
                    a, items, prompter.key_from_names(names), cache=cd / f"{slug}_chords.json")),
                ("lyrics", lambda: __import__("reacue_mcp.lyrics", fromlist=["x"]).cached_lyrics(
                    a, items, cache=cd / f"{slug}_lyrics.json")),
                ("drums", lambda: __import__("reacue_mcp.drums", fromlist=["x"]).cached_drums(
                    a, items, cache=cd / f"{slug}_drums.json")
                 if any(r == "drums" for r in assign_roles(names)) else None),
            )
            out = {}
            for label, fn in steps:
                if log:
                    log(f"{s.title} : {label}…")
                try:
                    out[label] = fn()
                except Exception as e:      # jamais bloquant
                    warns.append(_t("concert_extra_failed", title=s.title, what=label, e=e))
            act = out.get("activity") or {}
            grid, words, kit = out.get("chords"), out.get("lyrics"), out.get("drums")
        song = prompter.build_song(a, item, timeline, items, act, chords=grid, lyrics=words, drums=kit)
        from . import library
        library.attach(song, str(s.path))        # projet + notes de section (écran GROUPE de ReaCue Studio)
        song.update({"n": side["n"], "start_t": side["start"], "stop_t": side["stop"], "next_t": side["next"],
                     "next_title": res.songs[k + 1]["title"] if k + 1 < len(res.songs) else None})
        if warns:
            song["warnings"] = warns
        songs_out.append(song)
    data = {"version": 1, "language": get_lang(), "concert": {"name": res.name, "n": len(songs_out),
                                      "titles": [x["title"] for x in res.songs]},
            "songs": songs_out}
    try:                                       # onglet Lumière du prompteur (cues grandMA3)
        from . import lighting
        cfg = lighting.config()
        if cfg["export"]:
            data["lighting"] = lighting.web_data(lighting.show_from_songs(songs_out, res.name), cfg)
    except Exception:
        pass
    data["id"] = hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    from . import library
    for s, sg in zip(res.song_srcs, songs_out):      # résumés pour l'écran BIBLIO
        library.record_song(sg, str(s.path), lighting=bool(data.get("lighting")))
    return data


def write_prompter(res: ConcertResult, data: dict, publish: bool = True, only_if_current: bool = False) -> dict:
    from . import prompter
    tmp = res.prompter.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, res.prompter)
    out = {"file": str(res.prompter)}
    if publish:
        if only_if_current:
            try:
                cur = json.loads((prompter.WWW_DIR / prompter.SONG_NAME).read_text(encoding="utf-8"))
                if (cur.get("concert") or {}).get("name") != res.name:
                    out["published"] = False
                    return out
            except Exception:
                pass
        out.update(prompter.publish(data))
        out["published"] = True
    return out


def load_setlist(path) -> dict:
    d = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not d.get("songs"):
        raise ValueError(_t("concert_empty"))
    return d


def build_from_setlist(path, publish: bool = True) -> ConcertResult:
    d = load_setlist(path)
    out_dir = Path(path).expanduser().parent
    return build_concert(d.get("name") or Path(path).stem.replace(".setlist", ""), _setlist_songs(d, path),
                         float(d.get("gap_s", 4.0)), out_dir=out_dir, publish=publish,
                         live=d.get("live") or [], live_exceptions=d.get("live_exceptions") or {})


def _setlist_songs(data: dict, path) -> list:
    """Portable setlists resolve project paths beside the setlist, independent of cwd."""
    out = []
    for entry in data["songs"]:
        e = dict(entry) if isinstance(entry, dict) else entry
        ref = (e.get("project") or e.get("path") or e.get("name")) if isinstance(e, dict) else e
        relative = Path(path).expanduser().resolve().parent / str(ref)
        if not Path(str(ref)).is_absolute() and relative.is_file():
            if isinstance(e, dict):
                e["project"] = str(relative.resolve())
            else:
                e = str(relative.resolve())
        out.append(e)
    return out


def extras_from_setlist(path, log=None) -> dict:
    """Phase lente : accords, paroles, batterie, entrées/sorties par morceau (caches par morceau)."""
    res = _reload(path)
    data = concert_prompter(res, extras=True, log=log)
    out = write_prompter(res, data, publish=True, only_if_current=True)
    warns = [w for sg in data["songs"] for w in sg.get("warnings", [])]
    return {"prompteur": out, "warnings": warns,
            "morceaux": [{"titre": sg["title"], "accords": bool(sg.get("chords")),
                          "paroles": len(sg.get("lyrics") or []), "batterie": bool(sg.get("drums"))}
                         for sg in data["songs"]]}


def _reload(setlist_path) -> ConcertResult:
    """Relit un concert déjà construit (sans réécrire le RPP) pour enrichir son prompteur."""
    d = load_setlist(setlist_path)
    out_dir = Path(setlist_path).expanduser().parent
    slug = _slug(d.get("name") or "Concert")
    layout = concert_layout(gap_s=float(d.get("gap_s", 4.0)), stored=d.get("layout") or {"gap_s": d.get("gap_s", 4.0)})
    srcs, side, warnings = [], [], []
    for k, e in enumerate(_setlist_songs(d, setlist_path)):
        p = find_project(e["project"] if isinstance(e, dict) else e)
        s = load_song(p, e.get("title") if isinstance(e, dict) else None)
        _plan_song_span(s, layout["gap_s"])
        srcs.append(s)
        warnings += s.warnings
    for k, (s, pl) in enumerate(zip(srcs, place_songs(srcs, layout["slot_s"]))):
        pos = pl["shift"]
        side.append({"n": k + 1, "title": s.title, "start": round(pos, 6), "stop": round(s.stop + pos, 6),
                     "next": pl["next"]})
    return ConcertResult(d.get("name") or slug, out_dir / f"{slug}.RPP", Path(setlist_path).expanduser(),
                         out_dir / f"{slug}.concert.lua", out_dir / f"{slug}.prompteur.json", side, warnings, srcs)


# --------------------------------------------------------------------------- #
# « Joué en live » : stems coupés instrument par instrument
# --------------------------------------------------------------------------- #
# rôles des pistes communes du concert ; noms acceptés (FR, EN, variantes)
LIVE_ROLES = [r for r, _, _, _ in ROLE_TRACKS_I18N]
_ROLE_ALIASES = {
    "vocals": ("vocals", "vocal", "voice", "voix", "chant", "chanteur", "chanteuse", "vox", "singer"),
    "drums": ("drums", "drum", "batterie", "batteur", "batt", "kit"),
    "bass": ("bass", "basse", "bassiste"),
    "guitars": ("guitars", "guitar", "guitares", "guitare", "guitare rythmique", "rhythm guitar", "rhythm gtr", "gtr",
                "guitare rythm", "guitariste"),
    "lead_guitar": ("lead guitar", "lead_guitar", "guitare solo", "lead", "solo guitar", "lead gtr", "guitare lead"),
    "keys": ("keys", "claviers", "clavier", "piano", "synth", "keyboards", "keyboard", "orgue", "organ"),
    "other": ("other", "autres", "autre", "others"),
    "mix": ("mix",),
}


def norm_role(x) -> str:
    """Rôle (« drums »…) à partir d'un nom FR/EN (« Batterie », « Lead guitar »…) ; ValueError sinon."""
    n = _norm(x).replace("_", " ")
    for role, names in _ROLE_ALIASES.items():
        if n == role.replace("_", " ") or n in (_norm(a) for a in names):
            return role
    raise ValueError(_t("concert_live_role", r=x, roles=", ".join(LIVE_ROLES)))


def norm_live(live) -> list[str]:
    """Liste ordonnée et sans doublon des rôles joués en live."""
    if not live:
        return []
    if isinstance(live, str):
        live = [x for x in re.split(r"[,;/]+", live) if x.strip()]
    got = {norm_role(x) for x in live}
    return [r for r in LIVE_ROLES if r in got]


def _norm_mode(v) -> str | None:
    if v is True:
        return "live"
    if v is False:
        return "stem"
    if v is None:
        return None
    n = _norm(v)
    if n in ("live", "l", "joue en live", "played live", "coupe", "muted", "mute", "cut", "off"):
        return "live"
    if n in ("stem", "s", "joue", "played", "on", "stem joue", "unmuted", "garde", "keep"):
        return "stem"
    if n in ("", "default", "defaut", "none", "auto", "profil", "profile"):
        return None
    raise ValueError(_t("concert_live_mode", v=v))


def _song_key(k, titles: list[str]) -> str:
    if isinstance(k, int) or (isinstance(k, str) and k.strip().isdigit()):
        i = int(k)
        if 1 <= i <= len(titles):
            return titles[i - 1]
    want = _norm(k)
    for t_ in titles:
        if _norm(t_) == want:
            return t_
    for t_ in titles:
        if want and want in _norm(t_):
            return t_
    raise ValueError(_t("concert_live_song", s=k, songs=", ".join(titles)))


def norm_exceptions(exc, titles: list[str], live: list[str] | None = None, base: dict | None = None) -> dict:
    """{titre: {rôle: "live"|"stem"}} ; une liste de rôles = l'inverse du profil du concert pour ce morceau.
    Les exceptions identiques au profil sont retirées. `base` : exceptions existantes à compléter."""
    live = live or []
    out = {k: dict(v) for k, v in (base or {}).items() if k in titles}
    for k, v in (exc or {}).items():
        try:
            title = _song_key(k, titles)
        except ValueError:
            if base is None and not titles:
                continue
            raise
        cur = out.setdefault(title, {})
        if isinstance(v, (list, tuple, set, str)):
            items = [v] if isinstance(v, str) else list(v)
            for r in items:
                role = norm_role(r)
                cur[role] = "stem" if role in live else "live"
        elif isinstance(v, dict):
            for r, m in v.items():
                role = norm_role(r)
                mode = _norm_mode(m)
                if mode is None:
                    cur.pop(role, None)
                else:
                    cur[role] = mode
        elif v is None:
            out.pop(title, None)
            continue
        else:
            raise ValueError(_t("concert_live_mode", v=v))
    # retire ce qui ne change rien par rapport au profil
    clean = {}
    for title in titles:
        d = {r: m for r, m in (out.get(title) or {}).items() if (m == "live") != (r in live)}
        if d:
            clean[title] = {r: d[r] for r in LIVE_ROLES if r in d}
    return clean


def live_summary(live: list[str], exc: dict) -> dict:
    names = {r: n for r, n, _ in role_tracks()}
    out = {"joue_en_live": [names.get(r, r) for r in live]}
    if exc:
        out["exceptions_par_morceau"] = {k: {names.get(r, r): m for r, m in v.items()} for k, v in exc.items()}
    return out


def _write_json(path: Path, data: dict):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def setlist_path(name_or_path) -> Path:
    """Fichier <nom>.setlist.json d'un concert (nom, chemin du setlist, du RPP ou du .concert.lua)."""
    p = Path(str(name_or_path)).expanduser()
    if p.suffix.lower() == ".json" and p.exists():
        return p
    if p.suffix.lower() in (".rpp", ".lua") and p.parent.exists():
        stem = re.sub(r"\.concert$", "", p.stem)
        cand = p.parent / f"{stem}.setlist.json"
        if cand.exists():
            return cand
    cand = concert_dir() / f"{_slug(str(name_or_path))}.setlist.json"
    if cand.exists():
        return cand
    want = _norm(name_or_path)
    if concert_dir().exists():
        for f in concert_dir().glob("*.setlist.json"):
            if _norm(f.name[:-len(".setlist.json")]) == want:
                return f
    raise FileNotFoundError(_t("concert_not_found", name=name_or_path, d=concert_dir()))


def set_live_profile(name_or_path, live=None, exceptions=None, replace_exceptions: bool = False) -> dict:
    """Modifie le profil « joué en live » d'un concert existant SANS le reconstruire : la fenêtre
    « ReaCue - Concert » relit la setlist et applique les coupures aussitôt."""
    sp = setlist_path(name_or_path)
    d = json.loads(sp.read_text(encoding="utf-8"))
    titles = [e.get("title") if isinstance(e, dict) else _title_from(Path(str(e))) for e in d.get("songs") or []]
    titles = [x for x in titles if x]
    live_l = norm_live(d.get("live")) if live is None else norm_live(live)
    base = {} if replace_exceptions else (d.get("live_exceptions") or {})
    # exceptions existantes exprimées par rapport à l'ancien profil : on garde leur sens absolu
    exc = norm_exceptions(exceptions or {}, titles, live_l, base=base)
    d["live"], d["live_exceptions"] = live_l, exc
    _write_json(sp, d)
    out = {"concert": d.get("name") or sp.stem, "setlist": str(sp)}
    out.update(live_summary(live_l, exc))
    out["info"] = _t("concert_live_applied")
    return out
