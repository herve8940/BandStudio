"""Exercise the real Windows installer and child-process argument binding without model downloads."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("stems", "structure", "chords", "drums", "words")
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows PowerShell 5.1")


@pytest.fixture
def installer(tmp_path):
    # Keep spaces and accents: this is also the path format reported by users.
    app = tmp_path / "ReaCue é test"
    scripts = app / "install"
    scripts.mkdir(parents=True)
    (app / "calls").mkdir()
    resources = tmp_path / "REAPER resources"
    resources.mkdir()
    shutil.copyfile(ROOT / "install/install_windows.ps1", scripts / "install_windows.ps1")
    venv.EnvBuilder(with_pip=False).create(app / ".venv")
    # Only expensive dependencies and external systems are stubbed. The parent installer,
    # native powershell.exe calls, parameter binding and exit codes run unchanged.
    for module in ("librosa", "soundfile", "mcp"):
        (app / f"{module}.py").write_text('__version__ = "test"\n', encoding="utf-8")
    (scripts / "reacue_setup.py").write_text("", encoding="utf-8")
    (app / "reacue_gpu.py").write_text('print(\'{"install_words": true}\')\n', encoding="utf-8")
    for component in COMPONENTS:
        original = (ROOT / f"install/install_{component}_windows.ps1").read_text(encoding="utf-8-sig")
        signature = re.search(r"(?m)^param\([^\n]+\)", original).group()
        stub = signature + r'''
$ErrorActionPreference = "Stop"
$component = [IO.Path]::GetFileNameWithoutExtension($PSCommandPath).Replace("install_", "").Replace("_windows", "")
@{ lang = $Lang; index = $ExtraIndexUrl; has_index = $PSBoundParameters.ContainsKey("ExtraIndexUrl"); extra = @($args) } |
  ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) "calls") ($component + ".json")) -Encoding UTF8
if ($component -in ($env:REACUE_TEST_FAILURES -split ",")) { exit 23 }
exit 0
'''
        (scripts / f"install_{component}_windows.ps1").write_text(stub, encoding="utf-8-sig")
    harness = app / "harness.ps1"
    harness.write_text(r'''
$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ne 5) { throw "This regression must run in Windows PowerShell 5.1" }
function uv {
  $global:LASTEXITCODE = 0
  if ($args[0] -eq "--version") { "uv test (downloads disabled)" }
}
function nvidia-smi {
  $global:LASTEXITCODE = 0
  if ($env:REACUE_TEST_GPU) { "$($env:REACUE_TEST_GPU), 8192" }
}
function Get-ItemProperty {
  [CmdletBinding()] param([string]$Path)
  # No real registry access: the GPU is supplied by this test.
}
& (Join-Path $PSScriptRoot "install\install_windows.ps1") -Lang $env:REACUE_TEST_LANG -Mode $env:REACUE_TEST_MODE `
  -Mcp no -Stems $env:REACUE_TEST_CHOICE -Structure $env:REACUE_TEST_CHOICE -Chords $env:REACUE_TEST_CHOICE `
  -Drums $env:REACUE_TEST_CHOICE -Words $env:REACUE_TEST_CHOICE -ReaperDir $env:REACUE_TEST_RESOURCES
exit $LASTEXITCODE
''', encoding="utf-8-sig")

    def run(*, gpu="", failures=(), lang="en", mode="custom", choice="yes"):
        env = dict(os.environ, REACUE_TEST_GPU=gpu, REACUE_TEST_FAILURES=",".join(failures),
                   REACUE_TEST_LANG=lang, REACUE_TEST_MODE=mode, REACUE_TEST_CHOICE=choice,
                   REACUE_TEST_RESOURCES=str(resources))
        result = subprocess.run([shutil.which("powershell.exe"), "-NoProfile", "-NonInteractive",
                                 "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                                cwd=app, env=env, input="", capture_output=True,
                                encoding="utf-8", errors="replace", timeout=90)
        calls = {path.stem: json.loads(path.read_text(encoding="utf-8-sig"))
                 for path in (app / "calls").glob("*.json")}
        return result, calls

    return run


@pytest.mark.parametrize("gpu,index,lang,mode,choice", [
    ("", "", "fr", "custom", "yes"),
    ("", "", "en", "auto", "ask"),
    ("NVIDIA GeForce RTX 4090", "https://download.pytorch.org/whl/cu124", "en", "custom", "yes"),
    ("NVIDIA GeForce RTX 5090", "https://download.pytorch.org/whl/cu128", "fr", "custom", "yes"),
])
def test_optional_components_receive_valid_arguments(installer, gpu, index, lang, mode, choice):
    result, calls = installer(gpu=gpu, lang=lang, mode=mode, choice=choice)
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(calls) == set(COMPONENTS), result.stdout + result.stderr
    for call in calls.values():
        assert call == {"lang": lang, "index": index, "has_index": bool(index), "extra": []}
    assert "MissingArgument" not in result.stderr


@pytest.mark.parametrize("failures", [("stems",), COMPONENTS])
def test_optional_failures_are_reported_and_later_components_still_run(installer, failures):
    result, calls = installer(failures=failures)
    assert set(calls) == set(COMPONENTS), result.stdout + result.stderr
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{len(failures)} optional component(s) failed" in result.stdout
    assert "installation completed successfully" not in result.stdout
    for component in failures:
        assert f"Install ReaCue {component.title()}.bat" in result.stdout


def test_skipped_components_are_not_failures(installer):
    result, calls = installer(choice="no")
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == {}
    assert "installation completed successfully" in result.stdout
