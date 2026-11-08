"""Install the explicitly chosen local model, with pinned checkpoint hashes."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
from setup_studio_rhythm import setup as rhythm

DRUM_SHA256='aefaa8543c9b9c75e22f5f32b53ab86dfe416457849af1383ff1aef83401423f'


def drums(engine):
    import gdown
    folder=Path(engine)/'drumsep';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'49469ca8.th'
    if not target.exists():
        temporary=folder/'49469ca8.th.part'
        try:
            if not gdown.download(id='1-Dm666ScPkg8Gt2-lK3Ua0xOudWHZBGC',output=str(temporary),quiet=False):raise ValueError('Téléchargement DrumSep impossible.')
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=DRUM_SHA256:raise ValueError('Empreinte DrumSep différente de la version validée.')
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=DRUM_SHA256:raise ValueError('Modèle DrumSep modifié ou incomplet.')
    with urllib.request.urlopen('https://raw.githubusercontent.com/inagoy/drumsep/main/LICENSE',timeout=60) as response:
        (folder/'LICENSE').write_bytes(response.read())
    print('DrumSep prêt : grosse caisse, caisse claire, toms, cymbales et charleston regroupés.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('engine');p.add_argument('component',choices=['rhythm','drumsep']);a=p.parse_args()
    (rhythm if a.component=='rhythm' else drums)(a.engine)
