#!/usr/bin/env python3
"""Windows regression: reproduce NumPy/soxr ABI failure, run the actual repair installer.

Only model downloads are replaced with a no-op: this test checks binary imports,
resampling and CPU inference, not the quality of trained models or physical CUDA.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def check(report):
    if sys.platform!='win32':raise SystemExit('This integration check requires Windows PowerShell.')
    report=report.resolve();report.mkdir(parents=True,exist_ok=True)
    uv=shutil.which('uv');assert uv
    with tempfile.TemporaryDirectory(prefix='BandStudio analyse é ') as temp:
        engine=Path(temp)/'engine';(engine/'windows').mkdir(parents=True);(engine/'tools').mkdir()
        python=engine/'.venv-demucs/Scripts/python.exe'
        def run(args,*,success=True,timeout=600):
            result=subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,env={**os.environ,'PYTHONUTF8':'1'})
            with (report/'analysis-install.log').open('a',encoding='utf-8') as log:log.write(result.stdout+'\n'+result.stderr+'\n')
            if success and result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            return result
        run([uv,'venv',engine/'.venv-demucs','--python',sys.executable])
        run([uv,'pip','install','--python',python,'torch==2.5.1','torchaudio==2.5.1','--index-url','https://download.pytorch.org/whl/cpu'])
        run([uv,'pip','install','--python',python,'numpy==2.2.6','soxr==0.3.7'])
        broken=run([python,'-c','import soxr'],success=False)
        assert broken.returncode and 'numpy.core.multiarray failed to import' in broken.stderr,broken.stderr
        print('Reproduced numpy.core.multiarray failed to import with NumPy 2 and soxr 0.3.7.',flush=True)
        shutil.copy2(uv,engine/'tools/uv.exe')
        source=ROOT/'desktop/studio/windows/install_extra.ps1'
        (engine/'windows/install_extra.ps1').write_text(source.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
        (engine/'tools/setup_studio_models.py').write_text("print('Model download excluded from dependency regression')\n")
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',engine/'windows/install_extra.ps1','-Component','rhythm'])
        run([uv,'pip','install','--python',python,'-r',ROOT/'requirements-stems.txt'])
        probe=run([python,'-c', '''
import json,numpy as np,soxr,torch,torchaudio
from beat_this.inference import Audio2Beats
from demucs.demucs import Demucs
from demucs.apply import apply_model
torch.set_num_threads(2)
x=np.zeros(22050,dtype=np.float32)
assert len(soxr.resample(x,22050,44100))==44100
net=Demucs(sources=['one','two'],channels=4,depth=2,dconv_mode=0,lstm_layers=0,resample=False)
with torch.inference_mode():y=apply_model(net,torch.zeros(1,2,4410),device='cpu',shifts=0,split=False)
assert y.shape==(1,2,2,4410) and torch.isfinite(y).all()
assert np.__version__=='1.26.4' and torch.__version__.startswith('2.5.1')
print(json.dumps(dict(numpy=np.__version__,torch=torch.__version__,soxr=soxr.__version__,beat_this_import=True,demucs_cpu_inference=True)))
'''])
        result=json.loads(probe.stdout.strip().splitlines()[-1]);result['abi_error_reproduced']=True
        (report/'analysis-dependencies.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('Actual rhythm installer repaired NumPy; Beat This imports, soxr resamples and Demucs CPU inference passes.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.report)
