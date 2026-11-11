"""Install fixed public models. Personal audio never leaves this computer."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request
REVISION='4c8334b02c6ec4e8664a91979669a501ec497792'
KARAOKE_SHA='bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4'

def setup(engine):
    from huggingface_hub import snapshot_download
    folder=Path(engine)/'creative';folder.mkdir(parents=True,exist_ok=True)
    print('MusicGen Small : modèle CC-BY-NC 4.0, usage non commercial. Calcul local après téléchargement.',flush=True)
    snapshot_download('facebook/musicgen-small',revision=REVISION,local_dir=folder/'musicgen-small',allow_patterns=['config.json','generation_config.json','model.safetensors','preprocessor_config.json','special_tokens_map.json','spiece.model','tokenizer.json','tokenizer_config.json','README.md'])
    target=folder/'UVR_MDXNET_KARA_2.onnx'
    if not target.is_file():
        part=target.with_suffix('.part')
        try:
            with urllib.request.urlopen('https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx',timeout=120) as response,part.open('wb') as f:shutil.copyfileobj(response,f)
            if hashlib.sha256(part.read_bytes()).hexdigest()!=KARAOKE_SHA:raise ValueError('Modèle vocal incomplet ou modifié.')
            part.replace(target)
        finally:part.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=KARAOKE_SHA:raise ValueError('Empreinte du modèle vocal incorrecte.')
    (folder/'musicgen-revision.txt').write_text(REVISION+'\n')
    print('Modèles locaux prêts.',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('engine');setup(p.parse_args().engine)
