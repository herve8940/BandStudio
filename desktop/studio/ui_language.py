"""Interface language shared by the Windows host and its local workers."""
import locale
import os
from pathlib import Path

ENVIRONMENT_KEY = "BANDSTUDIO_UI_LANGUAGE"


def using_english():
    return os.environ.get(ENVIRONMENT_KEY) == "en"


def ui_text(french, english):
    return english if using_english() else french


def preference_path():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BandStudio" / "ui-language.txt"


def startup_language():
    try:
        saved = preference_path().read_text(encoding="utf-8").strip()
    except OSError:
        saved = ""
    if saved in ("fr", "en"):
        return saved
    if os.name == "nt":
        import ctypes
        language = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
    else:
        language = locale.getlocale()[0] or ""
    return "fr" if language.lower().startswith("fr") else "en"


def save_language(language):
    if language not in ("fr", "en"):
        raise ValueError("Unsupported interface language")
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as pending:
        pending.write(language)
    Path(pending.name).replace(path)
