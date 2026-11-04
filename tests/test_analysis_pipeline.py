"""Grid reuse without audio files or expensive signal/model inference."""
import numpy as np
import pytest
from types import SimpleNamespace

from reacue_mcp import analysis as A


@pytest.mark.parametrize("hint", [None, 120.0])
def test_variable_grid_tracks_once_and_preserves_result(monkeypatch, hint):
    calls = []
    beats = np.arange(0.25, 20, 0.5)
    def track(y, sr, bpm_hint, start_bpm=None):
        calls.append(bpm_hint)
        return 120.0, beats.copy()
    monkeypatch.setattr(A, "_beats", track)
    monkeypatch.setattr(A, "_try_constant_grid", lambda *a, **k: (None, ()))
    monkeypatch.setattr(A, "_refine", lambda y, sr, b: b)
    monkeypatch.setattr(A, "_beat_features", lambda *a, **k: np.zeros(len(beats)))
    monkeypatch.setattr(A, "_downbeat_phase", lambda *a: (4, 0))
    monkeypatch.setattr(A, "librosa", SimpleNamespace(
        feature=SimpleNamespace(rms=lambda **k: np.ones((1, 100))),
        frames_to_time=lambda *a, **k: 20.0))
    y = np.zeros(200)
    expected = A._build_grid_tracked(y, y, 10, 20, 4, 4, hint, [])
    calls.clear()
    actual = A._build_grid(y, y, 10, 20, 4, 4, hint, [])
    assert calls == [hint]
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[2], expected[2])
    assert actual[1] == expected[1] and actual[3] == expected[3]
    assert actual[4] is False and actual[5] == max(expected[5], 0.0121)


def test_constant_grid_with_hint_does_not_run_tracker(monkeypatch):
    monkeypatch.setattr(A, "_beats", lambda *a, **k: pytest.fail("unneeded tracking"))
    fixed = ([], 4, [], 120.0, True, 0.0, {})
    monkeypatch.setattr(A, "_try_constant_grid", lambda *a, **k: (fixed, ()))
    y = np.zeros(10)
    assert A._build_grid(y, y, 10, 1, 4, 4, 120.0, []) == fixed
