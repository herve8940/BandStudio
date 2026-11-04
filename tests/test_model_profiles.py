"""Profiles select costs explicitly, and disabled analyses never decode audio."""
import json
import sys
from types import SimpleNamespace

import pytest

from reacue_mcp import settings, drums, chords, chord_model, words
import reacue_setup


def test_balanced_defaults_agree_with_installer(tmp_path):
    effective = settings.load_settings(tmp_path / "absent.json")
    expected = dict(stems_model="htdemucs", performance_profile="standard",
                    structure_engine="auto", chords_engine="auto", drums_engine="adtof",
                    lyrics_auto="auto", lyrics_model="small", words_engine="off")
    for key, value in expected.items():
        assert effective[key] == reacue_setup.SETTINGS_DEFAULTS[key] == value
    assert effective["cue_lead_bars"] == effective["count_in_bars"] == 2


def test_explicit_advanced_choices_survive_loading(tmp_path):
    path = tmp_path / "settings.json"
    selected = dict(stems_model="htdemucs_ft", lyrics_model="large-v3-turbo",
                    words_engine="auto", drums_engine="adt-str", chords_engine="off")
    path.write_text(json.dumps(selected))
    effective = settings.load_settings(path)
    assert all(effective[key] == value for key, value in selected.items())


def test_bad_model_values_return_balanced_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({k: "invalid" for k in ("lyrics_model", "stems_model", "words_engine", "drums_engine")}))
    effective = settings.load_settings(path)
    assert effective["lyrics_model"] == "small"
    assert effective["stems_model"] == "htdemucs"
    assert effective["words_engine"] == "off"
    assert effective["drums_engine"] == "adtof"


def test_disabled_analyses_do_not_read_audio_or_old_cache(monkeypatch, tmp_path):
    def unexpected(*args, **kwargs):
        pytest.fail("disabled analysis started work")
    monkeypatch.setenv("REACUE_CHORDS_ENGINE", "off")
    monkeypatch.setenv("REACUE_DRUMS_ENGINE", "off")
    monkeypatch.setenv("REACUE_WORDS_ENGINE", "off")
    monkeypatch.setattr(chords, "detect_chords", unexpected)
    monkeypatch.setattr(drums, "_drum_source", unexpected)
    monkeypatch.setattr(words, "write_voice", unexpected)
    cache = tmp_path / "stale.json"
    cache.write_text('{"chords": [{"chord": "OLD"}], "drums": {"bars": [1]}}')
    assert chords.cached_chords(None, None, cache=cache) == []
    assert chord_model.LAST == {"engine": "off"}
    assert drums.cached_drums(None, cache=cache)["engine"] == "off"
    assert drums.detect_drums(None, engine="off")["bars"] == []
    lines = [{"text": "provided lyrics"}]
    assert words.add_words(None, None, lines) is lines


def test_auto_drums_never_starts_installed_advanced_model(monkeypatch):
    monkeypatch.setattr(drums, "_drum_source", lambda *args: ("drums.wav", 0))
    monkeypatch.setattr(drums, "_load_placed", lambda *args: [])
    monkeypatch.setattr(drums, "advanced_available", lambda *args: pytest.fail("advanced probed in auto"))
    monkeypatch.setattr(drums, "available", lambda *args: True)
    monkeypatch.setattr(drums, "model_onsets", lambda *args: ({}, True))
    monkeypatch.setattr(drums, "from_model", lambda *args: {"engine": "adtof"})
    assert drums.detect_drums(None, engine="auto")["engine"] == "adtof"


@pytest.mark.parametrize("selected", ["htdemucs", "htdemucs_6s", "htdemucs_ft"])
def test_reinstall_keeps_user_model_even_when_hardware_changes(tmp_path, monkeypatch, selected):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"stems_model": selected, "lyrics_model": "large-v3-turbo", "words_engine": "auto"}))
    fake = SimpleNamespace(detect_gpu=lambda: {"has_gpu": True, "is_dedicated": True, "vram_mb": 16000},
                           recommended_stems_model=lambda info: "htdemucs_6s")
    monkeypatch.setitem(sys.modules, "reacue_gpu", fake)
    reacue_setup.write_settings(path, "fr")
    data = json.loads(path.read_text())
    assert data["stems_model"] == selected
    assert data["lyrics_model"] == "large-v3-turbo" and data["words_engine"] == "auto"
    assert data["hardware"]["recommended_stems_model"] == "htdemucs_6s"
