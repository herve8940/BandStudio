#!/usr/bin/env python3
"""Build platform ZIP installers from a committed Git revision (standard library only)."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ("macOS", "Windows")
DIRECTORIES = {"reacue_mcp", "reaper", "install", "docs"}
DOCUMENTS = {"README.md", "LISEZMOI.md", "CHANGELOG.md", "LICENSE",
             "THIRD_PARTY_NOTICES.md", "CITATION.cff"}


def included(name: str, platform: str) -> bool:
    path = PurePosixPath(name)
    if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    if platform == "macOS" and path.suffix in {".bat", ".ps1"}:
        return False
    if platform == "Windows" and path.suffix in {".command", ".sh"}:
        return False
    if len(path.parts) > 1:
        return path.parts[0] in DIRECTORIES
    return (name in DOCUMENTS or name == "run_server.py"
            or (name.startswith("reacue_") and path.suffix == ".py")
            or (name.startswith("requirements") and path.suffix == ".txt"
                and name != "requirements-dev.txt")
            or path.suffix in {".command", ".bat"})


def instructions(platform: str) -> str:
    launcher = "Install ReaCue.command" if platform == "macOS" else "Install ReaCue.bat"
    return f"""ReaCue — {platform}

FRANÇAIS
1. Extrais tout le dossier ReaCue dans un emplacement permanent, par exemple Documents/ReaCue.
2. Lance REAPER une fois, puis ferme-le.
3. Double-clique sur « {launcher} » dans ce dossier.
4. Choisis la langue et les composants, puis relance REAPER et ouvre l'action ReaCue.

Internet est nécessaire pour installer Python, les dépendances et les modèles choisis.
Le programme et les scripts sont inclus ; les modèles d'IA et tes données personnelles ne le sont pas.
Conserve ce dossier après installation. Pour le déplacer, relance l'installateur au nouvel emplacement.
Documentation : LISEZMOI.md. Licences : LICENSE et THIRD_PARTY_NOTICES.md.
Windows reste en bêta : le fonctionnement avec REAPER doit être vérifié sur la machine cible.

ENGLISH
1. Extract the entire ReaCue folder to a permanent location, for example Documents/ReaCue.
2. Start REAPER once, then quit it.
3. Double-click "{launcher}" inside that folder.
4. Choose your language and components, then restart REAPER and open the ReaCue action.

Internet is needed to install Python, dependencies and the selected models.
The program and scripts are included; AI models and personal data are not bundled.
Keep this folder after installation. If you move it, rerun the installer at its new location.
Documentation: README.md. Licences: LICENSE and THIRD_PARTY_NOTICES.md.
Windows remains in beta: operation inside REAPER must be checked on the target computer.
"""


def write_entry(archive: zipfile.ZipFile, name: str, data: bytes, executable=False):
    # Stable timestamps, POSIX permissions even when built on Windows, and one root folder.
    info = zipfile.ZipInfo("ReaCue/" + name, date_time=(2020, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data, compresslevel=9)


def build(root: Path, output: Path, platforms=PLATFORMS, ref="HEAD") -> list[Path]:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])

    commit = git("rev-parse", "--verify", ref + "^{commit}").decode().strip()
    timestamp = git("show", "-s", "--format=%cI", commit).decode().strip()
    # Read Git objects, never the user's working files, virtual environments or model caches.
    source = git("archive", "--format=tar", commit)
    output.mkdir(parents=True, exist_ok=True)
    outputs = []
    with tarfile.open(fileobj=io.BytesIO(source)) as tree:
        members = sorted((m for m in tree if m.isfile()), key=lambda m: m.name)
        for platform in platforms:
            if platform not in PLATFORMS:
                raise ValueError(f"Unknown platform: {platform}")
            files = [m for m in members if included(m.name, platform)]
            names = {m.name for m in files}
            launcher = "Install ReaCue.command" if platform == "macOS" else "Install ReaCue.bat"
            required = {launcher, "install/reacue_setup.py", "requirements.txt", "run_server.py",
                        "reacue_cli.py", "reaper/ReaCue.lua", "reacue_mcp/web/studio.html", *DOCUMENTS}
            if missing := required - names:
                raise ValueError(f"Incomplete {platform} package: {sorted(missing)}")
            archive_path = output / f"ReaCue-{platform}.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for member in files:
                    data = tree.extractfile(member).read()
                    suffix = PurePosixPath(member.name).suffix
                    if suffix in {".bat", ".ps1"}:
                        # Windows PowerShell 5.1 requires a BOM for French text.
                        text = data.decode("utf-8-sig").replace("\r\n", "\n")
                        encoding = "utf-8-sig" if suffix == ".ps1" else "utf-8"
                        data = text.replace("\n", "\r\n").encode(encoding)
                    write_entry(archive, member.name, data, suffix in {".command", ".sh"})
                metadata = {"platform": platform, "commit": commit, "commit_date": timestamp,
                            "dependencies_bundled": False, "models_bundled": False}
                write_entry(archive, "BUILD_INFO.json", (json.dumps(metadata, indent=2) + "\n").encode())
                write_entry(archive, "INSTALLATION.txt", instructions(platform).encode("utf-8"))
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            checksum = archive_path.with_suffix(".zip.sha256")
            checksum.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
            outputs.extend((archive_path, checksum))
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--platform", choices=(*PLATFORMS, "all"), default="all")
    parser.add_argument("--ref", default="HEAD", help="Committed revision; working changes are not packaged")
    args = parser.parse_args()
    platforms = PLATFORMS if args.platform == "all" else (args.platform,)
    for path in build(ROOT, args.output, platforms, args.ref):
        print(path)


if __name__ == "__main__":
    main()
