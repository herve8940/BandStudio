"""Séparation de stems pour ReaCue (Demucs, en local) / Stem separation for ReaCue (Demucs, local).



Tourne dans l'environnement séparé .venv-demucs (installé par install/install_stems_*), jamais dans le

.venv de ReaCue : Demucs a besoin d'autres versions de torch / numpy. Bibliothèque standard + demucs.



Lancé par l'action REAPER « ReaCue - Séparer les stems » (ReaCue_stems.lua), en arrière-plan :

    <.venv-demucs python> reacue_stems.py separate --input <audio> --out <dossier> [--model htdemucs]

        -> <dossier>/<model>/<nom du fichier>-<stem>.wav

        -> <dossier>/demucs.log (progression de Demucs) et <dossier>/demucs_status.json

           {"state": "running" | "done" | "error", "time", "pid", "model", "files": [...], "message"}

Modèles hors ligne : --repo <dossier> (fichiers .th de Demucs ; --model = nom du modèle dans ce dossier).

Vérification après installation (télécharge les modèles, mesure la vitesse) :

    <.venv-demucs python> reacue_stems.py check [--lang fr|en] [--seconds 10]

"""

from __future__ import annotations



import argparse

import json

import os

import shutil

import sys

import time

import traceback

from pathlib import Path

import reacue_performance

reacue_performance.configure()

import reacue_metal

reacue_metal.configure()

# S'assurer que le cache PyTorch pointe vers un disque approprié (TORCH_HOME)
if "TORCH_HOME" not in os.environ:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as _k:
            _val, _ = winreg.QueryValueEx(_k, "TORCH_HOME")
            if _val and Path(_val).is_dir():
                os.environ["TORCH_HOME"] = _val
    except Exception:
        pass
    if "TORCH_HOME" not in os.environ:
        _local = Path(__file__).resolve().parent / ".cache" / "torch"
        if _local.is_dir():
            os.environ["TORCH_HOME"] = str(_local)



MODELS = {   # stems produits par chaque modèle Demucs (ordre d'import dans REAPER)

    "htdemucs_6s": ("vocals", "drums", "bass", "guitar", "piano", "other"),

    "htdemucs": ("vocals", "drums", "bass", "other"),

    "htdemucs_ft": ("vocals", "drums", "bass", "other"),

}

DEFAULT_MODEL = "htdemucs"

FILENAME = "{track}-{stem}.{ext}"     # le nom d'origine (tonalité, bpm) est gardé : ReaCue le lit





def stem_files(input_file: str | Path, out: str | Path, model: str) -> list[Path]:

    """Fichiers que Demucs écrira pour `input_file` (même convention que l'action REAPER)."""

    track = Path(input_file).name.rsplit(".", 1)[0]

    return [Path(out) / model / f"{track}-{s}.wav" for s in MODELS[model]]





def check_disk_space(path: Path, min_mb: int = 500) -> tuple[bool, int]:

    """Vérifie l'espace disque disponible sur le lecteur cible (en Mo)."""

    try:

        usage = shutil.disk_usage(str(path))

        free_mb = int(usage.free // (1024 * 1024))

        return (free_mb >= min_mb), free_mb

    except Exception:

        return True, 999999





class FlushingStream:

    """Flux avec vidage immédiat sur disque (évite la perte des barres \r de tqdm et des traces d'erreur)."""



    def __init__(self, stream):

        self._s = stream



    def write(self, s: str):

        res = self._s.write(s)

        self._s.flush()

        return res



    def flush(self):

        return self._s.flush()



    def isatty(self) -> bool:

        return False



    def close(self):

        return self._s.close()



    def __getattr__(self, name: str):

        return getattr(self._s, name)





_JOB = None

def _write_status(path: Path, state: str, **kw):

    """Écriture atomique du statut avec plusieurs essais (évite les conflits d'accès sous Windows avec REAPER)."""

    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}

    if _JOB is not None:
        _JOB.update(state, **kw)
        d.update({k: _JOB.data[k] for k in ("id", "project", "started")})

    content = json.dumps(d, ensure_ascii=False)

    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")

    for _ in range(10):

        try:

            tmp.write_text(content, encoding="utf-8")

            os.replace(tmp, path)

            return

        except OSError:

            time.sleep(0.05)

    try:

        path.write_text(content, encoding="utf-8")

    except Exception:

        pass





def separate(input_file: str, out: str, model: str = DEFAULT_MODEL, repo: str | None = None) -> int:

    out_dir = Path(out)

    out_dir.mkdir(parents=True, exist_ok=True)

    status = out_dir / "demucs_status.json"

    raw_log = open(out_dir / "demucs.log", "w", encoding="utf-8")

    log = FlushingStream(raw_log)

    old = sys.stdout, sys.stderr

    sys.stdout = log            # pythonw (Windows) : pas de console ; ailleurs : nohup

    sys.stderr = log            # tqdm (barre de progression de Demucs) écrit ici : lu par REAPER

    if model not in MODELS and not repo:

        model = DEFAULT_MODEL

    stems = MODELS.get(model, MODELS[DEFAULT_MODEL])

    track = Path(input_file).name.rsplit(".", 1)[0]

    files = [out_dir / model / f"{track}-{s}.wav" for s in stems]

    _write_status(status, "running", model=model, input=str(input_file))

    try:

        ok_space, free_mb = check_disk_space(out_dir, min_mb=500)

        if not ok_space:

            raise OSError(

                f"Espace disque insuffisant sur le lecteur cible ({free_mb} Mo disponibles, minimum 500 Mo requis). "

                "Libérez de l'espace sur ce disque avant de relancer la séparation."

            )

        if not Path(input_file).is_file():

            raise FileNotFoundError(input_file)

        from demucs.separate import main as demucs_main

        extra_args = reacue_performance.demucs_args()

        if repo:

            extra_args.extend(["--repo", str(repo)])

        # Forcer le bon device matériel pour Demucs (CUDA, MPS ou CPU)

        try:

            import torch

            if reacue_performance.cpu_threads():
                reacue_performance.configure_torch(torch)

            if torch.cuda.is_available():

                extra_args.extend(["-d", "cuda"])

            elif reacue_metal.device(torch) == "mps":

                extra_args.extend(["-d", "mps"])

            else:

                extra_args.extend(["-d", "cpu"])

        except Exception:

            pass

        try:

            args = ["-n", model, "-o", str(out_dir), "--filename", FILENAME] + extra_args + [str(input_file)]
            try:
                demucs_main(args)
            except (RuntimeError, NotImplementedError, TypeError) as error:
                if "-d" not in extra_args or extra_args[extra_args.index("-d") + 1] != "mps":
                    raise
                reacue_metal.cpu_fallback(error)
                args[args.index("-d") + 1] = "cpu"
                demucs_main(args)

        except SystemExit as e:              # Demucs appelle sys.exit en cas d'erreur

            if e.code not in (None, 0):

                raise RuntimeError(f"demucs exit {e.code}") from None

        missing = [str(f) for f in files if not f.is_file()]

        if missing:

            raise RuntimeError("missing: " + ", ".join(missing))

        _write_status(status, "done", model=model, files=[str(f) for f in files])

        return 0

    except BaseException as e:               # noqa: BLE001 - tout est rapporté à REAPER

        traceback.print_exc()

        try:

            log.flush()

        except Exception:

            pass

        _write_status(status, "error", model=model, message=f"{type(e).__name__}: {e}")

        return 1

    finally:

        sys.stdout, sys.stderr = old

        try:

            raw_log.close()

        except Exception:

            pass





def check(lang: str = "fr", seconds: int = 10) -> int:

    """Charge (et télécharge au besoin) les modèles, puis mesure la vitesse sur un signal de test."""

    def t(fr, en):

        return en if lang == "en" else fr

    try:

        import numpy

        import torch

        import torchaudio

        import demucs

        from demucs.apply import apply_model

        from demucs.pretrained import get_model

    except Exception as e:                   # noqa: BLE001

        print(t("ÉCHEC : Demucs n'est pas importable : ", "FAILED: Demucs cannot be imported: ") + repr(e))

        return 1



    # Détection de l'accélération matérielle

    if reacue_performance.cpu_threads():
        reacue_performance.configure_torch(torch)

    if torch.cuda.is_available():

        device = "cuda"

        gpu_name = torch.cuda.get_device_name(0)

        device_label = f"NVIDIA CUDA ({gpu_name})"

    elif reacue_metal.device(torch) == "mps":

        device = "mps"

        device_label = "Apple Silicon Metal (MPS)"

    else:

        device = "cpu"

        device_label = f"CPU ({torch.get_num_threads()} threads)"



    print(f"  python {sys.version.split()[0]} | numpy {numpy.__version__} | torch {torch.__version__} | "

          f"torchaudio {torchaudio.__version__} | demucs {demucs.__version__} | {device_label}")



    x = torch.randn(1, 2, 44100 * seconds) * 0.1

    # Sur GPU : tester htdemucs_6s, htdemucs_ft (haute fidélité) et htdemucs

    # Sur CPU : tester htdemucs et htdemucs_6s pour ne pas allonger inutilement l'installation

    models_to_check = ("htdemucs", "htdemucs_6s", "htdemucs_ft") if device != "cpu" else ("htdemucs", "htdemucs_6s")



    for name in models_to_check:

        t0 = time.time()

        m = get_model(name)

        m.eval()

        ft_tag = " (fine-tuned HQ)" if name == "htdemucs_ft" else ""

        print(t(f"  modèle {name}{ft_tag} prêt ({time.time() - t0:.0f} s) : {', '.join(m.sources)}",

                f"  model {name}{ft_tag} ready ({time.time() - t0:.0f} s): {', '.join(m.sources)}"))

        t0 = time.time()

        try:
            with torch.no_grad():
                apply_model(m, x, shifts=1, split=True, overlap=0.25, progress=False, device=device)
            if device == "mps":
                torch.mps.synchronize()
        except (RuntimeError, NotImplementedError, TypeError) as error:
            if device != "mps":
                raise
            m.to("cpu")
            reacue_metal.cpu_fallback(error)
            device = "cpu"
            t0 = time.time()
            with torch.no_grad():
                apply_model(m, x, shifts=1, split=True, overlap=0.25, progress=False, device=device)

        per_song_m = (time.time() - t0) / seconds * 240 / 60

        if per_song_m < 0.5:

            speed_str = t(f"environ {round(per_song_m * 60)} s", f"about {round(per_song_m * 60)} s")

        else:

            speed_str = t(f"environ {per_song_m:.1f} min", f"about {per_song_m:.1f} min")

        print(t(f"  vitesse {name} [{device.upper()}] : {speed_str} pour un morceau de 4 min",

                f"  speed {name} [{device.upper()}]: {speed_str} for a 4-minute song"))

    print("STEMS_OK")

    return 0





def main(argv=None) -> int:

    ap = argparse.ArgumentParser(prog="reacue_stems")

    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("separate")

    s.add_argument("--input", required=True)

    s.add_argument("--out", required=True)

    s.add_argument("--model", default=DEFAULT_MODEL)

    s.add_argument("--repo", help="dossier de modèles locaux (hors ligne) / local models folder (offline)")

    s.add_argument("--resource-dir")
    s.add_argument("--origin-project", default="")
    s.add_argument("--job-id")

    c = sub.add_parser("check")

    c.add_argument("--lang", default="fr", choices=["fr", "en"])

    c.add_argument("--seconds", type=int, default=10)

    a = ap.parse_args(argv)

    if a.cmd == "separate":

        if not a.resource_dir:
            return separate(a.input, a.out, a.model, a.repo)
        from reacue_mcp.jobs import Job, WorkerLease
        from reacue_mcp import show_lock
        global _JOB
        directory = Path(a.resource_dir) / "ReaCueMCP"
        _JOB = Job(directory, "stems", job_id=a.job_id, project=a.origin_project,
                   input=str(a.input), model=a.model, status_file=str(Path(a.out) / "demucs_status.json"))
        lease = WorkerLease(directory)
        code = 1
        try:
            if show_lock.locked(directory):
                raise RuntimeError(show_lock.message())
            if not lease.acquire():
                raise RuntimeError("Un traitement est déjà en cours. Attends sa fin.")
            code = separate(a.input, a.out, a.model, a.repo)
            return code
        except Exception as exc:
            _JOB.update("error", message=str(exc))
            if lease.file is not None:
                Path(a.out).mkdir(parents=True, exist_ok=True)
                _write_status(Path(a.out) / "demucs_status.json", "error", model=a.model, input=a.input, message=str(exc))
            return 1
        finally:
            _JOB.update("done" if code == 0 else "error")
            _JOB = None
            lease.release()

    return check(a.lang, a.seconds)





if __name__ == "__main__":

    sys.exit(main())

