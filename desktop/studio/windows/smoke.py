"""Exercise the shipped runtime without speakers, microphone, accounts or user songs."""
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
from windows import project as model
from windows.audio import Audio
from services import guides,export_reaper,import_reaper,atomic


def smoke(engine,root):
    engine=Path(engine);root=Path(root).resolve();(root/'Audio').mkdir(parents=True,exist_ok=True)
    p=model.fresh('Essai technique BandStudio');p['settings'].update(gridMode='fixed',manualBPM=120,countBars=1,voice='Système',language='en',callsEnabled=True,clickEnabled=True)
    t=np.arange(6*44100)/44100
    for role,hz in [('source',440),('drums',880),('bass',220)]:
        path=root/'Audio'/(role+'.wav');x=(.1*np.sin(t*2*np.pi*hz)).astype('float32');sf.write(path,np.column_stack((x,x)),44100,subtype='FLOAT');p['tracks'].append(model.track(path,root,role,role))
    p['sections']=[dict(id='intro',name='Intro',start=0,end=4,locked=True,origin='manual'),dict(id='chorus',name='Chorus',start=4,end=6,locked=True,origin='manual')]
    snapshot=root/'snapshot.json';atomic(snapshot,{**p,'_root':str(root)});folder=root/'Guides';folder.mkdir(exist_ok=True)
    guides(snapshot,folder/'result.json');result=json.loads((folder/'result.json').read_text());p['guideFiles']={k:Path(v).relative_to(root).as_posix() for k,v in result['files'].items()}
    for key,role in [('click','guide_click'),('calls','guide_voice'),('counts','guide_count')]:p['tracks'].append(model.track(root/p['guideFiles'][key],root,key,role))
    p['guideKey']=model.guide_key(p);model.save(p,root);loaded=model.load(root);a=Audio(engine);a.load(loaded,root);a.mode='minus'
    a.render(root/'mix.wav',0,6,True);x,sr=sf.read(root/'mix.wav');assert sr==44100 and len(x)==8*44100 and np.max(abs(x[:2*sr]))>.05
    a.pitch=12;a.prepare();a.render(root/'transposed.wav',0,6,True);y,_=sf.read(root/'transposed.wav');assert np.max(abs(x[:2*sr]-y[:2*sr]))<1e-5
    a.close();atomic(snapshot,{**p,'_root':str(root),'_mode':'minus'});export_reaper(snapshot,root/'rpp.json');rpp=Path(json.loads((root/'rpp.json').read_text())['path']);import_reaper(rpp,root/'import/result.json',engine,snapshot)
    restored=model.load(Path(json.loads((root/'import/result.json').read_text())['project']));assert restored['sections'][0]['start']==2
    assert restored['tracks'][0]['offset']==2
    from windows.host import Api
    host=Api(engine,root/'TemporaryLibrary');p['guideKey']='';model.save(p,root);host._load(root)
    assert host._ready_guides();host._audio.close()
    report=dict(host_guides=True,passed=True,python=sys.version.split()[0],frames=len(x),voice_peak=float(np.max(abs(x[:2*sr]))),voice_pitch_difference=float(np.max(abs(x[:2*sr]-y[:2*sr]))),reaper_regions=len(restored['sections']))
    atomic(root/'smoke-result.json',report);print(json.dumps(report))
