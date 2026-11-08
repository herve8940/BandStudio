"""Download the MIT-licensed Beat This checkpoint; all inference stays offline."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request

URL='https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt'
SHA256='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'


def setup(engine):
    folder=Path(engine)/'rhythm';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'final0.ckpt'
    if not target.exists():
        temp=folder/'final0.ckpt.part'
        try:
            with urllib.request.urlopen(URL,timeout=120) as response,temp.open('wb') as out:
                shutil.copyfileobj(response,out)
            if hashlib.sha256(temp.read_bytes()).hexdigest()!=SHA256:raise ValueError('L’empreinte du modèle Beat This ne correspond pas à la version validée.')
            temp.replace(target)
        finally:temp.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=SHA256:raise ValueError('Modèle Beat This modifié ou incomplet.')
    with urllib.request.urlopen('https://raw.githubusercontent.com/CPJKU/beat_this/v1.1.0/LICENSE',timeout=60) as response:
        (folder/'LICENSE').write_bytes(response.read())
    print('Beat This final0',target.stat().st_size,'bytes',hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('engine');setup(p.parse_args().engine)
