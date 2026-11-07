#!/usr/bin/env python3
"""Install a release ZIP into temporary REAPER resources, without optional AI models."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def smoke(archive: Path):
    if sys.platform not in {"darwin", "win32"}:
        raise SystemExit("Run this check on macOS or Windows.")
    archive = archive.resolve()
    with tempfile.TemporaryDirectory(prefix="ReaCue test é ") as temporary:
        work = Path(temporary).resolve()
        resources = work / "REAPER resources"
        (resources / "Scripts").mkdir(parents=True)
        env = dict(os.environ, REAPER_RESOURCE_PATH=str(resources), REACUE_MODE="custom",
                   REACUE_MCP="no", REACUE_STEMS="no", REACUE_STRUCTURE="no", REACUE_CHORDS="no",
                   REACUE_DRUMS="no", REACUE_WORDS="no", PYTHONUTF8="1",
                   UV_CACHE_DIR=str(work / "uv cache"))

        def run(command, cwd=None):
            subprocess.run(command, cwd=cwd, env=env, check=True, timeout=600,
                           stdin=subprocess.DEVNULL)

        if sys.platform == "darwin":
            run(["ditto", "-x", "-k", str(archive), str(work)])
        else:
            env.update(REACUE_TEST_ARCHIVE=str(archive), REACUE_TEST_DEST=str(work))
            run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Expand-Archive -LiteralPath $env:REACUE_TEST_ARCHIVE -DestinationPath $env:REACUE_TEST_DEST"])
        app = work / "ReaCue"
        if sys.platform == "darwin":
            assert os.access(app / "Install ReaCue.command", os.X_OK), "Launcher lost its executable bit"
            for script in sorted(app.rglob("*.sh")) + sorted(app.glob("*.command")):
                run(["bash", "-n", str(script)])
            run(["bash", "install/install_mac.sh", "en"], app)
            python = app / ".venv/bin/python"
        else:
            env["REACUE_TEST_APP"] = str(app)
            run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "$bad = $false; Get-ChildItem -LiteralPath $env:REACUE_TEST_APP -Recurse -Filter *.ps1 | "
                 "ForEach-Object { $e = $null; "
                 "[void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$e); "
                 "if ($e.Count) { $bad = $true; $e | ForEach-Object { Write-Output $_ } } }; "
                 "if ($bad) { exit 1 }"])
            run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                 str(app / "install/install_windows.ps1"), "-Lang", "en", "-Mode", "custom",
                 "-Mcp", "no", "-Stems", "no", "-Structure", "no", "-Chords", "no", "-Drums", "no",
                 "-Words", "no", "-ReaperDir", str(resources)], app)
            python = app / ".venv/Scripts/python.exe"

        run([str(python), "reacue_cli.py", "--help"], app)
        run([str(python), "-c", "import librosa, soundfile, mcp; import reacue_mcp.server"], app)
        assert (resources / "Scripts/ReaCue/ReaCue.lua").is_file()
        assert (resources / "reaper_www_root/studio.html").is_file()
        assert (resources / "reaper_www_root/prompteur.html").is_file()
        assert (resources / "ReaCueMCP/reacue_install.txt").read_text(encoding="utf-8").strip() == str(app)
        settings = resources / "ReaCueMCP/reacue_settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["count_in_bars"] = 7
        settings.write_text(json.dumps(data), encoding="utf-8")
        # Reconfiguration must preserve the user's preferences and avoid duplicate startup entries.
        run([str(python), "install/reacue_setup.py", "install", "--lang", "en", "--install-dir", str(app),
             "--reaper-dir", str(resources), "--mcp", "no", "--reaper-running", "no"], app)
        assert json.loads(settings.read_text(encoding="utf-8"))["count_in_bars"] == 7
        assert (resources / "Scripts/__startup.lua").read_text(encoding="utf-8").count("ReaCue_Bridge.lua") == 1
        assert "REACUE_" in (resources / "reaper-kb.ini").read_text(encoding="utf-8")
        print(f"PASS: {archive.name} installed and reconfigured in a path containing spaces and accents.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    smoke(parser.parse_args().archive)
