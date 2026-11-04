"""Model choices are editable before import without starting analysis or changing the song."""
import json
from pathlib import Path

import pytest

pytest.importorskip("lupa")

import test_concert_lua as TL
import test_reacue_window as W


@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return TL.make_concert(tmp_path_factory.mktemp("model-options"))


def open_models(concert, tmp_path, initial=None, lang="fr"):
    L, g = W.rt(concert, lang=lang, proj=tmp_path / "empty.RPP", tracks=False)
    path = Path(g.RES) / "ReaCueMCP" / "reacue_settings.json"
    data = {"language": lang, "custom_key": {"keep": 7}, **(initial or {})}
    path.write_text(json.dumps(data), encoding="utf-8")
    W.open_window(L, g)
    W.frame(L, g)
    g.INITIAL_SHELL_COUNT = len(list(g.state.shell.values()))
    W.press_text(L, g, "Réglages" if lang == "fr" else "Settings", exact=True)
    W.frame(L, g)
    return L, g, path, data


def test_default_models_are_read_only_and_fit_screen(concert, tmp_path):
    L, g, path, original = open_models(concert, tmp_path)
    settings = g.REACUE_CTX.tabs.settings
    assert settings.get("stems_model") == "htdemucs"
    assert settings.get("drums_engine") == "adtof"
    assert settings.lyrics_profile() == "essential"
    assert settings.get("structure_engine") == "auto"
    assert json.loads(path.read_text()) == original
    assert "Modèle à installer" in TL.texts(g)
    assert g.REACUE_CTX.layout_h < 800
    assert len(list(g.state.shell.values())) == g.INITIAL_SHELL_COUNT


def test_lyrics_profile_is_atomic_and_preserves_other_choices(concert, tmp_path):
    L, g, path, _ = open_models(concert, tmp_path, {"stems_model": "htdemucs_6s", "words_language": "en"})
    L.execute("""
      SETTINGS_WRITES = 0
      local write = REACUE_CTX.R.write_atomic
      REACUE_CTX.R.write_atomic = function(...)
        SETTINGS_WRITES = SETTINGS_WRITES + 1
        return write(...)
      end
    """)
    W.press_text(L, g, "Avancé", exact=True)
    data = json.loads(path.read_text())
    assert (data["lyrics_auto"], data["lyrics_model"], data["words_engine"]) == ("auto", "large-v3-turbo", "auto")
    assert g.SETTINGS_WRITES == 1
    assert data["custom_key"] == {"keep": 7} and data["stems_model"] == "htdemucs_6s"
    assert data["words_language"] == "en"
    W.frame(L, g)
    W.press_text(L, g, "Désactivé", exact=True)
    data = json.loads(path.read_text())
    assert (data["lyrics_auto"], data["words_engine"]) == ("off", "off")
    assert data["lyrics_model"] == "large-v3-turbo"  # disabling does not discard model choice
    W.frame(L, g)
    W.press_text(L, g, "Essentiel", exact=True)
    data = json.loads(path.read_text())
    assert (data["lyrics_auto"], data["lyrics_model"], data["words_engine"]) == ("auto", "small", "off")
    g.REACUE_CTX.tabs.settings.enter()
    assert g.REACUE_CTX.tabs.settings.lyrics_profile() == "essential"
    assert g.SETTINGS_WRITES == 3
    assert len(list(g.state.shell.values())) == g.INITIAL_SHELL_COUNT


def test_custom_lyrics_and_installed_advanced_model_do_not_change_defaults(concert, tmp_path):
    L, g, path, original = open_models(concert, tmp_path, {"lyrics_model": "large-v3-turbo", "words_engine": "off"})
    inst = Path(W.install(g, tmp_path))
    model = inst / "words" / "whisper" / "large-v3-turbo.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"test model placeholder")
    W.frame(L, g)
    assert g.REACUE_CTX.tabs.settings.lyrics_profile() == "custom"
    assert json.loads(path.read_text()) == original
    assert len(list(g.state.shell.values())) == g.INITIAL_SHELL_COUNT


def test_failed_settings_write_preserves_effective_profile(concert, tmp_path):
    L, g, path, original = open_models(concert, tmp_path)
    L.execute("REACUE_CTX.R.write_atomic = function() return nil end")
    W.press_text(L, g, "Avancé", exact=True)
    W.frame(L, g)
    assert json.loads(path.read_text()) == original
    assert g.REACUE_CTX.tabs.settings.lyrics_profile() == "essential"
    assert any("Enregistrement impossible" in text for text in TL.texts(g))


def test_models_can_be_disabled_or_selected_explicitly(concert, tmp_path):
    L, g, path, _ = open_models(concert, tmp_path)
    g.state.menu = 3
    W.press_text(L, g, "4 stems · équilibré", exact=False)
    assert json.loads(path.read_text())["stems_model"] == "htdemucs_ft"
    W.frame(L, g)
    g.state.menu = 3
    W.press_text(L, g, "Modèles installés", exact=False)
    assert json.loads(path.read_text())["chords_engine"] == "off"
    W.frame(L, g)
    g.state.menu = 2
    W.press_text(L, g, "ADTOF · équilibré", exact=False)
    assert json.loads(path.read_text())["drums_engine"] == "adt-str"
    W.frame(L, g)
    g.state.menu = 5
    W.press_text(L, g, "ADT_STR · avancé", exact=False)
    assert json.loads(path.read_text())["drums_engine"] == "off"


def test_missing_lyrics_model_installer_opens_only_on_explicit_click(concert, tmp_path):
    L, g, path, _ = open_models(concert, tmp_path)
    inst = W.install(g, tmp_path)
    (inst / "Install ReaCue Words.command").write_text("# test installer")
    W.frame(L, g)
    assert len(list(g.state.shell.values())) == g.INITIAL_SHELL_COUNT
    buttons = [list(o.values()) for o in g.state.ops.values()
               if o[1] == "text" and o[4] == "Installer"]
    words_button = max(buttons, key=lambda o: o[2])
    TL.frame(L, g, (words_button[1] + 3, words_button[2] + 3))
    assert "Install ReaCue Words.command" in list(g.state.shell.values())[-1]
    assert g.REACUE_CTX.tabs.settings.get("lyrics_model") == "small"


def test_lyrics_status_accepts_hf_weights_and_requires_word_models_when_selected(concert, tmp_path):
    L, g, _, _ = open_models(concert, tmp_path)
    inst = W.install(g, tmp_path)
    (inst / ".venv-words" / "bin").mkdir(parents=True)
    (inst / ".venv-words" / "bin" / "python").touch()
    (inst / "reacue_transcribe.py").touch()
    (inst / "reacue_words.py").touch()
    whisper = inst / "words" / "whisper"
    whisper.mkdir(parents=True)
    (whisper / "small-hf.pt").touch()
    g.TEST_HOME = str(tmp_path / "isolated-home")
    L.execute("""
      local getenv = os.getenv
      os.getenv = function(k)
        if k == "HOME" or k == "USERPROFILE" then return TEST_HOME end
        if k == "HF_HUB_CACHE" or k == "HF_HOME" or k == "REACUE_WORDS_DIR" then return nil end
        return getenv(k)
      end
    """)
    settings = g.REACUE_CTX.tabs.settings
    assert settings.lyrics_status() == "model_present"
    settings.set_lyrics_profile("advanced")
    (whisper / "large-v3-turbo-hf.pt").touch()
    assert settings.lyrics_status() == "words_missing"
    for lang in ("fr", "en"):
        model = inst / "words" / "models" / lang
        model.mkdir(parents=True)
        for name in ("config.json", "vocab.json", "model.safetensors"):
            (model / name).touch()
    assert settings.lyrics_status() == "model_present"


@pytest.mark.parametrize("profile", ["essential", "advanced", "off"])
def test_models_layout_is_usable_in_narrow_window(concert, tmp_path, profile):
    L, g, _, _ = open_models(concert, tmp_path)
    g.REACUE_CTX.tabs.settings.set_lyrics_profile(profile)
    L.globals().gfx.w = 560
    W.frame(L, g)
    assert g.REACUE_CTX.layout_h < 800
    for op in g.state.ops.values():
        if op[1] == "text":
            assert 0 <= op[2] <= 560


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_song_options_open_models_before_preparation(concert, tmp_path, lang):
    L, g, _ = W.song_runtime(concert, tmp_path, lang=lang)
    W.install(g, tmp_path)
    W.open_window(L, g)
    W.frame(L, g)
    before = len(list(g.state.shell.values()))
    W.press_text(L, g, "Options d'analyse" if lang == "fr" else "Analysis options", exact=True)
    W.frame(L, g)
    assert g.REACUE_CTX.tab == "settings"
    assert g.REACUE_CTX.tabs.settings.page() == "models"
    assert g.REACUE_CTX.tabs.settings.lyrics_profile() == "essential"
    assert len(list(g.state.shell.values())) == before
