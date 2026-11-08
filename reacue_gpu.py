"""Détection du GPU (NVIDIA CUDA, AMD, Apple Silicon, CPU) et audit d'environnement pour ReaCue.
GPU detection (NVIDIA CUDA, AMD, Apple Silicon, CPU) and environment audit for ReaCue.

Bibliothèque standard uniquement. Utilisé par :
  - install/install_windows.ps1 & install/install_stems_windows.ps1
  - install/install_mac.sh & install/install_stems_mac.sh
  - install/reacue_setup.py
  - reacue_stems.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def _cuda_index_url(gpu_name: str) -> str:
    """Renvoie l'URL de l'index PyTorch adapté à la génération de la carte NVIDIA."""
    name_lower = gpu_name.lower()
    # Architecture Blackwell (RTX 5070, 5080, 5090, sm_120) exige CUDA 12.8+
    if any(k in name_lower for k in ("rtx 50", "5070", "5080", "5090", "blackwell")):
        return "https://download.pytorch.org/whl/cu128"
    return "https://download.pytorch.org/whl/cu124"


def recommended_stems_model(info: dict) -> str:
    """Renvoie le modèle de stems optimal pour le matériel détecté.

    - GPU dédié avec >= 8 Go de VRAM : htdemucs_6s (6 stems de haute qualité).
    - GPU dédié avec < 8 Go de VRAM : htdemucs_ft (4 stems haute fidélité) ou htdemucs_6s.
    - Apple Silicon (MPS) : htdemucs_6s.
    - CPU : htdemucs (4 stems standard, pour éviter 15-20 min d'attente par morceau).
    """
    if not info.get("has_gpu") or not info.get("is_dedicated"):
        return "htdemucs"
    vendor = info.get("vendor", "")
    if vendor == "apple":
        return "htdemucs_6s"
    vram_mb = info.get("vram_mb", 0)
    if vram_mb >= 7500:  # ~8 Go
        return "htdemucs_6s"
    if vram_mb >= 2048:  # 2 à 8 Go
        return "htdemucs_ft"
    return "htdemucs"


def recommend_ai_suite(info: dict | None = None) -> dict:
    """Détermine la suite complète de modèles d'IA préconisée selon le matériel détecté.

    Propose les meilleurs modèles adaptés à la machine pour les novices, et détaille
    l'ensemble des capacités IA disponibles dans ReaCue :
      - Découpe de stems (Demucs : htdemucs_6s, htdemucs_ft, htdemucs)
      - Analyse de structure (SongFormer : MuQ + MusicFM)
      - Reconnaissance d'accords (Modèle entraîné ISMIR 2019)
      - Transcription de batterie (ADTOF)
      - Paroles Essentiel (Whisper small, calage par ligne ; mot-à-mot facultatif)
    """
    if info is None:
        info = detect_gpu()

    vendor = info.get("vendor", "cpu")
    is_dedicated = bool(info.get("is_dedicated"))
    vram_mb = info.get("vram_mb", 0)
    has_gpu = bool(info.get("has_gpu"))

    stems_model = recommended_stems_model(info)

    if vendor == "nvidia" and is_dedicated and vram_mb >= 7500:
        profile = "expert_gpu"
        title_fr = "Studio Pro / Performance Maximale"
        title_en = "Studio Pro / Maximum Performance"
        desc_fr = "GPU NVIDIA dédié : accélération des analyses compatibles, paroles Essentiel par défaut"
        desc_en = "Dedicated NVIDIA GPU: acceleration for compatible analyses, Essential lyrics by default"
        structure_window = 420
    elif vendor == "apple" and has_gpu:
        profile = "apple_silicon"
        title_fr = "Apple Silicon (Metal MPS) / Optimal"
        title_en = "Apple Silicon (Metal MPS) / Optimal"
        desc_fr = "Puce Apple avec mémoire unifiée : modèles 6 stems et analyse haute précision"
        desc_en = "Apple Silicon with unified memory: 6 stems and high-precision analysis"
        structure_window = 420
    elif is_dedicated and (vram_mb >= 2048 or vendor in ("nvidia", "amd")):
        profile = "mid_gpu"
        title_fr = "GPU Dédié / Équilibré"
        title_en = "Dedicated GPU / Balanced"
        desc_fr = "Accélération GPU dédiée : modèles haute fidélité optimisés pour la VRAM disponible"
        desc_en = "Dedicated GPU acceleration: high-fidelity models optimized for available VRAM"
        structure_window = 120
    else:
        profile = "standard_cpu"
        title_fr = "Processeur Standard (CPU) / Équilibré"
        title_en = "Standard Processor (CPU) / Balanced"
        desc_fr = "Sans GPU dédié : 4 stems et paroles Essentiel ; la durée des analyses dépend du morceau et du processeur"
        desc_en = "Without dedicated GPU: 4 stems and Essential lyrics; analysis time depends on the song and processor"
        structure_window = 120

    models = [
        {
            "id": "stems",
            "name": "Demucs v4",
            "selected_model": stems_model,
            "role_fr": "Séparation d'un MP3/WAV en stems (voix, batterie, basse, guitare, piano, autres)",
            "role_en": "Splits an MP3/WAV into stems (vocals, drums, bass, guitar, piano, other)",
            "why_fr": "Isole chaque instrument pour le prompteur, le mix de répétition et les mutes live",
            "why_en": "Isolates each instrument for the prompter, rehearsal mix, and live mutes",
        },
        {
            "id": "structure",
            "name": "SongFormer (MuQ + MusicFM)",
            "selected_model": f"Fenêtre {structure_window}s",
            "role_fr": "Découpage intelligent en sections (Intro, Couplets, Refrains, Ponts, Solos)",
            "role_en": "Intelligent section detection (Intro, Verses, Choruses, Bridges, Solos)",
            "why_fr": "Place automatiquement les marqueurs et les carrures sans découpe manuelle",
            "why_en": "Automatically places markers and bars without manual editing",
        },
        {
            "id": "chords",
            "name": "Modèle ISMIR 2019 (Chord Structure Decomposition)",
            "selected_model": "Large-Vocabulary CNN (~60 Mo)",
            "role_fr": "Reconnaissance précise des accords enrichis (7e, m7, maj7, dim, aug, sus, renversements D/F#)",
            "role_en": "Accurate recognition of extended chords (7th, m7, maj7, dim, aug, sus, D/F# inversions)",
            "why_fr": "Fournit les bonnes grilles d'accords pour le bassiste, le guitariste et le clavier",
            "why_en": "Provides accurate chord charts for bassist, guitarist, and keyboardist",
        },
        {
            "id": "drums",
            "name": "ADTOF (Automatic Drum Transcription on the Fly)",
            "selected_model": "ADTOF-PyTorch (359h audio, ~16 Mo)",
            "role_fr": "Transcription dynamique de batterie (kick, snare, toms, charley ouvert/fermé, crashs)",
            "role_en": "Dynamic drum transcription (kick, snare, toms, open/closed hi-hat, crashes)",
            "why_fr": "Alimente la vue du batteur avec alertes de fills, breaks et crashs",
            "why_en": "Feeds drummer prompter with fills, breaks, and crash cues",
        },
        {
            "id": "words",
            "name": "Whisper (Essentiel / Essential)",
            "selected_model": "Whisper small",
            "role_fr": "Brouillon automatique des paroles avec calage par ligne",
            "role_en": "Automatic lyrics draft with line timing",
            "why_fr": "Profil Avancé facultatif : large-v3-turbo et calage mot-à-mot wav2vec2",
            "why_en": "Optional Advanced profile: large-v3-turbo and wav2vec2 word alignment",
        },
    ]

    return {
        "profile": profile,
        "title_fr": title_fr,
        "title_en": title_en,
        "desc_fr": desc_fr,
        "desc_en": desc_en,
        "stems_model": stems_model,
        "install_stems": True,
        "install_structure": True,
        "structure_window": structure_window,
        "install_chords": True,
        "install_drums": True,
        "install_words": True,
        "models": models,
    }


def suite_summary(suite: dict, lang: str = "fr") -> str:
    """Formate un résumé lisible de la suite IA recommandée."""
    is_fr = lang == "fr"
    title = suite["title_fr"] if is_fr else suite["title_en"]
    desc = suite["desc_fr"] if is_fr else suite["desc_en"]
    lines = [
        f"  Profil recommandé : {title}" if is_fr else f"  Recommended profile: {title}",
        f"  {desc}",
        "  Modèles IA recommandés :" if is_fr else "  Recommended AI models:",
    ]
    for m in suite["models"]:
        name = m["name"]
        role = m["role_fr"] if is_fr else m["role_en"]
        sel = m["selected_model"]
        lines.append(f"    • {name} [{sel}] : {role}")
    return "\n".join(lines)


def _detect_nvidia_smi() -> dict | None:
    """Détection via nvidia-smi (rapide et fiable pour NVIDIA)."""
    if not shutil.which("nvidia-smi"):
        if sys.platform == "win32":
            alt = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
            if not alt.is_file():
                return None
            cmd = str(alt)
        else:
            return None
    else:
        cmd = "nvidia-smi"

    try:
        res = subprocess.run(
            [cmd, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        if lines:
            parts = lines[0].split(",")
            name = parts[0].strip()
            vram_mb = int(parts[1].strip()) if len(parts) > 1 else 0
            info = {
                "has_gpu": True,
                "vendor": "nvidia",
                "name": name,
                "vram_mb": vram_mb,
                "is_dedicated": True,
                "backend": "cuda",
                "index_url": _cuda_index_url(name),
            }
            info["recommended_stems_model"] = recommended_stems_model(info)
            return info
    except Exception:
        pass
    return None


def _detect_windows_registry() -> dict | None:
    """Détection via le registre Windows (NVIDIA, AMD dédié, etc.)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        best_gpu = None
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                    with winreg.OpenKey(k, sub) as sk:
                        try:
                            desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                            prov, _ = winreg.QueryValueEx(sk, "ProviderName")
                            vram_bytes = 0
                            for val_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                                try:
                                    val, _ = winreg.QueryValueEx(sk, val_name)
                                    if val:
                                        vram_bytes = int(val)
                                        break
                                except FileNotFoundError:
                                    pass

                            vram_mb = vram_bytes // (1024 * 1024)
                            is_dedicated = vram_mb >= 2048

                            prov_lower = prov.lower()
                            desc_lower = desc.lower()

                            if "nvidia" in prov_lower or "geforce" in desc_lower or "quadro" in desc_lower or "rtx" in desc_lower:
                                gpu = {
                                    "has_gpu": True,
                                    "vendor": "nvidia",
                                    "name": desc,
                                    "vram_mb": vram_mb,
                                    "is_dedicated": is_dedicated,
                                    "backend": "cuda",
                                    "index_url": _cuda_index_url(desc),
                                }
                                gpu["recommended_stems_model"] = recommended_stems_model(gpu)
                                if is_dedicated:
                                    return gpu
                                if not best_gpu:
                                    best_gpu = gpu

                            elif "advanced micro devices" in prov_lower or "amd" in prov_lower or "ati" in prov_lower or "radeon" in desc_lower:
                                gpu = {
                                    "has_gpu": True,
                                    "vendor": "amd",
                                    "name": desc,
                                    "vram_mb": vram_mb,
                                    "is_dedicated": is_dedicated,
                                    "backend": "rocm",
                                    "index_url": None,
                                }
                                gpu["recommended_stems_model"] = recommended_stems_model(gpu)
                                if is_dedicated:
                                    return gpu
                                if not best_gpu:
                                    best_gpu = gpu

                        except FileNotFoundError:
                            pass
                except OSError:
                    break
        return best_gpu
    except Exception:
        pass
    return None


def _detect_linux_gpu() -> dict | None:
    """Détection sous Linux (nvidia-smi, rocm-smi)."""
    if sys.platform != "linux":
        return None

    if shutil.which("rocm-smi"):
        try:
            res = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True, timeout=5)
            name = "AMD Radeon (ROCm)"
            for line in res.stdout.splitlines():
                if "Card series:" in line or "Card model:" in line:
                    name = line.split(":", 1)[1].strip()
                    break
            info = {
                "has_gpu": True,
                "vendor": "amd",
                "name": name,
                "vram_mb": 0,
                "is_dedicated": True,
                "backend": "rocm",
                "index_url": "https://download.pytorch.org/whl/rocm6.2",
            }
            info["recommended_stems_model"] = recommended_stems_model(info)
            return info
        except Exception:
            pass

    return None


def _detect_macos() -> dict | None:
    """Détection sous macOS (Apple Silicon Metal / MPS)."""
    if sys.platform != "darwin":
        return None
    if platform.machine() == "arm64":
        info = {
            "has_gpu": True,
            "vendor": "apple",
            "name": "Apple Silicon (Metal/MPS)",
            "vram_mb": 0,
            "is_dedicated": True,
            "backend": "mps",
            "index_url": None,
        }
        info["recommended_stems_model"] = recommended_stems_model(info)
        return info
    return None


def detect_gpu() -> dict:
    """Détecte l'accélération matérielle disponible (GPU dédié NVIDIA/AMD, Apple Silicon, ou CPU)."""
    # 1. NVIDIA (nvidia-smi direct)
    res = _detect_nvidia_smi()
    if res:
        return res

    # 2. Windows Registre (NVIDIA ou AMD)
    if sys.platform == "win32":
        res = _detect_windows_registry()
        if res:
            return res

    # 3. Linux
    if sys.platform == "linux":
        res = _detect_linux_gpu()
        if res:
            return res

    # 4. macOS Apple Silicon
    if sys.platform == "darwin":
        res = _detect_macos()
        if res:
            return res

    # 5. Fallback CPU
    info = {
        "has_gpu": False,
        "vendor": "cpu",
        "name": "CPU",
        "vram_mb": 0,
        "is_dedicated": False,
        "backend": "cpu",
        "index_url": None,
    }
    info["recommended_stems_model"] = recommended_stems_model(info)
    return info


def summary(info: dict, lang: str = "fr") -> str:
    """Formate un résumé lisible pour l'utilisateur en français ou anglais."""
    is_fr = lang == "fr"
    vram_unit = "Go" if is_fr else "GB"
    vram_str = f" ({round(info['vram_mb'] / 1024)} {vram_unit} VRAM)" if info.get("vram_mb") and info["vram_mb"] >= 1024 else ""

    if info["vendor"] == "nvidia":
        return (
            f"GPU dédié détecté : {info['name']}{vram_str} — Accélération matérielle NVIDIA CUDA activée"
            if is_fr
            else f"Dedicated GPU detected: {info['name']}{vram_str} — NVIDIA CUDA acceleration enabled"
        )
    if info["vendor"] == "amd":
        if info.get("is_dedicated"):
            return (
                f"GPU dédié détecté : {info['name']}{vram_str} — Accélération matérielle AMD détectée"
                if is_fr
                else f"Dedicated GPU detected: {info['name']}{vram_str} — AMD hardware acceleration detected"
            )
        return (
            f"GPU intégré détecté : {info['name']} — Mode standard"
            if is_fr
            else f"Integrated GPU detected: {info['name']} — Standard mode"
        )
    if info["vendor"] == "apple":
        return (
            f"Puce Apple Silicon détectée : {info['name']} — Accélération Metal (MPS) activée"
            if is_fr
            else f"Apple Silicon chip detected: {info['name']} — Metal (MPS) acceleration enabled"
        )
    return (
        "Aucun GPU dédié détecté — Mode processeur standard (CPU)"
        if is_fr
        else "No dedicated GPU detected — Standard processor mode (CPU)"
    )


def audit_venv(py_path: str | Path, gpu_info: dict | None = None) -> dict:
    """Audite un environnement virtuel Python pour vérifier l'adéquation de PyTorch
    avec le matériel détecté sur la machine actuelle.

    Returns dict with:
      - installed: bool
      - torch_version: str | None
      - status: 'optimal' | 'needs_reinstall' | 'not_installed'
      - action: 'keep' | 'reinstall' | 'install'
      - target_version: str ('2.8.0' ou '2.5.1')
      - target_index: str | None
      - reason / reason_fr: explication
    """
    py = Path(py_path)
    if not py.is_file():
        return {
            "py_path": str(py),
            "installed": False,
            "torch_version": None,
            "status": "not_installed",
            "action": "install",
            "target_version": "2.5.1",
            "target_index": None,
            "reason": "Python executable not found",
            "reason_fr": "Exécutable Python introuvable",
        }

    if gpu_info is None:
        gpu_info = detect_gpu()

    # Sonde exécutée dans l'environnement virtuel ciblé
    probe_code = (
        "import json, sys\n"
        "res = {'installed': False, 'version': None, 'cuda': False, 'device': None, 'cap': None, 'compute_ok': False, 'err': None}\n"
        "try:\n"
        "    import torch\n"
        "    res['installed'] = True\n"
        "    res['version'] = str(torch.__version__)\n"
        "    res['cuda'] = bool(torch.cuda.is_available())\n"
        "    if res['cuda']:\n"
        "        res['device'] = torch.cuda.get_device_name(0)\n"
        "        res['cap'] = list(torch.cuda.get_device_capability(0))\n"
        "        try:\n"
        "            x = torch.randn(16, 16, device='cuda')\n"
        "            _ = torch.matmul(x, x)\n"
        "            res['compute_ok'] = True\n"
        "        except Exception as e:\n"
        "            res['err'] = str(e)\n"
        "    elif getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available():\n"
        "        res['mps'] = True\n"
        "        try:\n"
        "            x = torch.randn(16, 16, device='mps')\n"
        "            _ = torch.matmul(x, x)\n"
        "            res['compute_ok'] = True\n"
        "        except Exception as e:\n"
        "            res['err'] = str(e)\n"
        "    else:\n"
        "        x = torch.randn(16, 16)\n"
        "        _ = torch.matmul(x, x)\n"
        "        res['compute_ok'] = True\n"
        "except Exception as e:\n"
        "    res['err'] = str(e)\n"
        "print(json.dumps(res))\n"
    )

    try:
        proc = subprocess.run(
            [str(py), "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            probe = {"installed": False, "err": proc.stderr.strip() or "probe failed"}
        else:
            probe = json.loads(proc.stdout.strip())
    except Exception as e:
        probe = {"installed": False, "err": str(e)}

    gpu_name = gpu_info.get("name", "")
    target_index = gpu_info.get("index_url")
    is_blackwell = bool(
        gpu_info.get("vendor") == "nvidia"
        and any(k in gpu_name.lower() for k in ("rtx 50", "5070", "5080", "5090", "blackwell"))
    )
    target_torch_ver = "2.8.0" if is_blackwell else "2.5.1"

    if not probe.get("installed"):
        return {
            "py_path": str(py),
            "installed": False,
            "torch_version": None,
            "status": "not_installed",
            "action": "install",
            "target_version": target_torch_ver,
            "target_index": target_index,
            "reason": "PyTorch is not installed in this environment",
            "reason_fr": "PyTorch n'est pas installé dans cet environnement",
        }

    version = probe.get("version") or ""
    compute_ok = probe.get("compute_ok", False)
    cuda_active = probe.get("cuda", False)
    err = probe.get("err") or ""

    # Cas 1 : GPU NVIDIA Dédié
    if gpu_info.get("vendor") == "nvidia" and gpu_info.get("is_dedicated"):
        if is_blackwell:
            # Blackwell (sm_120) exige CUDA 12.8 (torch 2.8.0) ET calcul effectif
            if "cu128" in version and compute_ok:
                return {
                    "py_path": str(py),
                    "installed": True,
                    "torch_version": version,
                    "status": "optimal",
                    "action": "keep",
                    "target_version": target_torch_ver,
                    "target_index": target_index,
                    "reason": f"PyTorch {version} with CUDA 12.8 is optimal for {gpu_name}",
                    "reason_fr": f"PyTorch {version} avec CUDA 12.8 est optimal pour {gpu_name}",
                }
            return {
                "py_path": str(py),
                "installed": True,
                "torch_version": version,
                "status": "needs_reinstall",
                "action": "reinstall",
                "target_version": "2.8.0",
                "target_index": target_index,
                "reason": f"Blackwell architecture requires CUDA 12.8 (current: {version or 'none'}, compute_ok={compute_ok})",
                "reason_fr": f"L'architecture Blackwell requiert CUDA 12.8 (actuel : {version or 'aucun'}, calcul={compute_ok})",
            }
        else:
            # Autres NVIDIA (Ada, Ampere, Turing, etc.)
            if cuda_active and compute_ok:
                return {
                    "py_path": str(py),
                    "installed": True,
                    "torch_version": version,
                    "status": "optimal",
                    "action": "keep",
                    "target_version": target_torch_ver,
                    "target_index": target_index,
                    "reason": f"PyTorch {version} with CUDA acceleration is optimal for {gpu_name}",
                    "reason_fr": f"PyTorch {version} avec accélération CUDA est optimal pour {gpu_name}",
                }
            return {
                "py_path": str(py),
                "installed": True,
                "torch_version": version,
                "status": "needs_reinstall",
                "action": "reinstall",
                "target_version": "2.5.1",
                "target_index": target_index,
                "reason": f"NVIDIA GPU detected but PyTorch has no working CUDA support ({version})",
                "reason_fr": f"GPU NVIDIA détecté mais PyTorch n'a pas d'accélération CUDA fonctionnelle ({version})",
            }

    # Cas 2 : Apple Silicon (MPS)
    if gpu_info.get("vendor") == "apple":
        if probe.get("mps") and compute_ok:
            return {
                "py_path": str(py),
                "installed": True,
                "torch_version": version,
                "status": "optimal",
                "action": "keep",
                "target_version": "2.5.1",
                "target_index": None,
                "reason": "Apple Silicon Metal (MPS) acceleration is optimal",
                "reason_fr": "Accélération Apple Silicon Metal (MPS) optimale",
            }
        return {
            "py_path": str(py),
            "installed": True,
            "torch_version": version,
            "status": "needs_reinstall",
            "action": "reinstall",
            "target_version": "2.5.1",
            "target_index": None,
            "reason": "Apple Silicon Metal acceleration missing or broken",
            "reason_fr": "Accélération Apple Silicon Metal manquante ou en échec",
        }

    # Cas 3 : Processeur standard (CPU)
    if not cuda_active and compute_ok:
        return {
            "py_path": str(py),
            "installed": True,
            "torch_version": version,
            "status": "optimal",
            "action": "keep",
            "target_version": "2.5.1",
            "target_index": None,
            "reason": f"PyTorch {version} is optimal for CPU",
            "reason_fr": f"PyTorch {version} est optimal pour processeur (CPU)",
        }
    if not compute_ok:
        return {
            "py_path": str(py),
            "installed": True,
            "torch_version": version,
            "status": "needs_reinstall",
            "action": "reinstall",
            "target_version": "2.5.1",
            "target_index": None,
            "reason": f"PyTorch compute test failed ({err})",
            "reason_fr": f"Le test de calcul PyTorch a échoué ({err})",
        }

    return {
        "py_path": str(py),
        "installed": True,
        "torch_version": version,
        "status": "optimal",
        "action": "keep",
        "target_version": "2.5.1",
        "target_index": None,
        "reason": "Standard configuration",
        "reason_fr": "Configuration standard",
    }


def sync_settings(settings_path: Path | str, gpu_info: dict | None = None, force_model: bool = False) -> dict:
    """Actualise le matériel sans remplacer le modèle choisi par l'utilisateur.

    La recommandation reste informative sauf demande explicite ``force_model``
    (commande ``sync-settings --force``).
    """
    p = Path(settings_path)
    if gpu_info is None:
        gpu_info = detect_gpu()
    rec_model = recommended_stems_model(gpu_info)

    data = {}
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    changed = False
    old_hw = data.get("hardware")
    new_hw = {
        "vendor": gpu_info.get("vendor"),
        "name": gpu_info.get("name"),
        "vram_mb": gpu_info.get("vram_mb", 0),
        "backend": gpu_info.get("backend"),
        "is_dedicated": gpu_info.get("is_dedicated", False),
        "index_url": gpu_info.get("index_url"),
        "recommended_stems_model": rec_model,
    }
    if old_hw != new_hw:
        data["hardware"] = new_hw
        changed = True

    current_model = data.get("stems_model")
    new_model = rec_model if force_model else (
        current_model if current_model in ("htdemucs", "htdemucs_ft", "htdemucs_6s") else "htdemucs"
    )
    if current_model != new_model:
        data["stems_model"] = new_model
        changed = True

    if changed:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "changed": changed,
        "stems_model": data["stems_model"],
        "hardware": data.get("hardware", new_hw),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Détection de GPU et audit matériel pour ReaCue")
    sub = ap.add_subparsers(dest="cmd")

    # audit <python_path>
    p_audit = sub.add_parser("audit", help="Auditer un environnement virtuel Python")
    p_audit.add_argument("python_path", help="Chemin vers python.exe ou python")
    p_audit.add_argument("--json", action="store_true", default=True, help="Sortie JSON (défaut)")

    # sync-settings <settings_path>
    p_sync = sub.add_parser("sync-settings", help="Synchroniser reacue_settings.json avec le matériel")
    p_sync.add_argument("settings_path", help="Chemin vers reacue_settings.json")
    p_sync.add_argument("--force", action="store_true", help="Forcer le modèle recommandé")

    # Commandes par défaut (détection)
    ap.add_argument("--json", action="store_true", help="Afficher les informations matérielles au format JSON")
    ap.add_argument("--index-url", action="store_true", help="Afficher l'URL d'index PyTorch (--extra-index-url)")
    ap.add_argument("--backend", action="store_true", help="Afficher le backend (cuda, rocm, mps, cpu)")
    ap.add_argument("--model", action="store_true", help="Afficher le modèle de stems recommandé")
    ap.add_argument("--target-torch-version", action="store_true", help="Afficher la version PyTorch cible (2.8.0 ou 2.5.1)")
    ap.add_argument("--suite", action="store_true", help="Afficher la suite IA recommandée en texte clair")
    ap.add_argument("--suite-json", action="store_true", help="Afficher la suite IA recommandée au format JSON")
    ap.add_argument("--lang", default="fr", choices=["fr", "en"], help="Langue du résumé")

    args = ap.parse_args(argv)

    if args.cmd == "audit":
        audit_res = audit_venv(args.python_path)
        print(json.dumps(audit_res, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "sync-settings":
        res = sync_settings(args.settings_path, force_model=args.force)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    info = detect_gpu()

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    if args.index_url:
        print(info.get("index_url") or "")
        return 0
    if args.backend:
        print(info.get("backend") or "cpu")
        return 0
    if args.model:
        print(info.get("recommended_stems_model") or "htdemucs_6s")
        return 0
    if args.target_torch_version:
        is_bw = bool(info.get("vendor") == "nvidia" and any(k in info.get("name", "").lower() for k in ("rtx 50", "5070", "5080", "5090", "blackwell")))
        print("2.8.0" if is_bw else "2.5.1")
        return 0
    if args.suite_json:
        print(json.dumps(recommend_ai_suite(info), ensure_ascii=False, indent=2))
        return 0
    if args.suite:
        print(suite_summary(recommend_ai_suite(info), args.lang))
        return 0

    print(summary(info, args.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
