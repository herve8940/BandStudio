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
        root=Path(temp).resolve()
        with zipfile.ZipFile(archive) as z:
            invalid=[name for name in z.namelist() if not (root/name).resolve().is_relative_to(root)]
            assert not invalid,invalid[:3]
            z.extractall(root)
        package=root/'BandStudio-DEV';engine=package/'engine';python=engine/'python/python.exe';launcher=engine/'windows/launcher.py'
        assert (package/'BandStudio.exe').is_file()
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',PYTHONPATH='',LOCALAPPDATA=str(root/'LocalAppData'))
        # Python's ZIP extractor does not propagate Explorer's Mark of the Web.
        # Explicitly reproduce a browser download on NTFS, including .NET DLLs.
        inventory=json.loads((engine/'python/runtime-libraries.json').read_text(encoding='utf-8'))
        marked=[engine/'python'/item['path'] for item in inventory['libraries']]
        zone=b'[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://github.com/herve8940/BandStudio/\r\n'
        for path in marked:Path(str(path)+':Zone.Identifier').write_bytes(zone)
        unrelated=package/'unlisted.dll';unrelated.write_bytes(b'User file: never unblock')
        unrelated_stream=Path(str(unrelated)+':Zone.Identifier');unrelated_stream.write_bytes(zone)
        baseline=subprocess.run([str(python),'-c','import clr'],cwd=root,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=60)
        (report/'blocked-clr.log').write_text(baseline.stdout+'\n'+baseline.stderr,encoding='utf-8')
        assert baseline.returncode!=0 and 'Failed to resolve Python.Runtime.Loader.Initialize' in baseline.stderr, 'The downloaded-DLL regression was not reproduced'
        print('Reproduced the reported Python.Runtime.Loader.Initialize failure with ZoneId=3.')
        for flag,target,timeout in [('--gui-smoke',report/'interface.json',120),('--smoke',root/'Test technique',180),('--gui-smoke',report/'interface-restart.json',120)]:
            result=subprocess.run([str(python),str(launcher),flag,str(target)],cwd=root,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=timeout)
            print(result.stdout);print(result.stderr)
            logname=target.stem if flag=='--gui-smoke' else flag[2:]
            (report/(logname+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode:raise RuntimeError(flag+' failed: '+str(result.returncode))
        smoke=json.loads((root/'Test technique/smoke-result.json').read_text())
        gui=json.loads((report/'interface.json').read_text())
        restart=json.loads((report/'interface-restart.json').read_text())
        assert smoke['passed'] and gui['ready'] and gui['bridge']=='function' and restart['ready']
        assert not any(Path(str(path)+':Zone.Identifier').exists() for path in marked)
        assert unrelated_stream.read_bytes()==zone, 'An unrelated file was unblocked'
        (report/'downloaded-runtime.json').write_text(json.dumps({'reproduced':True,'libraries':len(marked),'gui_ready':gui['ready'],'restart_ready':restart['ready'],'unrelated_file_unchanged':True},indent=2),encoding='utf-8')
        (report/'audio.json').write_text(json.dumps(smoke,indent=2),encoding='utf-8')
        print('Downloaded DLL repair, two WebView2 launches, relocated runtime, Windows speech, audio rendering and REAPER roundtrip passed.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.archive,a.report)
