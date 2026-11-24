"""Offline creative engines: MusicGen Small and a fixed UVR MDX vocal model.

MDX spectrum layout follows python-audio-separator (MIT, karaokenerds 2023).
Model weights retain their own licenses; see THIRD_PARTY_NOTICES.
"""
from ui_language import ui_text, using_english
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
import soundfile as sf
from advanced import finite
from services import atomic

KARAOKE_SHA='bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4'

def split_vocals(audio, folder, engine):
    import torch
    import onnxruntime as ort
    from analysis_progress import phase_items
    model=Path(engine)/'creative/UVR_MDXNET_KARA_2.onnx'
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest()!=KARAOKE_SHA:raise ValueError(ui_text('Modèle vocal absent ou empreinte incorrecte. Installe les outils créatifs locaux.', 'Vocal model missing or checksum incorrect. Install the local creative tools.'))
    info=sf.info(audio)
    if info.duration>900:raise ValueError(ui_text('La séparation chant/chœurs accepte des extraits de 15 minutes au maximum.', 'Lead and backing vocal separation supports clips up to 15 minutes.'))
    wave,sr=sf.read(audio,dtype='float32',always_2d=True)
    if wave.shape[1]==1:wave=np.repeat(wave,2,axis=1)
    if wave.shape[1]!=2:raise ValueError(ui_text('Une piste de chant mono ou stéréo est attendue.', 'Choose a mono or stereo vocal track.'))
    if sr!=44100:
        import torchaudio
        wave=torchaudio.functional.resample(torch.from_numpy(wave.T.copy()),sr,44100).numpy().T
    torch.set_num_threads(4)
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider'])
    n_fft,hop,bins,frames=5120,1024,2048,256;chunk=hop*(frames-1);trim=n_fft//2;step=chunk//2
    mix=np.pad(wave.T,((0,0),(trim,chunk)));result=np.zeros_like(mix);weight=np.zeros(mix.shape[1],np.float32)
    window=torch.hann_window(n_fft);fade=np.hanning(chunk).astype(np.float32);input_name=session.get_inputs()[0].name
    with torch.inference_mode():
        for start in phase_items(range(0,len(wave)+trim,step),0,1,ui_text("Séparation chant et chœurs", 'Separating lead and backing vocals')):
            block=np.zeros((2,chunk),np.float32);n=min(chunk,mix.shape[1]-start);block[:,:n]=mix[:,start:start+n]
            spectrum=torch.stft(torch.from_numpy(block),n_fft,hop_length=hop,window=window,center=True,return_complex=True)
            features=torch.view_as_real(spectrum).permute(0,3,1,2).reshape(1,4,n_fft//2+1,frames)[:,:,:bins,:].contiguous().numpy()
            features[:,:,:3,:]=0
            predicted=session.run(None,{input_name:features})[0]
            full=np.pad(predicted,((0,0),(0,0),(0,n_fft//2+1-bins),(0,0)))
            pairs=torch.from_numpy(full.reshape(2,2,n_fft//2+1,frames)).permute(0,2,3,1).contiguous()
            output=torch.istft(torch.view_as_complex(pairs),n_fft,hop_length=hop,window=window,center=True,length=chunk).numpy()
            result[:,start:start+n]+=output[:,:n]*fade[:n];weight[start:start+n]+=fade[:n]
            print((f'Lead/backing vocal separation: {min(100, round((start + step) / (len(wave) + trim) * 100))} %' if using_english() else f'Séparation chant/chœurs : {min(100,round((start+step)/(len(wave)+trim)*100))} %'),flush=True)
    backing=(result/np.maximum(weight,1e-8))[:,trim:trim+len(wave)].T*1.065
    lead=wave-backing
    tracks=[]
    for role,data in [('vocal_lead',lead),('vocal_backing',backing)]:
        path=Path(folder)/(role+'.wav');sf.write(path,data,44100,subtype='FLOAT');tracks.append(dict(role=role,path=str(path)))
    return dict(tracks=tracks,model='UVR_MDXNET_KARA_2',note=ui_text('Chant principal et chœurs proposés. Les fuites et erreurs restent possibles ; la somme reconstitue la piste de chant source.', 'Lead and backing vocals are ready to review. Some bleed is possible. Mixing the two tracks recreates the source vocal.'))

def generate(folder,engine,options):
    import torch
    from transformers import AutoProcessor,MusicgenForConditionalGeneration
    prompt=str(options.get('prompt','')).strip()
    if not prompt or len(prompt)>600:raise ValueError(ui_text('Décris un accompagnement en 600 caractères au maximum.', 'Describe an accompaniment in 600 characters or fewer.'))
    duration=finite(options.get('duration',8),2,20);seed=int(finite(options.get('seed',42),0,2147483647))
    model_path=Path(engine)/'creative/musicgen-small'
    if not (model_path/'model.safetensors').is_file():raise ValueError(ui_text('MusicGen Small n’est pas installé dans les outils créatifs locaux.', 'MusicGen Small is not installed in the local creative tools.'))
    print(ui_text('Chargement de MusicGen Small en local…', 'Loading MusicGen Small locally…'),flush=True);started=time.monotonic()
    torch.set_num_threads(4);torch.manual_seed(seed)
    processor=AutoProcessor.from_pretrained(str(model_path),local_files_only=True)
    model=MusicgenForConditionalGeneration.from_pretrained(str(model_path),local_files_only=True,use_safetensors=True,attn_implementation='eager').eval()
    inputs=processor(text=[prompt],padding=True,return_tensors='pt')
    print((f'Generating {duration:g} seconds. This can take several minutes on a CPU…' if using_english() else f'Création de {duration:g} secondes. Le calcul sur processeur peut prendre plusieurs minutes…'),flush=True)
    with torch.inference_mode():audio=model.generate(**inputs,do_sample=True,guidance_scale=3,max_new_tokens=round(duration*50)+3)
    rate=model.config.audio_encoder.sampling_rate
    data=audio[0].cpu().numpy().T[:round(duration*rate)]
    target=Path(folder)/'accompagnement-genere.wav';sf.write(target,data,rate,subtype='PCM_24')
    metadata=dict(prompt=prompt,seed=seed,duration=len(data)/rate,model='facebook/musicgen-small',revision='4c8334b02c6ec4e8664a91979669a501ec497792',secondsToGenerate=time.monotonic()-started,license='CC-BY-NC-4.0',note=ui_text('Création instrumentale expérimentale ; tempo et structure non garantis. Ce modèle ne génère pas un chant intelligible.', 'Experimental instrumental generation. Check the tempo and structure. This model does not generate intelligible singing.'))
    atomic(Path(folder)/'generation.json',metadata)
    return dict(tracks=[dict(role='take',path=str(target))],generation=metadata)

def run(kind,audio,output,engine,options):
    folder=Path(output).parent
    result=generate(folder,engine,options) if kind=='generate' else split_vocals(audio,folder,engine)
    atomic(output,result)
