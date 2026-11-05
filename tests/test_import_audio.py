"""Optional import: fake network/ffmpeg; all writes stay in temporary folders."""
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from reacue_mcp import import_audio as IA

URL = "https://www.youtube.com/watch?v=abcdefghijk"
META = {"id": "abcdefghijk", "title": "Demo", "duration": 60, "availability": "public", "live_status": "not_live"}


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "file:///tmp/x", "https://youtube.com.evil.test/watch?v=abcdefghijk",
    "https://youtube.com/watch?v=abcdefghijk&list=PLxx", "https://youtube.com/playlist?list=PLxx",
    "https://user:pass@youtube.com/watch?v=abcdefghijk", "https://youtube.com:8443/watch?v=abcdefghijk",
    "--exec rm -rf /", "https://youtu.be/short"])
def test_reject_non_video_urls(url):
    with pytest.raises(IA.ImportAudioError):
        IA.canonical_url(url)


def test_canonical_single_url_and_safe_names():
    assert IA.canonical_url("https://youtu.be/abcdefghijk?t=12") == (URL, "abcdefghijk")
    assert IA.canonical_url("https://m.youtube.com/shorts/abcdefghijk")[0] == URL
    assert IA.safe_title("../../CON") == "CON" or IA.safe_title("../../CON").startswith("Morceau")
    assert "/" not in IA.safe_title("Artist / Song")
    assert IA.safe_title("NUL") == "Morceau - NUL"
    assert IA.safe_title("Café") == "Café"


@pytest.mark.parametrize("extra", [{"is_live": True}, {"live_status": "is_upcoming"}, {"availability": "private"},
    {"availability": "needs_auth"}, {"availability": "unlisted"}, {"age_limit": 18},
    {"duration": float("inf")}, {"duration": 20000}, {"_type": "playlist"}, {"id": "other"}])
def test_reject_live_private_and_excess_duration(extra):
    with pytest.raises(IA.ImportAudioError):
        IA._metadata({**META, **extra}, URL, "abcdefghijk")


@pytest.fixture
def backend(tmp_path, monkeypatch):
    deps = {"python": "/isolated/python", "ffmpeg": "/tools/ffmpeg", "ffprobe": "/tools/ffprobe", "deno": "/tools/deno"}
    monkeypatch.setattr(IA, "dependencies", lambda: deps)
    monkeypatch.setattr(IA, "cache_root", lambda: tmp_path / "cache")
    calls = []
    def run(args, **kw):
        args = [str(a) for a in args]
        calls.append(args)
        if "--dump-single-json" in args:
            return json.dumps(META)
        if "--output" in args:
            path = Path(args[args.index("--output") + 1].replace("%(ext)s", "webm"))
            path.write_bytes(b"complete source audio")
            return str(path)
        if args[0].endswith("ffprobe"):
            duration = 60 if Path(args[-1]).name.startswith("source.") else 20
            return json.dumps({"format": {"duration": duration}, "streams": [{"codec_type": "audio", "codec_name": "opus"}]})
        if args[0].endswith("ffmpeg"):
            Path(args[-1]).write_bytes(b"complete selected audio")
            return ""
        raise AssertionError(args)
    monkeypatch.setattr(IA, "_run", run)
    projects = tmp_path / "projects"
    projects.mkdir()
    request = {"operation": "download", "url": URL, "root": str(projects), "title": "Demo", "start": 10, "end": 30}
    return request, calls, tmp_path


def test_inspect_uses_isolated_argv_no_config_or_browser_credentials(backend):
    _, calls, _ = backend
    result = IA.dispatch_request({"operation": "inspect", "url": URL})
    assert result["title"] == "Demo" and result["duration"] == 60
    command = calls[0]
    assert command[:3] == ["/isolated/python", "-m", "yt_dlp"]
    assert "--ignore-config" in command and "--no-plugin-dirs" in command
    assert "--no-cookies-from-browser" in command and "--no-remote-components" in command
    assert command[-2:] == ["--", URL]


def test_download_trim_no_recompression_then_reuse_completed_source(backend):
    request, calls, tmp = backend
    result = IA.dispatch_request(request)
    assert result["format"] == "best" and result["cached"] is False
    assert Path(result["file"]).name == "Demo.ogg" and Path(result["file"]).exists()
    command = next(c for c in calls if c[0].endswith("ffmpeg"))
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-ss") + 1] == "10.0"
    assert not list((tmp / "projects").glob(".reacue-import-*"))
    count = len(calls)
    second = IA.dispatch_request({**request, "title": "Another", "format": "mp3"})
    assert second["cached"] is True
    assert not any("--output" in c or "--dump-single-json" in c for c in calls[count:])
    assert "libmp3lame" in next(c for c in calls[count:] if c[0].endswith("ffmpeg"))


def test_existing_project_never_overwritten(backend):
    request, calls, _ = backend
    folder = Path(request["root"]) / "Demo"
    folder.mkdir()
    keep = folder / "Demo.RPP"
    keep.write_text("personal project")
    with pytest.raises(IA.ImportAudioError, match="existe déjà"):
        IA.dispatch_request(request)
    assert not calls and keep.read_text() == "personal project"


@pytest.mark.parametrize("start,end", [(30, 10), (-1, 30), (0, 61), (0, 0), (float("nan"), 30)])
def test_bad_passage_never_downloads(backend, start, end):
    request, calls, _ = backend
    with pytest.raises(IA.ImportAudioError):
        IA.dispatch_request({**request, "start": start, "end": end})
    assert not any("--output" in c for c in calls)


def test_cancel_before_start_does_not_create_project(backend):
    request, calls, tmp = backend
    cancel = tmp / "cancel"
    cancel.touch()
    with pytest.raises(IA.ImportCancelled):
        IA.dispatch_request({**request, "cancel_file": str(cancel)})
    assert not calls and not list(Path(request["root"]).iterdir())


def test_export_failure_keeps_source_cache_and_no_project(backend, monkeypatch):
    request, calls, tmp = backend
    real = IA._run
    def fail(args, **kw):
        if str(args[0]).endswith("ffmpeg"):
            raise IA.ImportAudioError("encode failed")
        return real(args, **kw)
    monkeypatch.setattr(IA, "_run", fail)
    with pytest.raises(IA.ImportAudioError):
        IA.dispatch_request(request)
    assert not list(Path(request["root"]).iterdir())
    assert (tmp / "cache/abcdefghijk/source.json").exists()
    assert not (tmp / "cache/abcdefghijk/active.lock").exists()


def test_corrupt_completed_cache_is_downloaded_again(backend):
    request, calls, tmp = backend
    IA.dispatch_request(request)
    (tmp / "cache/abcdefghijk/source.webm").write_bytes(b"bad")
    before = len(calls)
    IA.dispatch_request({**request, "title": "Retry"})
    assert any("--output" in c for c in calls[before:])


def test_lock_rejects_second_worker(tmp_path):
    with IA._lock(tmp_path):
        with pytest.raises(IA.ImportAudioError, match="déjà en cours"):
            with IA._lock(tmp_path):
                pytest.fail("concurrent worker accepted")


def test_real_subprocess_cancel_terminates_child_without_network(tmp_path):
    marker, pidfile = tmp_path / "cancel", tmp_path / "pid"
    script = "import os,time,pathlib; pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid())); time.sleep(20)"
    def cancel():
        for _ in range(100):
            if pidfile.exists():
                marker.touch()
                return
            time.sleep(0.02)
    thread = threading.Thread(target=cancel)
    thread.start()
    with pytest.raises(IA.ImportCancelled):
        IA._run([sys.executable, "-c", script], cancel_file=marker, timeout=5)
    thread.join(timeout=3)
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)


def test_actual_ffmpeg_packet_copy_for_synthetic_audio(tmp_path, monkeypatch):
    """Runs only where ffmpeg is installed; no online input or downloaded dependencies."""
    import shutil
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe unavailable")
    deps = {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
    folder = tmp_path / "cache/abcdefghijk"
    folder.mkdir(parents=True)
    source = folder / "source.m4a"
    IA._run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:a", "aac", str(source)])
    IA._atomic_json(folder / "source.json", {"file": source.name, "size": source.stat().st_size,
        "sha256": IA._sha(source), "metadata": {**META, "url": URL, "duration": 3}})
    monkeypatch.setattr(IA, "dependencies", lambda: deps)
    monkeypatch.setattr(IA, "cache_root", lambda: tmp_path / "cache")
    projects = tmp_path / "projects"
    projects.mkdir()
    result = IA.dispatch_request({"operation": "download", "url": URL, "title": "Synthetic",
        "root": str(projects), "start": 0.5, "end": 2.5})
    assert result["cached"] and 1.8 < result["duration"] < 2.2
    assert IA._probe(Path(result["file"]), deps)[1] == "aac"
