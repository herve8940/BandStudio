"""Settings writes must not discard the previous file when writing or replacing fails."""
from pathlib import Path

import pytest

pytest.importorskip("lupa")
from test_lua import load_run


def test_posix_replaces_without_deleting_destination(tmp_path):
    L, R = load_run(tmp_path)
    path = tmp_path / "settings.json"
    path.write_text("old")
    L.globals().TARGET = str(path)
    L.execute("""
      local remove = os.remove
      os.remove = function(path) assert(path ~= TARGET, "destination must stay present"); return remove(path) end
    """)
    assert R.write_atomic(str(path), "new")
    assert path.read_text() == "new"


def test_posix_failed_rename_preserves_destination(tmp_path):
    L, R = load_run(tmp_path)
    path = tmp_path / "settings.json"
    path.write_text("old")
    L.execute('os.rename = function() return nil, "simulated failure" end')
    assert not R.write_atomic(str(path), "new")
    assert path.read_text() == "old"
    assert not Path(str(path) + ".tmp").exists()


@pytest.mark.parametrize("fail_close", [False, True])
def test_write_or_close_failure_never_replaces_destination(tmp_path, fail_close):
    L, R = load_run(tmp_path)
    path = tmp_path / "settings.json"
    path.write_text("old")
    L.globals().FAIL_CLOSE = fail_close
    L.execute("""
      io.open = function() return {
        write = function() return FAIL_CLOSE and true or nil end,
        close = function() return not FAIL_CLOSE and true or nil end,
      } end
      os.rename = function() error("must not rename an incomplete file") end
    """)
    assert not R.write_atomic(str(path), "new")
    assert path.read_text() == "old"


@pytest.mark.parametrize("fail_replace", [False, True])
def test_windows_backup_restores_original_on_replacement_failure(tmp_path, fail_replace):
    L, R = load_run(tmp_path, "Win64")
    path = tmp_path / "settings.json"
    path.write_text("old")
    L.globals().FAIL_REPLACE = fail_replace
    L.execute("""
      local rename = os.rename
      os.rename = function(source, dest)
        local f = io.open(dest, "rb")
        if f then f:close(); return nil, "destination exists" end
        if FAIL_REPLACE and source:sub(-4) == ".tmp" then return nil, "simulated failure" end
        return rename(source, dest)
      end
    """)
    assert bool(R.write_atomic(str(path), "new")) is not fail_replace
    assert path.read_text() == ("old" if fail_replace else "new")
    assert not Path(str(path) + ".tmp").exists()
    assert not Path(str(path) + ".previous").exists()


def test_windows_does_not_overwrite_unrecovered_backup(tmp_path):
    L, R = load_run(tmp_path, "Win64")
    path = tmp_path / "settings.json"
    backup = Path(str(path) + ".previous")
    path.write_text("old")
    backup.write_text("older")
    L.execute('os.rename = function() return nil, "simulated failure" end')
    assert not R.write_atomic(str(path), "new")
    assert path.read_text() == "old" and backup.read_text() == "older"
