"""CUDA selection for standalone audio workers, with bounded-memory CPU recovery."""
import gc
from importlib import metadata
import os

import diagnostics


def versions(task):
    info = {'task': task}
    for name in ('numpy', 'torch', 'torchaudio', 'soxr', 'beat-this', 'demucs'):
        try:info[name] = metadata.version(name)
        except metadata.PackageNotFoundError:pass
    if task in ('separate','drumsep','smartgrid','structure','lyrics','chords','drums'):
        try:
            from reacue_gpu import detect_gpu
            gpu=detect_gpu()
            info.update(gpu=gpu.get('name'),gpu_vendor=gpu.get('vendor'),vram_mb=gpu.get('vram_mb'))
        except (ImportError,OSError,RuntimeError):pass
    diagnostics.event('analysis.environment', **info)
    return info


def select_device(torch):
    """Availability is insufficient: verify a real CUDA operation in this runtime."""
    info = {'device': 'cpu'}
    if os.environ.get('REACUE_DEVICE', 'auto').lower() == 'cpu':
        return info
    try:
        if torch.cuda.is_available():
            probe = torch.ones(1, device='cuda') * 2
            torch.cuda.synchronize()
            del probe
            props = torch.cuda.get_device_properties(0)
            info.update(device='cuda', gpu=props.name, vram_mb=props.total_memory // (1024 * 1024),
                        cuda=str(torch.version.cuda))
    except (RuntimeError, OSError) as error:
        info['fallback'] = 'CUDA indisponible : ' + str(error)[:300]
    return info


def cuda_error(error):
    return isinstance(error, RuntimeError) and any(word in str(error).lower()
        for word in ('cuda', 'cudnn', 'cublas', 'out of memory'))


def run(torch, task, action, *, cleanup=lambda: None, notify=lambda info: None):
    """Retry once on CPU only for an accelerator failure, never for invalid data."""
    info = select_device(torch)
    diagnostics.event('analysis.compute', task=task, **info)
    notify(info)
    try:
        return action(info), info
    except RuntimeError as error:
        if info['device'] != 'cuda' or not cuda_error(error):raise
        reason = str(error)[:300]
    # Leave the exception handler so failed GPU tensors are no longer retained
    # by its traceback. Move the model before releasing cached allocations.
    cleanup()
    gc.collect()
    try:torch.cuda.empty_cache()
    except RuntimeError:pass
    info = {**info, 'device': 'cpu', 'fallback': reason}
    diagnostics.event('analysis.fallback', task=task, **info)
    print('Mémoire GPU ou calcul CUDA indisponible : reprise sur le processeur.', flush=True)
    notify(info)
    return action(info), info


def demucs_segment(info):
    # GTX 1650-class cards usually have 4 GB, also shared with the Windows UI.
    return 4.0 if info['device'] == 'cuda' and info.get('vram_mb', 0) <= 4608 else None
