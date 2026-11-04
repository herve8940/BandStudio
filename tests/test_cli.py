"""CLI (boutons REAPER) et serveur avec un faux pont REAPER : aucun audio, aucun REAPER."""
import json
from pathlib import Path

import numpy as np
import pytest

from reacue_mcp import cli, server, i18n
from reacue_mcp.analysis import Analysis, Section


def fake_analysis(file="/songs/Demo/drums.wav"):
    bar = 2.0
    db = [0.5 + k * bar for k in range(41)]
    secs = [Section(0, 8, "A", "Intro"), Section(8, 24, "B", "Couplet 1"), Section(24, 32, "C", "Refrain 1"),
            Section(32, 36, "D", "Pont"), Section(36, 40, "C", "Refrain 2")]
    return Analysis(file=file, duration=90.0, bpm=120.0, beats_per_bar=4, denominator=4, tempo_stable=True,
                    tempo_cv=0.001, beats=list(np.arange(0.5, 80.6, 0.5)), downbeats=db, sections=secs,
                    warnings=[i18n.t("bpm_from_name", bpm=120.0)])


class FakeBridge:
    def __init__(self, version="1.3.0", items=None):
        self.version = version
        self.items = items if items is not None else [
            {"guid": "{D}", "file": "/songs/Demo/Demo-drums.wav", "position": 0.0, "offset": 0.0, "rate": 1.0,
             "track": "Drums", "track_idx": 1, "length": 90.0},
            {"guid": "{B}", "file": "/songs/Demo/Demo-bass.wav", "position": 0.0, "offset": 0.0, "rate": 1.0,
             "track": "Bass", "track_idx": 2, "length": 90.0}]
        self.plans = []

    async def call(self, cmd, args=None, timeout=30.0):
        if cmd == "ping":
            return {"bridge": self.version, "reaper": "7.27", "project": "", "items": 2, "tracks": 2}
        if cmd == "get_audio_items":
            return {"items": [dict(i) for i in self.items], "selected_guids": []}
        if cmd == "apply_plan":
            self.plans.append(args)
            return {"warnings": [], "state": {"regions": args["regions"], "markers": args["markers"],
                                              "tempo": args["tempo"], "tracks": []},
                    "click_items": 1, "cue_items": len(args["cues"]["items"]),
                    "voice_items": len(args["voice"]["items"])}
        if cmd == "get_state":
            return {"tracks": ["Drums", "Bass"]}
        raise AssertionError(cmd)

    def alive(self):
        return True, "ok"


class FakeVoice:
    def __init__(self, cache, voice=None, rate=200, lang="fr", **kw):
        self.lang, self.warnings, self.available = lang, [], True

    def render(self, text, max_len=None):
        return f"/voice/{self.lang}/{text}.wav"


@pytest.fixture
def env(monkeypatch, bridge_dir, resdir, tmp_path):
    fb = FakeBridge()
    # grille PDF : dans un dossier temporaire (les fichiers de test pointent vers /songs/…)
    monkeypatch.setattr(server.sheet, "song_folder", lambda files: tmp_path / "song")
    monkeypatch.setattr(server.bridge, "call", fb.call)
    monkeypatch.setattr(server.bridge, "alive", fb.alive)
    monkeypatch.setattr(server, "analyze_stems", lambda *a, **k: fake_analysis())
    monkeypatch.setattr(server, "analyze", lambda *a, **k: fake_analysis())
    monkeypatch.setattr(server, "Voice", FakeVoice)
    monkeypatch.setattr(server.chords, "cached_chords", lambda *a, **k: [
        {"bar": b, "chords": [{"beat": 1, "chord": "Am", "bass": "A", "confidence": 0.9}]} for b in range(1, 41)])
    monkeypatch.setattr(server.lyrics, "cached_lyrics", lambda *a, **k: None)
    monkeypatch.setattr(server.drums, "cached_drums", lambda *a, **k: {"steps": 16, "lanes": [], "patterns": {}, "bars": []})
    monkeypatch.setattr(server.prompter, "stem_activity", lambda *a, **k: {"drums": [1] * 40, "bass": [1] * 40})
    (bridge_dir / "last_session.json").unlink(missing_ok=True)
    yield fb
    (bridge_dir / "last_session.json").unlink(missing_ok=True)


def status(bridge_dir):
    return json.loads((bridge_dir / "cli_status.json").read_text(encoding="utf-8"))


def test_prepare_french(env, lang, bridge_dir, resdir):
    lang("fr")
    assert cli.main(["prepare", "--resource-dir", str(resdir)]) == 0
    st = status(bridge_dir)
    assert st["state"] == "done"
    assert st["prompter_published"] is True
    assert st["message"].startswith("Morceau préparé") and "Refrain 1" in st["message"]
    assert "lu dans le nom" not in st["message"]                     # avertissement informatif masqué
    plan = env.plans[-1]
    assert [r["name"] for r in plan["regions"]] == ["Intro", "Couplet 1", "Refrain 1", "Pont", "Refrain 2"]
    assert plan["voice"]["track_name"] == "VOIX"
    said = {Path(v["file"]).stem for v in plan["voice"]["items"]}
    assert {"Refrain", "Couplet", "Pont", "one", "two", "three", "four"} <= said      # décompte anglais
    assert all("/voice/fr/" in v["file"] for v in plan["voice"]["items"] if not v["name"].startswith("count"))
    song = json.loads((resdir / "reaper_www_root" / "reacue_song.json").read_text(encoding="utf-8"))
    assert song["language"] == "fr" and song["sections"][2]["type"] == "chorus"
    assert (resdir / "reaper_www_root" / "prompteur.html").exists()
    assert song["count_in_bars"] == 2


def test_prepare_reports_failed_publication_for_flow_retry(env, lang, bridge_dir, monkeypatch):
    lang("fr")
    def fail(*a, **k):
        raise OSError("publication unavailable")
    monkeypatch.setattr(server.prompter, "publish", fail)
    assert cli.main(["prepare", "--reanalyse"]) == 0  # REAPER plan succeeded
    st = status(bridge_dir)
    assert st["state"] == "done" and st["prompter_published"] is False
    assert "publication unavailable" in st["message"]


def test_publication_exposes_auto_lyrics_warning_and_clears_previous_job(env, lang, monkeypatch):
    import asyncio
    from reacue_mcp import lyrics_auto
    lang("fr")
    def auto(*a, **k):
        lyrics_auto.LAST_INFO.update({"state": "existing", "model": "small", "selected_model": "turbo",
                                      "warning": "Existing small draft kept"})
        return None
    monkeypatch.setattr(server.lyrics, "cached_lyrics", auto)
    result = asyncio.run(server.prepare_song(reanalyse=True))["prompteur"]
    assert result["lyrics_auto"]["model"] == "small"
    assert result["lyrics_auto"]["selected_model"] == "turbo"
    assert "Existing small draft kept" in result["warning"]
    monkeypatch.setattr(server.lyrics, "cached_lyrics", lambda *a, **k: None)
    result = asyncio.run(server.prepare_song(reanalyse=True))["prompteur"]
    assert result["lyrics_auto"] == {}
    assert "Existing small draft kept" not in result.get("warning", "")


def test_prepare_english(env, lang, bridge_dir, resdir):
    lang("en")
    assert cli.main(["prepare"]) == 0
    st = status(bridge_dir)
    assert st["message"].startswith("Song prepared") and "Chorus 1" in st["message"] and "Structure:" in st["message"]
    plan = env.plans[-1]
    assert [r["name"] for r in plan["regions"]] == ["Intro", "Verse 1", "Chorus 1", "Bridge", "Chorus 2"]
    assert [m["name"] for m in plan["markers"]][1:3] == ["→ Intro", "→ Verse 1"]
    assert plan["voice"]["track_name"] == "VOICE"
    said = {Path(v["file"]).stem for v in plan["voice"]["items"]}
    assert {"Chorus", "Verse", "Bridge", "one"} <= said
    song = json.loads((resdir / "reaper_www_root" / "reacue_song.json").read_text(encoding="utf-8"))
    assert song["language"] == "en" and song["sections"][1]["name"] == "Verse 1"
    # le même morceau : reconstruit sans réanalyse, structure conservée
    assert cli.main(["prepare"]) == 0
    assert status(bridge_dir)["message"].startswith("Song rebuilt")
    # republier seulement le prompteur
    n = len(env.plans)
    assert cli.main(["publish"]) == 0
    assert status(bridge_dir)["message"].startswith("Prompter republished") and len(env.plans) == n


@pytest.mark.parametrize("chord_info", [
    {"engine": "reacue", "fallback": True, "message": "Chord model failed; rules used"},
    {"engine": "reacue", "warning": "Chord model failed; rules used"},
])
def test_publication_exposes_model_fallbacks_and_clears_previous_job(env, lang, monkeypatch, chord_info):
    import asyncio
    from reacue_mcp import chord_model
    lang("en")

    def fallback(*a, **k):
        chord_model.LAST.update(chord_info)
        return []

    monkeypatch.setattr(server.chords, "cached_chords", fallback)
    monkeypatch.setattr(server.drums, "cached_drums", lambda *a, **k: {
        "engine": "adtof", "bars": [], "warning": "ADT_STR missing; ADTOF used"})
    result = asyncio.run(server.prepare_song(reanalyse=True))["prompteur"]
    assert result["data"]
    assert "Chord model failed; rules used" in result["warning"]
    assert "ADT_STR missing; ADTOF used" in result["warning"]

    monkeypatch.setattr(server.chords, "cached_chords", lambda *a, **k: [])
    monkeypatch.setattr(server.drums, "cached_drums", lambda *a, **k: {"bars": []})
    result = asyncio.run(server.prepare_song(reanalyse=True))["prompteur"]
    assert "Chord model failed; rules used" not in result.get("warning", "")
    assert "ADT_STR missing; ADTOF used" not in result.get("warning", "")


def test_old_bridge_keeps_voix_track(env, lang, monkeypatch):
    lang("en")
    env.version = "1.2.0"
    assert cli.main(["prepare", "--reanalyse"]) == 0
    assert env.plans[-1]["voice"]["track_name"] == "VOIX"


def test_error_message_localized(env, lang, bridge_dir, monkeypatch):
    lang("en")
    env.items = []
    assert cli.main(["prepare", "--reanalyse"]) == 1
    st = status(bridge_dir)
    assert st["state"] == "error" and st["message"].startswith("Error: No audio item")


def test_exception_logged(env, lang, bridge_dir, monkeypatch):
    lang("fr")

    async def boom(*a, **k):
        raise RuntimeError("panne simulée")
    monkeypatch.setattr(server.bridge, "call", boom)
    assert cli.main(["prepare"]) == 1
    st = status(bridge_dir)
    assert "panne simulée" in st["message"] and "cli.log" in st["message"]
    assert "panne simulée" in (bridge_dir / "cli.log").read_text(encoding="utf-8")


def test_old_session_options_loaded(env, bridge_dir):
    """Session écrite par l'ancienne version (options sans les nouvelles clés, clé inconnue) : chargée."""
    a = fake_analysis()
    d = {"analysis": a.to_dict(), "item": {"guid": "{D}", "file": "/x.wav", "position": 0.0},
         "options": {"count_in_bars": 2, "voice_name": "Thomas", "obsolete": 1}}
    (bridge_dir / "last_session.json").write_text(json.dumps(d), encoding="utf-8")
    a2, item, opts, items = server._load()
    assert opts.count_in_bars == 2 and opts.voice_name == "Thomas" and items is None


def test_settings_changed_after_preparation_are_applied(env, lang, bridge_dir):
    lang("fr", click_to_master=True)
    assert cli.main(["prepare"]) == 0
    # réglage fait avec Claude entre-temps : à garder
    sess = json.loads((bridge_dir / "last_session.json").read_text(encoding="utf-8"))
    sess["options"]["click_to_master"] = False
    (bridge_dir / "last_session.json").write_text(json.dumps(sess), encoding="utf-8")
    assert cli.main(["prepare"]) == 0                                 # réglages inchangés : session gardée
    assert env.plans[-1]["click"]["to_master"] is False
    lang("fr", click_to_master=True, count_in_bars=4)                 # l'utilisateur change le count-in
    assert cli.main(["prepare"]) == 0
    sess = json.loads((bridge_dir / "last_session.json").read_text(encoding="utf-8"))
    assert sess["options"]["count_in_bars"] == 4 and sess["options"]["click_to_master"] is False
    song = json.loads((bridge_dir.parent / "reaper_www_root" / "reacue_song.json").read_text(encoding="utf-8"))
    assert song["count_in_bars"] == 4


def test_old_session_without_settings_snapshot_untouched(env, lang, bridge_dir):
    lang("fr")
    assert cli.main(["prepare"]) == 0
    sess = json.loads((bridge_dir / "last_session.json").read_text(encoding="utf-8"))
    del sess["settings"]
    sess["options"]["voice_name"] = "Thomas"
    (bridge_dir / "last_session.json").write_text(json.dumps(sess), encoding="utf-8")
    lang("fr", count_in_bars=1, announce_voice="Amélie")
    assert cli._changed_settings(server) == {}


def test_prepare_structure_progress_and_message(env, lang, bridge_dir, resdir, monkeypatch):
    """« Analyse de structure… » visible dans REAPER pendant l'analyse, puis rappelée dans le résumé."""
    from reacue_mcp import structure
    lang("fr")
    seen = {}

    def fake_engine(a, stems=None, title=None, **kw):
        structure.PROGRESS(i18n.t("structure_running", s=12))
        seen["step"] = status(bridge_dir).get("step")
        seen["stems"] = [s["file"] for s in stems]
        return a, {"engine": "songformer", "cached": False, "message": i18n.t("structure_used", s=12)}
    monkeypatch.setattr(server.structure, "apply_engine", fake_engine)
    assert cli.main(["prepare", "--resource-dir", str(resdir)]) == 0
    assert seen["step"].startswith("Analyse de structure (SongFormer)") and status(bridge_dir)["state"] == "done"
    assert seen["stems"][0].endswith("Demo-drums.wav") and len(seen["stems"]) == 2
    assert "Sections détectées par SongFormer" in status(bridge_dir)["message"]
