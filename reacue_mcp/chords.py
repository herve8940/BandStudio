"""Détection des accords par mesure pour le prompteur des musiciens.

Méthode (librosa / numpy / scipy uniquement, quelques secondes) :
  1. spectre CQT (3 cases par demi-ton, accordage estimé) de chaque stem harmonique, moyenné par temps ;
  2. « NNLS » : le spectre de chaque temps est décomposé en notes (gabarits avec harmoniques) pour
     retirer les harmoniques de la distorsion, puis replié en chroma (12 classes) ; mélange pondéré :
     guitare rythmique 1, claviers/other 0,8, guitare solo 0,3, × activité et netteté du stem
     (mode MP3 : le mix seul, partie stable dans le temps) ;
  3. basse : note basse dominante par temps (stem basse, sinon bas du spectre du mix) ;
  4. score de chaque accord (maj, m, 7, m7, sus2, sus4, 5, dim) = gabarit · chroma + accord avec la
     basse + a priori de tonalité ; les accords sans tierce rejoignent l'accord de la tonalité
     (E5/Esus2 → Em en Mi mineur) ; Viterbi sur les temps (changer coûte cher, moins sur les temps
     1 et 3 ; le 4e temps, souvent anticipé, compte moins) ; a posteriori = confiance ;
  5. regroupement : un accord par mesure, deux si la seconde moitié change franchement (confirmé
     sur le temps 3, pas une simple note de passage), « N.C. » quand rien d'harmonique ne joue.

Modèle entraîné (facultatif, chord_model.py + reacue_chords.py dans .venv-chords) : s'il est installé,
cached_chords l'utilise d'abord (stems sans voix ni batterie, décodage calé sur les temps de ReaCue),
puis chords_from_segments cale ses accords sur les mesures (même format de sortie) ; la méthode
ci-dessus reste le repli automatique.
"""
from __future__ import annotations

import re

import numpy as np

from .analysis import Analysis, SR, HOP, _place, _frame_db, assign_roles

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
NC = "N.C."
VERSION = "chords-1"          # à changer quand l'algorithme change (invalide le cache)

# qualité -> (intervalles, poids des notes, suffixe affiché, a priori de « simplicité »)
QUALITIES = {
    "maj":  ((0, 4, 7), (1.0, 0.9, 0.8), "", 0.0),
    "min":  ((0, 3, 7), (1.0, 0.9, 0.8), "m", 0.0),
    "5":    ((0, 7), (1.0, 0.8), "5", -0.015),
    "7":    ((0, 4, 7, 10), (1.0, 0.9, 0.8, 0.7), "7", -0.05),
    "m7":   ((0, 3, 7, 10), (1.0, 0.9, 0.8, 0.7), "m7", -0.05),
    "sus2": ((0, 2, 7), (1.0, 0.8, 0.8), "sus2", -0.10),
    "sus4": ((0, 5, 7), (1.0, 0.8, 0.8), "sus4", -0.10),
    "dim":  ((0, 3, 6), (1.0, 0.9, 0.8), "dim", -0.08),
}
Q_NAMES = list(QUALITIES)

# poids des stems dans le chroma harmonique (rôle -> poids) ; basse et batterie à part
STEM_WEIGHTS = {"guitars": 1.0, "other": 0.8, "keys": 1.0, "lead_guitar": 0.3, "vocals": 0.0, "drums": 0.0}

MIDI_LO, N_NOTES = 24, 84          # CQT de C1 à B7, 3 cases par demi-ton
THIRD_MIN = 0.2          # part de chroma minimale pour qu'une tierce soit « entendue »
NC_ACT = 0.25            # activité harmonique (0..1) sous laquelle le temps est « N.C. »
BASS_WEIGHT = 0.5        # poids de la note de basse dans le score des accords


# --------------------------------------------------------------------------- #
# Tonalité, noms des notes
# --------------------------------------------------------------------------- #
def parse_key(key) -> tuple[int, bool] | None:
    """{"chord": "Em"} ou "Em" / "F# minor" -> (tonique 0..11, mineur)."""
    if not key:
        return None
    s = key.get("chord") if isinstance(key, dict) else str(key)
    m = re.match(r"\s*([A-Ga-g])\s*(#|b|♯|♭)?\s*(m(?!aj)|min|minor|mineur)?", s or "")
    if not m:
        return None
    pc = SHARPS.index(m.group(1).upper())
    acc = m.group(2) or ""
    pc = (pc + (1 if acc in ("#", "♯") else -1 if acc in ("b", "♭") else 0)) % 12
    return pc, bool(m.group(3))


def _use_flats(tonic: int, minor: bool) -> bool:
    rel = (tonic + 3) % 12 if minor else tonic          # tonalité majeure relative
    return rel in (5, 10, 3, 8, 1)                       # F, Bb, Eb, Ab, Db


def _estimate_key(chroma: np.ndarray, bass: np.ndarray) -> tuple[int, bool]:
    """Krumhansl-Schmuckler sur le chroma global (la basse compte double)."""
    maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    g = chroma.sum(0) + 2 * bass.sum(0)
    best = (-2.0, 0, False)
    for t in range(12):
        for prof, mi in ((maj, False), (mnr, True)):
            r = float(np.corrcoef(g, np.roll(prof, t))[0, 1])
            if r > best[0]:
                best = (r, t, mi)
    return best[1], best[2]


def _key_prior(tonic: int, minor: bool) -> dict[tuple[int, str], float]:
    """Bonus des accords de la tonalité (diatoniques, puis emprunts courants en rock)."""
    if minor:   # i ii° III iv v VI VII + V (mineur harmonique) + IV (dorien)
        strong = [(0, "min"), (2, "dim"), (3, "maj"), (5, "min"), (7, "min"), (8, "maj"), (10, "maj"),
                  (7, "maj")]
        weak = [(7, "7"), (5, "maj"), (0, "m7"), (5, "m7"), (7, "m7")]
    else:       # I ii iii IV V vi vii° + bVII, iv, bVI (rock)
        strong = [(0, "maj"), (2, "min"), (4, "min"), (5, "maj"), (7, "maj"), (9, "min"), (11, "dim")]
        weak = [(7, "7"), (10, "maj"), (5, "min"), (8, "maj"), (2, "m7"), (9, "m7"), (4, "m7"), (4, "maj")]
    pri = {}
    for d, q in strong:
        pri[((tonic + d) % 12, q)] = 0.06
    for d, q in weak:
        pri.setdefault(((tonic + d) % 12, q), 0.03)
    # power chord / sus : bonus si la fondamentale est un degré de la gamme
    scale = [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]
    for d in scale:
        r = (tonic + d) % 12
        for q in ("5", "sus2", "sus4"):
            pri.setdefault((r, q), 0.04 if q == "5" else 0.02)
    return pri


# --------------------------------------------------------------------------- #
# Signal -> spectre par temps
# --------------------------------------------------------------------------- #
def _beat_frames(a: Analysis) -> tuple[np.ndarray, np.ndarray]:
    """Temps (secondes) : chaque mesure divisée régulièrement en beats_per_bar temps.
    Renvoie (bornes des temps [n_beats + 1], index de la mesure de chaque temps)."""
    m = max(1, int(a.beats_per_bar))
    db = np.asarray(a.downbeats, dtype=float)
    t = [db[k] + (db[k + 1] - db[k]) * j / m for k in range(len(db) - 1) for j in range(m)]
    t.append(db[-1])
    return np.array(t), np.repeat(np.arange(len(db) - 1), m)


def _tuning(y: np.ndarray) -> float:
    """Écart d'accordage (fraction de demi-ton) estimé sur une minute de signal actif."""
    import librosa
    i0 = int(np.argmax(np.abs(y) > 0.02 * (np.abs(y).max() + 1e-9)))
    seg = y[i0: i0 + SR * 60]
    try:
        return float(librosa.estimate_tuning(y=seg, sr=SR, bins_per_octave=36))
    except Exception:
        return 0.0


def _semitone_spec(y: np.ndarray, tuning: float | None = None) -> np.ndarray:
    """|CQT| en demi-tons (N_NOTES × trames), case centrale de chaque demi-ton + voisines."""
    import librosa
    if tuning is None:
        tuning = _tuning(y)
    C = np.abs(librosa.cqt(y, sr=SR, hop_length=HOP, fmin=librosa.midi_to_hz(MIDI_LO - 1 / 3),
                           n_bins=N_NOTES * 3, bins_per_octave=36, tuning=tuning))
    C = C.reshape(N_NOTES, 3, -1)
    return C[:, 1] + 0.5 * (C[:, 0] + C[:, 2])


def _beat_mean(X: np.ndarray, tb: np.ndarray) -> np.ndarray:
    """Moyenne de X (… × trames) sur chaque temps : (n_beats × …)."""
    import librosa
    fr = librosa.time_to_frames(tb, sr=SR, hop_length=HOP)
    n = X.shape[-1]
    fr = np.clip(fr, 0, n)
    cs = np.concatenate([np.zeros(X.shape[:-1] + (1,)), np.cumsum(X, axis=-1)], axis=-1)
    a, b = fr[:-1], np.maximum(fr[1:], fr[:-1] + 1)
    b = np.minimum(b, n)
    a = np.minimum(a, b - 1)
    return ((cs[..., b] - cs[..., a]) / (b - a)).T


_DICT = None


def _note_dict(n: int = N_NOTES, s: float = 0.6, n_harm: int = 8) -> np.ndarray:
    """Gabarits de notes (colonnes) : harmoniques h à 12·log2(h) demi-tons, amplitude s^(h-1)."""
    global _DICT
    if _DICT is not None and _DICT.shape[0] == n:
        return _DICT
    D = np.zeros((n, n))
    for i in range(n):
        for h in range(1, n_harm + 1):
            j = i + int(round(12 * np.log2(h)))
            if j < n:
                D[j, i] += s ** (h - 1)
    _DICT = D / np.linalg.norm(D, axis=0, keepdims=True)
    return _DICT


def _nnls_chroma(S: np.ndarray, lo: int = 40, hi: int = 96) -> np.ndarray:
    """S : (n_beats × N_NOTES) spectre par temps -> chroma (n_beats × 12), harmoniques retirées.
    lo/hi : plage MIDI des notes gardées (E2..C7)."""
    from scipy.optimize import nnls
    D = _note_dict()
    out = np.zeros((S.shape[0], 12))
    # blanchiment : on retire le fond spectral lissé (bruit de distorsion, souffle)
    from scipy.ndimage import uniform_filter1d
    for t, v in enumerate(S):
        if v.max() <= 0:
            continue
        v = v / v.max()
        bg = uniform_filter1d(v, 13, mode="nearest")
        v = np.clip(v - 0.6 * bg, 0, None)
        x, _ = nnls(D, v, maxiter=200)
        notes = np.arange(N_NOTES) + MIDI_LO
        keep = (notes >= lo) & (notes <= hi)
        np.add.at(out[t], notes[keep] % 12, x[keep])
    return out


def _bass_notes(S: np.ndarray, lo: int = 28, hi: int = 55) -> np.ndarray:
    """Distribution (n_beats × 12) de la note de basse dominante : spectre bas, les octaves
    supérieures (harmoniques) renforcent la fondamentale ; normalisée (somme 1 si présente)."""
    i0, i1 = lo - MIDI_LO, hi - MIDI_LO + 1
    X = S[:, i0:i1]
    # somme harmonique : fondamentale + 0.5·octave + 0.3·quinte+octave
    H = X.copy()
    H[:, :-12] += 0.5 * X[:, 12:]
    H[:, :-19] += 0.3 * X[:, 19:]
    out = np.zeros((S.shape[0], 12))
    notes = np.arange(lo, hi + 1)
    for t, v in enumerate(H):
        if v.max() <= 0:
            continue
        w = np.clip(v / v.max(), 0, None) ** 4         # la note dominante écrase les autres
        np.add.at(out[t], notes % 12, w)
    s = out.sum(1, keepdims=True)
    return np.divide(out, s, out=np.zeros_like(out), where=s > 0)


def _activity(y: np.ndarray, tb: np.ndarray, span: float = 30.0) -> tuple[np.ndarray, float]:
    """Niveau par temps ramené à 0..1 sur [p90 − span, p90 − 10 dB], et p90 (dB)."""
    d = _frame_db(y)
    if d.max() < -80:
        return np.zeros(len(tb) - 1), -120.0
    top = float(np.percentile(d, 90))
    lin = _beat_mean(10 ** (d / 20)[None, :], tb)[:, 0]
    bdb = 20 * np.log10(lin + 1e-9)
    return np.clip((bdb - (top - span)) / (span - 10.0), 0, 1), top


# --------------------------------------------------------------------------- #
# Chargement des sources
# --------------------------------------------------------------------------- #
def _sources(a: Analysis, items: list[dict] | None) -> list[tuple[str, str, float]]:
    """[(rôle, fichier, décalage s)] dans le temps du stem de référence."""
    if items:
        from .prompter import _shifts
        files = [d["file"] for d in items]
        sh = _shifts(items)
        return [(r, f, sh[f]) for r, f in zip(assign_roles(files), files)]
    if a.stems and len(a.stems) > 1:
        return [(r, f, 0.0) for r, f in a.stems.items()]
    return [("mix", a.file, 0.0)]


def _load(f: str, shift: float, n: int | None) -> np.ndarray:
    import librosa
    y = librosa.load(f, sr=SR, mono=True)[0]
    if shift or n:
        n = n or len(y) + max(0, int(round(shift * SR)))
        y = _place(y, shift, SR, n)
    return y


def features(a: Analysis, items: list[dict] | None = None) -> dict:
    """Chroma harmonique, basse et activité par temps."""
    tb, bar_of = _beat_frames(a)
    srcs = _sources(a, items)
    nb = len(tb) - 1
    n = int((a.downbeats[-1] + 2.0) * SR)
    bass = np.zeros((nb, 12))
    bass_act = np.zeros(nb)
    per_stem = {}
    harm = {}
    tuning = None
    # la basse est traitée après un stem harmonique pour profiter de son accordage
    srcs = sorted(srcs, key=lambda s: re.sub(r"_\d+$", "", s[0]) == "bass")
    if len(srcs) == 1:                                  # mode MP3 : le mix seul
        from scipy.ndimage import median_filter
        y = _load(srcs[0][1], 0.0, n)
        S = _semitone_spec(y)
        S = np.minimum(S, median_filter(S, size=(1, 15)))   # garde la partie stable (harmonique)
        Sb = _beat_mean(S, tb)
        act, _ = _activity(y, tb)
        c = _nnls_chroma(Sb, lo=45)
        nrm = c.max(1, keepdims=True)
        harm["mix"] = (np.divide(c, nrm, out=np.zeros_like(c), where=nrm > 0), act)
        bass = _bass_notes(Sb, 28, 52)
        bass_act = act * 0.6
        per_stem["mix"] = act
    else:
        for role, f, sh in srcs:
            base = re.sub(r"_\d+$", "", role)
            if base in ("drums", "vocals"):
                continue
            y = _load(f, sh, n)
            act, top = _activity(y, tb)
            per_stem[role] = act
            if top < -70:
                continue
            if tuning is None and base != "bass":      # accordage commun, estimé une fois
                tuning = _tuning(y)
            Sb = _beat_mean(_semitone_spec(y, tuning if tuning is not None else 0.0), tb)
            if base == "bass":
                bass = _bass_notes(Sb)
                bass_act = act
                continue
            c = _nnls_chroma(Sb)
            nrm = c.max(1, keepdims=True)
            harm[role] = (np.divide(c, nrm, out=np.zeros_like(c), where=nrm > 0), act)
    return {"tb": tb, "bar_of": bar_of, "harm": harm, "bass": bass, "bass_act": bass_act,
            "stems": per_stem}


def _combine(F: dict) -> None:
    """Chroma harmonique pondéré (rôle -> STEM_WEIGHTS × activité du stem)."""
    nb = len(F["tb"]) - 1
    chroma, wsum, harm_act = np.zeros((nb, 12)), np.zeros(nb), np.zeros(nb)
    for role, (c, act) in F["harm"].items():
        w = 1.0 if role == "mix" else STEM_WEIGHTS.get(re.sub(r"_\d+$", "", role), 0.8)
        if w <= 0:
            continue
        # netteté : part du chroma dans les 4 classes les plus fortes ; un stem confus (repisse,
        # bruit de séparation, mélodie glissante) compte moins qu'une partie d'accords nette
        top4 = np.sort(c, 1)[:, -4:].sum(1) / (c.sum(1) + 1e-9)
        clar = np.clip((top4 - 0.55) / 0.35, 0.15, 1.0)
        chroma += (w * act * clar)[:, None] * c
        wsum += w * act * clar
        harm_act = np.maximum(harm_act, act if w >= 0.5 else 0.5 * act)
    F["chroma"] = np.divide(chroma, wsum[:, None], out=np.zeros_like(chroma), where=wsum[:, None] > 0)
    F["chroma_w"], F["harm_act"] = wsum, harm_act


# --------------------------------------------------------------------------- #
# Scores, Viterbi
# --------------------------------------------------------------------------- #
def _templates():
    labels, T, tones = [], [], []
    for q in Q_NAMES:
        iv, w, _, _ = QUALITIES[q]
        for r in range(12):
            v = np.zeros(12)
            for i, ww in zip(iv, w):
                v[(r + i) % 12] = ww
            labels.append((r, q))
            T.append(v / np.linalg.norm(v))
            tones.append({(r + i) % 12 for i in iv})
    return labels, np.array(T), tones


def _emissions(F: dict, kp: tuple[int, bool]) -> tuple[list, np.ndarray]:
    labels, T, tones = _templates()
    C = F["chroma"]
    # compression douce : une note un peu présente compte, sans écraser la dominante
    Cc = np.sqrt(np.clip(C, 0, None))
    nrm = np.linalg.norm(Cc, axis=1, keepdims=True)
    Cn = np.divide(Cc, nrm, out=np.zeros_like(Cc), where=nrm > 0)
    E = Cn @ T.T                                                  # cosinus (n_beats × n_chords)
    # basse : fondamentale = +, autre note de l'accord (renversement) = + faible, hors accord = −
    B, ba = F["bass"], F["bass_act"]
    bs = np.zeros_like(E)
    for k, (r, q) in enumerate(labels):
        on_root = B[:, r]
        on_tone = B[:, sorted(tones[k] - {r})].sum(1)
        bs[:, k] = on_root - 0.25 * (1 - on_root - on_tone) + 0.1 * on_tone
    # la basse pèse davantage quand les instruments harmoniques sont faibles (intro basse…)
    wb = BASS_WEIGHT * ba * (0.6 + 0.4 * (1 - np.clip(F["chroma_w"], 0, 1)))
    E = E * (F["chroma_w"] > 0)[:, None] + wb[:, None] * bs
    pri = _key_prior(*kp)
    # mix seul (batterie, voix…) : chroma plus bruité, on s'appuie davantage sur la tonalité
    kw = 2.0 if set(F["harm"]) == {"mix"} else 1.0
    prior = np.array([kw * pri.get(l, 0.0) + QUALITIES[l[1]][3] for l in labels])
    E = E + prior[None, :]
    # N.C. : aucun instrument harmonique (basse comprise) ne joue
    act = np.maximum(F["harm_act"], 0.7 * F["bass_act"])
    silent = act < NC_ACT
    nc = np.where(silent, 5.0, -5.0)
    E = np.where(silent[:, None], -5.0, E)
    labels = labels + [None]
    E = np.hstack([E, nc[:, None]])
    return labels, E


def _viterbi(E: np.ndarray, beat_in_bar: np.ndarray, beta: float, pen: dict) -> tuple[np.ndarray, np.ndarray]:
    """Chemin le plus probable et a posteriori (forward-backward) ; pénalité de changement selon
    la position du temps dans la mesure."""
    from scipy.special import logsumexp
    L = beta * E
    n, K = L.shape
    P = np.array([pen.get(int(b), pen["other"]) for b in beat_in_bar])
    # Viterbi
    dp = L[0].copy()
    back = np.zeros((n, K), dtype=np.int32)
    for t in range(1, n):
        best = int(np.argmax(dp))
        stay = dp
        jump = dp[best] - P[t]
        back[t] = np.where(stay >= jump, np.arange(K), best)
        dp = np.maximum(stay, jump) + L[t]
    path = np.zeros(n, dtype=np.int32)
    path[-1] = int(np.argmax(dp))
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    # forward-backward, même modèle que Viterbi (rester = 1, aller vers un autre état = e^-P)
    la = np.zeros((n, K))
    la[0] = L[0] - logsumexp(L[0])
    for t in range(1, n):
        prev = la[t - 1]
        tot = logsumexp(prev)
        trans = np.logaddexp(prev, tot - P[t])
        la[t] = trans + L[t]
        la[t] -= logsumexp(la[t])
    lb = np.zeros((n, K))
    for t in range(n - 2, -1, -1):
        nxt = lb[t + 1] + L[t + 1]
        tot = logsumexp(nxt)
        lb[t] = np.logaddexp(nxt, tot - P[t + 1])
        lb[t] -= logsumexp(lb[t])
    post = la + lb
    post = np.exp(post - logsumexp(post, axis=1, keepdims=True))
    return path, post


# --------------------------------------------------------------------------- #
# Sortie
# --------------------------------------------------------------------------- #
def _name(root: int, q: str, flats: bool) -> str:
    return (FLATS if flats else SHARPS)[root] + QUALITIES[q][2]


_NEUTRAL = ("5", "sus2", "sus4")


def _families(labels: list, pri: dict, simple: bool) -> list[tuple]:
    """Regroupe les états en accords « affichables » : [(fondamentale, famille, [états])].
    simple : m / m7 (+ sans tierce si la tonalité dit mineur) ; maj / 7 (+ sans tierce si la
    tonalité dit majeur) ; dim ; sans tierce seul si la tonalité ne tranche pas ; N.C."""
    idx = {l: i for i, l in enumerate(labels)}
    fams = []
    for r in range(12):
        if not simple:
            fams += [(r, q, [idx[(r, q)]]) for q in Q_NAMES]
            continue
        dmin = pri.get((r, "min"), 0) >= 0.06
        dmaj = pri.get((r, "maj"), 0) >= 0.06
        neutral = [idx[(r, q)] for q in _NEUTRAL]
        fams.append((r, "min", [idx[(r, "min")], idx[(r, "m7")]] + (neutral if dmin and not dmaj else [])))
        fams.append((r, "maj", [idx[(r, "maj")], idx[(r, "7")]] + (neutral if dmaj and not dmin else [])))
        fams.append((r, "dim", [idx[(r, "dim")]]))
        if dmin == dmaj:
            fams.append((r, "5", neutral))
    fams.append((None, NC, [idx[None]]))
    return fams


def detect_chords(a: Analysis, items: list[dict] | None = None, key: dict | str | None = None,
                  simple: bool = True, beta: float = 12.0, F: dict | None = None) -> list[dict]:
    """Accords par mesure : [{"bar": 1-based, "chords": [{"beat", "chord", "bass", "confidence"}]}].

    items : stems placés dans REAPER [{"file","position","offset","rate"}] (None = a.stems ou a.file).
    key : {"chord": "Em"} (cf. prompter.key_from_names) ou "Em" ; absent = estimée sur l'audio.
    simple : un accord sans tierce (power chord E5, sus2, sus4) s'affiche avec la tierce de la
             tonalité (E5 → Em en Mi mineur), sauf si l'autre tierce s'entend nettement ;
             False : vocabulaire complet affiché tel quel (E5, Asus2…).
    confidence : 0..1, probabilité a posteriori (lissée par le HMM) de l'accord affiché.
    """
    if F is None:
        F = features(a, items)
    _combine(F)
    m = max(1, int(a.beats_per_bar))
    kp = parse_key(key) or _estimate_key(F["chroma"], F["bass"])
    flats = _use_flats(*kp)
    pri = _key_prior(*kp)
    labels, E = _emissions(F, kp)
    fams = _families(labels, pri, simple)
    Ef = np.stack([E[:, mem].max(1) for _, _, mem in fams], axis=1)
    nb = Ef.shape[0]
    beat_in_bar = np.tile(np.arange(m), nb // m + 1)[:nb]
    half = m // 2 if m % 2 == 0 and m >= 4 else None
    pen = {0: 0.9, "other": 2.2}
    if half:
        pen[half] = 1.6
    # temps faibles moins écoutés : le 4e temps porte souvent l'anticipation de l'accord suivant
    bw_ = np.full(m, 0.8)
    bw_[0] = 1.0
    if half:
        bw_[half] = 0.9
    if m >= 3:
        bw_[m - 1] = 0.6
    path, post = _viterbi(Ef * bw_[beat_in_bar][:, None], beat_in_bar, beta, pen)
    C = F["chroma"]
    names = FLATS if flats else SHARPS
    mix_mode = set(F["harm"]) == {"mix"}
    t_min, t_ratio = (0.35, 2.0) if mix_mode else (THIRD_MIN, 1.5)

    def shown(f, h):
        """Qualité affichée pour la famille f sur les temps h."""
        root, fq, mem = fams[f]
        best = labels[mem[int(np.argmax(E[np.ix_(h, mem)].mean(0)))]][1]
        c = C[h].mean(0)
        th = {"min": c[(root + 3) % 12], "maj": c[(root + 4) % 12]}
        if fq in ("min", "maj"):
            # 7e affichée seulement si elle l'emporte nettement sur l'accord parfait
            sev = "m7" if fq == "min" else "7"
            if best == sev and E[np.ix_(h, [labels.index((root, sev))])].mean() > \
                    E[np.ix_(h, [labels.index((root, fq))])].mean() + 0.03:
                return sev
            return fq
        if fq == "5" and simple:                       # tonalité muette : la tierce entendue
            hi = max(th, key=th.get)
            lo = "min" if hi == "maj" else "maj"
            if th[hi] >= t_min and th[hi] >= t_ratio * th[lo]:
                return hi
            return best
        return fq if fq != "5" else best

    def seg_info(f, h):
        if fams[f][0] is None:
            return NC, None, float(post[h, f].mean())
        q = shown(f, h)
        return _name(fams[f][0], q, flats), q, float(post[h, f].mean())

    # 1) famille majoritaire de chaque demi-mesure
    n_bars = len(a.downbeats) - 1
    halves_all = []
    for k in range(n_bars):
        idx = np.arange(k * m, min((k + 1) * m, nb))
        parts = [idx] if not half else [idx[:half], idx[half:]]
        segs = []
        for hi, h in enumerate(parts):
            if len(h) == 0:
                continue
            st, cnt = np.unique(path[h], return_counts=True)
            best = st[np.argmax(cnt)] if cnt.max() * 2 > len(h) else path[h[0]]
            segs.append([hi * (half or 0) + 1, int(best), h])
        halves_all.append((idx, segs))

    # 2) deux accords dans la mesure seulement si le changement est franc
    out = []
    for k, (idx, segs) in enumerate(halves_all):
        if len(segs) == 2:
            (b1, f1, h1), (b2, f2, h2) = segs
            n1 = seg_info(f1, h1)[0]
            n2, _, c2 = seg_info(f2, h2)
            nxt = halves_all[k + 1][1] if k + 1 < n_bars else None
            n_next = seg_info(nxt[0][1], nxt[0][2])[0] if nxt else None
            keep = (n1 != n2
                    and Ef[h2[0], f2] > Ef[h2[0], f1] + 0.04        # le temps 3 lui-même le confirme
                    and c2 >= 0.55
                    and not (n_next == n1 and c2 < 0.85))          # A-X-A : note de passage
            if not keep:
                segs = [[b1, f1, idx]]
        chords = []
        for beat, f, h in segs:
            name, q, conf = seg_info(f, h)
            if q is None:
                chords.append({"beat": beat, "chord": NC, "bass": None, "confidence": round(conf, 2)})
                continue
            root = fams[f][0]
            # basse : note dominante du segment si c'est une autre note de l'accord (renversement)
            bnote = root
            bw = F["bass"][h].sum(0) * F["bass_act"][h].mean()
            if bw.sum() > 0:
                cand = int(np.argmax(bw))
                tones = {(root + i) % 12 for i in QUALITIES[q][0]}
                if cand != root and cand in tones and bw[cand] >= 0.6 * bw.sum() \
                        and bw[root] < 0.25 * bw.sum():
                    bnote = cand
            if bnote != root:
                name = f"{name}/{names[bnote]}"
            chords.append({"beat": beat, "chord": name, "bass": names[bnote],
                           "confidence": round(min(1.0, conf), 2)})
        out.append({"bar": k + 1, "chords": chords})
    return out


# --------------------------------------------------------------------------- #
# Accords du modèle entraîné (chord_model) -> grille par mesure
# --------------------------------------------------------------------------- #
# qualité Harte -> suffixe affiché (vocabulaire complet)
HARTE_SUFFIX = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "5": "5", "1": "",
    "7": "7", "maj7": "maj7", "min7": "m7", "hdim7": "m7b5", "dim7": "dim7", "minmaj7": "m(maj7)",
    "maj6": "6", "min6": "m6", "9": "9", "maj9": "maj9", "min9": "m9", "11": "11", "13": "13",
    "sus2": "sus2", "sus4": "sus4", "sus4(b7)": "7sus4", "sus4(b7,9)": "9sus4", "7(#9)": "7#9",
    "maj(9)": "add9", "maj(*3)": "5",
}
# simplification « lisible en live » : les 9e, 11e et 13e se jouent comme la 7e correspondante
SIMPLE_SUFFIX = {"9": "7", "maj9": "maj7", "m9": "m7", "11": "7sus4", "13": "7", "9sus4": "7sus4",
                 "7#9": "7", "add9": "", "m(maj7)": "m"}
# degré de la basse (renversement) -> demi-tons au-dessus de la fondamentale
DEGREE = {"1": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5, "#4": 6, "b5": 6, "5": 7, "#5": 8, "b6": 8,
          "6": 9, "bb7": 9, "b7": 10, "7": 11, "9": 2, "b9": 1}
_PC = {n: i for i, n in enumerate(SHARPS)} | {n: i for i, n in enumerate(FLATS)} | {"Cb": 11, "Fb": 4, "E#": 5,
                                                                                  "B#": 0}


def parse_harte(label: str) -> tuple[int, str, int] | None:
    """« A:min/b3 » -> (fondamentale 9, qualité "min", basse 0) ; « N » / « X » -> None."""
    s = str(label or "").strip()
    if not s or s in ("N", "X") or ":" not in s and s[:1] not in "ABCDEFG":
        return None
    root, _, rest = s.partition(":")
    rest = rest or "maj"
    q, _, inv = rest.partition("/")
    if root not in _PC:
        return None
    r = _PC[root]
    bass = (r + DEGREE.get(inv, 0)) % 12 if inv else r
    return r, q or "maj", bass


def _suffix(q: str, simple: bool) -> str:
    suf = HARTE_SUFFIX.get(q)
    if suf is None:                     # qualité hors dictionnaire : couleur de la tierce
        suf = "m" if q.startswith("min") else "dim" if q.startswith("dim") else ""
    if simple:
        suf = SIMPLE_SUFFIX.get(suf, suf)
    return suf


def _tones(r: int, q: str) -> list[int]:
    base = {"min": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
            "hdim7": (0, 3, 6, 10), "dim7": (0, 3, 6, 9), "min7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11),
            "7": (0, 4, 7, 10), "min9": (0, 3, 7, 10, 2), "9": (0, 4, 7, 10, 2), "maj9": (0, 4, 7, 11, 2)}
    iv = base.get(q) or ((0, 3, 7) if q.startswith("min") else (0, 4, 7))
    return [(r + i) % 12 for i in iv]


def speller(kp: tuple[int, bool]):
    """Nom des notes selon la tonalité : notes de la gamme avec les altérations de la tonalité ; hors
    gamme, bémol pour les emprunts (bII, bIII, bVI, bVII en majeur) et dièse pour les notes « montantes »
    (#IV, sensible et 6te majeure du mineur, tierce du IV majeur emprunté en mineur…)."""
    tonic, minor = kp
    flats = _use_flats(tonic, minor)
    scale = {(tonic + d) % 12 for d in ((0, 2, 3, 5, 7, 8, 10) if minor else (0, 2, 4, 5, 7, 9, 11))}
    up = {(tonic + d) % 12 for d in ((1, 4, 6, 9, 11) if minor else (6,))}
    if minor:
        up.discard((tonic + 1) % 12)     # bII (napolitain) : bémol

    def name(pc: int) -> str:
        pc %= 12
        if pc in scale:
            return (FLATS if flats else SHARPS)[pc]
        return (SHARPS if pc in up else FLATS)[pc]
    return name


_LETTERS = "CDEFGAB"
_NAT = (0, 2, 4, 5, 7, 9, 11)
# intervalle (demi-tons) -> nombre de lettres au-dessus de la fondamentale (tierce = 2, quinte = 4…)
_STEPS = (0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6)


def spell_above(root_name: str, semis: int, fallback=None) -> str:
    """Note à `semis` demi-tons au-dessus de root_name, épelée comme intervalle de l'accord :
    E + 4 -> G# (et non Ab), Bb + 4 -> D, F# + 3 -> A. Altération double : fallback(pc) si fourni."""
    li = _LETTERS.index(root_name[0])
    rpc = _PC.get(root_name, _NAT[li])
    letter = _LETTERS[(li + _STEPS[semis % 12]) % 7]
    pc = (rpc + semis) % 12
    acc = (pc - _NAT[_LETTERS.index(letter)] + 6) % 12 - 6
    if acc in (-1, 0, 1):
        return letter + {-1: "b", 0: "", 1: "#"}[acc]
    return fallback(pc) if fallback else (SHARPS[pc])


def _segments_key(segs: list[tuple]) -> tuple[int, bool]:
    """Tonalité estimée sur les accords du modèle (notes des accords pondérées par la durée, basse double)."""
    ch, bs = np.zeros((1, 12)), np.zeros((1, 12))
    for st, en, p, _ in segs:
        if p is None:
            continue
        d = en - st
        for pc in _tones(p[0], p[1]):
            ch[0, pc] += d
        bs[0, p[2]] += d
    if ch.sum() <= 0:
        return 0, False
    return _estimate_key(ch, bs)


def chords_from_segments(a: Analysis, segments: list[dict], key: dict | str | None = None,
                         simple: bool = True, min_conf2: float = 0.35) -> list[dict]:
    """Segments du modèle [{start, end, label (Harte), confidence}] (temps du stem de référence) ->
    grille par mesure, même format que detect_chords : [{"bar", "chords": [{"beat", "chord", "bass",
    "confidence"}]}] ; au plus deux accords par mesure (temps 1 et temps du milieu en mesure paire).

    Chaque demi-mesure prend l'accord qui y dure le plus longtemps ; le 2e accord n'est gardé que s'il
    diffère du 1er, occupe plus de la moitié de sa demi-mesure et que sa confiance >= min_conf2.
    simple : 9e / 11e / 13e affichées comme la 7e correspondante (C9 -> C7, Cmaj9 -> Cmaj7…)."""
    segs = []
    for s in segments or []:
        try:
            st, en = float(s["start"]), float(s["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if en > st:
            segs.append((st, en, parse_harte(s.get("label")), float(s.get("confidence", 0.5) or 0.0)))
    segs.sort(key=lambda x: x[0])
    kp = parse_key(key) or _segments_key(segs)
    spell = speller(kp)
    m = max(1, int(a.beats_per_bar))
    half = m // 2 if m % 2 == 0 and m >= 4 else None
    db = [float(x) for x in a.downbeats]
    starts = np.array([s[0] for s in segs]) if segs else np.zeros(0)

    def tally(t0: float, t1: float) -> dict:
        """{étiquette: [durée, confiance × durée]} sur [t0, t1)."""
        out = {}
        i = max(0, int(np.searchsorted(starts, t0, side="right")) - 1)
        while i < len(segs) and segs[i][0] < t1:
            st, en, p, c = segs[i]
            ov = min(en, t1) - max(st, t0)
            if ov > 0:
                lab = None if p is None else (p[0], _suffix(p[1], simple), p[2])
                e = out.setdefault(lab, [0.0, 0.0])
                e[0] += ov
                e[1] += c * ov
            i += 1
        return out

    def best(tl: dict):
        if not tl:
            return None, 0.0, 0.0
        lab, (d, cd) = max(tl.items(), key=lambda kv: kv[1][0])
        return lab, d, cd / d if d > 0 else 0.0

    def entry(beat: int, lab, conf: float) -> dict:
        if lab is None:
            return {"beat": beat, "chord": NC, "bass": None, "confidence": round(min(1.0, conf), 2)}
        r, suf, b = lab
        rn = spell(r)
        bn = rn if b == r else spell_above(rn, (b - r) % 12, spell)      # renversement : note de l'accord
        name = rn + suf + ("" if b == r else "/" + bn)
        return {"beat": beat, "chord": name, "bass": bn, "confidence": round(min(1.0, conf), 2)}

    out = []
    for k in range(len(db) - 1):
        t0, t1 = db[k], db[k + 1]
        if not half:
            lab, d, c = best(tally(t0, t1))
            out.append({"bar": k + 1, "chords": [entry(1, lab, c if d > 0 else 0.0)]})
            continue
        tm = t0 + (t1 - t0) * half / m
        l1, d1, c1 = best(tally(t0, tm))
        l2, d2, c2 = best(tally(tm, t1))
        whole, dw, cw = best(tally(t0, t1))
        if l1 != l2 and d2 > 0.5 * (t1 - tm) and d1 > 0 and c2 >= min_conf2:
            chords = [entry(1, l1, c1), entry(half + 1, l2, c2)]
        else:
            chords = [entry(1, whole, cw if dw > 0 else 0.0)]
        out.append({"bar": k + 1, "chords": chords})
    return out


def model_chords(a: Analysis, items: list[dict] | None = None, key=None, simple: bool = True,
                 install_dir=None) -> tuple[list[dict], dict]:
    """Grille d'accords par le modèle entraîné (chord_model) ; lève une exception en cas d'échec."""
    from . import chord_model
    segs, info = chord_model.model_segments(a, _sources(a, items), install_dir)
    grid = chords_from_segments(a, segs, key, simple)
    if not grid:
        raise RuntimeError("empty")
    from .i18n import t
    return grid, {**info, "message": t("chords_model_used")}


def chords_cache_key(a: Analysis, items: list[dict] | None, key=None, engine: str = "reacue") -> str:
    """Clé de cache : fichiers + décalages + grille + tonalité + version de l'algorithme + moteur."""
    import hashlib
    import json
    srcs = _sources(a, items)
    k = parse_key(key)
    parts = [[s[1] for s in srcs], [round(s[2], 4) for s in srcs],
             [round(float(x), 4) for x in a.downbeats], a.beats_per_bar, list(k) if k else None, VERSION]
    if engine != "reacue":              # détection de ReaCue : clé inchangée (caches existants valables)
        from . import chord_model
        parts += [engine, chord_model.MODEL_REV, chord_model.CACHE_VERSION, chord_model.audio_key(
            chord_model.harmonic_sources(srcs))]
    return hashlib.md5(json.dumps(parts).encode()).hexdigest()


def cached_chords(a: Analysis, items: list[dict] | None, key=None, cache=None) -> list[dict]:
    """Grille d'accords avec cache disque (un seul morceau mémorisé, comme stem_activity).

    Moteur : le modèle entraîné (chord_model, composant facultatif) s'il est installé et que le réglage
    `chords_engine` vaut "auto" ; sinon, ou en cas d'échec, la détection de ReaCue (detect_chords).
    chord_model.LAST décrit le moteur utilisé (et l'erreur éventuelle)."""
    import json
    import sys
    from pathlib import Path
    from . import chord_model
    if chord_model.engine_setting() == "off":
        chord_model.LAST = {"engine": "off"}
        return []
    if cache is None:
        from .bridge import BRIDGE_DIR
        cache = BRIDGE_DIR / "prompter_chords.json"
    cache = Path(cache)
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        c = {}

    def save(ck, res):
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"key": ck, "chords": res}), encoding="utf-8")
        except OSError:
            pass
    info = {"engine": "reacue"}
    if chord_model.wanted():
        ck = chords_cache_key(a, items, key, chord_model.ENGINE)
        if c.get("key") == ck:
            chord_model.LAST = {"engine": chord_model.ENGINE, "cached": True}
            return c["chords"]
        try:
            res, info = model_chords(a, items, key)
            chord_model.LAST = info
            save(ck, res)
            return res
        except Exception as e:          # noqa: BLE001 - la détection de ReaCue prend le relais
            from .i18n import t
            info = {"engine": "reacue", "fallback": True, "error": str(e), "message": t("chords_model_failed", e=e)}
            print(info["message"], file=sys.stderr)
    ck = chords_cache_key(a, items, key)
    if c.get("key") == ck:
        chord_model.LAST = {**info, "cached": True}
        return c["chords"]
    res = detect_chords(a, items, key)
    chord_model.LAST = info
    save(ck, res)
    return res
