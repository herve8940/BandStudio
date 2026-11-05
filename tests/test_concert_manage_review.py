"""Independent review regressions for ownership, late collisions and portable renames."""
import json
from pathlib import Path
import shutil

import pytest

from reacue_mcp import concert as C, concert_manage as M
from test_concert_manage import show, request, snapshot, side  # noqa: F401


def test_late_collision_preserves_foreign_file_and_restores_originals(show, monkeypatch):
    before = snapshot(show.rpp.parent)
    foreign = show.rpp.parent / "New.RPP"
    install = M._install
    def collided(source, destination):
        if destination == foreign and not foreign.exists():
            foreign.write_text("other application created this project")
        return install(source, destination)
    monkeypatch.setattr(M, "_install", collided)
    with pytest.raises(FileExistsError):
        request(show, "rename", name="New")
    assert foreign.read_text() == "other application created this project"
    after = snapshot(show.rpp.parent)
    after.pop("New.RPP")
    assert after == before


def test_prefixed_shared_audio_is_not_owned_by_concert(show):
    shared = show.rpp.parent / "Original show.shared.wav"
    shared.write_bytes(b"shared source audio")
    project = show.song_srcs[0].path
    lines = project.read_text().splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.strip().startswith("FILE "))
    lines[first] = "        FILE " + C.q(str(shared)) + "\n"
    project.write_text("".join(lines))
    before = project.read_bytes()
    result = request(show, "rename", name="New")
    assert Path(result["projet"]).exists()
    assert shared.read_bytes() == b"shared source audio"
    assert project.read_bytes() == before
    assert not (shared.parent / "New.shared.wav").exists()


def test_renamed_portable_package_stays_relative_and_lighting_links_work(show, tmp_path):
    package = tmp_path / "Portable"
    result = request(show, "portable", destination=str(package))
    renamed = M.dispatch_request({"operation": "rename", "setlist": result["setlist"], "name": "Renamed"})
    moved = tmp_path / "USB"
    shutil.move(package, moved)
    for project in moved.rglob("*.RPP"):
        for line in project.read_text().splitlines():
            if line.strip().startswith("FILE "):
                ref = C.tokens(line.strip())[1]
                assert not M._absolute(ref), (project, ref)
                assert (project.parent / ref).is_file(), (project, ref)
    metadata = side(moved / "Renamed.concert.lua")
    assert metadata["rpp"] == "Renamed.RPP"
    assert metadata["setlist"] == "Renamed.setlist.json"
    web = moved / "Renamed.web"
    song = json.loads((web / "reacue_song.json").read_text())
    for entry in (song.get("lighting") or {}).get("files", []):
        assert (web / Path(entry["url"]).name).is_file(), entry
    setlist = json.loads((moved / "Renamed.setlist.json").read_text())
    assert all((moved / s["project"]).is_file() for s in setlist["songs"])
