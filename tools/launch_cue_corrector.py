"""Launch the supervised corrector as a persistent, low-priority local job."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def launch(manifest, analysis, output, resume=False):
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record_path = output / 'launch.json'
        if record_path.exists():
            previous = json.loads(record_path.read_text())
            try:
                os.kill(previous['pid'], 0)
            except ProcessLookupError:
                if not resume:
                    raise RuntimeError('Previous job exited; inspect status then use --resume')
            else:
                raise RuntimeError('Job is already running: ' + str(previous['pid']))
        command = [sys.executable, str(Path(__file__).with_name('train_cue_corrector.py')),
                   '--manifest', str(manifest), '--analysis', str(analysis), '--output', str(output), '--wait-for-analysis']
        environment = dict(os.environ, PYTHONUNBUFFERED='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2')
        with (output / 'run.log').open('a') as log:
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=environment,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        helper = None
        if sys.platform == 'darwin':
            try:
                helper = subprocess.Popen(['/usr/bin/caffeinate', '-s', '-t', '172800', '-w', str(process.pid)],
                                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          start_new_session=True)
            except OSError:
                pass
        record = dict(pid=process.pid, started=time.time(), command=command,
                      sleepPreventionPID=helper.pid if helper else None, sleepPreventionMaximumSeconds=172800,
                      threads=2, niceIncrement=10, automaticTrainingAfterSuccessfulAnalysis=True,
                      modelInstallation=False, stopFile=str(output / 'STOP'))
        if record_path.exists():
            (output / ('launch-previous-' + str(int(time.time())) + '.json')).write_text(record_path.read_text())
        temporary = output / 'launch.json.tmp'
        temporary.write_text(json.dumps(record, indent=2)); temporary.replace(record_path)
        print(json.dumps(record, ensure_ascii=False))
        return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    launch(args.manifest.resolve(), args.analysis.resolve(), args.output.resolve(), args.resume)
