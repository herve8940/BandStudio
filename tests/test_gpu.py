"""Tests unitaires pour la détection de GPU et accélération matérielle (reacue_gpu.py)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reacue_gpu


def test_detect_gpu_structure():
    info = reacue_gpu.detect_gpu()
    assert isinstance(info, dict)
    required_keys = {
        "has_gpu",
        "vendor",
        "name",
        "vram_mb",
        "is_dedicated",
        "backend",
        "index_url",
        "recommended_stems_model",
    }
    assert required_keys <= set(info.keys())
    assert info["vendor"] in ("nvidia", "amd", "apple", "intel", "cpu")
    assert info["backend"] in ("cuda", "rocm", "mps", "directml", "cpu")
    assert info["recommended_stems_model"] in ("htdemucs_6s", "htdemucs_ft", "htdemucs")


def test_summary_formatting():
    # NVIDIA
    nv = {
        "has_gpu": True,
        "vendor": "nvidia",
        "name": "NVIDIA GeForce RTX 4080",
        "vram_mb": 16384,
        "is_dedicated": True,
        "backend": "cuda",
    }
    s_fr = reacue_gpu.summary(nv, "fr")
    s_en = reacue_gpu.summary(nv, "en")
    assert "NVIDIA GeForce RTX 4080" in s_fr and "16 Go VRAM" in s_fr and "CUDA" in s_fr
    assert "NVIDIA GeForce RTX 4080" in s_en and "16 GB VRAM" in s_en and "CUDA" in s_en

    # AMD dédié
    amd_ded = {
        "has_gpu": True,
        "vendor": "amd",
        "name": "AMD Radeon RX 7900 XT",
        "vram_mb": 20480,
        "is_dedicated": True,
        "backend": "rocm",
    }
    s_fr = reacue_gpu.summary(amd_ded, "fr")
    assert "AMD Radeon RX 7900 XT" in s_fr and "20 Go VRAM" in s_fr and "AMD" in s_fr

    # AMD intégré
    amd_int = {
        "has_gpu": True,
        "vendor": "amd",
        "name": "AMD Radeon(TM) Graphics",
        "vram_mb": 512,
        "is_dedicated": False,
        "backend": "rocm",
    }
    assert "intégré" in reacue_gpu.summary(amd_int, "fr").lower()

    # Apple Silicon
    apple = {
        "has_gpu": True,
        "vendor": "apple",
        "name": "Apple Silicon (Metal/MPS)",
        "vram_mb": 0,
        "is_dedicated": True,
        "backend": "mps",
    }
    assert "Metal" in reacue_gpu.summary(apple, "fr")
    assert "Metal" in reacue_gpu.summary(apple, "en")

    # CPU
    cpu = {
        "has_gpu": False,
        "vendor": "cpu",
        "name": "CPU",
        "vram_mb": 0,
        "is_dedicated": False,
        "backend": "cpu",
    }
    assert "CPU" in reacue_gpu.summary(cpu, "fr")
    assert "CPU" in reacue_gpu.summary(cpu, "en")


def test_cli_flags(capsys):
    # --json
    assert reacue_gpu.main(["--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "vendor" in out and "backend" in out

    # --backend
    assert reacue_gpu.main(["--backend"]) == 0
    assert capsys.readouterr().out.strip() in ("cuda", "rocm", "mps", "cpu", "directml")

    # --model
    assert reacue_gpu.main(["--model"]) == 0
    assert capsys.readouterr().out.strip() in ("htdemucs_6s", "htdemucs_ft", "htdemucs")

    # --index-url
    assert reacue_gpu.main(["--index-url"]) == 0
    capsys.readouterr()  # consomme la sortie (peut être vide ou URL)

    # --suite-json
    assert reacue_gpu.main(["--suite-json"]) == 0
    suite = json.loads(capsys.readouterr().out)
    assert "profile" in suite and "stems_model" in suite and "models" in suite

    # --suite
    assert reacue_gpu.main(["--suite"]) == 0
    txt = capsys.readouterr().out
    assert "Demucs" in txt and "SongFormer" in txt


def test_mock_nvidia_smi(monkeypatch):
    class FakeProcess:
        stdout = "NVIDIA GeForce RTX 3080, 10240\n"

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProcess())
    res = reacue_gpu._detect_nvidia_smi()
    assert res is not None
    assert res["vendor"] == "nvidia"
    assert res["name"] == "NVIDIA GeForce RTX 3080"
    assert res["vram_mb"] == 10240
    assert res["is_dedicated"] is True
    assert res["backend"] == "cuda"
    assert "cu124" in res["index_url"]


def test_blackwell_cuda_index(monkeypatch):
    class FakeProcess:
        stdout = "NVIDIA GeForce RTX 5070 Ti, 16303\n"

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProcess())
    res = reacue_gpu._detect_nvidia_smi()
    assert res is not None
    assert "cu128" in res["index_url"]


def test_mock_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    res = reacue_gpu._detect_macos()
    assert res is not None
    assert res["vendor"] == "apple"
    assert res["backend"] == "mps"
    assert res["is_dedicated"] is True


def test_recommended_stems_model():
    # GPU 16 Go -> 6s
    assert reacue_gpu.recommended_stems_model({"has_gpu": True, "is_dedicated": True, "vram_mb": 16384}) == "htdemucs_6s"
    # GPU 4 Go -> ft
    assert reacue_gpu.recommended_stems_model({"has_gpu": True, "is_dedicated": True, "vram_mb": 4096}) == "htdemucs_ft"
    # Apple Silicon -> 6s
    assert reacue_gpu.recommended_stems_model({"has_gpu": True, "is_dedicated": True, "vendor": "apple", "vram_mb": 0}) == "htdemucs_6s"
    # CPU -> htdemucs
    assert reacue_gpu.recommended_stems_model({"has_gpu": False, "is_dedicated": False}) == "htdemucs"
    # iGPU 512 Mo -> htdemucs
    assert reacue_gpu.recommended_stems_model({"has_gpu": True, "is_dedicated": False, "vram_mb": 512}) == "htdemucs"

    # Suite complète IA :
    suite_high = reacue_gpu.recommend_ai_suite({"vendor": "nvidia", "is_dedicated": True, "vram_mb": 16384, "has_gpu": True})
    assert suite_high["profile"] == "expert_gpu"
    assert suite_high["stems_model"] == "htdemucs_6s"
    assert suite_high["install_words"] is True
    assert suite_high["structure_window"] == 420

    suite_mid = reacue_gpu.recommend_ai_suite({"vendor": "nvidia", "is_dedicated": True, "vram_mb": 4096, "has_gpu": True})
    assert suite_mid["profile"] == "mid_gpu"
    assert suite_mid["stems_model"] == "htdemucs_ft"
    assert suite_mid["structure_window"] == 120

    suite_apple = reacue_gpu.recommend_ai_suite({"vendor": "apple", "is_dedicated": True, "has_gpu": True})
    assert suite_apple["profile"] == "apple_silicon"
    assert suite_apple["stems_model"] == "htdemucs_6s"

    suite_cpu = reacue_gpu.recommend_ai_suite({"vendor": "cpu", "is_dedicated": False, "has_gpu": False})
    assert suite_cpu["profile"] == "standard_cpu"
    assert suite_cpu["stems_model"] == "htdemucs"
    assert suite_cpu["install_words"] is True
    for suite in (suite_high, suite_mid, suite_apple, suite_cpu):
        assert suite["install_words"] is True
        lyrics = next(model for model in suite["models"] if model["id"] == "words")
        assert lyrics["selected_model"] == "Whisper small"
        assert "calage par ligne" in lyrics["role_fr"] and "line timing" in lyrics["role_en"]
        assert "facultatif" in lyrics["why_fr"] and "Optional" in lyrics["why_en"]


def test_audit_venv_missing(tmp_path):
    res = reacue_gpu.audit_venv(tmp_path / "nonexistent_python.exe")
    assert res["status"] == "not_installed"
    assert res["action"] == "install"


def test_audit_venv_optimal_and_reinstall(monkeypatch, tmp_path):
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("")

    class FakeProc:
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = 0
            self.stderr = ""

    # Cas A : RTX 5070 Ti avec torch cu128 optimal
    gpu_bw = {
        "has_gpu": True,
        "vendor": "nvidia",
        "name": "NVIDIA GeForce RTX 5070 Ti",
        "is_dedicated": True,
        "backend": "cuda",
        "index_url": "https://download.pytorch.org/whl/cu128",
    }
    probe_ok = json.dumps({"installed": True, "version": "2.8.0+cu128", "cuda": True, "compute_ok": True})
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProc(probe_ok))
    res_ok = reacue_gpu.audit_venv(fake_py, gpu_info=gpu_bw)
    assert res_ok["status"] == "optimal"
    assert res_ok["action"] == "keep"

    # Cas B : RTX 5070 Ti avec torch CPU
    probe_cpu = json.dumps({"installed": True, "version": "2.5.1+cpu", "cuda": False, "compute_ok": True})
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProc(probe_cpu))
    res_cpu = reacue_gpu.audit_venv(fake_py, gpu_info=gpu_bw)
    assert res_cpu["status"] == "needs_reinstall"
    assert res_cpu["action"] == "reinstall"
    assert res_cpu["target_version"] == "2.8.0"


def test_sync_settings(tmp_path):
    sf = tmp_path / "reacue_settings.json"
    gpu_bw = {
        "has_gpu": True,
        "vendor": "nvidia",
        "name": "NVIDIA GeForce RTX 5070 Ti",
        "vram_mb": 16303,
        "is_dedicated": True,
        "backend": "cuda",
        "index_url": "https://download.pytorch.org/whl/cu128",
    }
    res = reacue_gpu.sync_settings(sf, gpu_info=gpu_bw)
    assert res["changed"] is True
    assert res["stems_model"] == "htdemucs"
    assert res["hardware"]["vendor"] == "nvidia"
    assert res["hardware"]["recommended_stems_model"] == "htdemucs_6s"
    assert reacue_gpu.sync_settings(sf, gpu_info=gpu_bw)["changed"] is False

    # Seules les informations matérielles changent sur CPU.
    gpu_cpu = {
        "has_gpu": False,
        "vendor": "cpu",
        "name": "CPU",
        "vram_mb": 0,
        "is_dedicated": False,
        "backend": "cpu",
        "index_url": None,
    }
    res2 = reacue_gpu.sync_settings(sf, gpu_info=gpu_cpu)
    assert res2["changed"] is True
    assert res2["stems_model"] == "htdemucs"


@pytest.mark.parametrize("model", ["htdemucs", "htdemucs_ft", "htdemucs_6s"])
def test_sync_settings_preserves_explicit_model_across_hardware(tmp_path, model):
    sf = tmp_path / "reacue_settings.json"
    sf.write_text(json.dumps({"stems_model": model, "language": "en"}), encoding="utf-8")
    for gpu_info in (
        {"has_gpu": False, "is_dedicated": False, "backend": "cpu", "vram_mb": 0},
        {"has_gpu": True, "is_dedicated": True, "backend": "cuda", "vram_mb": 16384},
    ):
        result = reacue_gpu.sync_settings(sf, gpu_info=gpu_info)
        assert result["stems_model"] == model
        saved = json.loads(sf.read_text(encoding="utf-8"))
        assert saved["stems_model"] == model and saved["language"] == "en"
        before = sf.stat().st_mtime_ns
        assert reacue_gpu.sync_settings(sf, gpu_info=gpu_info)["changed"] is False
        assert sf.stat().st_mtime_ns == before


@pytest.mark.parametrize("model", [None, "", "unknown", [], {}])
def test_sync_settings_repairs_invalid_model_with_balanced_default(tmp_path, model):
    sf = tmp_path / "reacue_settings.json"
    sf.write_text(json.dumps({"stems_model": model}), encoding="utf-8")
    result = reacue_gpu.sync_settings(sf, gpu_info={"has_gpu": True, "is_dedicated": True, "vram_mb": 16384})
    assert result["changed"] is True
    assert result["stems_model"] == "htdemucs"
    assert result["hardware"]["recommended_stems_model"] == "htdemucs_6s"


def test_sync_settings_explicit_force_applies_recommendation(tmp_path):
    sf = tmp_path / "reacue_settings.json"
    sf.write_text(json.dumps({"stems_model": "htdemucs"}), encoding="utf-8")
    gpu = {"has_gpu": True, "is_dedicated": True, "vram_mb": 16384}
    result = reacue_gpu.sync_settings(sf, gpu_info=gpu, force_model=True)
    assert result["changed"] is True
    assert result["stems_model"] == "htdemucs_6s"
    assert reacue_gpu.sync_settings(sf, gpu_info=gpu, force_model=True)["changed"] is False

