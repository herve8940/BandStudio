#!/usr/bin/env python3
"""Captures d'écran du prompteur pour la documentation (outil de développement).

Fabrique un morceau de démonstration entièrement fictif (« Demo Song » : structure, accords,
paroles et batterie inventés) et un concert fictif de trois morceaux, les sert avec la page du prompteur
sur un faux serveur REAPER (/_/TRANSPORT renvoie une position fixe ; instruments, Régie et répétition
simulés), puis photographie chaque vue avec Playwright (Chromium) : rôles, tablette, concert, Régie (PIN 1234),
Lumière (cues grandMA3), ReaCue Studio (écran Travail : pistes /_/TRACK et formes d'onde fictives ; écrans
Concert et Lumière sur le concert fictif).

    pip install playwright && playwright install chromium
    python3 tools/make_screenshots.py [--out docs/images] [--check]

--check : vérifie seulement que la page s'affiche sans erreur console (FR et EN, tous les rôles).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reacue_mcp.i18n import localize_section, section_color, section_kind  # noqa: E402

PAGE = ROOT / "reacue_mcp" / "web" / "prompteur.html"
WEB = ROOT / "reacue_mcp" / "web"
CTYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
          ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".json": "application/json"}

BPM = 112.0
BPB = 4
COUNT_IN = 2
# structure (noms internes FR, traduits pour la version anglaise)
STRUCT = [("Intro", 1, 8), ("Couplet 1", 9, 24), ("Pré-refrain 1", 25, 28), ("Refrain 1", 29, 44),
          ("Couplet 2", 45, 60), ("Pré-refrain 2", 61, 64), ("Refrain 2", 65, 80), ("Pont", 81, 88),
          ("Solo", 89, 96), ("Refrain 3", 97, 112), ("Outro", 113, 120)]
N_BARS = 120
CHORDS = {"intro": ["Am", "F", "C", "G"], "verse": ["Am", "F", "C", "G"], "prechorus": ["Dm", "Em", "F", "G"],
          "chorus": ["C", "G", "Am", "F"], "bridge": ["F", "G", "Em", "Am"], "solo": ["Am", "F", "C", "G"],
          "outro": ["Am", "F", "C", "G"]}

# notes de section (champ « notes » des données publiées), inventées pour la démonstration
NOTES = {"Pré-refrain 1": {"fr": "On coupe tout sur le dernier temps de la mes. 28.",
                           "en": "Everybody stops on the last beat of bar 28."},
         "Refrain 1": {"fr": "Crash sur le 1, on double le tempo à la caisse claire.",
                       "en": "Crash on 1, snare in double time."}}

# paroles 100 % inventées pour cette démonstration
LYRICS = {
    "fr": {
        "verse": ["La ville s'allume au bout du quai", "On compte les pas jusqu'au dernier train",
                  "Les néons fredonnent un air oublié", "Et la nuit nous tend la main",
                  "Les vitrines dorment, le pavé luit", "Un vieux refrain tourne dans nos têtes",
                  "On garde le tempo jusqu'à minuit", "La rue entière bat la mesure"],
        "prechorus": ["Encore un tour, encore un soir"],
        "chorus": ["Allume le son, laisse-nous chanter", "Quatre temps pour tout recommencer",
                   "Allume le son, jusqu'au matin", "On tient la mesure, on tient le refrain"],
    },
    "en": {
        "verse": ["The city hums along the empty pier", "We count the steps until the final train",
                  "Neon signs are singing something we can't hear", "And the night calls out our name",
                  "Shop windows sleep, the pavement gleams", "An old refrain keeps spinning round",
                  "We hold the tempo past midnight", "The whole street keeps the time"],
        "prechorus": ["One more round, one more night"],
        "chorus": ["Turn the sound up, let the whole room sing", "Four on the floor and we start again",
                   "Turn the sound up till the morning light", "Hold the tempo, hold the line tonight"],
    },
}


def bar_len(bpm: float = BPM) -> float:
    return 60.0 * BPB / bpm


def bar_time(bar: int, pos: float = 0.0, bpm: float = BPM, t0: float = 0.0) -> float:
    """Mesure 1-based (≤ 0 : count-in) -> secondes sur la timeline (t0 : début du morceau dans un concert)."""
    return round(t0 + (bar - 1 + COUNT_IN + pos / BPB) * bar_len(bpm), 4)


def _drums(lang: str) -> dict:
    hh8 = list(range(0, 16, 2))
    pats = {
        "A": {"hits": {"HH": hh8, "SD": [4, 12], "BD": [0, 7, 8]}, "accents": {"HH": [0, 4, 8, 12]}},
        "B": {"hits": {"RD": hh8, "SD": [4, 12], "BD": [0, 6, 8, 10]}, "accents": {}},
        "C": {"hits": {"HH": list(range(16)), "SD": [12], "BD": [0, 8]}, "accents": {}},
    }
    use = {"A": ["verse", "intro", "outro"], "B": ["chorus", "solo"], "C": ["prechorus"]}
    for k, p in pats.items():
        names = []
        for kind in use[k]:
            fr = {"verse": "couplet", "intro": "intro", "outro": "outro", "chorus": "refrain", "solo": "solo",
                  "prechorus": "pré-refrain"}[kind]
            names.append(fr if lang == "fr" else {"verse": "verse", "chorus": "chorus", "prechorus": "pre-chorus"}.get(kind, kind))
        p["name"] = f"Groove {k} — " + " / ".join(names)
    groove = {"verse": "A", "intro": "A", "outro": "A", "chorus": "B", "solo": "B", "prechorus": "C", "bridge": "A"}
    bars = []
    for name, a, b in STRUCT:
        kind = section_kind(name)
        for bar in range(a, b + 1):
            if kind == "bridge" and bar <= a + 3:
                bars.append({"bar": bar, "pattern": None, "rest": True})
                continue
            e = {"bar": bar, "pattern": groove[kind], "fill": False, "crash": bar == a and kind in ("chorus", "solo"),
                 "hits": dict(pats[groove[kind]]["hits"])}
            if bar == b and bar != N_BARS:
                e.update(pattern=None, fill=True, hits={"SD": [8, 10, 12, 13], "T1": [9, 14], "FT": [11, 15],
                                                        "BD": [0, 4], "HH": [0, 2, 4, 6]})
            bars.append(e)
    return {"steps": 16, "lanes": ["CR", "HH", "RD", "SD", "T1", "T2", "FT", "BD"], "patterns": pats, "bars": bars,
            "version": "demo"}


def _lighting(songs: list[dict], concert: str | None = None) -> dict:
    """Bloc « lighting » (onglet Lumière), calculé par le vrai module d'export grandMA3."""
    from reacue_mcp import lighting
    cfg = lighting.config({"gma3_fps": 25, "gma3_tc_start": "01:00:00:00",
                           "gma3_song_slot": 0, "gma3_ltc_output": 7, "gma3_mtc_output": "IAC Bus 1", "gma3_tc_slot": 1})
    return lighting.web_data(lighting.show_from_songs(songs, concert), cfg)


def demo_song(lang: str, title: str = "Demo Song", bpm: float = BPM, t0: float = 0.0) -> dict:
    secs = []
    for name, a, b in STRUCT:
        nm = localize_section(name, lang)
        secs.append({"name": nm, "type": section_kind(nm), "group": "", "start_bar": a, "end_bar": b,
                     "color": "#%02x%02x%02x" % section_color(nm), "notes": NOTES.get(name, {}).get(lang, "")})
    chords = []
    for name, a, b in STRUCT:
        prog = CHORDS[section_kind(name)]
        for bar in range(a, b + 1):
            c = prog[(bar - a) % len(prog)]
            entry = [{"beat": 1, "chord": c, "bass": c.rstrip("m"), "confidence": 0.9}]
            if section_kind(name) == "prechorus" and (bar - a) % 4 == 3:
                entry.append({"beat": 3, "chord": "E", "bass": "E", "confidence": 0.7})
            chords.append({"bar": bar, "chords": entry})
    act = {"drums": [], "bass": [], "guitars": [], "lead_guitar": [], "vocals": []}
    for bar in range(1, N_BARS + 1):
        kind = section_kind(next(n for n, a, b in STRUCT if a <= bar <= b))
        act["drums"].append(0 if 81 <= bar <= 84 else 1)
        act["bass"].append(0 if bar <= 4 else 1)
        act["guitars"].append(0 if 81 <= bar <= 84 else 1)
        act["lead_guitar"].append(1 if kind in ("solo", "intro") else 0)
        act["vocals"].append(1 if kind in ("verse", "prechorus", "chorus") else 0)
    lyrics, i = [], 0
    L = LYRICS[lang]
    for name, a, b in STRUCT:
        kind = section_kind(name)
        lines = L.get(kind)
        if not lines:
            continue
        step = 2 if kind != "prechorus" else 4
        for k, bar in enumerate(range(a, b + 1, step)):
            text = lines[k % len(lines)]
            ta, tb = bar_time(bar, 0.5, bpm, t0), bar_time(bar + 1, 3.0, bpm, t0)
            lyrics.append({"i": i, "line": i + 1, "bar": bar, "beat": 0, "pos": 0.5, "t": ta, "end": tb,
                           "text": text, "confidence": 0.9, "copy": False})
            i += 1
    song = {
        "version": 1, "language": lang, "title": title, "bpm": bpm, "beats_per_bar": BPB,
        "tempo_mode": "constant", "count_in_bars": COUNT_IN, "n_bars": N_BARS,
        "bar_times": [bar_time(k, 0.0, bpm, t0) for k in range(-COUNT_IN + 1, N_BARS + 2)],
        "key": {"chord": "Am", "fr": "La mineur", "en": "A minor"},
        "sections": secs, "activity": act, "roles": sorted(act), "chords": chords, "lyrics": lyrics,
        "drums": _drums(lang),
    }
    song["lighting"] = _lighting([song])
    song["id"] = hashlib.md5(json.dumps(song, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return song


# concert fictif : trois morceaux inventés à la suite sur la même timeline, 4 s de blanc entre eux
CONCERT = [("Demo Song", 112.0), ("Second Demo", 150.0), ("Third Demo", 100.0)]
GAP = 4.0


def demo_concert(lang: str) -> dict:
    songs, t = [], 0.0
    for k, (title, bpm) in enumerate(CONCERT):
        s = demo_song(lang, title, bpm, t)
        stop = s["bar_times"][-1]
        s.update({"n": k + 1, "start_t": t, "stop_t": stop, "next_t": stop + GAP,
                  "next_title": CONCERT[k + 1][0] if k + 1 < len(CONCERT) else None})
        songs.append(s)
        t = stop + GAP
    name = "Concert de démo" if lang == "fr" else "Demo concert"
    data = {"version": 1, "language": lang, "concert": {"name": name, "n": len(songs), "titles": [x[0] for x in CONCERT]},
            "songs": songs}
    data["lighting"] = _lighting(songs, name)
    data["id"] = hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return data


# bibliothèque fictive (écran BIBLIO) : même format que reacue_mcp/library.build_library
LIB_SONGS = [  # titre, tempo, ton, étape, manuel ?, composants (stems, accords, paroles, batterie, lumière), préparé
    ("Demo Song", 112, "Am", "stage", False, (5, True, 46, True, True), True),
    ("Second Demo", 150, "Em", "band", False, (4, True, 46, True, True), True),
    ("Third Demo", 100, "C", "band", True, (0, True, 0, False, True), True),
    ("Night Drive Demo", 124, "F#m", "solo", False, (6, True, 32, True, False), True),
    ("Morning Riff", 96, "D", "new", False, (4, False, 0, True, False), True),
    ("Unfinished Idea", 0, "", "new", False, (0, False, 0, False, False), False),
]


def demo_library(lang: str) -> dict:
    from reacue_mcp import library
    secs = []
    for name, a, b in STRUCT:
        nm = localize_section(name, lang)
        secs.append({"name": nm, "type": section_kind(nm), "color": "#%02x%02x%02x" % section_color(nm), "bars": b - a + 1})
    songs, base = [], "/Users/demo/Documents/REAPER Media"
    for k, (title, bpm, key, stage, manual, comp, prep) in enumerate(LIB_SONGS):
        path = f"{base}/{title}/{title}.RPP"
        cut = secs if k % 2 == 0 else secs[:9]
        st = {"new": (0, 0, 0), "solo": (14, 0, 0), "band": (22, 9, 1), "stage": (40, 31, 3)}[stage]
        songs.append({
            "key": library.song_key(path), "path": path, "title": title, "folder": title, "bpm": bpm or None, "sig": "4/4",
            "key_name": {"chord": key, "fr": key, "en": key} if key else None,
            "duration_s": round(sum(x["bars"] for x in cut) * 240 / bpm, 1) if bpm else 0, "bars": sum(x["bars"] for x in cut),
            "sections": cut if prep else [], "prepared": prep,
            "components": {"stems": comp[0], "chords": comp[1], "lyrics": comp[2], "drums": comp[3], "lighting": comp[4]},
            "concerts": (["Concert de démo" if lang == "fr" else "Demo concert"] if k < 3 else []),
            "published": 1761480000 if prep else None, "stage": stage,
            "stage_auto": "solo" if manual else stage, "stage_manual": stage if manual else None,
            "practice": {"solo_min": st[0], "band_min": st[1], "band_days": st[2], "last": None}, "notes": 2 if k < 2 else 0,
        })
    name = "Concert de démo" if lang == "fr" else "Demo concert"
    data = {"version": 1, "generated": 1761480000, "language": lang, "projects_dir": base, "concert_dir": base + "/Concerts",
            "stages": list(library.STAGES), "rules": {"solo_min": 5, "band_min": 3, "stage_days": 2, "day_min": 2},
            "songs": songs, "concerts": [{"name": name, "rpp": f"{base}/Concerts/{name}.RPP", "built": True,
                                         "songs": [x["key"] for x in songs[:3]]},
                                        {"name": "Festival 2027", "rpp": f"{base}/Concerts/Festival 2027.RPP", "built": False,
                                         "songs": [x["key"] for x in songs[1:5]]}]}
    data["id"] = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    return data


# musiciens connectés (écran GROUPE) : ReaCue/band = époque|id,rôle,nom,prêt,âge;…
DEMO_BAND = "1761480000|a1b2c3d4,vocals,Camille,1,1;b2c3d4e5,drums,Max,1,0;c3d4e5f6,bass,,0,2;d4e5f6a7,guitars,L%C3%A9a,1,1;e5f6a7b8,regie,,0,3"


# --------------------------------------------------------------------------- faux REAPER
# pistes du projet de démonstration (Studio) : nom, mute, solo, volume (1 = 0 dB), pan, crête (dB)
DEMO_TRACKS = [("Chant", 0, 0, 0.69, -0.2, -9), ("Batterie", 0, 0, 0.89, 0.0, -3), ("Basse", 0, 0, 0.6, 0.0, -11),
               ("Guitares", 1, 0, 1.0, -0.4, -60), ("Claviers", 0, 0, 0.4, 0.3, -18), ("CUES", 0, 0, 1.0, 0.0, -150),
               ("VOIX", 0, 0, 0.7, 0.0, -150), ("CLICK", 0, 0, 0.8, 0.0, -14)]


def demo_tracks() -> list[dict]:
    return [{"name": n, "mute": m, "solo": so, "vol": v, "pan": pa, "peak": pk} for n, m, so, v, pa, pk in DEMO_TRACKS]


def demo_peaks(song: dict) -> dict:
    """Formes d'onde inventées (enveloppes sinusoïdales) au format de reacue_peaks.json."""
    import math
    import numpy as np
    from reacue_mcp import studio
    hop = studio.HOP
    n = int(math.ceil((song["bar_times"][-1] + 1) / hop))
    t = np.arange(n) * hop
    out = []
    for k, (name, role) in enumerate((("Chant", "vocals"), ("Batterie", "drums"), ("Basse", "bass"),
                                      ("Guitares", "guitars"), ("Claviers", "keys"))):
        seed = 0.7 + 0.37 * k
        env = 0.25 + 0.75 * np.abs(np.sin(t * 0.9 * seed + seed) * np.cos(t * 0.13 + 2 * seed))
        env[t < song["bar_times"][2]] = 0.0              # count-in : silence
        if role == "vocals":
            env *= (np.sin(t * 0.21) > -0.3)
        data, peak = studio.encode_peaks(-env.astype(np.float32), env.astype(np.float32))
        out.append({"name": name, "role": role, "guid": "", "peak": peak, "data": data})
    return {"version": 1, "song_id": song["id"], "hop": hop, "n": n, "duration": round(n * hop, 3), "sr": 44100,
            "tracks": out, "tc": {"fps": 25, "tc_start": "01:00:00:00", "offset_s": 3600.0, "ltc": True, "mtc": False}}


class FakeReaper(SimpleHTTPRequestHandler):
    song: dict = {}
    pos: float = 0.0
    play: int = 0
    mix: str = ""
    rehearsal: str = ""
    studio: str = ""
    peaks: dict | None = None
    export: dict | None = None
    tctest: str = ""                # test timecode en cours : secondes restantes
    band: str = ""                  # prompteurs connectés (écran GROUPE)
    library: dict | None = None     # reacue_library.json (écran BIBLIO)
    tracks: list = []
    log: list = []                  # commandes SET/… et actions reçues (tests)

    def log_message(self, *a):
        pass

    def _api(self, path: str) -> bytes:
        """/_/cmd;cmd;… : TRANSPORT, TRACK, GET/EXTSTATE, SET/TRACK, SET/POS, SET/EXTSTATE (accusé immédiat)."""
        cls = FakeReaper
        ext = {"mix": cls.mix, "remote_alive": str(int(time.time() * 2)), "remote_ack": cls.__dict__.get("ack", ""),
               "rehearsal": cls.rehearsal, "studio": cls.studio, "tctest": cls.tctest, "band": cls.band}
        body = ""
        for c in path[3:].split(";"):
            c = unquote(c)
            if c == "TRANSPORT":
                body += f"TRANSPORT\t{cls.play}\t{cls.pos:.4f}\t0\t1.1.00\t1.1.00\n"
            elif c == "TRACK":
                for i, tr in enumerate(cls.tracks, 1):
                    fl = (8 if tr["mute"] else 0) | (16 if tr["solo"] else 0)
                    body += (f"TRACK\t{i}\t{tr['name']}\t{fl}\t{tr['vol']:.6f}\t{tr['pan']:.6f}\t{int(tr['peak'] * 10)}"
                             f"\t{int(tr['peak'] * 10)}\t1.0\t3\t0\t0\t0\t0\n")
            elif c.startswith("GET/EXTSTATE/ReaCue/"):
                key = c.split("/")[3]
                body += f"EXTSTATE\tReaCue\t{key}\t{ext.get(key, '')}\n"
            elif c.startswith("SET/") or c.isdigit():
                cls.log.append(c)
                part = c.split("/")
                if part[:2] == ["SET", "TRACK"] and len(part) >= 5 and part[2].isdigit():
                    i = int(part[2]) - 1
                    if 0 <= i < len(cls.tracks):
                        key, v = part[3], float(part[4])
                        tr = cls.tracks[i]
                        if key in ("MUTE", "SOLO"):
                            tr[key.lower()] = (1 - tr[key.lower()]) if v < 0 else int(v)
                        elif key in ("VOL", "PAN"):
                            tr[key.lower()] = v
                elif part[:2] == ["SET", "POS"]:
                    cls.pos = float(part[2])
                elif c.startswith("SET/EXTSTATE/ReaCue/remote/"):
                    v = c[len("SET/EXTSTATE/ReaCue/remote/"):].split("|")
                    if len(v) == 4:
                        cls.ack = f"{v[3]}|{'ok' if v[2] == '1234' else 'badpin'}"
        return body.encode("utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/_/"):           # API web : transport, pistes, EXTSTATE ReaCue (instruments, Régie, Studio)
            body, ctype = self._api(path), "text/plain"
        elif path == "/reacue_song.json":
            body, ctype = json.dumps(self.song, ensure_ascii=False).encode("utf-8"), "application/json"
        elif path in ("/reacue_peaks.json", "/reacue_export.json", "/reacue_library.json"):
            d = {"/reacue_peaks.json": FakeReaper.peaks, "/reacue_export.json": FakeReaper.export,
                 "/reacue_library.json": FakeReaper.library}[path]
            if d is None:
                self.send_error(404)
                return
            body, ctype = json.dumps(d).encode("utf-8"), "application/json"
        elif path in ("/", "/prompteur.html"):
            body, ctype = PAGE.read_bytes(), "text/html; charset=utf-8"
        elif (path == "/studio.html" or path.startswith("/reacue_studio/")) and ".." not in path:
            f = WEB / unquote(path.lstrip("/"))
            if not f.is_file():
                self.send_error(404)
                return
            body, ctype = f.read_bytes(), CTYPES.get(f.suffix, "application/octet-stream")
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(FakeReaper))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# position affichée pour chaque vue : (mesure, temps 0-based)
VIEWS = {
    "drums": (21, 1.2),        # couplet 1 : groove, pré-refrain bientôt
    "bass": (31, 2.3),         # refrain 1
    "guitars": (27, 2.6),      # pré-refrain : changement d'accord imminent
    "vocals": (11, 1.6),       # couplet 1, ligne en cours
    "lead_guitar": (93, 1.0),  # solo
    "all": (30, 0.5),
    "light": (31, 0.5),        # refrain 1 : cue en cours surligné
}
TABLET_VIEWS = {"drums": (24, 1.2), "vocals": (30, 1.5)}   # fill avant le pré-refrain ; refrain 1
PHONE = {"width": 390, "height": 844}
S_LIGHT = {"fr": "Refrain 1", "en": "Chorus 1"}      # cue attendu dans la liste de l'onglet Lumière
TABLET = {"width": 1180, "height": 820}


def run(out: Path | None, check_only: bool) -> list[str]:
    from playwright.sync_api import sync_playwright
    srv, base = serve()
    errors, shots = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for lang in ("fr", "en"):
                FakeReaper.song = demo_song(lang)
                plan = [(r, PHONE, "phone") for r in VIEWS] + [("drums", TABLET, "tablet"), ("vocals", TABLET, "tablet")]
                for role, vp, kind in plan:
                    bar, beat = (TABLET_VIEWS if kind == "tablet" else VIEWS)[role]
                    FakeReaper.pos = bar_time(bar, beat)
                    ctx = browser.new_context(viewport=vp, device_scale_factor=2 if kind == "phone" else 1.5,
                                              locale="fr-FR" if lang == "fr" else "en-US")
                    page = ctx.new_page()
                    page.on("console", lambda m, r=role, lg=lang: m.type == "error" and errors.append(f"{lg}/{r}: {m.text}"))
                    page.on("pageerror", lambda e, r=role, lg=lang: errors.append(f"{lg}/{r}: {e}"))
                    page.goto(f"{base}/prompteur.html?role={role}&lang={lang}")
                    page.wait_for_function("document.getElementById('nowName').textContent !== '—'", timeout=8000)
                    page.wait_for_timeout(600)
                    if role == "light" and S_LIGHT[lang] not in (page.text_content("#lCues") or ""):
                        errors.append(f"{lang}/light: cue list missing")
                    if role == "light" and not page.is_visible("#lCues .row.cur"):
                        errors.append(f"{lang}/light: current cue not highlighted")
                    if out and not check_only and role in ("drums", "vocals", "light"):
                        f = out / f"prompter_{role}_{lang}{'_tablet' if kind == 'tablet' else ''}.png"
                        page.screenshot(path=str(f))
                        shots.append(f.name)
                    ctx.close()
            # mode concert (2e morceau, stem de la batterie coupé) et Régie (télécommande, PIN 1234)
            for lang in ("fr", "en"):
                data = demo_concert(lang)
                s2 = data["songs"][1]
                bt = lambda bar, beat=0.0: bar_time(bar, beat, s2["bpm"], s2["start_t"])
                FakeReaper.song = data
                FakeReaper.mix = "vocals=1,drums=0L,bass=1,guitars=1;;0;2"
                chorus = next(x for x in s2["sections"] if x["start_bar"] == 29)
                shots_c = [("drums", "concert", PHONE, bt(21, 1.2), 0, ""),
                           ("vocals", "concert_vocals", PHONE, bt(11, 1.6), 0, ""),
                           ("regie", "regie", PHONE, bt(31, 0.5), 1,
                            f"1|0.9|{bt(29):.3f}|{bt(45):.3f}|{chorus['name']}")]
                for role, name, vp, pos, play, reh in shots_c:
                    FakeReaper.pos, FakeReaper.play, FakeReaper.rehearsal = pos, play, reh
                    ctx = browser.new_context(viewport=vp, device_scale_factor=2, locale="fr-FR" if lang == "fr" else "en-US")
                    ctx.add_init_script("localStorage.setItem('reacue_pin', '1234')")
                    page = ctx.new_page()
                    page.on("console", lambda m, r=name, lg=lang: m.type == "error" and errors.append(f"{lg}/{r}: {m.text}"))
                    page.on("pageerror", lambda e, r=name, lg=lang: errors.append(f"{lg}/{r}: {e}"))
                    page.goto(f"{base}/prompteur.html?role={role}&lang={lang}")
                    sel = "rTitle" if role == "regie" else "nowName"
                    page.wait_for_function(f"document.getElementById('{sel}').textContent !== '—'", timeout=8000)
                    page.wait_for_timeout(900)
                    rank = page.text_content("#rRank" if role == "regie" else "#title") or ""
                    if "2" not in rank:
                        errors.append(f"{lang}/{name}: concert rank missing ({rank!r})")
                    if out and not check_only:
                        f = out / f"prompter_{name}_{lang}.png"
                        page.screenshot(path=str(f))
                        shots.append(f.name)
                        if role == "regie":           # bas de la Régie : sections, setlist
                            page.eval_on_selector("#regie", "e => e.scrollTop = e.scrollHeight")
                            page.wait_for_timeout(300)
                            f = out / f"prompter_regie2_{lang}.png"
                            page.screenshot(path=str(f))
                            shots.append(f.name)
                    ctx.close()
            FakeReaper.mix, FakeReaper.play, FakeReaper.rehearsal = "", 0, ""
            # ReaCue Studio, écran Travail (bureau 1440 × 900) : refrain en boucle, rampe 85 → 100 %, 4e passage
            for lang in ("fr", "en"):
                song = demo_song(lang)
                ch2 = next(x for x in song["sections"] if x["start_bar"] == 65)
                FakeReaper.song, FakeReaper.peaks, FakeReaper.tracks = song, demo_peaks(song), demo_tracks()
                FakeReaper.pos, FakeReaper.play = bar_time(70, 2.3), 1
                FakeReaper.rehearsal = f"1|0.94|{bar_time(65):.3f}|{bar_time(81):.3f}|{ch2['name']}"
                FakeReaper.studio = "0.940|0|4|8|0.85|1.00"
                ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                          locale="fr-FR" if lang == "fr" else "en-US")
                ctx.add_init_script("localStorage.setItem('reacue_studio_me', 'Guitares')")
                page = ctx.new_page()
                page.on("console", lambda m, lg=lang: m.type == "error" and errors.append(f"{lg}/studio: {m.text}"))
                page.on("pageerror", lambda e, lg=lang: errors.append(f"{lg}/studio: {e}"))
                page.goto(f"{base}/studio.html?lang={lang}")
                page.wait_for_function("document.querySelectorAll('.tv-row').length >= 5", timeout=8000)
                page.wait_for_timeout(700)
                if song["title"].upper() not in (page.text_content("#title") or "").upper():
                    errors.append(f"{lang}/studio: title missing")
                if out and not check_only:
                    f = out / f"studio_{lang}.png"
                    page.screenshot(path=str(f))
                    shots.append(f.name)
                ctx.close()
            FakeReaper.play, FakeReaper.rehearsal, FakeReaper.studio, FakeReaper.peaks = 0, "", "", None
            FakeReaper.tracks = []
            # ReaCue Studio, écrans Concert et Lumière (concert fictif, 2e morceau, refrain 1 en lecture)
            for lang in ("fr", "en"):
                data = demo_concert(lang)
                s2 = data["songs"][1]
                FakeReaper.song, FakeReaper.tracks, FakeReaper.peaks = data, demo_tracks(), demo_peaks(s2)
                FakeReaper.pos, FakeReaper.play = bar_time(31, 2.5, s2["bpm"], s2["start_t"]), 1
                for mode in ("concert", "lumiere"):
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                              locale="fr-FR" if lang == "fr" else "en-US")
                    page = ctx.new_page()
                    page.on("console", lambda m, lg=lang, md=mode: m.type == "error" and errors.append(f"{lg}/{md}: {m.text}"))
                    page.on("pageerror", lambda e, lg=lang, md=mode: errors.append(f"{lg}/{md}: {e}"))
                    page.goto(f"{base}/studio.html?lang={lang}#{mode}")
                    sel = "#csSecs .cs-sec.now" if mode == "concert" else "#lmList .cs-cue.now"
                    page.wait_for_selector(sel, timeout=8000)
                    page.wait_for_timeout(600)
                    if mode == "concert" and "Second Demo".upper() not in (page.text_content("#csTitle") or "").upper():
                        errors.append(f"{lang}/concert: title missing")
                    if out and not check_only:
                        f = out / f"studio_{mode}_{lang}.png"
                        page.screenshot(path=str(f))
                        shots.append(f.name)
                    ctx.close()
            FakeReaper.play, FakeReaper.tracks, FakeReaper.peaks = 0, [], None
            # ReaCue Studio, écrans Biblio (bibliothèque fictive) et Groupe (concert fictif, 2e morceau, musiciens)
            for lang in ("fr", "en"):
                data = demo_concert(lang)
                s2 = data["songs"][1]
                FakeReaper.song, FakeReaper.tracks, FakeReaper.library = data, demo_tracks(), demo_library(lang)
                FakeReaper.peaks = demo_peaks(s2)
                FakeReaper.band = DEMO_BAND
                for mode, pos, sel in (("biblio", bar_time(31, 2.5, s2["bpm"], s2["start_t"]), "#bbRows .bb-row"),
                                       ("groupe", bar_time(31, 2.5, s2["bpm"], s2["start_t"]), "#grNotes .gr-note.now")):
                    FakeReaper.pos, FakeReaper.play = pos, 1
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                              locale="fr-FR" if lang == "fr" else "en-US")
                    page = ctx.new_page()
                    page.on("console", lambda m, lg=lang, md=mode: m.type == "error" and errors.append(f"{lg}/{md}: {m.text}"))
                    page.on("pageerror", lambda e, lg=lang, md=mode: errors.append(f"{lg}/{md}: {e}"))
                    page.goto(f"{base}/studio.html?lang={lang}#{mode}")
                    page.wait_for_selector(sel, timeout=8000)
                    if mode == "groupe":
                        page.wait_for_selector("#grBand .gr-mus", timeout=8000)
                    page.wait_for_timeout(600)
                    if out and not check_only:
                        f = out / f"studio_{mode}_{lang}.png"
                        page.screenshot(path=str(f))
                        shots.append(f.name)
                    ctx.close()
            FakeReaper.play, FakeReaper.tracks, FakeReaper.library, FakeReaper.band = 0, [], None, ""
            FakeReaper.peaks = None
            # bouton de langue : FR -> EN sans erreur, mémorisé
            ctx = browser.new_context(viewport=PHONE)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(f"toggle: {e}"))
            FakeReaper.song = demo_song("fr")
            page.goto(f"{base}/prompteur.html?role=bass")
            page.wait_for_function("document.getElementById('nowName').textContent !== '—'", timeout=8000)
            page.click("#langBtn")
            page.wait_for_timeout(300)
            if page.text_content("#nextK") != "Next":
                errors.append("toggle: language button did not switch to English")
            ctx.close()
            browser.close()
    finally:
        srv.shutdown()
    if errors:
        raise SystemExit("Erreurs dans la page :\n" + "\n".join(errors))
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "images"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = run(out, args.check)
    print("OK, aucune erreur console." + (f" Captures : {', '.join(shots)}" if shots else ""))


if __name__ == "__main__":
    main()
