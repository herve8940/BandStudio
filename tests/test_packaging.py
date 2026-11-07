"""Release payload, reproducibility, executable launchers and Windows encodings."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_installers", ROOT / "tools/package_installers.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


@pytest.fixture(scope="module")
def archives(tmp_path_factory):
    output = tmp_path_factory.mktemp("installers")
    package.build(ROOT, output)
    return output


@pytest.mark.parametrize("platform", package.PLATFORMS)
def test_release_payload(archives, platform):
    path = archives / f"ReaCue-{platform}.zip"
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for required in ("LICENSE", "THIRD_PARTY_NOTICES.md", "requirements.txt", "reacue_cli.py",
                         "install/reacue_setup.py", "reaper/ReaCue.lua", "reacue_mcp/server.py",
                         "reacue_mcp/web/studio.html", "INSTALLATION.txt", "BUILD_INFO.json"):
            assert "ReaCue/" + required in names
        assert all(n.startswith("ReaCue/") for n in names)
        assert not any("/." in n or "/tests/" in n or "/tools/" in n or "__pycache__" in n for n in names)
        assert "ReaCue/requirements-dev.txt" not in names
        metadata = json.loads(archive.read("ReaCue/BUILD_INFO.json"))
        assert metadata["platform"] == platform
        assert metadata["commit"] == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
        assert metadata["models_bundled"] is False
        if platform == "macOS":
            assert not any(n.endswith((".bat", ".ps1")) for n in names)
            assert archive.getinfo("ReaCue/Install ReaCue.command").external_attr >> 16 & 0o111 == 0o111
        else:
            assert not any(n.endswith((".command", ".sh")) for n in names)
            for name in names:
                if name.endswith((".ps1", ".bat")):
                    data = archive.read(name)
                    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
                    if name.endswith(".ps1"):
                        assert data.startswith(b"\xef\xbb\xbf")
            assert "ReaCue/Install ReaCue.bat" in names
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.with_suffix(".zip.sha256").read_text().strip() == f"{digest}  {path.name}"


def test_build_is_reproducible(archives, tmp_path):
    package.build(ROOT, tmp_path)
    for original in archives.iterdir():
        assert (tmp_path / original.name).read_bytes() == original.read_bytes()


def test_untracked_user_files_are_never_packaged(tmp_path):
    # Even a file in an included directory is omitted unless committed.
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repo)], check=True)
    personal = repo / "reacue_mcp/personal-song.txt"
    personal.write_text("private lyrics", encoding="utf-8")
    # Also ensure an edited tracked file cannot silently misrepresent its source commit.
    (repo / "LICENSE").write_text("local change", encoding="utf-8")
    output = tmp_path / "release"
    package.build(repo, output, ("macOS",))
    with zipfile.ZipFile(output / "ReaCue-macOS.zip") as archive:
        assert "ReaCue/reacue_mcp/personal-song.txt" not in archive.namelist()
        assert archive.read("ReaCue/LICENSE") != b"local change"
