"""Analyse audio : tempo, temps, premiers temps de mesure et sections."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field, asdict

import numpy as np
import librosa
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.cluster.hierarchy import linkage, fcluster

from .i18n import t, section_color  # noqa: F401  (section_color : réexporté pour compatibilité)

SR = 22050
HOP = 512


@dataclass
class Section:
    start_bar: int          # index de mesure (0 = premier temps fort du morceau)
    end_bar: int            # exclu
    label: str              # lettre de groupe (A, B, C…) : même lettre = même musique
    name: str               # nom lisible (Intro, Couplet 1, Refrain 1…)
    energy_db: float = 0.0


@dataclass
class Analysis:
    file: str
    duration: float
    bpm: float                       # tempo moyen (noires/min)
    beats_per_bar: int
    denominator: int
    tempo_stable: bool
    tempo_cv: float                  # variation relative de la durée des mesures
    beats: list[float]               # secondes, temps du fichier
    downbeats: list[float]           # début de chaque mesure + fin de la dernière
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alt_bpm: float | None = None                 # autre octave de tempo plausible (moitié / double)
    stems: dict[str, str] = field(default_factory=dict)   # rôle -> fichier (mode multi-stems)
    vocal_activity: list[float] = field(default_factory=list)  # par mesure, 0..1

    @property
    def n_bars(self) -> int:
        return len(self.downbeats) - 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["n_bars"] = self.n_bars
        return d

    @staticmethod
    def from_dict(d: dict) -> "Analysis":
        d = dict(d)
        d.pop("n_bars", None)
        d["sections"] = [Section(**s) for s in d.get("sections", [])]
        return Analysis(**d)


# --------------------------------------------------------------------------- #
# Tempo et temps
# --------------------------------------------------------------------------- #
def _beats(y, sr, bpm_hint, start_bpm=None):
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    tempo, frames = librosa.beat.beat_track(
        onset_envelope=onset, sr=sr, hop_length=HOP,
        start_bpm=bpm_hint or start_bpm or 120.0, tightness=100, trim=False)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
    if bpm_hint and len(beats) > 4:
        est = 60.0 / np.median(np.diff(beats))
        ratio = est / bpm_hint
        if ratio > 1.6:                       # détecté au double : un temps sur deux
            beats = beats[::2]
        elif ratio < 0.625:                   # détecté à la moitié : on intercale
            mids = (beats[:-1] + beats[1:]) / 2
            beats = np.sort(np.concatenate([beats, mids]))
    return onset, beats


def _refine(y, sr, beats, before=0.06, after=0.03):
    """Recale chaque temps sur la vraie attaque (montée d'énergie la plus raide, résolution ~3 ms)."""
    hop = 64
    e = librosa.feature.rms(y=y, frame_length=256, hop_length=hop, center=True)[0]
    le = np.log(e + 1e-6)
    rise = np.diff(le, prepend=le[0])
    out = []
    for b in beats:
        a = max(0, int((b - before) * sr / hop))
        z = min(len(rise), int((b + after) * sr / hop) + 1)
        if z - a < 3 or rise[a:z].max() < 0.15:
            out.append(b)          # pas d'attaque nette : on garde la position détectée
            continue
        out.append(librosa.frames_to_time(a + int(np.argmax(rise[a:z])), sr=sr, hop_length=hop))
    out = np.array(out)
    return np.maximum.accumulate(out)


def _beat_features(y, sr, beats, y_low=None):
    """Indice "temps fort" par temps : attaque grave (grosse caisse/basse) + changement d'harmonie."""
    mel = librosa.feature.melspectrogram(y=y if y_low is None else y_low, sr=sr, hop_length=HOP,
                                         n_mels=64, fmax=8000)
    mel_db = librosa.power_to_db(mel)
    low = np.maximum(0, np.diff(mel_db[:6], axis=1, prepend=mel_db[:6, :1])).sum(axis=0)
    frames = librosa.time_to_frames(beats, sr=sr, hop_length=HOP)
    w = 2
    low_b = np.array([low[max(0, f - w): f + w + 1].max() if f < len(low) else 0 for f in frames])

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    cs = librosa.util.sync(chroma, np.concatenate([[0], frames]), aggregate=np.median)
    cs = cs[:, 1:len(frames) + 1] if cs.shape[1] > len(frames) else cs
    cs = cs / (np.linalg.norm(cs, axis=0, keepdims=True) + 1e-9)
    nov = np.zeros(len(frames))
    n = min(cs.shape[1], len(frames))
    nov[1:n] = 1 - np.sum(cs[:, 1:n] * cs[:, :n - 1], axis=0)

    def z(v):
        return (v - v.mean()) / (v.std() + 1e-9)
    return z(low_b) + 0.7 * z(nov)


def _downbeat_phase(score, meters):
    best = None
    for m in meters:
        for p in range(m):
            idx = np.arange(len(score))
            on = score[(idx - p) % m == 0]
            off = score[(idx - p) % m != 0]
            if len(on) < 2:
                continue
            s = on.mean() - off.mean()
            if m == 3:
                s *= 0.85        # léger avantage au 4/4, bien plus fréquent
            if best is None or s > best[0]:
                best = (s, m, p)
    return best[1], best[2]


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _bar_agg(X, frames, n_frames):
    """Moyenne par mesure des colonnes de X (trames)."""
    fr = np.clip(np.asarray(frames), 0, n_frames - 1)
    out = []
    for a, b in zip(fr[:-1], fr[1:]):
        b = max(b, a + 1)
        out.append(X[..., a:b].mean(axis=-1))
    return np.array(out)


def _bar_features(y, sr, downbeats):
    """Par mesure : chroma (CQT), timbre (MFCC), énergie (dB), densité d'attaques aiguës (batterie)."""
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    mel = librosa.power_to_db(librosa.feature.melspectrogram(S=S ** 2, sr=sr, n_mels=64))
    mfcc = librosa.feature.mfcc(S=mel, n_mfcc=13)[1:]
    rms = librosa.feature.rms(S=S)[0]
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    dens = _band_flux(S, f, 2000, 10000)
    n = min(chroma.shape[1], mfcc.shape[1], len(rms), len(dens))
    frames = librosa.time_to_frames(downbeats, sr=sr, hop_length=HOP)
    C = _bar_agg(chroma[:, :n], frames, n)
    M = _bar_agg(mfcc[:, :n], frames, n)
    E = 20 * np.log10(_bar_agg(rms[:n], frames, n) + 1e-9)
    D = _bar_agg(dens[:n], frames, n)
    low = (S[f < 160] ** 2).sum(axis=0)[:n]               # grave : grosse caisse + basse
    R = 10 * np.log10(_bar_agg(low, frames, n) + 1e-9)
    # part percussive (HPSS sur le mel, rapide) : présence de la batterie sans stem
    _, Pm = librosa.decompose.hpss(10 ** (mel / 10), kernel_size=31)
    P = 10 * np.log10(_bar_agg(Pm.sum(axis=0)[:n], frames, n) + 1e-9)
    return {"C": C, "M": M, "E": E, "D": D, "R": R, "P": P}


def _zs(X):
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    return (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9) / np.sqrt(X.shape[1])


def _kernel_novelty(F, L):
    Fn = F / (np.linalg.norm(F, axis=1, keepdims=True) + 1e-9)
    S = Fn @ Fn.T
    n = len(S)
    g = np.exp(-0.5 * (np.linspace(-1.5, 1.5, 2 * L) ** 2))
    K = np.outer(g, g) * np.kron([[1, -1], [-1, 1]], np.ones((L, L)))
    Sp = np.pad(S, L, mode="edge")
    nov = np.array([np.sum(Sp[i:i + 2 * L, i:i + 2 * L] * K) for i in range(n)])
    nov = np.maximum(nov, 0)
    return nov / (nov.max() + 1e-9)


def _novelty(G, energy):
    """Nouveauté multi-échelle (noyaux 2 / 4 / 8 mesures) + sauts d'énergie. Longueur n+1."""
    n = len(G)
    Ls = [L for L in (2, 4, 8) if 2 * L <= n] or [1]
    nov = sum(_kernel_novelty(G, L) for L in Ls) / len(Ls)
    e = np.abs(np.diff(gaussian_filter1d(energy, 0.7), prepend=energy[0]))
    nov = nov + 0.3 * e / (e.max() + 1e-9)
    return np.r_[nov, 0.0]


def _stop_bars(R):
    """Mesures d'arrêt : la section rythmique (grave / basse + batterie) chute pendant une mesure
    entre deux mesures pleines. Une telle mesure termine presque toujours une section : la
    suivante commence juste après. Retourne un poids 0..1 par mesure."""
    R = np.asarray(R, dtype=float)
    n = len(R)
    w = np.zeros(n)
    if n < 3:
        return w
    full = float(np.median(R)) - 3.0
    for i in range(1, n - 1):
        if min(R[i - 1], R[i + 1]) < full:
            continue
        d = min(R[i - 1], R[i + 1]) - R[i]
        w[i] = float(np.clip((d - 2.0) / 3.0, 0.0, 1.0))
    return w


def _phrase_bonus(L):
    """Préférence pour les carrures : 8 > 4 mesures ; 4k+1 toléré (mesure d'arrêt en fin de section)."""
    if L % 8 == 0:
        return 0.3
    if L % 4 == 0:
        return 0.2
    if L % 4 == 1 and L > 4:
        return 0.1
    return 0.0


def _segment_dp(nov, n, K, min_len=4, max_len=32):
    """K sections exactement : maximise Σ nouveauté aux frontières + bonus de carrure."""
    K = max(1, min(K, n // max(1, min_len)))
    max_len = max(max_len, int(math.ceil(n / K)) + min_len)
    NEG = -1e18
    best = np.full((K + 1, n + 1), NEG)
    prv = np.zeros((K + 1, n + 1), dtype=int)
    best[0, 0] = 0.0
    bonus = np.array([_phrase_bonus(L) for L in range(max_len + 1)])
    for j in range(1, K + 1):
        for b in range(min_len, n + 1):
            a0 = max(0, b - max_len)
            a1 = b - min_len
            if a1 < a0:
                continue
            cand = best[j - 1, a0:a1 + 1] + bonus[b - np.arange(a0, a1 + 1)]
            i = int(np.argmax(cand))
            if cand[i] <= NEG / 2:
                continue
            best[j, b] = cand[i] + (nov[b] if b < n else 0.0)
            prv[j, b] = a0 + i
    if best[K, n] <= NEG / 2:
        return [0, n]
    out, j = [n], K
    while j > 0:
        out.append(int(prv[j, out[-1]]))
        j -= 1
    return sorted(set(out[::-1]))


BARS_PER_SECTION = 9.0           # granularité de la segmentation (le nommage regroupe ensuite)
MAX_SECTIONS = 24


COSEG_THR = 0.7       # similarité diagonale (mesure à mesure) d'une vraie répétition
COSEG_LONG = 24      # au-delà, on cherche aussi les répétitions internes
COSEG_MIN = 8         # longueur mini de la section modèle


def _cosegment(bounds, X, min_len, n_fixed=0):
    """Co-segmentation : si une section longue commence (ou finit) par la répétition exacte, mesure à
    mesure, d'une autre section, on la coupe au même endroit. Les passages répétés sont ainsi
    découpés de la même façon, ce qui stabilise les étiquettes (un refrain d'un seul bloc ici,
    en deux moitiés là)."""
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    def dsim(a, b, L):
        return float(np.mean(np.sum(Xn[a:a + L] * Xn[b:b + L], axis=1)))
    bounds = sorted(set(bounds))
    for _ in range(20):
        segs = [(a, b) for a, b in zip(bounds[:-1], bounds[1:]) if a >= n_fixed]
        added = None
        for ta, tb in sorted(segs, key=lambda t: t[1] - t[0]):
            LT = tb - ta
            if LT < COSEG_MIN:
                continue
            for sa, sb in segs:
                if (sa, sb) == (ta, tb) or sb - sa < LT + min_len:
                    continue
                for cut, pos in ((sa + LT, sa), (sb - LT, sb - LT)):
                    if abs(pos - ta) >= LT and dsim(pos, ta, LT) >= COSEG_THR:
                        added = cut
                        break
                if added is None and sb - sa > COSEG_LONG:
                    # section longue : la répétition peut aussi se trouver à l'intérieur
                    best = max(((dsim(p, ta, LT), p) for p in range(sa + min_len, sb - LT - min_len + 1)
                                if abs(p - ta) >= LT), default=(0.0, None))
                    if best[0] >= COSEG_THR:
                        added = best[1]
                if added is not None:
                    break
            if added is not None:
                break
        if added is None:
            break
        bounds = sorted(set(bounds) | {added})
    return bounds


SECTION_PENALTY = 0.6    # coût d'une section supplémentaire (DP pénalisée ; None = nombre fixe)


def _segment_pen(nov, n, lam, min_len=4, max_len=32):
    """Découpage optimal à coût fixe par section : maximise Σ nouveauté aux frontières + bonus de
    carrure − lam × nombre de sections. Local : prolonger la fin ne bouleverse pas le début."""
    NEG = -1e18
    best = np.full(n + 1, NEG)
    prv = np.zeros(n + 1, dtype=int)
    best[0] = 0.0
    bonus = np.array([_phrase_bonus(L) for L in range(max_len + 1)])
    for b in range(min_len, n + 1):
        a0 = max(0, b - max_len)
        a1 = b - min_len
        if a1 < a0:
            continue
        cand = best[a0:a1 + 1] + bonus[b - np.arange(a0, a1 + 1)]
        i = int(np.argmax(cand))
        if cand[i] <= NEG / 2:
            continue
        best[b] = cand[i] + (nov[b] if b < n else 0.0) - lam
        prv[b] = a0 + i
    if best[n] <= NEG / 2:
        # fin non atteignable (morceau plus court que min_len ou trou) : une seule section
        return [0, n]
    out = [n]
    while out[-1] > 0:
        out.append(int(prv[out[-1]]))
    return sorted(set(out))


def _n_sections(n_bars):
    """Nombre de sections visé : ~1 par 12-13 mesures, 8 à 16 pour une chanson de 3-5 min."""
    return int(np.clip(round(n_bars / BARS_PER_SECTION), min(8, max(1, n_bars // 6)), MAX_SECTIONS))


CONTAIN_MIN = 8       # longueur mini pour la similarité « contenue » (0 = symétrique seulement)


def _block_sim(X, s1, s2, w=4):
    """Similarité de deux sections par blocs de 4 mesures (meilleur appariement, symétrique).
    Avec CONTAIN_MIN : si les deux sections font au moins CONTAIN_MIN mesures, on garde la meilleure
    des deux directions (une demi-section retrouvée entière dans une section complète)."""
    def blocks(a, b):
        B = [X[i:min(i + w, b)].mean(axis=0) for i in range(a, b, w) if min(i + w, b) - i >= 2]
        B = np.array(B) if B else X[a:b].mean(axis=0)[None]
        return B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    A, B = blocks(*s1), blocks(*s2)
    S = A @ B.T
    d1, d2 = S.max(axis=1).mean(), S.max(axis=0).mean()
    if CONTAIN_MIN and min(s1[1] - s1[0], s2[1] - s2[0]) >= CONTAIN_MIN:
        return max(d1, d2)
    return 0.5 * (d1 + d2)


VOC_SPLIT_DB = 1.5    # écart mini de niveau de chant entre deux groupes d'une même étiquette


def _split_by_voice(labels, segs, vlev, sung_floor):
    """Même harmonie, voix nettement plus forte : couplet et refrain peuvent partager la grille
    d'accords et ne différer que par le chant. Une étiquette dont les passages chantés forment deux
    groupes de niveau bien séparés (écart ≥ VOC_SPLIT_DB et ≥ 2 × l'étendue de chaque groupe)
    est scindée ; le groupe le plus fort reçoit une nouvelle lettre."""
    labels = list(labels)
    lv = [float(np.mean(vlev[a:b])) for a, b in segs]
    used = set(labels)
    for l in sorted(set(labels)):
        occ = sorted((lv[i], i) for i, x in enumerate(labels) if x == l and lv[i] > sung_floor)
        if len(occ) < 4:
            continue
        vals = [v for v, _ in occ]
        k = int(np.argmax(np.diff(vals))) + 1
        lo, hi = vals[:k], vals[k:]
        gap = vals[k] - vals[k - 1]
        if len(lo) < 2 or len(hi) < 2 or gap < VOC_SPLIT_DB or gap < 2 * max(lo[-1] - lo[0], hi[-1] - hi[0]):
            continue
        # les deux groupes doivent alterner (couplet / refrain) : des derniers passages simplement
        # chantés plus fort (montée finale) restent la même section
        if not any(i > min(j for _, j in occ[k:]) for _, i in occ[:k]):
            continue
        new = next(c for c in (chr(ord("A") + j) for j in range(26)) if c not in used)
        used.add(new)
        for _, i in occ[k:]:
            labels[i] = new
    return labels


def _label(X, segs, thr=0.5, join=0.62):
    if len(segs) == 1:
        return ["A"]
    n = len(segs)
    Sm = np.array([[_block_sim(X, s, t) for t in segs] for s in segs])
    D = np.clip(1 - (Sm + Sm.T) / 2, 0, 2)
    Z = linkage(D[np.triu_indices(n, 1)], method="average")
    ids = fcluster(Z, t=1 - thr, criterion="distance")
    # une section isolée rejoint le groupe répété le plus proche si elle lui ressemble nettement
    S2 = (Sm + Sm.T) / 2
    for i in range(n):
        if np.sum(ids == ids[i]) > 1:
            continue
        cand = [(S2[i, j], ids[j]) for j in range(n) if j != i and np.sum(ids == ids[j]) > 1]
        if cand:
            v, g = max(cand)
            if v >= join:
                ids[i] = g
    letters, out = {}, []
    for i in ids:
        if i not in letters:
            letters[i] = chr(ord("A") + len(letters)) if len(letters) < 26 else f"Z{len(letters)}"
        out.append(letters[i])
    return out


def _number(names):
    totals = {x: names.count(x) for x in names}
    seen, out = {}, []
    for x in names:
        seen[x] = seen.get(x, 0) + 1
        out.append(f"{x} {seen[x]}" if totals[x] > 1 else x)
    return out


VOC_RANGE_DB = 15.0   # plage utile du niveau de chant (sous le max)
PRE_MAX = 12          # longueur max d'un pré-refrain (8 + mesures de transition)
STOP_W = 0.6          # poids de l'indice « mesure d'arrêt » dans la nouveauté
RIFF_DROP_DB = 1.5    # sans voix : écart de niveau d'un riff instrumental sous le corps chanté
PERC_DROP_DB = 4.0    # sans stems : chute de la part percussive (dB) qui signale un break
SUNG_MIN = 0.3        # part de mesures chantées en dessous de laquelle une section est instrumentale


def _role_names(idx, segs, labels, seg_e, n_bars=None, pool=None):
    """Couplet / Refrain / Pré-refrain / Pont pour les sections chantées idx (répétition + énergie)."""
    labs = [labels[i] for i in idx]
    # nombre de passages : des segments consécutifs de même étiquette comptent pour un seul passage
    count = {}
    for k, i in enumerate(idx):
        if k == 0 or not (idx[k - 1] == i - 1 and labels[idx[k - 1]] == labels[i]):
            count[labels[i]] = count.get(labels[i], 0) + 1
    rep = [l for l in dict.fromkeys(labs) if count[l] >= 2]
    names = {}
    if not rep:
        for k, i in enumerate(idx):
            names[i] = "Couplet" if k == 0 else "Pont"
        return names
    n_bars = n_bars or segs[-1][1]
    e_all = np.array([seg_e[i] for i in idx])
    e_ref, e_sd = float(np.mean(e_all)), float(np.std(e_all)) + 0.5

    def chorus_score(l):
        own = [i for i in idx if labels[i] == l]
        bars = sum(segs[i][1] - segs[i][0] for i in own)
        e = sum(seg_e[i] * (segs[i][1] - segs[i][0]) for i in own) / bars
        # un refrain arrive dès la première moitié du morceau et revient vers la fin
        spread = float(any(segs[i][0] < 0.5 * n_bars for i in own)) + \
            float(any(segs[i][1] > 0.6 * n_bars for i in own))
        s = (e - e_ref) / e_sd + 0.5 * count[l] + 0.6 * spread
        if l == labs[0]:
            s -= 1.2                      # le premier passage chanté est plus souvent un couplet
        return s
    chorus = max(rep, key=chorus_score)
    first_ch = min(k for k, i in enumerate(idx) if labels[i] == chorus)
    first_seg = idx[first_ch]
    verse = None
    # suite du refrain : étiquette dont chaque passage chanté suit immédiatement un refrain (2e partie,
    # post-refrain) → même section que le refrain
    # (pool : toutes les sections nommables, chantées ou non ; une partie qui revient au moins deux
    # fois et toujours juste après le refrain appartient au bloc refrain)
    pool = sorted(set(pool or idx) | set(idx))
    cont = {chorus}
    changed = True
    while changed:
        changed = False
        for l in dict.fromkeys(labels[i] for i in pool):
            if l in cont or l == verse:
                continue
            occ = [i for i in pool if labels[i] == l]
            if any(i < first_seg for i in occ if i in idx):
                continue              # déjà chantée avant le 1er refrain : une partie à part entière
            if len(occ) >= 2 and all(i - 1 in pool and labels[i - 1] in cont | {l} for i in occ) \
                    and any(labels[i - 1] in cont for i in occ):
                cont.add(l)
                changed = True
    others = [l for l in rep if l not in cont]
    early = [l for l in others if any(labels[i] == l for i in idx[:first_ch])]
    verse = min(early or others, key=lambda l: labs.index(l)) if (early or others) else None
    # suite du couplet : un couplet est souvent fait de plusieurs phrases ; une phrase qui n'apparaît
    # que derrière le couplet (avant le dernier refrain) en fait partie
    vcont = {verse} if verse is not None else set()
    last_ch = max(i for i in idx if labels[i] in cont)
    changed = verse is not None
    while changed:
        changed = False
        for l in dict.fromkeys(labels[i] for i in pool):
            if l in vcont or l in cont:
                continue
            occ = [i for i in pool if labels[i] == l and i < last_ch]
            pre_like = all(segs[i][1] - segs[i][0] <= PRE_MAX and i + 1 in pool and labels[i + 1] in cont
                           for i in occ)          # toujours juste avant le refrain : pré-refrain
            if len(occ) >= 2 and not pre_like \
                    and all(i - 1 in pool and labels[i - 1] in vcont | {l} for i in occ) \
                    and any(labels[i - 1] in vcont for i in occ):
                vcont.add(l)
                changed = True
    for k, i in enumerate(idx):
        l = labels[i]
        L = segs[i][1] - segs[i][0]
        nxt = idx[k + 1] if k + 1 < len(idx) else None
        before_ch = nxt is not None and labels[nxt] == chorus and nxt == i + 1
        if l in cont:
            names[i] = "Refrain"
        elif before_ch and L <= PRE_MAX and l not in vcont:
            names[i] = "Pré-refrain"
        elif l in vcont:
            names[i] = "Couplet"
        elif l in others:
            pre = sum(1 for kk, j in enumerate(idx[:-1]) if labels[j] == l and labels[idx[kk + 1]] == chorus)
            names[i] = "Pré-refrain" if pre >= count[l] / 2 and L <= PRE_MAX else "Pont"
        else:
            names[i] = "Pont"
    return names


def _name_all(segs, labels, ctx):
    """Noms lisibles. ctx : E (dB/mesure), dens (attaques aiguës), vocal, lead_db, drums_db, pre_name."""
    n = len(segs)
    E = ctx["E"]
    seg_e = [float(np.mean(E[a:b])) for a, b in segs]
    lens = [b - a for a, b in segs]
    names = [None] * n
    first = 0
    if ctx.get("pre_name") and n > 1:
        names[0] = ctx["pre_name"]
        first = 1

    def seg_mean(v, i):
        a, b = segs[i]
        return float(np.mean(v[a:b]))
    vocal = ctx.get("vocal")
    has_voc = vocal is not None

    def sung_frac(i):
        """Part des mesures réellement chantées (voix présente sur au moins la moitié de la mesure)."""
        a, b = segs[i]
        return float(np.mean(vocal[a:b] >= 0.5)) if has_voc else 1.0

    # sans batterie au milieu du morceau : Break (instrumental) ou Pont (chanté, à décider plus bas)
    drums = ctx.get("drums_db")
    dens = ctx.get("dens")
    perc = ctx.get("perc")
    drumless = set()
    for i in range(first + 1, n - 1):
        if drums is not None:
            ref = float(np.median(drums[segs[first][0]:]))
            if seg_mean(drums, i) < ref - 15:
                drumless.add(i)
        elif perc is not None:                # sans stem batterie : part percussive du mix
            ref = float(np.median(perc[segs[first][0]:]))
            if seg_mean(perc, i) < ref - PERC_DROP_DB:
                drumless.add(i)
        elif dens is not None:
            ref = float(np.median([seg_mean(dens, j) for j in range(first, n)]))
            if seg_mean(dens, i) < 0.7 * ref and seg_e[i] < float(np.median(seg_e)) - 0.5:
                drumless.add(i)
    for i in drumless:
        names[i] = "Break"
    sung_drumless = [i for i in drumless if has_voc and sung_frac(i) >= 0.5]

    if has_voc:
        sung = [i for i in range(n) if names[i] is None and sung_frac(i) >= SUNG_MIN]
    else:
        sung = [i for i in range(n) if names[i] is None]
    # bords : avant le 1er passage chanté = Intro, après le dernier = Outro
    if has_voc and sung:
        for i in range(first, sung[0]):
            if names[i] is None:
                names[i] = "Intro"
        for i in range(sung[-1] + 1, n):
            if names[i] is None:
                names[i] = "Outro"
    elif not has_voc and n > 2:
        if names[first] is None and (lens[first] <= 8 or seg_e[first] < np.median(seg_e) - 3):
            names[first] = "Intro"
        if names[n - 1] is None and (lens[-1] <= 16 or seg_e[-1] < np.median(seg_e) - 3):
            names[n - 1] = "Outro"
        sung = [i for i in sung if names[i] is None]
    if not has_voc and len(sung) >= 4:
        # sans voix connue : un bloc court qui revient, nettement moins fort que le corps du morceau
        # (pas de chant par-dessus), est le riff instrumental
        body = float(np.median([seg_e[i] for i in sung]))
        for l in dict.fromkeys(labels[i] for i in sung):
            occ = [i for i in range(first, n) if labels[i] == l and i not in drumless]
            quiet = [i for i in occ if lens[i] <= 8 and seg_e[i] <= body - RIFF_DROP_DB]
            runs = sum(1 for k, i in enumerate(quiet) if k == 0 or quiet[k - 1] != i - 1)
            if runs >= 2 and sum(lens[i] for i in quiet) > sum(lens[i] for i in occ if i not in quiet):
                for i in quiet:
                    if names[i] is None:
                        names[i] = "Main Riff"
        sung = [i for i in sung if names[i] is None]
    pool = [i for i in range(first, n) if i not in drumless]
    roles = _role_names(sung, segs, labels, seg_e, segs[-1][1], pool) if sung else {}
    for i, nm in roles.items():
        names[i] = nm
    chorus = {labels[i] for i, nm in roles.items() if nm == "Refrain"}

    if not has_voc and roles:
        # sans voix connue : l'intro dure tant que sa musique continue ; après le dernier refrain,
        # les segments courts (ou de même musique que le dernier) forment l'outro
        k = first
        while names[k] == "Intro" and k + 1 < n and labels[k + 1] == labels[k] and k + 1 in roles:
            names[k + 1] = "Intro"
            k += 1
        last_ch = max((i for i in roles if roles[i] == "Refrain"), default=None)
        if last_ch is not None and names[n - 1] == "Outro":
            for i in range(n - 2, last_ch, -1):
                if i in roles and (lens[i] <= 8 or labels[i] == labels[n - 1]):
                    names[i] = "Outro"
                else:
                    break
    # un pont est une vraie section (≥ 8 mesures) ; un fragment unique plus court prolonge la
    # section chantée voisine de même niveau, sinon c'est un interlude
    for i in range(first, n):
        if names[i] == "Pont" and lens[i] < 8:
            if any(0 <= j < n and names[j] == "Pont" for j in (i - 1, i + 1)):
                continue                  # morceau d'un pont plus long : fusionné ensuite
            nb = [j for j in (i + 1, i - 1) if 0 <= j < n and names[j] in ("Couplet", "Refrain")
                  and abs(seg_e[j] - seg_e[i]) <= 1.0]
            names[i] = names[nb[0]] if nb else "Interlude"
    # Pont sans batterie : la partie chantée sans batterie est LE pont du morceau, sauf s'il en a déjà
    # un (un morceau a rarement deux ponts) : c'est alors un break chanté.
    if sung_drumless and "Pont" not in names:
        names[max(sung_drumless, key=lambda i: lens[i])] = "Pont"

    # dernière section, musique unique, après un refrain et nettement plus faible : outro (fondu,
    # ad-libs), pas un pont
    if n - 1 > first and names[n - 1] not in ("Outro", "Refrain") and labels.count(labels[n - 1]) == 1 \
            and "Refrain" in names[:n - 1] and seg_e[n - 1] < float(np.median(seg_e)) - 6:
        names[n - 1] = "Outro"
    # un « pré-refrain » qui s'étend sur plus de PRE_MAX mesures d'affilée est un pont (le pont
    # reprend souvent la grille du pré-refrain ou de l'intro)
    i = first
    while i < n:
        j = i
        while j + 1 < n and names[i] == "Pré-refrain" and names[j + 1] == "Pré-refrain":
            j += 1
        if names[i] == "Pré-refrain" and sum(lens[i:j + 1]) > PRE_MAX:
            for k in range(i, j + 1):
                names[k] = "Pont"
        i = j + 1
    # Pré-refrain : il porte ses propres paroles. Un bloc où la voix se tait presque (fin de phrase
    # puis anacrouse) avant le refrain est la queue du couplet, pas un pré-refrain.
    for i in range(first + 1, n):
        if names[i] == "Pré-refrain" and has_voc and sung_frac(i) < 0.5 and names[i - 1] == "Couplet":
            names[i] = "Couplet"

    # parties instrumentales restantes : Solo, queue de couplet, Main Riff, Interlude
    lead = ctx.get("lead_db")
    solo_thr = None
    if lead is not None and len(lead):
        solo_thr = max(float(np.median(lead)) + 3.0, float(np.percentile(lead, 90)) - 10.0)
    instr = [i for i in range(first, n) if names[i] in (None, "Intro", "Outro")]
    lab_count = {}
    for i in instr:
        lab_count[labels[i]] = lab_count.get(labels[i], 0) + 1
    riff_labels = {l for l, c in lab_count.items() if c >= 2 and l not in chorus}
    for i in range(n):
        if names[i] is not None:
            continue
        prev = names[i - 1] if i > 0 else None
        nxt = names[i + 1] if i + 1 < n else None
        if i == 0:
            names[i] = "Intro"
        elif i == n - 1:
            names[i] = "Outro"
        elif solo_thr is not None and seg_mean(lead, i) > solo_thr and lens[i] >= 4:
            names[i] = "Solo"
        elif prev == "Couplet" and nxt in ("Refrain", "Pré-refrain") and lens[i] <= 8:
            names[i] = "Couplet"          # mesures instrumentales entre couplet et refrain : fin du couplet
        elif labels[i] in riff_labels:
            names[i] = "Main Riff"
        elif prev == "Refrain" and lens[i] <= 8:
            names[i] = "Refrain"          # quelques mesures instrumentales qui terminent le refrain
        else:
            names[i] = "Interlude"
    # un segment court qui prolonge la même musique que la section précédente en garde le nom
    for i in range(first + 1, n - 1):
        if labels[i] == labels[i - 1] and lens[i] <= 4 and names[i] != names[i - 1] \
                and names[i - 1] in ("Break", "Pont", "Solo", "Main Riff", "Interlude"):
            names[i] = names[i - 1]
    # après une intro séparée (pré-roll), l'entrée du groupe sur le riff récurrent est le Main Riff
    if first == 1 and names[1] == "Intro" and labels[1] in riff_labels and \
            any(names[j] == "Main Riff" for j in range(2, n)):
        names[1] = "Main Riff"
    return names, seg_e


MAX_SECTION_BARS = 32  # garde-fou : une fusion ne crée jamais de section plus longue


def _merge_same(segs, labels, names):
    """Fusionne les sections voisines de même nom (un couplet coupé en deux, un refrain doublé…),
    sans dépasser MAX_SECTION_BARS : au-delà, deux passages successifs restent séparés."""
    out = []
    for s, l, nm in zip(segs, labels, names):
        if out and out[-1][2] == nm and s[1] - out[-1][0][0] <= MAX_SECTION_BARS:
            (a, _), l0, _ = out[-1]
            out[-1] = ((a, s[1]), l0, nm)
        else:
            out.append((s, l, nm))
    return [o[0] for o in out], [o[1] for o in out], [o[2] for o in out]


EQUALIZE = {"Pré-refrain": 4, "Refrain": 1}   # écart max (mesures) corrigé entre deux passages
EQ_MAX_LOSS = 0.15                              # perte de nouveauté tolérée pour déplacer une frontière


def _equalize(segs, names, nov, min_len):
    """Les passages d'un même pré-refrain ont la même longueur, ceux d'un refrain aussi à une mesure
    près (anacrouse) : on déplace le début du passage le plus long (ou le plus court) quand la
    nouveauté à la nouvelle frontière est presque aussi forte."""
    segs = [list(x) for x in segs]
    for typ, dmax in EQUALIZE.items():
        idx = [i for i, nm in enumerate(names) if nm == typ]
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                i, j = idx[x], idx[y]
                d = (segs[j][1] - segs[j][0]) - (segs[i][1] - segs[i][0])
                if d == 0 or abs(d) > dmax or (dmax > 1 and abs(d) % 4):
                    continue          # au-delà d'une mesure : seulement une phrase entière (4)
                longer, shorter = (j, i) if d > 0 else (i, j)
                cands = []
                for k, delta in ((longer, abs(d)), (shorter, -abs(d))):
                    if k == 0:
                        continue
                    a = segs[k][0]
                    new = a + delta
                    if new - segs[k - 1][0] < min_len or segs[k][1] - new < min_len:
                        continue
                    cands.append((float(nov[a] - nov[new]), k, new))
                if cands:
                    loss, k, new = min(cands)
                    if loss < EQ_MAX_LOSS:
                        segs[k][0] = new
                        segs[k - 1][1] = new
    return [tuple(x) for x in segs]


def stable_guess(cv: float) -> bool:
    return cv < 0.012


# --------------------------------------------------------------------------- #
# Grille droite (tempo constant) : peigne de Fourier + phase locale par fenêtres
# --------------------------------------------------------------------------- #
GHOP = 256                 # pas fin pour la pulsation (≈ 11.6 ms à 22050 Hz)
CONST_MAD_MS = 15.0        # écart médian toléré à la grille droite
CONST_INLIER_MS = 35.0     # écart max d'une fenêtre « en place »
CONST_INLIER_FRAC = 0.7    # part des fenêtres fortes qui doivent être en place


def _onset_env(y, sr, hop=GHOP):
    o = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    o = np.maximum(0.0, o - np.convolve(o, np.ones(64) / 64, "same"))   # sans la composante lente
    return o.astype(np.float64)


def _comb(o, h, bpm_lo, bpm_hi, step):
    """Tempo maximisant |Σ o(t) e^{-2iπt/p}| : énergie des attaques sur une grille droite."""
    t = np.arange(len(o)) * h
    bpms = np.arange(bpm_lo, bpm_hi + step / 2, step)
    z = np.array([np.dot(o, np.exp(-2j * np.pi * t * b / 60.0)) for b in bpms])
    i = int(np.argmax(np.abs(z)))
    return float(bpms[i]), z[i]


def _phase(z, period):
    return float((-np.angle(z) / (2 * np.pi)) * period % period)


def _local_phases(o, h, bpm, W):
    """Phase de la pulsation par fenêtre de W trames (recouvrement 1/2) : [(t, phase, force)]."""
    p = 60.0 / bpm
    t = np.arange(len(o)) * h
    e = np.exp(-2j * np.pi * t / p)
    out = []
    for a in range(0, max(1, len(o) - W + 1), W // 2):
        z = np.dot(o[a:a + W], e[a:a + W])
        out.append(((a + W / 2) * h, _phase(z, p), abs(z) / W))
    return out


def _straight_grid(o, h, bpm0, span):
    """Tempo fin + test « une seule grille droite explique tout le morceau ».
    Retourne (bpm, phase0, constant?, mad_ms, frac)."""
    bpm, _ = _comb(o, h, bpm0 - span, bpm0 + span, 0.02)
    bpm, z = _comb(o, h, bpm - 0.03, bpm + 0.03, 0.0005)
    p = 60.0 / bpm
    phi = _phase(z, p)
    W = max(8, int(32 * p / h))                    # ≈ 8 mesures de 4/4
    loc = _local_phases(o, h, bpm, W)
    if not loc:
        return bpm, phi, False, 1e9, 0.0
    mags = np.array([m for _, _, m in loc])
    strong = mags >= 0.35 * np.percentile(mags, 90)
    ts = np.array([t for t, _, _ in loc])[strong]
    dev = np.array([((ph - phi + p / 2) % p) - p / 2 for _, ph, _ in loc])[strong]
    w = mags[strong]
    # affinage robuste : droite sur les fenêtres en place seulement (pas sur tout ce qui a été suivi)
    for _ in range(3):
        inl = np.abs(dev) < CONST_INLIER_MS / 1000.0
        if inl.sum() < 3:
            break
        A = np.vstack([ts[inl], np.ones(inl.sum())]).T * w[inl, None]
        slope, icpt = np.linalg.lstsq(A, dev[inl] * w[inl], rcond=None)[0]
        p = p * (1 + slope)                 # dev(t) ≈ icpt + slope·t  →  vraie période p·(1+slope)
        phi = (phi + icpt) % p
        bpm = 60.0 / p
        loc = _local_phases(o, h, bpm, W)
        dev = np.array([((ph - phi + p / 2) % p) - p / 2 for _, ph, _ in loc])[strong]
    adev = np.abs(dev) * 1000
    frac = float(np.mean(adev < CONST_INLIER_MS))
    mad = float(np.median(adev))
    const = frac >= CONST_INLIER_FRAC and mad < CONST_MAD_MS and strong.sum() >= 3
    return bpm, phi, const, mad, frac


def _attack_offset(y, sr, grid, win=0.05):
    """Décalage médian entre la grille (enveloppe d'attaque, en retard) et la montée réelle du son."""
    hop = 32
    e = librosa.feature.rms(y=y, frame_length=256, hop_length=hop, center=True)[0]
    le = np.log(e + 1e-6)
    r = np.diff(le, prepend=le[0])
    offs = []
    for b in grid:
        a, z = int((b - win) * sr / hop), int((b + win) * sr / hop)
        if a < 0 or z >= len(r) or r[a:z].max() < 0.3:
            continue
        offs.append((a + int(np.argmax(r[a:z]))) * hop / sr - b)
    return float(np.median(offs)) if len(offs) >= 8 else 0.0


def _band_flux(S, freqs, lo, hi):
    B = np.log1p(10 * S[(freqs >= lo) & (freqs < hi)])
    return np.maximum(0, np.diff(B, axis=1, prepend=B[:, :1])).sum(axis=0)


def _beat_pos_features(y_drums, y_harm, sr, beats):
    """Par temps : grosse caisse (grave), caisse claire (médium-aigu), changement harmonique (basse/accords)."""
    S = np.abs(librosa.stft(y_drums, n_fft=2048, hop_length=HOP))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    kick, snare = _band_flux(S, f, 30, 150), _band_flux(S, f, 1000, 5000)
    idx = librosa.time_to_frames(beats, sr=sr, hop_length=HOP)
    idx = np.clip(idx[idx < len(kick) - 3], 0, None)          # garde l'indexation des temps
    K = np.array([kick[max(0, i - 1):i + 3].max() for i in idx])
    Sn = np.array([snare[max(0, i - 1):i + 3].max() for i in idx])
    C = librosa.feature.chroma_stft(y=y_harm, sr=sr, hop_length=HOP)
    cb = librosa.util.sync(C, np.unique(np.r_[0, idx]), aggregate=np.median)[:, 1:]
    if idx[0] == 0:
        cb = np.hstack([cb[:, :1], cb])
    cb = cb / (np.linalg.norm(cb, axis=0, keepdims=True) + 1e-9)
    H = np.zeros(len(idx))
    n = min(cb.shape[1], len(idx))
    H[1:n] = 1 - np.sum(cb[:, 1:n] * cb[:, :n - 1], axis=0)
    act = K + Sn > 0.2 * np.percentile(K + Sn, 90)
    return K, Sn, H, act


def _phase_scores(K, Sn, H, act, m):
    """Score de chaque phase de mesure p (le temps d'indice p est un « 1 »)."""
    def z(v):
        v = v[act] if act.sum() > 8 else v
        return v / (v.std() + 1e-9)
    idx = np.arange(len(K))[act] if act.sum() > 8 else np.arange(len(K))
    Kz, Sz, Hz = z(K), z(Sn), z(H)
    def pos_mean(v):
        return np.array([v[(idx % m) == j].mean() if np.any((idx % m) == j) else 0.0 for j in range(m)])
    k, s, hh = pos_mean(Kz), pos_mean(Sz), pos_mean(Hz)
    out = []
    for p in range(m):
        r = lambda j: (p + j) % m
        if m == 4:
            sc = (k[r(0)] + k[r(2)] - k[r(1)] - k[r(3)]) + (s[r(1)] + s[r(3)] - s[r(0)] - s[r(2)]) \
                + 2.0 * (hh[r(0)] - hh[r(2)]) + 0.5 * (k[r(0)] - k[r(2)])
        else:
            others = [r(j) for j in range(1, m)]
            sc = (k[r(0)] - np.mean(k[others])) + (np.mean(s[others]) - s[r(0)]) \
                + 2.0 * (hh[r(0)] - np.mean(hh[others]))
        out.append(float(sc))
    return out


def _active_frames(y, sr, rel_db=35.0):
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    d = 20 * np.log10(rms + 1e-9)
    ref = np.percentile(d, 95)
    return d > ref - rel_db


def _music_span(ys, sr):
    """Début / fin de la musique (premier / dernier instant où un des signaux est actif)."""
    st, en = None, None
    for y in ys:
        a = np.where(_active_frames(y, sr))[0]
        if len(a) == 0:
            continue
        s0 = librosa.frames_to_time(a[0], sr=sr, hop_length=HOP)
        e0 = librosa.frames_to_time(a[-1], sr=sr, hop_length=HOP)
        st = s0 if st is None else min(st, s0)
        en = e0 if en is None else max(en, e0)
    return st or 0.0, en


def _try_constant_grid(y_beat, y_drums, y_harm, sr, dur, beats_per_bar, denominator, bpm0, span,
                       warnings, preroll_sources=None):
    """Grille droite si le morceau la supporte, sinon None. preroll_sources : [(rôle, signal)]."""
    o = _onset_env(y_beat, sr)
    h = GHOP / sr
    bpm, phi, const, mad, frac = _straight_grid(o, h, bpm0, span)
    if not const:
        return None, (bpm, mad, frac)
    p = 60.0 / bpm
    phi = phi + _attack_offset(y_beat, sr, np.arange(phi, dur, p))
    phi = phi % p
    grid = np.arange(phi, dur, p)

    # mesure et phase des premiers temps
    K, Sn, H, act = _beat_pos_features(y_drums, y_harm, sr, grid)
    if beats_per_bar:
        m = beats_per_bar
        sc = _phase_scores(K, Sn, H, act, m)
    else:
        s4, s3 = _phase_scores(K, Sn, H, act, 4), _phase_scores(K, Sn, H, act, 3)
        m, sc = (4, s4) if max(s4) >= 0.85 * max(s3) else (3, s3)
    pb = int(np.argmax(sc))
    bar = m * p
    first_db = grid[pb] if pb < len(grid) else phi
    first_db = first_db % bar                     # grille de mesures prolongée jusqu'au début du fichier

    # début et fin réels : mesure où démarre la pulsation, éventuelle intro avant (pré-roll)
    beat_act = _active_frames(y_beat, sr, 30.0)
    bfr = np.where(beat_act)[0]
    beat_start = librosa.frames_to_time(bfr[0], sr=sr, hop_length=HOP) if len(bfr) else 0.0
    srcs = preroll_sources or [("mix", y_harm)]
    music_start, music_end = _music_span([y for _, y in srcs] + [y_beat], sr)
    if music_end is None:
        music_end = dur
    tol = 0.25 * bar
    k_beat = math.ceil((beat_start - tol - first_db) / bar)
    bar1_beat = first_db + max(0, k_beat) * bar
    bar1 = bar1_beat
    pre_role = None
    k_mus = math.ceil((music_start - tol - first_db) / bar)
    bar1_mus = first_db + max(0, k_mus) * bar
    n_pre = int(round((bar1_beat - bar1_mus) / bar))
    if n_pre >= 2:
        # cohérence rythmique : les attaques du pré-roll tombent sur la grille (croches comprises)
        best = None
        for role, y in srcs:
            oo = _onset_env(y[int(bar1_mus * sr): int(bar1_beat * sr)], sr)
            if oo.sum() <= 0:
                continue
            z = np.dot(oo, np.exp(-2j * np.pi * np.arange(len(oo)) * h / (p / 2)))
            conc = abs(z) / (oo.sum() + 1e-9)
            dphase = ((_phase(z, p / 2) + p / 4) % (p / 2)) - p / 4
            en = float(np.sum(y[int(bar1_mus * sr): int(bar1_beat * sr)] ** 2))
            if best is None or en > best[0]:
                best = (en, role, conc, dphase)
        if best and best[2] > 0.15 and abs(best[3]) < 0.2 * p:
            bar1 = bar1_mus
            pre_role = best[1]
        else:
            warnings.append(t("intro_off_tempo"))
    n_bars = int(math.floor((music_end + 0.25 * bar - bar1) / bar + 1e-9))
    n_bars = max(1, min(n_bars, int(math.floor((dur - bar1) / bar + 0.5))))
    downbeats = bar1 + bar * np.arange(n_bars + 1)
    beats = bar1 + p * np.arange(n_bars * m + 1)
    bpm_out = 60.0 * m / bar * (denominator / 4)
    cv = mad / 1000.0 / bar
    info = {"pre_bars": int(round((bar1_beat - bar1) / bar)), "pre_role": pre_role}
    return (beats, m, downbeats, bpm_out, True, cv, info), (bpm, mad, frac)


def _bpm_prior(y_beat, sr, bpm_hint, start_bpm, tracked_beats=None):
    if bpm_hint:
        return float(bpm_hint), max(1.5, 0.02 * bpm_hint)
    if tracked_beats is None:
        _, beats = _beats(y_beat, sr, None, start_bpm)
    else:
        beats = tracked_beats
    if len(beats) < 8:
        return None, None
    b = 60.0 / float(np.median(np.diff(beats)))
    return b, 0.05 * b               # le suivi est quantifié (~2 %) : on cherche large


def _build_grid(y_beat, y_feat, sr, dur, beats_per_bar, denominator, bpm_hint, warnings,
                y_low=None, start_bpm=None, y_drums=None, y_harm=None, preroll_sources=None):
    """Temps, premiers temps de mesure, tempo moyen et stabilité.
    1) grille droite si une seule droite explique la pulsation ; 2) sinon carte de tempo (suivi)."""
    # The constant-grid prior and the variable-tempo fallback use the same tracker.
    # Keep its result for this call instead of tracking the whole song twice.
    tracked_beats = None
    if not bpm_hint:
        _, tracked_beats = _beats(y_beat, sr, None, start_bpm)
    bpm0, span = _bpm_prior(y_beat, sr, bpm_hint, start_bpm, tracked_beats)
    if bpm0:
        res, diag = _try_constant_grid(y_beat, y_drums if y_drums is not None else y_beat,
                                       y_harm if y_harm is not None else y_feat, sr, dur,
                                       beats_per_bar, denominator, bpm0, span, warnings,
                                       preroll_sources)
        if res is not None:
            return res
    beats, m, downbeats, bpm, stable, cv = _build_grid_tracked(
        y_beat, y_feat, sr, dur, beats_per_bar, denominator, bpm_hint, warnings, y_low, start_bpm,
        tracked_beats=tracked_beats)
    return beats, m, downbeats, bpm, False, max(cv, 0.0121), {"pre_bars": 0, "pre_role": None}


def _build_grid_tracked(y_beat, y_feat, sr, dur, beats_per_bar, denominator, bpm_hint, warnings,
                        y_low=None, start_bpm=None, tracked_beats=None):
    """Carte de tempo à partir du suivi des temps (morceaux à tempo variable)."""
    if tracked_beats is None:
        _, beats = _beats(y_beat, sr, bpm_hint, start_bpm)
    else:
        beats = tracked_beats
    if len(beats) < 8:
        raise ValueError(t("too_few_beats"))

    beats = _refine(y_beat, sr, beats)
    score = _beat_features(y_feat, sr, beats, y_low=y_low)
    meters = [beats_per_bar] if beats_per_bar else [4, 3]
    m, phase = _downbeat_phase(score, meters)
    db = beats[phase::m]
    rms = librosa.feature.rms(y=y_feat, hop_length=HOP)[0]
    rdb = 20 * np.log10(rms + 1e-9)
    loud = np.where(rdb > rdb.max() - 30)[0]
    music_end = librosa.frames_to_time(loud[-1], sr=sr, hop_length=HOP) if len(loud) else dur
    med0 = float(np.median(np.diff(db)))
    db = db[db < music_end - 0.25 * med0]
    bar_d = np.diff(db)
    med = float(np.median(bar_d))
    last_end = db[-1] + med
    if last_end > dur + 0.5 * med:
        db = db[:-1]
        last_end = db[-1] + med
    downbeats = np.append(db, last_end)
    if len(downbeats) < 3:
        raise ValueError(t("too_short"))
    bar_d = np.diff(downbeats[:-1]) if len(downbeats) > 3 else np.diff(downbeats)
    core = bar_d[(bar_d > 0.8 * med) & (bar_d < 1.25 * med)]
    cv = float(np.std(core) / np.mean(core)) if len(core) > 2 else 0.0
    if len(core) < 0.8 * len(bar_d):
        warnings.append(t("irregular_pulse"))
    bpm = 60.0 * m / med * (denominator / 4)
    return beats, m, downbeats, bpm, False, cv


def _sections(feats, min_section_bars=4, stem_cols=None, n_pre=0, pre_name=None,
              vocal=None, lead_db=None, drums_db=None, voc_db=None):
    """Découpage + étiquettes + noms. feats : sortie de _bar_features ; stem_cols : (n, k) niveaux des stems."""
    E = feats["E"]
    n = len(E)
    parts = [_zs(feats["C"]), _zs(feats["M"])]
    if stem_cols is not None:
        parts.append(2.0 * _zs(stem_cols))
    G = np.hstack(parts)
    min_len = max(2, int(min_section_bars or 4))
    nov = _novelty(G, E)
    stop = _stop_bars(feats["R"]) if "R" in feats else np.zeros(n)
    nov[1:n + 1] += STOP_W * stop                 # frontière juste après la mesure d'arrêt…
    nov[:n] *= 1 - 0.7 * stop                     # …et pas juste avant
    if n < 2 * min_len:
        bounds = [0, n]
    else:
        n_pre = n_pre if 2 <= n_pre <= n - 2 * min_len else 0
        if SECTION_PENALTY is not None:
            body = _segment_pen(nov[n_pre:], n - n_pre, SECTION_PENALTY, min_len=min_len)
        else:
            body = _segment_dp(nov[n_pre:], n - n_pre, _n_sections(n - n_pre), min_len=min_len)
        bounds = sorted(set(([0] if n_pre else []) + [x + n_pre for x in body]))
    Xl = np.hstack([_zs(feats["C"]), 0.5 * _zs(feats["M"])])
    vlev = None
    if voc_db is not None and len(voc_db) == n:
        # niveau de chant (plancher à -15 dB sous le maximum) : à harmonie égale, un refrain se
        # distingue souvent du couplet par une voix plus forte
        top = float(np.percentile(voc_db, 95))
        vlev = np.clip(voc_db, top - VOC_RANGE_DB, top)
    if n >= 2 * min_len:
        bounds = _cosegment(bounds, Xl, min_len, n_fixed=n_pre if n_pre else 0)
    segs = list(zip(bounds[:-1], bounds[1:]))
    labels = _label(Xl, segs)
    if vlev is not None:
        labels = _split_by_voice(labels, segs, vlev, float(np.max(vlev)) - VOC_RANGE_DB + 3)
    ctx = {"E": E, "dens": feats.get("D"), "perc": feats.get("P"), "vocal": vocal, "lead_db": lead_db, "drums_db": drums_db,
           "pre_name": pre_name if n_pre else None}
    names, _ = _name_all(segs, labels, ctx)
    segs, labels, names = _merge_same(segs, labels, names)
    segs = _equalize(segs, names, nov, min_len)
    seg_e = [float(np.mean(E[a:b])) for a, b in segs]
    names = _number(names)
    return [Section(int(a), int(b), l, nm, round(e, 1)) for (a, b), l, nm, e in zip(segs, labels, names, seg_e)]


def _mix_inputs(y, sr, downbeats, ginfo):
    """Entrées de _sections en mode fichier unique (sans stems)."""
    feats = _bar_features(y, sr, downbeats)
    pre = ginfo.get("pre_bars", 0)
    return {"feats": feats, "n_pre": pre, "pre_name": "Intro" if pre else None}


def analyze(path: str, beats_per_bar: int | None = None, denominator: int = 4,
            bpm_hint: float | None = None, min_section_bars: int = 4) -> Analysis:
    y, sr = librosa.load(path, sr=SR, mono=True)
    dur = len(y) / sr
    warnings = []

    beats, m, downbeats, bpm, stable, cv, ginfo = _build_grid(
        y, y, sr, dur, beats_per_bar, denominator, bpm_hint, warnings)

    inp = _mix_inputs(y, sr, downbeats, ginfo)
    sections = _sections(min_section_bars=min_section_bars, **inp)

    return Analysis(
        file=path, duration=round(dur, 3), bpm=round(bpm, 3), beats_per_bar=m,
        denominator=denominator, tempo_stable=bool(stable), tempo_cv=round(cv, 5),
        beats=[round(float(b), 4) for b in beats],
        downbeats=[round(float(d), 4) for d in downbeats],
        sections=sections, warnings=warnings)


# --------------------------------------------------------------------------- #
# Plusieurs stems (un fichier par instrument)
# --------------------------------------------------------------------------- #
_ROLE_WORDS = (       # ordre = priorité (le chant avant la guitare : « lead vox » n'est pas une guitare)
    ("vocals", ("vocals", "vocal", "voice", "voices", "voix", "chant", "lead vox", "leadvox", "vox")),
    ("drums", ("drums", "drum", "batterie", "batt", "percussion", "percussions", "perc", "kick")),
    ("bass", ("bass", "basse")),
    ("guitars", ("guitars", "guitar", "guitares", "guitare", "gtr", "guit")),
)


def classify_stem(path: str) -> str:
    """Rôle d'un stem d'après son nom de fichier : drums, vocals, bass, lead_guitar, guitars, other."""
    name = os.path.splitext(os.path.basename(str(path)))[0].lower()
    norm = re.sub(r"[^a-zA-Z0-9\u00C0-\u017F]+", " ", name).strip()
    for role, words in _ROLE_WORDS:
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", norm, re.IGNORECASE):
                if role == "guitars" and ("lead" in norm or "solo" in norm):
                    return "lead_guitar"
                return role
    return "other"


def assign_roles(files: list[str]) -> list[str]:
    """Rôle par fichier ; un rôle déjà pris reçoit un suffixe (« guitars_2 »)."""
    seen, out = {}, []
    for f in files:
        r = classify_stem(f)
        seen[r] = seen.get(r, 0) + 1
        out.append(r if seen[r] == 1 else f"{r}_{seen[r]}")
    return out


def reference_index(files: list[str]) -> int:
    """Stem de référence : la batterie si elle est identifiable, sinon le premier."""
    roles = assign_roles(files)
    return roles.index("drums") if "drums" in roles else 0


def bpm_from_filenames(files: list[str]) -> float | None:
    for f in files:
        m = re.search(r"(?<![\d.])(\d{2,3}(?:[.,]\d+)?)\s*bpm", os.path.basename(str(f)), re.I)
        if m:
            v = float(m.group(1).replace(",", "."))
            if 40 <= v <= 300:
                return v
    return None


def _place(y, shift, sr, n):
    off = int(round(shift * sr))
    out = np.zeros(n, dtype=np.float32)
    seg = y[:max(0, n - off)] if off >= 0 else y[-off:][:n]
    if off >= 0:
        out[off:off + len(seg)] = seg
    else:
        out[:len(seg)] = seg
    return out


def _bar_db(y, sr, downbeats, floor=-90.0):
    """Niveau moyen (dB) par mesure."""
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    frames = librosa.time_to_frames(downbeats, sr=sr, hop_length=HOP)
    n = len(rms)
    out = []
    for a, b in zip(frames[:-1], frames[1:]):
        a = min(a, n - 1)
        b = min(max(b, a + 1), n)
        out.append(max(floor, 20 * np.log10(np.mean(rms[a:b]) + 1e-9)))
    return np.array(out)


def _frame_db(y):
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    return 20 * np.log10(rms + 1e-9)


def _vocal_activity(y, sr, downbeats, window_db=20.0, d=None):
    """Part de chaque mesure où le chant dépasse (90e centile de son propre niveau - 20 dB) :
    seuil relatif au niveau actif du stem, la repisse (bleed) des autres instruments est ignorée."""
    rdb = _frame_db(y) if d is None else d
    if rdb.max() < -80:
        return np.zeros(len(downbeats) - 1)
    act = (rdb > np.percentile(rdb, 90) - window_db).astype(float)
    frames = librosa.time_to_frames(downbeats, sr=sr, hop_length=HOP)
    return _bar_agg(act, frames, len(act))


def _stem_levels(d, sr, downbeats, span=40.0):
    """Niveau par mesure d'un stem, ramené à 0..1 sur [p95 - 40 dB, p95]."""
    top = float(np.percentile(d, 95))
    frames = librosa.time_to_frames(downbeats, sr=sr, hop_length=HOP)
    lv = _bar_agg(np.clip(d, top - span, top), frames, len(d))
    return (lv - (top - span)) / span


PRE_NAMES = {"guitars": "Intro guitare", "lead_guitar": "Intro guitare", "bass": "Intro basse",
             "other": "Intro claviers", "vocals": "Intro voix"}


def _dominant_pre(levels_db, n_pre):
    """Stem qui domine les n_pre premières mesures (≥ 10 dB au-dessus des autres), sinon None."""
    if n_pre <= 0 or len(levels_db) < 2:
        return None
    m = {r: float(np.mean(v[:n_pre])) for r, v in levels_db.items()}
    order = sorted(m, key=m.get, reverse=True)
    if m[order[0]] - m[order[1]] >= 10:
        return order[0].split("_")[0] if order[0].split("_")[0] in PRE_NAMES else order[0]
    return None


def _stems_inputs(by_role, mix, downbeats, ginfo):
    """Entrées de _sections en mode stems (caractéristiques par mesure)."""
    feats = _bar_features(mix, SR, downbeats)
    fdb = {r: _frame_db(p) for r, p in by_role.items()}
    stem_cols = np.array([_stem_levels(fdb[r], SR, downbeats) for r in sorted(by_role)]).T
    vocal = lead_db = drums_db = None
    voc_act = []
    if "vocals" in by_role:
        raw = _vocal_activity(by_role["vocals"], SR, downbeats, d=fdb["vocals"])
        if raw.max() > 0:
            vocal = gaussian_filter1d(raw, 0.5, mode="nearest")
            voc_act = [round(float(v), 3) for v in vocal]
            stem_cols = np.hstack([stem_cols, raw[:, None]])
    frames = librosa.time_to_frames(downbeats, sr=SR, hop_length=HOP)
    bar_db = {r: 20 * np.log10(_bar_agg(10 ** (d / 20), frames, len(d)) + 1e-9) for r, d in fdb.items()}
    if "lead_guitar" in bar_db:
        lead_db = bar_db["lead_guitar"]
    if "drums" in by_role:
        drums_db = bar_db["drums"]
    rh = [r for r in ("bass", "drums") if r in bar_db]
    if rh:                                                # section rythmique : basse + batterie
        feats["R"] = 10 * np.log10(sum(10 ** (bar_db[r] / 10) for r in rh) + 1e-12)
    pre = ginfo.get("pre_bars", 0)
    pre_name = None
    if pre:
        dom = _dominant_pre({r: v for r, v in bar_db.items() if r != "drums"}, pre)
        pre_name = PRE_NAMES.get(dom, "Intro") if dom else "Intro"
    voc_db = bar_db["vocals"] if vocal is not None else None
    return {"feats": feats, "stem_cols": stem_cols, "n_pre": pre, "pre_name": pre_name,
            "vocal": vocal, "lead_db": lead_db, "drums_db": drums_db, "voc_act": voc_act,
            "voc_db": voc_db}



def analyze_stems(stems: list[dict], beats_per_bar: int | None = None, denominator: int = 4,
                  bpm_hint: float | None = None, min_section_bars: int = 4) -> Analysis:
    """Analyse d'un morceau découpé en stems : [{"file": chemin, "shift": secondes}, …].
    shift = position du t=0 de ce fichier par rapport au t=0 du stem de référence (batterie si
    présente, sinon le premier). Les temps de l'Analysis sont dans le temps du stem de référence."""
    if not stems:
        raise ValueError(t("no_stem"))
    files = [str(s["file"]) for s in stems]
    roles = assign_roles(files)
    ref = reference_index(files)
    base = float(stems[ref].get("shift", 0.0) or 0.0)
    shifts = [float(s.get("shift", 0.0) or 0.0) - base for s in stems]   # re-référencé sur le stem de réf.
    warnings = []

    ys = [librosa.load(f, sr=SR, mono=True)[0] for f in files]
    n = max(len(ys[ref]), max(len(y) + max(0, int(round(sh * SR))) for y, sh in zip(ys, shifts)))
    placed = [_place(y, sh, SR, n) for y, sh in zip(ys, shifts)]
    mix = np.sum(placed, axis=0)
    mix = (mix / (np.abs(mix).max() + 1e-9)).astype(np.float32)
    dur = n / SR
    by_role = {r: p for r, p in zip(roles, placed)}

    if bpm_hint is None:
        bpm_hint = bpm_from_filenames(files)
        if bpm_hint:
            warnings.append(t("bpm_from_name", bpm=bpm_hint))
    has_drums = "drums" in by_role
    y_beat = by_role["drums"] if has_drums else mix
    harm = [by_role[r] for r in ("bass",) if r in by_role]
    y_harm = harm[0] if harm else mix
    pre_src = [(r, p) for r, p in by_role.items() if r != "drums"] or [("mix", mix)]
    beats, m, downbeats, bpm, stable, cv, ginfo = _build_grid(
        y_beat, mix, SR, dur, beats_per_bar, denominator, bpm_hint, warnings,
        y_low=None, start_bpm=150.0, y_drums=y_beat, y_harm=y_harm, preroll_sources=pre_src)

    alt = bpm / 2 if bpm >= 100 else bpm * 2
    alt_bpm = round(alt, 2) if 40 <= alt <= 260 else None
    if alt_bpm and not bpm_hint:
        warnings.append(t("tempo_octave", bpm=bpm, alt=alt_bpm))

    inp = _stems_inputs(by_role, mix, downbeats, ginfo)
    voc_act = inp.pop("voc_act")
    sections = _sections(min_section_bars=min_section_bars, **inp)

    return Analysis(
        file=files[ref], duration=round(dur, 3), bpm=round(bpm, 3), beats_per_bar=m,
        denominator=denominator, tempo_stable=bool(stable), tempo_cv=round(cv, 5),
        beats=[round(float(b), 4) for b in beats],
        downbeats=[round(float(d), 4) for d in downbeats],
        sections=sections, warnings=warnings, alt_bpm=alt_bpm,
        stems={r: f for r, f in zip(roles, files)}, vocal_activity=voc_act)


def resection(a: Analysis, sections: list[dict]) -> Analysis:
    """Remplace les sections : liste de {start_bar (1 = 1re mesure), name}."""
    items = sorted(sections, key=lambda s: int(s["start_bar"]))
    if not items:
        raise ValueError(t("empty_sections"))
    starts = [max(0, int(s["start_bar"]) - 1) for s in items]
    starts[0] = 0
    ends = starts[1:] + [a.n_bars]
    out = []
    for s, st, en in zip(items, starts, ends):
        if en <= st:
            raise ValueError(t("bad_section", name=s["name"]))
        out.append(Section(st, en, s.get("label", "?"), s["name"], 0.0))
    a.sections = out
    return a
