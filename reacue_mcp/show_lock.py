"""Shared performance lock for the native window, CLI and MCP operations."""
from __future__ import annotations

import json
from pathlib import Path


def locked(directory: Path | None = None) -> bool:
    if directory is None:
        from .bridge import BRIDGE_DIR
        directory = BRIDGE_DIR
    path = Path(directory) / "show_lock.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return not isinstance(data, dict) or data.get("locked") is not False
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return True


def message() -> str:
    from .i18n import get_lang
    return ("Concert locked. Unlock editing in the Stage tab first." if get_lang() == "en"
            else "Concert verrouillé. Déverrouille les modifications dans l’onglet Scène.")


def require_edit(directory: Path | None = None) -> None:
    if locked(directory):
        raise RuntimeError(message())
