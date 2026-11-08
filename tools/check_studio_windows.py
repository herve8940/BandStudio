#!/usr/bin/env python3
"""Test the actual ZIP after relocation; never open audio devices or user projects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def check(archive,report):
    archive=archive.resolve();report=report.resolve();report.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==archive.with_suffix('.zip.sha256').read_text().split()[0]
    with tempfile.TemporaryDirectory(prefix='BandStudio relocated é ') as temp:
        root=Path(temp)
        with zipfile.ZipFile(archive) as z:
            assert all((root/name).resolve().is_relative_to(root) for name in z.namelist())
            z.extractall(root)
        package=root/'BandStudio-DEV';engine=package/'engine';python=engine/'python/python.exe';launcher=engine/'windows/launcher.py'
        assert (package/'BandStudio.exe').is_file()
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',PYTHONPATH='',LOCALAPPDATA=str(root/'LocalAppData'))
        for flag,target,timeout in [('--smoke',root/'Test technique',180),('--gui-smoke',report/'interface.json',120)]:
            result=subprocess.run([str(python),str(launcher),flag,str(target)],cwd=root,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=timeout)
            print(result.stdout);print(result.stderr)
            (report/(flag[2:]+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode:raise RuntimeError(flag+' failed: '+str(result.returncode))
        smoke=json.loads((root/'Test technique/smoke-result.json').read_text())
        gui=json.loads((report/'interface.json').read_text())
        assert smoke['passed'] and gui['ready'] and gui['bridge']=='function'
        (report/'audio.json').write_text(json.dumps(smoke,indent=2),encoding='utf-8')
        print('Relocated runtime, real Windows speech, audio rendering, REAPER roundtrip and WebView2 passed.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.archive,a.report)
