"""Transcription de la batterie par mesure pour le prompteur des musiciens (vue « batteur »).

Deux moteurs, même format de sortie (cf. prompter.build_song) :
  - ADTOF (modèle entraîné sur 359 h de musique réelle, composant facultatif .venv-drums, lancé en
    sous-processus par reacue_drums.py) : coups de grosse caisse, caisse claire, toms, charley,
    cymbales ; le signal du stem précise toms aigu/médium/basse, charley fermé/ouvert, crash/ride ;
    quantification sur la grille de ReaCue (double-croches ou triolets selon le morceau), puis motifs,
    fills et crashs comme ci-dessous (from_model) ;
  - règles sur le signal (repli, ou réglage drums_engine = « reacue »), décrites ici.

Méthode par règles (librosa / numpy uniquement, quelques secondes) :
  1. stem batterie (obligatoire : sur un mix, la transcription n'est pas fiable) placé dans le temps
     du stem de référence ; STFT fine (hop 128 à 22 050 Hz, ~6 ms) ;
  2. grille à la double-croche (16 pas par mesure en 4/4) ; décalage global attaque/grille estimé ;
     à chaque pas, « saut » d'énergie (dB, max après − niveau juste avant) par bande :
       grosse caisse 40-110 Hz, corps caisse claire/toms 120-450 Hz, timbre caisse claire 1,5-5 kHz,
       cymbales 7-11 kHz ;
  3. classement : BD = saut grave ; SD = saut médium + bruit aigu ; tom = saut médium-grave sans bruit
     (hauteur → T1/T2/FT) ; cymbale = saut 7-11 kHz, crash si la décroissance est lente et le coup fort,
     ride si la cymbale longue est jouée en continu, charley sinon ; seuils relatifs au niveau du stem ;
  4. motifs : distance entre mesures (BD/SD/toms comptent double des cymbales) ; groove d'une section =
     vote majoritaire des mesures proches de sa mesure médiane ; grooves identiques entre sections =
     même lettre ; mesure éloignée du groove de sa section (ou avec des toms) = fill.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np

from .analysis import Analysis, SR, _place, assign_roles

VERSION = "drums-2"
# HO (charley ouvert) : voie ajoutée avec le moteur ADTOF ; une ancienne page l'affiche sous son code
LANES = ["CR", "HH", "HO", "RD", "SD", "T1", "T2", "FT", "BD"]
GM = {"BD": 36, "SD": 38, "HH": 42, "HO": 46, "CR": 49, "RD": 51, "T1": 48, "T2": 45, "FT": 43}
CYM = ("HH", "HO", "RD")                  # flux de cymbale du groove (le crash est compté à part)
H = 128                       # pas d'analyse (≈ 5,8 ms)
NFFT = 1024


def _drum_source(a: Analysis, items):
    """(fichier, décalage) du stem batterie, ou None."""
    if items:
        from .prompter import _shifts
        files = [d["file"] for d in items]
        sh = _shifts(items)
        for r, f in zip(assign_roles(files), files):
            if r == "drums":
                return f, sh[f]
        return None
    if a.stems and "drums" in a.stems:
        return a.stems["drums"], 0.0
    return None


def _band_db(P, fr, lo, hi):
    m = (fr >= lo) & (fr < hi)
    return 10 * np.log10(P[m].mean(0) + 1e-12)


def _features(y):
    import librosa
    P = np.abs(librosa.stft(y, n_fft=NFFT, hop_length=H)) ** 2
    fr = librosa.fft_frequencies(sr=SR, n_fft=NFFT)
    bands = {
        "bd": _band_db(P, fr, 40, 110),
        "body": _band_db(P, fr, 120, 450),
        "snr": _band_db(P, fr, 1500, 5000),
        "cym": _band_db(P, fr, 7000, 11000),
    }
    lowspec = P[(fr >= 60) & (fr < 500)]
    lowfr = fr[(fr >= 60) & (fr < 500)]
    broad = np.log10(P[(fr >= 40) & (fr < 11000)].sum(0) + 1e-12)
    return bands, lowspec, lowfr, broad


def _offset(broad, grid_t):
    """Décalage (s) entre attaques et grille : maximise le flux à large bande sur les pas."""
    flux = np.maximum(0, np.diff(broad, prepend=broad[0]))
    best, bo = -1, 0.0
    for lag in np.arange(-0.04, 0.0401, 0.002):
        idx = np.round((grid_t + lag) * SR / H).astype(int)
        idx = idx[(idx > 0) & (idx < len(flux))]
        v = flux[idx].sum()
        if v > best:
            best, bo = v, lag
    return bo


def _jump(e, i):
    """Saut (dB) au pas d'indice i : max de [i-3, i+5] − moyenne de [i-10, i-4] ; niveau atteint."""
    a0, a1 = max(0, i - 3), min(len(e), i + 6)
    b0, b1 = max(0, i - 10), max(1, i - 4)
    pk = e[a0:a1].max()
    return pk - e[b0:b1].mean(), pk, a0 + int(np.argmax(e[a0:a1]))


def transcribe(y, downbeats, steps=16, offset=None):
    """Coups par mesure : liste (n_bars) de {voie: {pas: force dB}} ; plus diagnostic."""
    bands, lowspec, lowfr, broad = _features(y)
    nb = len(downbeats) - 1
    db = np.asarray(downbeats, float)
    grid = np.concatenate([db[k] + (db[k + 1] - db[k]) * np.arange(steps) / steps for k in range(nb)])
    off = _offset(broad, grid) if offset is None else offset
    idx = np.round((grid + off) * SR / H).astype(int)
    n = len(bands["bd"])
    ref = {k: np.percentile(v, 99) for k, v in bands.items()}
    J = {k: np.zeros(len(idx)) for k in bands}
    L = {k: np.full(len(idx), -120.0) for k in bands}
    pki = np.zeros(len(idx), int)
    for j, i in enumerate(idx):
        if i < 12 or i >= n - 60:
            continue
        for k, e in bands.items():
            J[k][j], pk, p = _jump(e, i)
            L[k][j] = pk - ref[k]
            if k == "cym":
                pki[j] = p
    # cymbales : vraies attaques (montée sur ~35 ms), quantifiées au pas le plus proche — un crash
    # arrive souvent entre deux pas (frappe ample, retard du stem séparé)
    cym = bands["cym"]
    dly = int(0.18 * SR / H)
    lo = np.array([cym[max(0, t - 6):t + 1].min() for t in range(n)])
    rise = np.r_[cym[2:], cym[-1:], cym[-1:]] - lo
    from scipy.signal import find_peaks
    pk_, _ = find_peaks(rise, height=3.0, distance=max(1, int(0.045 * SR / H)))
    CY = {}                                   # indice de pas -> (niveau, montée, décroissance)
    t_step = grid + off
    for t in pk_:
        p = t + int(np.argmax(cym[t:t + 6]))
        lc, jc = cym[p] - ref["cym"], rise[t]
        dec = cym[min(n - 1, p + dly)] - cym[p]
        j = int(np.argmin(np.abs(t_step - t * H / SR)))
        if abs(t_step[j] - t * H / SR) > 0.6 * (grid[1] - grid[0]) or not ((jc > 6 and lc > -15) or (jc > 3 and lc > -6)):
            continue
        if j not in CY or CY[j][0] < lc:
            CY[j] = (lc, jc, dec)
    out = []
    for b in range(nb):
        bar = {}
        for s in range(steps):
            j = b * steps + s
            jb, js, jbody, jc = J["bd"][j], J["snr"][j], J["body"][j], J["cym"][j]
            lb, ls, lbody, lc = L["bd"][j], L["snr"][j], L["body"][j], L["cym"][j]
            is_bd = jb > 10 and lb > -12
            # caisse claire : corps ET timbre au niveau des coups les plus forts (la grosse caisse,
            # attaque claquante, a aussi du bruit aigu mais un corps 5-7 dB plus bas)
            is_sd = js > 5 and ls > -7 and jbody > 6 and lbody > -4
            # tom : corps médium-grave fort, sans timbre ni grave de grosse caisse
            is_tom = (not is_sd) and jbody > 7 and lbody > -7 and ls < -8 and lb < -10
            if is_bd:
                bar.setdefault("BD", {})[s] = round(float(lb), 1)
            if is_sd:
                bar.setdefault("SD", {})[s] = round(float(ls), 1)
            if is_tom:
                i = idx[j]
                spec = lowspec[:, i:i + 8].mean(1)
                f0 = float(lowfr[int(np.argmax(spec))])
                lane = "FT" if f0 < 110 else ("T2" if f0 < 170 else "T1")
                bar.setdefault(lane, {})[s] = round(float(lbody), 1)
            if j in CY:
                lc, jc, dec = CY[j]
                long_ = dec > -6
                if not (is_sd and not (long_ and lc > -4)):   # sinon : aigu de la caisse claire
                    if long_ and lc > -4 and jc > 6:
                        bar.setdefault("CR", {})[s] = round(float(lc), 1)
                    else:
                        bar.setdefault("CY", {})[s] = round(float(lc), 1)
                        bar.setdefault("_dec", {})[s] = round(float(dec), 1)
        out.append(bar)
    # crash du 1er temps : nappe aiguë tenue (300 ms) nettement au-dessus de la mesure précédente
    W3 = int(0.3 * SR / H)
    sus = np.array([cym[i:i + W3].mean() - ref["cym"] if i < n else -99 for i in idx]).reshape(nb, steps)
    q = max(1, steps // 4)
    for b in range(1, nb):
        bar = out[b]
        on = sorted(set(bar.get("CY", {})) | set(bar.get("CR", {})))
        first = [x for x in on if x < q]
        prev = np.median(sus[b - 1])
        if first and sus[b, :q].max() >= max(-10.0, prev + 4.0) and not any(x < q for x in bar.get("CR", {})):
            x = max(first, key=lambda k: bar.get("CY", {}).get(k, -99))
            bar.setdefault("CR", {})[x] = bar.get("CY", {}).pop(x, round(float(sus[b, x]), 1))
            bar.get("_dec", {}).pop(x, None)
    level = np.array([broad[idx[b * steps]:idx[min(len(idx) - 1, (b + 1) * steps - 1)] + 1].max()
                      if idx[b * steps] < n else -12 for b in range(nb)])
    return out, {"offset": off, "level": level}


def _cymbal_lanes(bars, steps=16, sections=None):
    """Flux de cymbale (charley / ride) : les coups cachés sous la caisse claire sont complétés si le
    flux est régulier (noires ou croches). Voie décidée par section (une voie stable pour le groove) :
    ride si le son tient (décroissance médiane lente), sinon charley. Le crash reste à part."""
    q = steps // 4
    lane_of = ["HH"] * len(bars)
    spans = [(s.start_bar, min(s.end_bar, len(bars))) for s in sections] if sections else [(0, len(bars))]
    for b0, b1 in spans:
        # médiane des médianes par mesure, sur les 3/4 de la section (la montée finale, pleine de
        # crashs, ne doit pas décider de la voie du groove)
        b2 = b0 + max(2, int(round(0.75 * (b1 - b0))))
        d = [np.median(list(bars[b]["_dec"].values())) for b in range(b0, min(b1, b2)) if bars[b].get("_dec")]
        lane = "RD" if (len(d) >= 2 and np.median(d) > -12) else "HH"
        for b in range(b0, b1):
            lane_of[b] = lane
    for k, bar in enumerate(bars):
        c = bar.pop("CY", {})
        bar.pop("_dec", None)
        if c:
            for p in (q, q // 2):
                if p < 1:
                    continue
                ph = min(c) % p
                on = [s for s in c if s % p == ph]
                slots = [s for s in range(ph, steps, p) if s not in bar.get("SD", {})]
                if len(on) >= 2 and len(on) >= 0.6 * max(1, len(slots)):
                    for s in range(ph, steps, p):
                        if s not in c and s in bar.get("SD", {}):
                            c[s] = float(np.median(list(c.values())))
                    break
            bar[lane_of[k]] = c
        if "CR" in bar:                           # crash et charley au même pas : on garde le crash
            for lane in ("HH", "RD"):
                for s in list(bar.get(lane, {})):
                    if s in bar["CR"]:
                        del bar[lane][s]
        for lane in list(bar):
            if not bar[lane]:
                del bar[lane]
    return bars


W = {"BD": 1.0, "SD": 1.0, "T1": 1.0, "T2": 1.0, "FT": 1.0, "HH": 0.5, "HO": 0.5, "RD": 0.5, "CR": 0.0}


def _vec(bar, steps=16):
    v = np.zeros((len(LANES), max(16, steps)))
    for k, lane in enumerate(LANES):
        for s in bar.get(lane, {}):
            if 0 <= int(s) < v.shape[1]:
                v[k, int(s)] = 1
    return v


_WV = np.array([W[l] for l in LANES])[:, None]
_CORE = np.array([1.0 if l in ("BD", "SD", "T1", "T2", "FT") else 0.0 for l in LANES])[:, None]


def _dist(u, v):
    """BD/SD/toms : 1 par écart ; cymbales : 0,5 (charley fermé / ouvert / ride confondus) + 0,4 si la
    voie diffère."""
    ci = [LANES.index(c) for c in CYM]
    lane_d = sum(np.abs(u[i] - v[i]).sum() for i in ci)
    d = (np.abs(u - v) * _WV).sum() - 0.5 * lane_d
    cu, cv = u[ci].max(0), v[ci].max(0)
    return d + 0.5 * np.abs(cu - cv).sum() + 0.4 * lane_d


def _hits(bar):
    return {l: sorted(int(s) for s in bar[l]) for l in LANES if bar.get(l)}


def group(bars, sections, n_bars, rest, steps=16, near=2.5, fill_d=4.0):
    """Motifs, grooves de section, fills."""
    V = [_vec(b, steps) for b in bars]
    patterns, pvec, order = {}, [], []
    sec_of = [None] * n_bars
    for si, s in enumerate(sections):
        for b in range(s.start_bar, min(s.end_bar, n_bars)):
            sec_of[b] = si
    sec_groove = {}
    for si, s in enumerate(sections):
        play = [b for b in range(s.start_bar, min(s.end_bar, n_bars)) if not rest[b]]
        if len(play) < 2:
            continue
        D = np.array([[_dist(V[i], V[j]) for j in play] for i in play])
        med = play[int(np.argmin(np.median(D, 1)))]
        close = [b for b in play if _dist(V[b], V[med]) <= near + 1]
        if len(close) < max(2, len(play) // 3):
            continue
        frac = np.mean([V[b] for b in close], 0)
        g = (frac > 0.5).astype(float)
        g[LANES.index("CR")] = 0
        # même groove qu'un motif déjà vu ?
        best = None
        if pvec:
            # même groove : mêmes grosse caisse / caisse claire (à 2 coups près) et même voie de cymbale
            def lane_(u):
                h = u[LANES.index("HH")].sum() + u[LANES.index("HO")].sum()
                r = u[LANES.index("RD")].sum()
                return "RD" if r > h else ("HH" if h else None)
            dd = [float((np.abs(g - pv) * _CORE).sum()) if lane_(g) == lane_(pv) else 99 for pv in pvec]
            if min(dd) <= 2:
                best = int(np.argmin(dd))
        if best is None:
            name = chr(ord("A") + len(pvec))
            pvec.append(g)
            order.append(name)
            acc = {}
            for lane in ("HH", "RD", "SD", "BD"):
                li = LANES.index(lane)
                st = [int(x) for x in np.nonzero(g[li])[0]]
                if lane in ("HH", "RD") and len(st) >= 3:
                    lv = {x: np.median([bars[b][lane][x] for b in close if x in bars[b].get(lane, {})]) for x in st}
                    m = np.median(list(lv.values()))
                    a_ = [x for x in st if lv[x] > m + 3]
                    if a_:
                        acc[lane] = a_
            patterns[name] = {"name": f"Groove {name} — {s.name}", "sections": [s.name],
                              "hits": {l: [int(x) for x in np.nonzero(g[LANES.index(l)])[0]]
                                       for l in LANES if g[LANES.index(l)].any()},
                              "accents": acc}
            best = len(pvec) - 1
        else:
            patterns[order[best]]["sections"].append(s.name)
        sec_groove[si] = best
    # chaque groove est revoté sur toutes les mesures des sections qui l'utilisent (proches au cœur)
    for k, name in enumerate(order):
        mem = [b for b in range(n_bars) if not rest[b] and sec_of[b] is not None
               and sec_groove.get(sec_of[b]) == k and float((np.abs(V[b] - pvec[k]) * _CORE).sum()) <= 2]
        if len(mem) >= 4:
            g = (np.mean([V[b] for b in mem], 0) > 0.5).astype(float)
            g[LANES.index("CR")] = 0
            pvec[k] = g
            patterns[name]["hits"] = {l: [int(x) for x in np.nonzero(g[LANES.index(l)])[0]]
                                      for l in LANES if g[LANES.index(l)].any()}
            for lane in list(patterns[name]["accents"]):
                patterns[name]["accents"][lane] = [x for x in patterns[name]["accents"][lane]
                                                   if x in patterns[name]["hits"].get(lane, [])]
    out = []
    for b in range(n_bars):
        if rest[b]:
            out.append({"bar": b + 1, "pattern": None, "rest": True})
            continue
        bar = bars[b]
        ds = [_dist(V[b], pv) for pv in pvec]
        si = sec_of[b]
        own = sec_groove.get(si)
        toms = sum(len(bar.get(l, {})) for l in ("T1", "T2", "FT"))
        ref_d = ds[own] if own is not None else (min(ds) if ds else 99)
        # fill : des coups de caisse claire / toms en plus du groove, ou une mesure très différente
        # (une variation de grosse caisse ou de charley seule n'est pas un fill)
        extra = 0
        if own is not None:
            g = pvec[own]
            for lane in ("SD", "T1", "T2", "FT"):
                li = LANES.index(lane)
                extra += int(((V[b][li] > 0) & (g[li] == 0)).sum())
        core_d = float((np.abs(V[b] - pvec[own]) * _CORE).sum()) if own is not None else 0.0
        fill = bool(toms >= 2 or extra >= 2 or core_d >= fill_d)
        # groove de la section d'abord (variations tolérées), sinon le motif le plus proche
        pat = None
        if not fill:
            core = lambda u, v: float((np.abs(u - v) * _CORE).sum())
            if own is not None and (ref_d <= near + 0.5 or core(V[b], pvec[own]) <= 2):
                pat = order[own]
            elif ds and min(ds) <= near:
                pat = order[int(np.argmin(ds))]
            else:
                fill = True                   # passage nettement différent du groove de la section
        e = {"bar": b + 1, "pattern": pat, "fill": fill, "crash": any(x < steps // 4 for x in bar.get("CR", {})),
             "hits": _hits(bar)}
        out.append(e)
    return patterns, out


def default_steps(beats_per_bar, denominator) -> int:
    """Pas par mesure : double-croches (16 en 4/4) ; croches subdivisées en 2 pour les mesures en /8."""
    if beats_per_bar == 4 and denominator in (4, None):
        return 16
    return 4 * int(beats_per_bar) if denominator == 4 else 2 * int(beats_per_bar)


def _rest_and_finish(a: Analysis, bars, level, steps, n_bars, offset, engine) -> dict:
    """Mesures silencieuses, motifs, fills, noms des grooves -> format du prompteur."""
    loud = np.percentile(level, 90) if len(level) else 0.0
    rest = [bool(level[b] < loud - 2.5 or not any(bars[b].values())) for b in range(n_bars)]
    # au moins 3 coups pour parler de batterie (repisse / baguettes isolées)
    rest = [r or sum(len(v) for v in bars[b].values()) < 3 for b, r in enumerate(rest)]
    patterns, out = group(bars, a.sections, n_bars, rest, steps)
    used = [l for l in LANES if any(l in e.get("hits", {}) for e in out)
            or any(l in p["hits"] for p in patterns.values())]
    for k, p in patterns.items():                 # nom lisible : les types de section qui l'utilisent
        ts = []
        for nm in p.pop("sections", []):
            t = re.sub(r"\s*\d+$", "", nm).strip().lower()
            if t not in ts:
                ts.append(t)
        p["name"] = f"Groove {k} — " + " / ".join(ts)
    return {"steps": steps, "lanes": used, "patterns": patterns, "bars": out,
            "offset_ms": round(offset * 1000, 1), "version": VERSION, "engine": engine}


def _load_placed(a: Analysis, f, shift):
    import librosa
    y = librosa.load(f, sr=SR, mono=True)[0]
    n = max(len(y) + max(0, int(round(shift * SR))), int((a.downbeats[-1] + 1.0) * SR))
    return _place(y, shift, SR, n)


def detect_rules(a: Analysis, y) -> dict:
    """Méthode historique (règles sur le signal, sans modèle)."""
    steps = default_steps(a.beats_per_bar, a.denominator)
    n_bars = a.n_bars
    bars, diag = transcribe(y, a.downbeats[:n_bars + 1], steps)
    bars = _cymbal_lanes(bars, steps, a.sections)
    return _rest_and_finish(a, bars, diag["level"], steps, n_bars, diag["offset"], "reacue")


def detect_drums(a: Analysis, items=None, engine: str | None = None, install_dir=None) -> dict:
    """Transcription de la batterie (format du prompteur, cf. module) ; ValueError sans stem batterie.

    Moteur : ADTOF (modèle entraîné, composant facultatif) s'il est installé et que le réglage
    `drums_engine` vaut « auto », sinon les règles de ReaCue ; tout échec du modèle retombe sur les règles
    (clé « warning » dans le résultat)."""
    eng = engine or engine_setting()
    if eng == "off":
        return {"engine": "off", "bars": [], "lanes": [], "sections": [], "version": VERSION}
    src = _drum_source(a, items)
    if src is None:
        from .i18n import t as _t
        raise ValueError(_t("no_drum_stem"))
    f, shift = src
    y = _load_placed(a, f, shift)
    warn = None
    if eng == "adt-str" and advanced_available(install_dir):
        try:
            res, cached = advanced_onsets(f, install_dir)
            out = from_advanced(a, res, shift)
            out["model_cached"] = cached
            return out
        except Exception as e:
            warn = "ADT_STR: " + str(e)
            print(warn, file=sys.stderr)
    elif eng == "adt-str":
        warn = "ADT_STR is not installed; using the available fallback."
    if eng in ("auto", "adt-str", "adtof") and available(install_dir):
        try:
            res, cached = model_onsets(f, install_dir)
            out = from_model(a, y, res, shift)
            out["model_cached"] = cached
            if warn:
                out["warning"] = warn
            return out
        except Exception as e:                    # noqa: BLE001 - les règles de ReaCue prennent le relais
            from .i18n import t as _t
            warn = ((warn + " | ") if warn else "") + _t("drums_model_failed", e=e)
            print(warn, file=sys.stderr)
    out = detect_rules(a, y)
    if warn:
        out["warning"] = warn
    return out


def _file_sig(f) -> list:
    try:
        st = Path(f).stat()
        return [str(Path(f).resolve()), st.st_size, st.st_mtime_ns]
    except (OSError, TypeError):
        return [str(f), None, None]


def drums_cache_key(a: Analysis, items) -> str:
    import hashlib
    import json
    src = _drum_source(a, items)
    eng = engine_setting()
    model = [ENGINE, ADTOF_REV, MODEL_CACHE_VERSION] if eng in ("auto", "adtof", "adt-str") and available() else None
    return hashlib.md5(json.dumps([src and _file_sig(src[0]), src and round(src[1], 4),
                                   [round(float(x), 4) for x in a.downbeats], a.beats_per_bar,
                                   a.denominator, [(s.start_bar, s.end_bar, s.name) for s in a.sections],
                                   VERSION, model, eng, advanced_stamp() if eng == "adt-str" else None]).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Moteur ADTOF (modèle entraîné, composant facultatif .venv-drums)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent          # dossier d'installation de ReaCue
ENGINE = "adtof"
# révision figée du portage PyTorch d'ADTOF (même valeur dans install/install_drums_*)
ADTOF_REV = "85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9"
MODEL_CACHE_VERSION = 1
TIMEOUT_S = 900                  # 15 min : CPU lent + 1er lancement ; au-delà, règles de ReaCue
CLASSES = ("BD", "SD", "TT", "HH", "CY")


def drums_python(install_dir: Path | None = None, windows: bool | None = None) -> Path:
    d = Path(install_dir or ROOT)
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        return d / ".venv-drums" / "Scripts" / "python.exe"
    return d / ".venv-drums" / "bin" / "python"


def available(install_dir: Path | None = None) -> bool:
    d = Path(install_dir or ROOT)
    return (drums_python(d).exists() and (d / "reacue_drums.py").is_file()
            and (d / "drums" / "ADTOF-pytorch" / "src" / "adtof_pytorch" / "model.py").is_file())


def engine_setting() -> str:
    """« auto » (ADTOF s'il est installé) | « reacue » (règles seules) ; REACUE_DRUMS_ENGINE l'emporte."""
    env = os.environ.get("REACUE_DRUMS_ENGINE", "").lower()
    if env in ("auto", "reacue", "adtof", "adt-str", "off"):
        return env
    try:
        from .settings import load_settings
        v = str(load_settings().get("drums_engine") or "adtof").lower()
    except Exception:
        v = "adtof"
    return v if v in ("auto", "reacue", "adtof", "adt-str", "off") else "adtof"


def run_model(audio: str, out_json: Path, install_dir: Path | None = None, timeout: float = TIMEOUT_S,
              python: str | None = None, script: str | None = None) -> dict:
    """Lance reacue_drums.py analyze ; renvoie le résultat (dict) ou lève RuntimeError."""
    import json
    import subprocess
    import time
    from .i18n import t
    d = Path(install_dir or ROOT)
    py = python or str(drums_python(d))
    sc = script or str(d / "reacue_drums.py")
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    status = out_json.with_name(out_json.stem + "_status.json")
    for p in (out_json, status):
        try:
            p.unlink()
        except OSError:
            pass
    cmd = [py, sc, "analyze", "--input", str(audio), "--out", str(out_json), "--status", str(status)]
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}       # CREATE_NO_WINDOW
    log = out_json.with_name(out_json.stem + ".log")
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(d), **kw)
        while proc.poll() is None:
            if time.time() - t0 > timeout:
                proc.kill()
                proc.wait()
                raise RuntimeError(("ADT_STR" if Path(sc).name == "reacue_adt.py" else "ADTOF") + f" timeout ({int(timeout // 60)} min)")
            time.sleep(0.2)
    try:
        res = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        res = None
    if proc.returncode != 0 or not isinstance(res, dict) or not isinstance(res.get("onsets"), dict):
        msg = ""
        try:
            msg = json.loads(status.read_text(encoding="utf-8")).get("message") or ""
        except (OSError, ValueError):
            pass
        if not msg:
            try:
                msg = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1][:500]
            except (OSError, IndexError):
                pass
        raise RuntimeError(msg or f"exit {proc.returncode} ({log})")
    return res


def model_cache_path(f) -> Path:
    p = Path(f)
    return p.parent / ".reacue" / f"{p.stem}_drums_{ENGINE}.json"


def model_cache_key(f) -> str:
    import hashlib
    import json
    return hashlib.sha1(json.dumps([ENGINE, ADTOF_REV, MODEL_CACHE_VERSION,
                                    _file_sig(Path(f).resolve())]).encode()).hexdigest()


def model_onsets(f, install_dir: Path | None = None) -> tuple[dict, bool]:
    """Coups détectés par ADTOF dans le stem batterie (temps du fichier) ; mis en cache à côté du stem
    (.reacue/<stem>_drums_adtof.json) : changer la grille ou les sections ne relance pas le modèle."""
    import json
    import tempfile
    cpath, key = model_cache_path(f), model_cache_key(f)
    try:
        c = json.loads(cpath.read_text(encoding="utf-8"))
        if c.get("key") == key and isinstance(c.get("onsets"), dict):
            return c, True
    except (OSError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix="reacue_drums_") as tmp:
        res = run_model(str(f), Path(tmp) / "result.json", install_dir)
    res = {"key": key, "engine": ENGINE, "rev": ADTOF_REV, "fps": res.get("fps", 100),
           "onsets": {c: res["onsets"].get(c, []) for c in CLASSES}, "seconds": res.get("seconds")}
    try:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(res), encoding="utf-8")
    except OSError:
        pass
    return res, False


# ----------------------------------------------------------------- quantification sur la grille de ReaCue
def quantize(times, downbeats, steps):
    """Temps (s) -> (indice de mesure 0-based, pas) sur la grille (mesures de longueurs variables
    comprises) ; un coup juste avant une barre de mesure va sur le 1er pas de la mesure suivante.
    Renvoie deux tableaux et un masque « dans la grille »."""
    db = np.asarray(downbeats, float)
    t = np.asarray(times, float).reshape(-1)
    nb = len(db) - 1
    if nb < 1 or not len(t):
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0, bool)
    k = np.clip(np.searchsorted(db, t, side="right") - 1, 0, nb - 1)
    frac = (t - db[k]) / (db[k + 1] - db[k])
    s = np.round(frac * steps).astype(int)
    bar = k + np.floor_divide(s, steps)
    s = np.mod(s, steps)
    ok = (bar >= 0) & (bar < nb)
    return bar, s, ok


def grid_offset(times, downbeats, beats_per_bar, limit=0.04) -> float:
    """Retard global (s) des coups par rapport à la grille : médiane des écarts à la croche la plus
    proche (coups forts de grosse caisse / caisse claire), borné à ±40 ms."""
    t = np.asarray(times, float)
    if len(t) < 4:
        return 0.0
    sub = 2 * int(beats_per_bar)
    bar, s, ok = quantize(t, downbeats, sub)
    if ok.sum() < 4:
        return 0.0
    db = np.asarray(downbeats, float)
    g = db[bar[ok]] + (db[bar[ok] + 1] - db[bar[ok]]) * s[ok] / sub
    return float(np.clip(np.median(t[ok] - g), -limit, limit))


def choose_steps(times, downbeats, beats_per_bar, denominator) -> int:
    """Double-croches (4 pas par temps) ou triolets de croches (3 pas par temps) selon le morceau :
    seuls les coups hors des temps comptent ; triolets si l'écart moyen à leur grille est nettement plus
    petit. Mesures en /8 : pas de choix (croches subdivisées en 2)."""
    base = default_steps(beats_per_bar, denominator)
    if denominator not in (4, None):
        return base
    bpb = int(beats_per_bar)
    bar, s, ok = quantize(times, downbeats, 48 * bpb)            # position fine : 1/48 de temps
    pos = (s[ok] / 48.0) % 1.0                                    # position dans le temps (0..1)
    pos = pos[(pos > 0.1) & (pos < 0.9)]
    if len(pos) < 8:
        return base
    eb = np.abs(pos * 4 - np.round(pos * 4)) / 4
    et = np.abs(pos * 3 - np.round(pos * 3)) / 3
    return 3 * bpb if et.mean() < 0.6 * eb.mean() else base


def _tom_lanes(f0s) -> list[str]:
    """Hauteurs des coups de tom -> T1 / T2 / FT : groupes de hauteur du morceau (écart > 15 %), du plus
    aigu (T1) au plus grave (FT) ; une seule hauteur : seuils absolus (FT < 110 Hz < T2 < 170 Hz < T1)."""
    if not len(f0s):
        return []
    f = np.asarray(f0s, float)
    order = np.argsort(f)
    groups, cur = [], [order[0]]
    for i in order[1:]:
        if f[i] > f[cur[-1]] * 1.15:
            groups.append(cur)
            cur = [i]
        else:
            cur.append(i)
    groups.append(cur)
    out = [""] * len(f)
    if len(groups) == 1:
        return ["FT" if x < 110 else ("T2" if x < 170 else "T1") for x in f]
    for gi, g in enumerate(groups):
        lane = "FT" if gi == 0 else ("T1" if gi == len(groups) - 1 else "T2")
        for i in g:
            out[i] = lane
    return out


def from_model(a: Analysis, y, res: dict, shift: float = 0.0) -> dict:
    """Coups ADTOF (temps du stem) -> format du prompteur, sur la grille de ReaCue.

    ADTOF donne 5 classes ; le signal du stem précise : toms aigu / médium / basse (hauteur), charley
    fermé / ouvert (l'aigu tient après le coup), crash / ride (flux régulier dans la section = ride, coup
    plus fort sur le 1er temps = crash ; hors flux = crash)."""
    n_bars = a.n_bars
    db = np.asarray(a.downbeats[:n_bars + 1], float)
    bpb = int(a.beats_per_bar)
    ons = {}
    for c in CLASSES:
        v = np.asarray(res.get("onsets", {}).get(c) or [], float).reshape(-1, 2)
        ons[c] = np.c_[v[:, 0] + shift, v[:, 1]] if len(v) else np.zeros((0, 2))
    strong = np.concatenate([ons[c][ons[c][:, 1] >= 0.4, 0] for c in ("BD", "SD")])
    off = grid_offset(strong, db, bpb)
    tune = np.concatenate([ons[c][ons[c][:, 1] >= 0.3, 0] for c in ("BD", "SD", "HH", "CY")]) - off
    steps = choose_steps(tune, db, bpb, a.denominator)

    bands, lowspec, lowfr, broad = _features(y)
    n = len(bands["bd"])
    ref = {k: np.percentile(v, 99) for k, v in bands.items()}
    cym = bands["cym"]
    fr = lambda t: int(np.clip(round(t * SR / H), 0, n - 1))          # noqa: E731
    band_of = {"BD": "bd", "SD": "snr", "TT": "body", "HH": "cym", "CY": "cym"}

    def level(c, t):
        i = fr(t)
        e = bands[band_of[c]]
        return round(float(e[max(0, i - 2):i + 7].max() - ref[band_of[c]]), 1)

    bars = [dict() for _ in range(n_bars)]

    def put(lane, b, s, lv):
        d = bars[b].setdefault(lane, {})
        d[int(s)] = max(lv, d.get(int(s), -999.0))

    # attaques aiguës (charley + cymbales) : la tenue d'un coup est mesurée jusqu'au coup suivant
    hi_t = np.sort(np.concatenate([ons["HH"][:, 0], ons["CY"][:, 0]]))

    def next_gap(t):
        j = np.searchsorted(hi_t, t + 0.02)
        return float(hi_t[j] - t) if j < len(hi_t) else 1.0

    for c in ("BD", "SD"):
        bar, s, ok = quantize(ons[c][:, 0] - off, db, steps)
        for t, b, st, o in zip(ons[c][:, 0], bar, s, ok):
            if o:
                put(c, b, st, level(c, t))
    # toms
    bar, s, ok = quantize(ons["TT"][:, 0] - off, db, steps)
    toms = [(t, b, st) for t, b, st, o in zip(ons["TT"][:, 0], bar, s, ok) if o]
    f0s = []
    for t, _, _ in toms:
        i = fr(t)
        if lowspec.shape[1] <= i + 1:
            f0s.append(100.0)
            continue
        # hauteur de ce qui vient d'arriver (le tom précédent résonne encore) : hausse du spectre grave
        now = lowspec[:, i:i + 8].mean(1)
        rise = np.maximum(0.0, now - lowspec[:, max(0, i - 6):max(1, i - 1)].mean(1))
        f0s.append(float(lowfr[int(np.argmax(rise if rise.max() > 0 else now))]))
    for (t, b, st), lane in zip(toms, _tom_lanes(f0s)):
        put(lane, b, st, level("TT", t))
    # charley et cymbales : décision par section (flux régulier = voie du groove), puis coup par coup
    low_t = np.sort(np.concatenate([ons["SD"][:, 0], ons["BD"][:, 0]]))
    hi = []                                   # (classe ADTOF, mesure, pas, niveau, tenue, ouvert, long)
    for c in ("HH", "CY"):
        bar, s, ok = quantize(ons[c][:, 0] - off, db, steps)
        for t, b, st, o in zip(ons[c][:, 0], bar, s, ok):
            if not o:
                continue
            i = fr(t)
            pre = float(cym[max(0, i - 7):max(1, i - 2)].mean())
            pk = float(cym[max(0, i - 2):i + 7].max())
            dec = float(cym[fr(t + 0.18)]) - pk                        # tenue à 180 ms (ride / charley)
            long_ = float(cym[fr(t + 0.3):fr(t + 0.45) + 1].min()) - pk  # creux à 300-450 ms (crash)
            # ouvert : l'aigu tient jusqu'au coup suivant (baisse <= 60 dB/s, au moins 6 dB permis ;
            # mesurable sur 50 ms au moins, 150 ms si une caisse claire ou une grosse caisse tombe en même
            # temps : son timbre tient aussi un peu)
            w = min(0.2, next_gap(t) - 0.015)
            j = np.searchsorted(low_t, t - 0.03)
            with_low = j < len(low_t) and abs(low_t[j] - t) <= 0.03
            opened = False
            if w >= (0.15 if with_low else 0.05):
                drop = pk - float(cym[fr(t + w)])
                opened = pk - pre > 3 and drop <= max(6.0, 60.0 * w)
            hi.append((c, int(b), int(st), level(c, t), dec, long_, opened))
    spans = [(sc.start_bar, min(sc.end_bar, n_bars)) for sc in a.sections] or [(0, n_bars)]
    q = max(1, steps // bpb)
    for b0, b1 in spans:
        mine = [x for x in hi if b0 <= x[1] < b1]
        if not mine:
            continue

        def stream(cls):
            per_bar = {}
            for x in mine:
                if x[0] == cls:
                    per_bar.setdefault(x[1], set()).add(x[2])
            return bool(per_bar) and np.median([len(v) for v in per_bar.values()]) >= 3 \
                and len(per_bar) >= 0.5 * max(1, b1 - b0)
        ride_cy = stream("CY")
        # charley en flux dont le son tient (médiane > -12 dB à 180 ms) : c'est une ride
        hh_dec = [x[4] for x in mine if x[0] == "HH"]
        ride_hh = stream("HH") and not ride_cy and float(np.median(hh_dec)) > -12
        med = float(np.median([x[3] for x in mine]))
        # crash dans un flux de ride : seulement le 1er coup de cymbale du 1er temps, plus fort que le flux
        first = {}
        for x in mine:
            if x[0] == "CY" and x[2] < q:
                first[x[1]] = min(first.get(x[1], q), x[2])
        for c, b, st, lv, dec, long_, opened in mine:
            loud_long = lv >= max(-4.0, med + 4) and long_ > -10
            if c == "CY":
                lane = "RD" if ride_cy and not (first.get(b) == st and lv >= med + 4) else "CR"
            elif ride_hh:
                lane = "CR" if loud_long else "RD"
            else:
                lane = "CR" if loud_long else ("HO" if opened else "HH")
            put(lane, b, st, lv)
    # crash et charley / ride au même pas : on garde le crash
    for bar_ in bars:
        for lane in CYM:
            for st in list(bar_.get(lane, {})):
                if st in bar_.get("CR", {}):
                    del bar_[lane][st]
            if lane in bar_ and not bar_[lane]:
                del bar_[lane]
    level_ = np.array([broad[fr(db[b]):max(fr(db[b]) + 1, fr(db[b + 1]))].max() for b in range(n_bars)])
    return _rest_and_finish(a, bars, level_, steps, n_bars, off, ENGINE)


def cached_drums(a: Analysis, items=None, cache=None) -> dict:
    """detect_drums avec cache disque (un seul morceau mémorisé, comme cached_chords)."""
    import json
    from pathlib import Path
    if engine_setting() == "off":
        return {"engine": "off", "bars": [], "lanes": [], "sections": [], "version": VERSION}
    if cache is None:
        from .bridge import BRIDGE_DIR
        cache = BRIDGE_DIR / "prompter_drums.json"
    cache = Path(cache)
    ck = drums_cache_key(a, items)
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("key") == ck:
            return c["drums"]
    except Exception:
        pass
    res = detect_drums(a, items)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"key": ck, "drums": res}), encoding="utf-8")
    except OSError:
        pass
    return res


# --------------------------------------------------------------------------- #
# Export MIDI (fichier type 0, canal 10, notes GM), sans dépendance
# --------------------------------------------------------------------------- #
def _vlq(v: int) -> bytes:
    b = [v & 0x7F]
    v >>= 7
    while v:
        b.append((v & 0x7F) | 0x80)
        v >>= 7
    return bytes(reversed(b))


def drums_to_midi(d: dict, bpm: float, path, beats_per_bar: int = 4, ppq: int = 480) -> str:
    steps = int(d.get("steps", 16))
    tps = ppq * beats_per_bar // steps           # ticks par pas
    ev = []
    for e in d["bars"]:
        base = (int(e["bar"]) - 1) * steps * tps
        for lane, st in (e.get("hits") or {}).items():
            for s in st:
                t = base + int(s) * tps
                vel = 110 if (lane == "CR" or (lane in ("HH", "RD") and s % (steps // beats_per_bar) == 0)) else 90
                ev.append((t, 1, GM[lane], vel))
                ev.append((t + max(1, tps // 2), 0, GM[lane], 0))
    if d.get("engine") == "adt-str" and "raw_notes" in d:
        ev = []
        for note in d["raw_notes"]:
            start = max(0, round(float(note["t"]) * bpm / 60 * ppq))
            end = max(start + 1, round(float(note["end"]) * bpm / 60 * ppq))
            ev.extend([(start, 1, int(note["pitch"]), int(note["velocity"])),
                       (end, 0, int(note["pitch"]), 0)])
    ev.sort(key=lambda x: (x[0], x[1]))
    tempo = int(round(60_000_000 / bpm))
    trk = bytearray(b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big"))
    trk += b"\x00\xff\x58\x04" + bytes([beats_per_bar, 2, 24, 8])
    last = 0
    for t, on, note, vel in ev:
        trk += _vlq(t - last) + bytes([0x99 if on else 0x89, note, vel])
        last = t
    trk += b"\x00\xff\x2f\x00"
    data = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") \
        + ppq.to_bytes(2, "big") + b"MTrk" + len(trk).to_bytes(4, "big") + bytes(trk)
    with open(path, "wb") as fh:
        fh.write(data)
    return str(path)


# Detailed ADT_STR transcription is isolated from the legacy PyTorch environment.
def advanced_python(install_dir=None):
    d = Path(install_dir or ROOT) / ".venv-drums-advanced"
    return d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def advanced_available(install_dir=None):
    d = Path(install_dir or ROOT)
    from reacue_adt import CODE_REV, MODEL_REV
    try:
        stamp = (d / "drums/adt-str-model/.ready").read_text().splitlines()
    except OSError:
        return False
    return (advanced_python(d).is_file() and (d / "drums/ADT_STR/adt_transcriber.py").is_file()
            and stamp == [CODE_REV, MODEL_REV])


def advanced_stamp(install_dir=None):
    from reacue_adt import CODE_REV, MODEL_REV, VARIANT
    return [CODE_REV, MODEL_REV, VARIANT, advanced_available(install_dir)]


def advanced_onsets(f, install_dir=None):
    import hashlib
    import json
    import tempfile
    d = Path(install_dir or ROOT)
    key = hashlib.sha1(json.dumps([_file_sig(f), advanced_stamp(d)]).encode()).hexdigest()
    cp = Path(f).parent / ".reacue" / (Path(f).stem + "_drums_adt-str.json")
    try:
        cached = json.loads(cp.read_text())
        if cached.get("key") == key and isinstance(cached.get("notes"), list):
            return cached, True
    except (OSError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix="reacue_adt_") as tmp:
        result = run_model(str(f), Path(tmp) / "out.json", d, timeout=3600,
                           python=str(advanced_python(d)), script=str(d / "reacue_adt.py"))
    if result.get("engine") != "adt-str" or not isinstance(result.get("notes"), list):
        raise ValueError("Invalid ADT_STR result")
    result["key"] = key
    try:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(result))
    except OSError:
        pass
    return result, False


# UI lanes are a projection only: all 26 GM classes remain in raw_notes / MIDI.
ADVANCED_LANES = {35:"BD",36:"BD",37:"SD",38:"SD",40:"SD",42:"HH",44:"HH",46:"HO",
                  41:"FT",43:"FT",45:"T2",47:"T2",48:"T1",50:"T1",
                  49:"CR",52:"CR",55:"CR",57:"CR",51:"RD",53:"RD",59:"RD"}


def from_advanced(a, result, shift=0.0):
    import math
    notes = []
    for note in result["notes"]:
        t, end = float(note["t"]) + shift, float(note["end"]) + shift
        pitch, velocity = int(note["pitch"]), int(note["velocity"])
        if math.isfinite(t) and math.isfinite(end) and 0 <= t < a.duration and end > t and 0 <= pitch <= 127 and 1 <= velocity <= 127:
            notes.append(dict(t=t, end=min(end, a.duration), pitch=pitch, velocity=velocity))
    db = np.asarray(a.downbeats[:a.n_bars + 1], float)
    times = np.array([n["t"] for n in notes])
    steps = choose_steps(times, db, a.beats_per_bar, a.denominator)
    bi, si, ok = quantize(times, db, steps)
    bars = [{} for _ in range(a.n_bars)]
    for note, b, step, valid in zip(notes, bi, si, ok):
        lane = ADVANCED_LANES.get(note["pitch"])
        if valid and lane:
            hits = bars[b].setdefault(lane, {})
            hits[int(step)] = max(hits.get(int(step), -100), 20 * np.log10(note["velocity"] / 127))
    rest = [not any(bar.values()) for bar in bars]
    patterns, out = group(bars, a.sections, a.n_bars, rest, steps)
    for name, pattern in patterns.items():
        pattern["name"] = "Groove " + name
        pattern.pop("sections", None)
    return dict(engine="adt-str", version=VERSION, steps=steps, lanes=[l for l in LANES if any(l in b for b in bars)],
                bars=out, patterns=patterns, offset_ms=0, raw_notes=notes,
                model_revision=result.get("model_revision"), seconds=result.get("seconds"))
