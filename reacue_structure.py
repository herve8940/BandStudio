"""Analyse de structure pour ReaCue (SongFormer, en local) / Structure analysis for ReaCue (SongFormer, local).

Tourne dans l'environnement séparé .venv-structure (installé par install/install_structure_*), jamais dans
le .venv de ReaCue. Utilise SongFormer (ASLP-lab, licence CC BY 4.0, arXiv 2510.02797) téléchargé par
l'installateur dans <ReaCue>/structure/SongFormer (révision figée), avec ses dépendances MuQ et MusicFM.
Modèles : dans <ReaCue>/structure/SongFormer/src/SongFormer/ckpts et <ReaCue>/structure/hf (HF_HOME).

    <python> reacue_structure.py analyze --input <audio> --out <résultat.json> [--status <état.json>]
                                         [--window auto|420|120]
        -> {"segments": [{"start", "end", "label"}], "window_s", "seconds", "engine": "songformer"}
    <python> reacue_structure.py check [--lang fr|en]    # télécharge les modèles, teste, « STRUCTURE_OK »
    <python> reacue_structure.py reuse [--lang fr|en] [--from <dossier>]...
        # réutilise des modèles déjà téléchargés (copie ou lien, vérifiés par md5 / taille) au lieu de
        # les retélécharger : ckpts d'une autre installation de SongFormer (ex. ~/Documents/ReaCue-labo)
        # et cache Hugging Face par défaut (~/.cache/huggingface/hub, %USERPROFILE%/.cache/huggingface/hub).
        # Les sources ne sont jamais modifiées ni supprimées.

Fenêtre automatique : 30–60 s sur CPU, 60–120 s sur Metal, 120–420 s sur CUDA selon la mémoire.
Les caractéristiques utiles sont extraites sans calculer les couches et sorties inutilisées.
Une saturation CUDA relance une fois sur CPU avec une fenêtre courte.
Calcul sur CUDA, Metal/MPS sur Mac compatible, sinon CPU.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import traceback
import types
from contextlib import contextmanager, ExitStack
from pathlib import Path

import reacue_performance

reacue_performance.configure()

import reacue_metal

reacue_metal.configure()

HERE = Path(__file__).resolve().parent
STRUCT_DIR = Path(os.environ.get("REACUE_STRUCTURE_DIR") or HERE / "structure")
REPO = STRUCT_DIR / "SongFormer"
LABELS = ("intro", "verse", "pre-chorus", "chorus", "bridge", "inst", "silence", "outro")


def ram_gb() -> float:
    """Mémoire vive totale (Go) : macOS / Linux (sysconf), Windows (GlobalMemoryStatusEx)."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except Exception:
        return 8.0


def choose_window(window: str | int | None = "auto", ram: float | None = None) -> int:
    if str(window).isdigit():
        return max(30, int(window))
    probe_gpu = ram is None and os.environ.get("REACUE_DEVICE", "auto").lower() != "cpu"
    ram = ram_gb() if ram is None else ram
    # Attention cost is quadratic in time. Total host RAM alone must never select
    # a whole-song CPU window: a 6-minute song can page tens of GB on a 16-GB Mac.
    selected = 60 if ram >= 12 else 30
    if reacue_performance.profile() == "fast":
        return 30
    if probe_gpu:
        try:
            import torch
            if torch.cuda.is_available():
                total = torch.cuda.get_device_properties(0).total_memory
                free, _ = torch.cuda.mem_get_info()
                selected = 420 if total > 8 * 2**30 and free >= 12 * 2**30 else 120
            elif reacue_metal.device(torch) == "mps":
                selected = 120 if ram >= 24 else 60
        except (ImportError, RuntimeError, OSError):
            pass
    return selected


def _sdpa_forward(attention, original):
    """Same rotary attention, without materializing the quadratic score matrix."""
    def forward(hidden_states, attention_mask=None, relative_position_embeddings=None,
                output_attentions=False):
        import torch.nn.functional as F
        if attention.training or output_attentions or attention.position_embeddings_type != "rotary":
            return original(hidden_states, attention_mask, relative_position_embeddings, output_attentions)
        if relative_position_embeddings is None:
            return original(hidden_states, attention_mask, relative_position_embeddings, output_attentions)
        batch, _, _ = hidden_states.shape
        rotated = attention._apply_rotary_embedding(hidden_states, relative_position_embeddings)
        def heads(projection, values):
            return projection(values).view(batch, -1, attention.num_heads, attention.head_size).transpose(1, 2)
        result = F.scaled_dot_product_attention(
            heads(attention.linear_q, rotated), heads(attention.linear_k, rotated),
            heads(attention.linear_v, hidden_states), attn_mask=attention_mask, dropout_p=0.0)
        result = result.transpose(1, 2).reshape(batch, -1, attention.num_heads * attention.head_size)
        return attention.linear_out(result), None
    return forward


class _FeaturesReady(Exception):
    def __init__(self, features):
        self.features = features


def _tiled_convolution(conv, values, block=512):
    """Bound the pinned 4x subsampler's temporary activations to about 5 s.

    Its receptive field is 19 mel frames. A 12-frame halo (aligned to stride
    four) preserves every output, including the original end padding.
    """
    import torch
    frames = values.shape[-1]
    if frames <= block:
        return conv(values)
    pieces = []
    for start in range(0, frames, block):
        end = min(frames, start + block)
        left, right = max(0, start - 12), min(frames, end + 12)
        output = conv(values[..., left:right])
        offset = (start - left) // 4
        pieces.append(output[:, offset:offset + (end-start+3)//4])
    return torch.cat(pieces, dim=1)


class _ConvolutionReuse:
    """Keep one context's small features, reusing the interior of local excerpts.

    The mel boundary and convolution halo are recomputed from the local audio.
    Reuse requires the same waveform storage AND matching interior mel values.
    No attention context is reused between different excerpts.
    """
    def __init__(self, conv):
        self.conv = conv
        self.wave = self.base_wave = None
        self.mel = self.output = None

    def observe(self, original):
        def predict(wave, *args, **kwargs):
            previous, self.wave = self.wave, wave
            try:
                return original(wave, *args, **kwargs)
            finally:
                self.wave = previous
        return predict

    def __call__(self, values):
        import torch
        wave, base = self.wave, self.base_wave
        if (wave is not None and base is not None and wave.ndim == base.ndim == 2
                and wave.shape[0] == base.shape[0] == 1 and wave.stride(-1) == base.stride(-1) == 1
                and wave.untyped_storage().data_ptr() == base.untyped_storage().data_ptr()):
            samples = wave.storage_offset() - base.storage_offset()
            offset = samples // 240
            frames = values.shape[-1]
            if (samples >= 0 and samples % 960 == 0
                    and samples + wave.shape[-1] <= base.shape[-1]
                    and offset + frames <= self.mel.shape[-1] and frames > 160
                    and torch.allclose(values[..., 64:-64], self.mel[..., offset+64:offset+frames-64],
                                       rtol=1e-6, atol=1e-7)):
                length = (frames+3)//4
                result = self.output[:, offset//4:offset//4+length].clone()
                result[:, :16] = self.conv(values[..., :80])[:, :16]
                start = (length-16)*4-12
                result[:, -16:] = self.conv(values[..., start:])[:, 3:19]
                return result
        result = _tiled_convolution(self.conv, values)
        self.base_wave, self.mel, self.output = wave, values, result
        return result


def _feature_encoder(model, original, muq, convolution=None):
    """SongFormer consumes hidden_states[10], before layer 10 and final normalization.

    Stop at that exact point, avoiding later layers, all intermediate copies and
    the unused codebook projection. The hook is removed even on failure.
    """
    def encode(values, *args, **kwargs):
        if args or kwargs.get("attention_mask") is not None or model.training:
            return original(values, *args, **kwargs)
        def ready(_module, inputs):
            raise _FeaturesReady(inputs[0])
        handle = model.conformer.layers[10].register_forward_pre_hook(ready)
        try:
            try:
                model.conformer((convolution or model.conv)(values), output_hidden_states=False)
            except _FeaturesReady as done:
                features = done.features
            else:
                raise RuntimeError("SongFormer feature extraction did not reach layer 10")
        finally:
            handle.remove()
        states = (None,) * 10 + (features,)
        return (None, states, None) if muq else (None, states)
    return encode


@contextmanager
def efficient_inference(app):
    """Scoped optimizations for the pinned encoders; unknown architectures stay intact."""
    from unittest.mock import patch
    with ExitStack() as stack:
        for model, muq in ((getattr(getattr(app, "muq_model", None), "model", None), True),
                           (getattr(app, "musicfm_model", None), False)):
            conformer = getattr(model, "conformer", None)
            if (type(conformer).__name__ != "Wav2Vec2ConformerEncoder"
                    or not type(conformer).__module__.startswith("transformers.models.wav2vec2_conformer.")
                    or len(conformer.layers) <= 10 or model.training):
                continue
            # Only these pinned frontends have the stride/receptive field used below.
            conv = model.conv
            reuse = None
            if (type(conv).__name__ == "Conv2dSubsampling"
                    and type(conv).__module__ in ("muq.muq.modules.conv", "musicfm.modules.conv")
                    and all(block.conv1.stride == (2, 2) and block.conv2.stride == (1, 1)
                            and block.conv1.kernel_size == block.conv2.kernel_size == (3, 3)
                            and block.conv1.padding == block.conv2.padding == (1, 1)
                            for block in conv.conv)
                    and len(conv.conv) == 2
                    and model.preprocessor_melspec_2048.mel_stft.hop_length == 240
                    and model.preprocessor_melspec_2048.mel_stft.n_fft == 2048):
                reuse = _ConvolutionReuse(conv)
                stack.enter_context(patch.object(model, "get_predictions", reuse.observe(model.get_predictions)))
            stack.enter_context(patch.object(model, "encoder", _feature_encoder(model, model.encoder, muq, reuse)))
            import torch.nn.functional as F
            if hasattr(F, "scaled_dot_product_attention"):
                for layer in conformer.layers[:10]:
                    attention = layer.self_attn
                    stack.enter_context(patch.object(attention, "forward", _sdpa_forward(attention, attention.forward)))
        yield


def _write_status(path: Path | None, state: str, **kw):
    if not path:
        return
    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _stub_modules():
    """gradio (interface web de app.py) et msaf.eval (scores d'évaluation) : inutiles ici."""
    class _Any:
        def __init__(self, *a, **k): pass
        def __call__(self, *a, **k): return _Any()
        def __getattr__(self, n):
            if n.startswith("__"):
                raise AttributeError(n)
            return _Any()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter(())

    def _ga(n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Any()
    gr = types.ModuleType("gradio")
    gr.__getattr__ = _ga
    sys.modules.setdefault("gradio", gr)
    msaf = types.ModuleType("msaf")
    ev = types.ModuleType("msaf.eval")
    ev.compute_results = lambda *a, **k: {}
    msaf.eval = ev
    sys.modules.setdefault("msaf", msaf)
    sys.modules.setdefault("msaf.eval", ev)


def load_app():
    """Importe app.py de SongFormer (sans son interface) ; renvoie le module."""
    if not (REPO / "app.py").is_file():
        raise FileNotFoundError(f"SongFormer introuvable / not found: {REPO}")
    os.environ.setdefault("HF_HOME", str(STRUCT_DIR / "hf"))
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    _stub_modules()
    import app  # noqa: E402  (fait chdir dans src/SongFormer et ajoute third_party au chemin)
    return app


def _initialize_models(app, force_cpu=False):
    from contextlib import nullcontext
    from unittest.mock import patch
    import torch
    # The pinned upstream loader chooses CUDA internally. Scope the override to
    # this isolated worker's initialization; restore torch before returning.
    override = patch.object(torch.cuda, "is_available", return_value=False) if force_cpu else nullcontext()
    with override:
        app.initialize_models(model_name="SongFormer", checkpoint="SongFormer.safetensors",
                              config_path="SongFormer.yaml")


def _cuda_oom(error):
    return isinstance(error, RuntimeError) and "out of memory" in str(error).lower()


def _cpu_recovery(app, reason, notify, stage, *, discard=False):
    import torch
    if discard:
        for name in ("muq_model", "musicfm_model", "msa_model"):
            setattr(app, name, None)
        app.device = "cpu"
    else:
        _move_models(app, "cpu")
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except (RuntimeError, OSError):
        pass
    print("Mémoire CUDA insuffisante : reprise de l’analyse de structure sur le processeur.", flush=True)
    notify(dict(stage=stage, device="cpu", fallback=reason))


def init_models(app, notify=lambda info: None):
    app.download_all(use_mirror=False)
    import torch
    force_cpu = os.environ.get("REACUE_DEVICE", "auto").lower() == "cpu"
    reason = None
    try:
        _initialize_models(app, force_cpu=force_cpu)
    except RuntimeError as error:
        if force_cpu or not str(getattr(app, "device", "cpu")).startswith("cuda") or not _cuda_oom(error):
            raise
        reason = str(error)
    if reason is not None:
        # Run outside the exception handler: its traceback can retain GPU tensors.
        _cpu_recovery(app, reason, notify, "structure-loading", discard=True)
        _initialize_models(app, force_cpu=True)
        return
    if reacue_metal.device(torch) == "mps":
        try:
            _move_models(app, "mps")
        except (RuntimeError, NotImplementedError, TypeError) as error:
            _move_models(app, "cpu")
            reacue_metal.cpu_fallback(error)


def _move_models(app, target):
    # Upstream initializes on CUDA/CPU and reads this global for input tensors.
    for name in ("muq_model", "musicfm_model", "msa_model"):
        getattr(app, name).to(target)
    app.device = target


def segments_from_app(app, audio: str, window: int, notify=lambda info: None) -> list[dict]:
    with efficient_inference(app):
        return _segments_from_app(app, audio, window, notify)


def _process_audio(app, audio, window):
    """Avoid upstream's non-advancing `continue` on a final <=1024-sample tail."""
    from contextlib import nullcontext
    from unittest.mock import patch
    loader = getattr(app, "librosa", None)
    original = getattr(loader, "load", None)
    def load(*args, **kwargs):
        samples, rate = original(*args, **kwargs)
        if len(samples) <= 1024:
            raise ValueError("Audio trop court pour l’analyse de structure.")
        remainder = len(samples) % (window * rate)
        if 0 < remainder <= 1024:
            samples = samples[:-remainder]  # At most 43 ms; the source file is untouched.
        return samples, rate
    with patch.object(loader, "load", load) if original else nullcontext():
        return app.process_audio(audio, win_size=window, hop_size=window)


def _segments_from_app(app, audio: str, window: int, notify) -> list[dict]:
    recovery = None
    try:
        _, msa = _process_audio(app, audio, window)
    except (RuntimeError, NotImplementedError, TypeError) as error:
        target = str(getattr(app, "device", "cpu"))
        if target == "mps":
            recovery = ("mps", str(error))
        elif target.startswith("cuda") and _cuda_oom(error):
            recovery = ("cuda", str(error))
        else:
            raise
    if recovery is not None:
        if recovery[0] == "cuda":
            _cpu_recovery(app, recovery[1], notify, "structure-analysis")
        else:
            _move_models(app, "cpu")
            gc.collect()
            reacue_metal.cpu_fallback(recovery[1])
            notify(dict(stage="structure-analysis", device="cpu", fallback=recovery[1]))
        retry_window = min(window, 60 if ram_gb() >= 12 else 30)
        _, msa = _process_audio(app, audio, retry_window)
    msa = app.rule_post_processing(msa)
    return [{"start": float(s["start"]), "end": float(s["end"]), "label": str(s["label"])}
            for s in app.format_as_segments(msa)]


def analyze(audio: str, out: str, status: str | None = None, window: str = "auto") -> int:
    st = Path(status) if status else None
    audio = str(Path(audio).resolve())
    out = Path(out).resolve()
    t0 = time.time()
    try:
        if not Path(audio).is_file():
            raise FileNotFoundError(audio)
        win = choose_window(window)
        _write_status(st, "running", step="chargement des modèles / loading models", window_s=win)
        app = load_app()
        import torch
        reacue_performance.configure_torch(torch)
        init_models(app)
        _write_status(st, "running", step="analyse / analysing", window_s=win)
        segs = segments_from_app(app, audio, win)
        res = {"engine": "songformer", "segments": segs, "window_s": win, "seconds": round(time.time() - t0)}
        tmp = Path(str(out) + ".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, out)
        _write_status(st, "done", seconds=res["seconds"])
        return 0
    except BaseException as e:                       # noqa: BLE001 - rapporté à ReaCue
        traceback.print_exc()
        _write_status(st, "error", message=f"{type(e).__name__}: {e}")
        return 1


# --------------------------------------------------------------------------- réutilisation des modèles
CKPTS = ("SongFormer.safetensors", "MusicFM/pretrained_msd.pt", "MusicFM/msd_stats.json")
HF_REPOS = ("models--OpenMuQ--MuQ-large-msd-iter", "models--facebook--wav2vec2-conformer-rope-large-960h-ft")


def ckpts_dir(struct_dir: Path | None = None) -> Path:
    return (struct_dir or STRUCT_DIR) / "SongFormer" / "src" / "SongFormer" / "ckpts"


def _md5(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5_table(*dirs: Path) -> dict:
    """md5sum.txt de SongFormer (« <md5>  <chemin relatif> ») ; premier fichier trouvé."""
    for d in dirs:
        f = d / "md5sum.txt"
        if f.is_file():
            out = {}
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    out[parts[-1].replace("\\", "/")] = parts[0].lower()
            return out
    return {}


def ckpt_sources(extra: list | None = None, home: Path | None = None) -> list[Path]:
    """Dossiers ckpts candidats : --from / REACUE_REUSE_DIRS, puis ~/Documents/ReaCue-labo (laboratoire)."""
    home = home or Path.home()
    cands = [Path(x) for x in (extra or [])]
    cands += [Path(x) for x in os.environ.get("REACUE_REUSE_DIRS", "").split(os.pathsep) if x]
    cands.append(home / "Documents" / "ReaCue-labo" / "SongFormer" / "src" / "SongFormer" / "ckpts")
    out = []
    for c in cands:
        for d in (c, c / "src" / "SongFormer" / "ckpts", c / "SongFormer" / "src" / "SongFormer" / "ckpts"):
            if d.is_dir() and (d / CKPTS[0]).is_file() and d not in out:
                out.append(d)
                break
    return out


def hf_sources(home: Path | None = None) -> list[Path]:
    """Caches Hugging Face par défaut (macOS, Linux, Windows) : dossiers « hub »."""
    home = home or Path.home()
    cands = []
    if os.environ.get("REACUE_HF_SOURCE"):
        cands.append(Path(os.environ["REACUE_HF_SOURCE"]))
    if os.environ.get("HF_HUB_CACHE"):
        cands.append(Path(os.environ["HF_HUB_CACHE"]))
    if os.environ.get("HF_HOME"):
        cands.append(Path(os.environ["HF_HOME"]) / "hub")
    if os.environ.get("XDG_CACHE_HOME"):
        cands.append(Path(os.environ["XDG_CACHE_HOME"]) / "huggingface" / "hub")
    cands.append(home / ".cache" / "huggingface" / "hub")
    if os.environ.get("USERPROFILE"):
        cands.append(Path(os.environ["USERPROFILE"]) / ".cache" / "huggingface" / "hub")
    out = []
    for c in cands:
        if c.is_dir() and c not in out:
            out.append(c)
    return out


def _place(src: Path, dst: Path):
    """Lien physique si possible (même disque, aucune place en plus), sinon copie ; via un .part."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    if tmp.exists():
        tmp.unlink()
    try:
        os.link(src, tmp)
    except OSError:
        import shutil
        shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def _hf_repo_ok(repo: Path) -> bool:
    """Snapshot complet : au moins un fichier, tous non vides (liens résolus)."""
    snaps = repo / "snapshots"
    if not snaps.is_dir():
        return False
    files = [f for f in snaps.rglob("*") if not f.is_dir()]
    try:
        return bool(files) and all(f.exists() and f.stat().st_size > 0 for f in files)
    except OSError:
        return False


def reuse(sources: list | None = None, struct_dir: Path | None = None, hf_home: Path | None = None,
          home: Path | None = None, log=print, lang: str = "fr") -> dict:
    """Copie / lie les modèles déjà présents sur la machine vers l'emplacement attendu par ReaCue.
    Renvoie {"ckpts": [fichiers placés], "hf": [dépôts placés], "skipped": [(élément, raison)]}."""
    import shutil

    def t(fr, en):
        return en if lang == "en" else fr
    struct_dir = Path(struct_dir or STRUCT_DIR)
    dest = ckpts_dir(struct_dir)
    hf_hub = Path(hf_home or os.environ.get("HF_HOME") or struct_dir / "hf") / "hub"   # comme load_app
    res = {"ckpts": [], "hf": [], "skipped": []}
    srcs = ckpt_sources(sources, home)
    table = _md5_table(dest, *srcs)
    for rel in CKPTS:
        d = dest / rel
        want = table.get(rel)
        if d.is_file() and d.stat().st_size > 0 and (not want or _md5(d) == want):
            continue                                   # déjà en place et intact
        for s in srcs:
            f = s / rel
            if not f.is_file() or f.stat().st_size == 0:
                continue
            if want and _md5(f) != want:
                res["skipped"].append((str(f), "md5"))
                continue
            if d.exists() and d.resolve() == f.resolve():
                break
            _place(f, d)
            res["ckpts"].append(rel)
            log(t(f"  modèle réutilisé : {rel} (depuis {s})", f"  model reused: {rel} (from {s})"))
            break
    for repo in HF_REPOS:
        d = hf_hub / repo
        if _hf_repo_ok(d):
            continue
        for s in hf_sources(home):
            src = s / repo
            if d.exists() and src.resolve() == d.resolve():
                break
            if not _hf_repo_ok(src):
                if src.exists():
                    res["skipped"].append((str(src), "incomplete"))
                continue
            if d.exists():
                shutil.rmtree(d)                       # copie précédente incomplète (jamais la source)
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(d.name + ".part")
            if tmp.exists():
                shutil.rmtree(tmp)
            shutil.copytree(src, tmp, symlinks=True)
            os.replace(tmp, d)
            res["hf"].append(repo)
            log(t(f"  modèle réutilisé : {repo} (depuis {s})", f"  model reused: {repo} (from {s})"))
            break
    if not res["ckpts"] and not res["hf"]:
        log(t("  aucun modèle déjà téléchargé à réutiliser.", "  no already-downloaded model to reuse."))
    return res


def check(lang: str = "fr", seconds: int = 20) -> int:
    def t(fr, en):
        return en if lang == "en" else fr
    try:
        app = load_app()
        import numpy as np
        import torch
        import soundfile as sf
    except Exception as e:                           # noqa: BLE001
        print(t("ÉCHEC : SongFormer n'est pas importable : ", "FAILED: SongFormer cannot be imported: ") + repr(e))
        return 1
    reacue_performance.configure_torch(torch)
    win = choose_window("auto")
    print(f"  python {sys.version.split()[0]} | torch {torch.__version__} | numpy {np.__version__} | "
          f"RAM {ram_gb():.0f} Go/GB -> {t('fenêtre', 'window')} {win} s")
    print(t("  téléchargement des modèles (environ 2 Go la première fois)…",
            "  downloading the models (about 2 GB the first time)…"), flush=True)
    t0 = time.time()
    init_models(app)
    print(f"  device: {getattr(app, 'device', 'cpu')}")
    print(t(f"  modèles prêts ({time.time() - t0:.0f} s)", f"  models ready ({time.time() - t0:.0f} s)"), flush=True)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "test.wav"
        sr = 24000
        x = (np.random.default_rng(0).standard_normal(sr * seconds) * 0.05).astype(np.float32)
        sf.write(str(wav), x, sr)
        t0 = time.time()
        segments_from_app(app, str(wav), min(win, 120))
        per_song = (time.time() - t0) / seconds * 240 / 60
    print(t(f"  vitesse : environ {per_song:.0f} min pour un morceau de 4 min",
            f"  speed: about {per_song:.0f} min for a 4-minute song"))
    print("STRUCTURE_OK")
    return 0



def benchmark_threads(app, audio, counts, repeats=2, window=120, clock=time.perf_counter, progress=None):
    """Compare actual SongFormer CPU inference, excluding model load and warm-up."""
    import torch
    _move_models(app, "cpu")
    previous = torch.get_num_threads()
    results = []
    try:
        for count in counts:
            if progress:
                progress(f"Testing / Test : {count} threads…", flush=True)
            torch.set_num_threads(count)
            segments_from_app(app, str(audio), window)  # warm-up for this thread count
            times = []
            for _ in range(repeats):
                start = clock()
                segments_from_app(app, str(audio), window)
                times.append(clock() - start)
            results.append({"threads": count, "seconds": sum(times) / len(times)})
    finally:
        torch.set_num_threads(previous)
    return sorted(results, key=lambda row: row["seconds"])


def benchmark(args):
    import tempfile
    import numpy as np
    import soundfile as sf
    counts = sorted(set(int(x) for x in args.threads.split(",")))
    if not counts or any(x < 1 or x > (os.cpu_count() or 1) for x in counts):
        raise ValueError("Threads must be between 1 and the logical CPU count")
    if args.input and not Path(args.input).is_file():
        raise FileNotFoundError(args.input)
    os.environ["REACUE_DEVICE"] = "cpu"  # This benchmark intentionally calibrates CPU inference.
    print("CPU benchmark / Étalonnage CPU — SongFormer, model loaded once.", flush=True)
    print("This can take several minutes / Cela peut prendre plusieurs minutes.", flush=True)
    app = load_app()
    init_models(app)
    with tempfile.TemporaryDirectory() as tmp:
        audio = args.input
        if not audio:
            audio = str(Path(tmp) / "benchmark.wav")
            noise = np.random.default_rng(0).standard_normal(24000 * 20).astype(np.float32) * 0.05
            sf.write(audio, noise, 24000)
        results = benchmark_threads(app, audio, counts, progress=print)
    for row in results:
        print(f"  {row['threads']} threads: {row['seconds']:.3f} s")
    best = results[0]["threads"]
    print(f"Best on this sample / Meilleur sur cet extrait: {best} threads")
    if args.save:
        reacue_performance.save_threads(best)
        print("Saved for subsequent analyses / Enregistré pour les prochaines analyses.")
    print("Results depend on the audio and model / Résultat dépendant de l'audio et du modèle.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reacue_structure")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--input", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--status")
    a.add_argument("--window", default="auto")
    c = sub.add_parser("check")
    c.add_argument("--lang", default="fr", choices=["fr", "en"])
    c.add_argument("--seconds", type=int, default=20)
    b = sub.add_parser("benchmark", help="Compare CPU threads using actual SongFormer inference")
    b.add_argument("--input", help="Optional representative audio excerpt (otherwise 20s synthetic audio)")
    b.add_argument("--threads", default=",".join(str(n) for n in (1, 2, 4, 8) if n <= (os.cpu_count() or 1)))
    b.add_argument("--save", action="store_true", help="Save fastest thread count to ReaCue settings")
    r = sub.add_parser("reuse")
    r.add_argument("--lang", default="fr", choices=["fr", "en"])
    r.add_argument("--from", dest="sources", action="append", default=[])
    args = ap.parse_args(argv)
    if args.cmd == "benchmark":
        return benchmark(args)
    if args.cmd == "analyze":
        return analyze(args.input, args.out, args.status, args.window)
    if args.cmd == "reuse":
        try:
            reuse(args.sources, lang=args.lang)
        except Exception as e:                       # noqa: BLE001 - jamais bloquant : on téléchargera
            print(("  réutilisation impossible : " if args.lang == "fr" else "  reuse failed: ") + repr(e))
        return 0
    return check(args.lang, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
