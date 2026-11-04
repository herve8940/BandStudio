"""Réglages utilisateur : <ressources REAPER>/ReaCueMCP/reacue_settings.json.

Le fichier est créé par l'installateur ; toute clé absente prend sa valeur par défaut, une clé
inconnue est ignorée. Lu à chaque préparation (pas besoin de redémarrer quoi que ce soit).
"""
from __future__ import annotations

import json
from pathlib import Path

from .bridge import BRIDGE_DIR

SETTINGS_NAME = "reacue_settings.json"

DEFAULTS: dict = {
    "performance_profile": "standard",  # standard | fast (compromis vitesse/qualité explicite)
    "cpu_threads": 0,             # 0 = automatique ; sinon nombre de threads PyTorch
    "language": "fr",            # "fr" | "en" : régions, annonces, prompteur, messages
    "announce_voice": None,      # voix des annonces (macOS : Thomas… ; Windows : Microsoft Hortense…) ; None = auto
    "count_voice": None,         # voix du décompte ; None = auto (voix anglaise si count_lang = "en")
    "count_lang": "en",          # langue du décompte : "en" (one two three four) | "fr" (un deux trois quatre)
    "count_in_bars": 2,          # mesures de click avant la mesure 1
    "cue_lead_bars": 2,          # annonce N mesures avant la section (2 = avant-dernière mesure)
    "voice_cues": True,          # annonces vocales (« Refrain »…)
    "voice_count_in": True,      # décompte sur la dernière mesure du count-in
    "voice_count_each": True,    # décompte sur la dernière mesure de chaque section
    "voice_volume": 0.8,
    "click_volume": 0.5,
    "click_to_master": True,     # False : click et voix seulement sur la sortie click_hw_output
    "click_hw_output": None,     # sortie physique (0 = 1/2, 2 = 3/4…) ; None = aucune
    "tempo_mode": "auto",        # auto | constant | beatmap
    "count_rate": 240,           # débit du décompte (mots/min)
    "stems_model": "htdemucs",  # 4 stems équilibrés ; 6 sources et 4 HQ sur demande
    "structure_engine": "auto",  # sections : "auto" (SongFormer s'il est installé, sinon ReaCue) | "reacue"
    "chords_engine": "auto",     # auto (modèle puis règles), reacue, off
    "drums_engine": "adtof",     # auto/adtof (ADTOF puis règles), adt-str explicite, reacue, off
    "projects_dir": None,        # mode concert : dossier des projets des morceaux ; None = <Documents>/REAPER Media
    "concert_dir": None,         # mode concert : dossier des concerts ; None = <dossier des projets>/Concerts
    # paroles mot par mot (composant optionnel .venv-words)
    "words_engine": "off",       # lignes par défaut ; auto = calage mot par mot facultatif
    "words_language": "auto",    # langue chantée : "auto" (déduite du texte des paroles) | "fr" | "en"
    # paroles automatiques (Whisper, dans .venv-words) : brouillon « paroles (auto).txt » sans fichier de paroles
    "lyrics_auto": "auto",       # "auto" (si Whisper est installé) | "off"
    "lyrics_model": "small",     # Essentiel : small ; Avancé : large-v3-turbo
    # lumière grandMA3 (lighting.py) : Sequence + Timecode + fiche de conduite à chaque préparation / concert
    "gma3_export": True,         # False : aucun fichier lumière
    "gma3_fps": 25,              # images/s du timecode SMPTE (24, 25, 29.97, 30)
    "gma3_tc_start": "00:00:00:00",  # timecode du début du projet (ex. "01:00:00:00"), ajouté aux temps du XML
    "gma3_song_gap": None,       # concert : blanc minimum entre deux morceaux (s) ; None = celui de la setlist (4 s)
    "gma3_song_slot": 0,         # concert : créneau rond (s) du départ de chaque morceau (600 = 0, 10 min…) ; 0 = non
    # timecode envoyé par REAPER (timecode.py) : pistes TIMECODE LTC / TIMECODE MTC ; vide = pas de piste
    "gma3_ltc_output": None,     # sortie audio du LTC : 7 (= sortie 7, mono) ou "7/8" (paire) ; None = aucune
    "gma3_mtc_output": None,     # sortie MIDI du MTC : nom du périphérique ("IAC Driver Bus 1", "Réseau MIDI"…)
    "gma3_tc_slot": 1,           # TC Slot grandMA3 (1 à 8) réglé par le plugin ReaCue
}

LANGS = ("fr", "en")


def settings_path() -> Path:
    return BRIDGE_DIR / SETTINGS_NAME


def load_settings(path: Path | None = None) -> dict:
    """Réglages fusionnés avec les valeurs par défaut (fichier absent ou illisible : défauts)."""
    out = dict(DEFAULTS)
    p = Path(path) if path else settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in DEFAULTS:
                out[k] = v
    lang = str(out.get("language") or "fr").lower()[:2]
    out["language"] = lang if lang in LANGS else "fr"
    cl = str(out.get("count_lang") or "en").lower()[:2]
    out["count_lang"] = cl if cl in LANGS else "en"
    se = str(out.get("structure_engine") or "auto").lower()
    out["structure_engine"] = se if se in ("auto", "reacue") else "auto"
    sm = str(out.get("stems_model") or DEFAULTS["stems_model"]).lower()
    out["stems_model"] = sm if sm in ("htdemucs", "htdemucs_6s", "htdemucs_ft") else DEFAULTS["stems_model"]
    we = str(out.get("words_engine") or DEFAULTS["words_engine"]).lower()
    out["words_engine"] = we if we in ("auto", "off") else DEFAULTS["words_engine"]
    wl = str(out.get("words_language") or "auto").lower()[:4]
    out["words_language"] = wl if wl in ("auto", "fr", "en") else "auto"
    la = str(out.get("lyrics_auto") or "auto").lower()
    out["lyrics_auto"] = la if la in ("auto", "off") else "auto"
    lm = str(out.get("lyrics_model") or DEFAULTS["lyrics_model"]).lower()
    out["lyrics_model"] = lm if lm in ("small", "large-v3-turbo") else DEFAULTS["lyrics_model"]
    ce = str(out.get("chords_engine") or "auto").lower()
    out["chords_engine"] = ce if ce in ("auto", "reacue", "off") else "auto"
    de = str(out.get("drums_engine") or DEFAULTS["drums_engine"]).lower()
    out["drums_engine"] = de if de in ("auto", "reacue", "adtof", "adt-str", "off") else DEFAULTS["drums_engine"]
    out["gma3_export"] = out["gma3_export"] is not False and str(out["gma3_export"]).lower() not in ("0", "false", "no")
    return out


def option_defaults(s: dict | None = None) -> dict:
    """Valeurs initiales des Options du planificateur tirées des réglages."""
    s = s or load_settings()
    return {
        "count_in_bars": int(s["count_in_bars"]),
        "cue_lead_bars": int(s["cue_lead_bars"]),
        "voice_cues": bool(s["voice_cues"]),
        "voice_count_in": bool(s["voice_count_in"]),
        "voice_count_each": bool(s["voice_count_each"]),
        "voice_volume": float(s["voice_volume"]),
        "click_volume": float(s["click_volume"]),
        "click_to_master": bool(s["click_to_master"]),
        "click_hw_output": None if s["click_hw_output"] is None else int(s["click_hw_output"]),
        "tempo_mode": s["tempo_mode"] if s["tempo_mode"] in ("auto", "constant", "beatmap") else "auto",
        "voice_name": s["announce_voice"] or None,
        "count_voice": s["count_voice"] or None,
        "count_lang": s["count_lang"],
        "count_rate": int(s["count_rate"]),
    }
