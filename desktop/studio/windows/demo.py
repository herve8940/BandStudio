"""Create a synthetic demonstration, never package the developer's music."""
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
from windows import project as model


def create(root):
    root=Path(root);(root/'Audio').mkdir(parents=True,exist_ok=True);sr=44100;duration=16;t=np.arange(sr*duration)/sr
    drums=np.zeros(len(t));rng=np.random.default_rng(42)
    for beat in range(32):
        at=int(beat*.5*sr);d=np.arange(int(.15*sr))/sr
        hit=.24*np.sin(2*np.pi*(55*d+2*(1-np.exp(-d*35))))*np.exp(-d*25) if beat%2==0 else .12*rng.standard_normal(len(d))*np.exp(-d*40)
        drums[at:at+len(hit)]+=hit
        for sub in range(2):
            start=at+int(sub*.25*sr);n=int(.04*sr);drums[start:start+n]+=.035*rng.standard_normal(n)*np.exp(-np.arange(n)/sr*100)
    bass=.08*np.sin(2*np.pi*110*t)*(.5+.5*np.exp(-(t%.5)*8));other=.035*np.sin(2*np.pi*330*t)+.025*np.sin(2*np.pi*440*t)
    p=model.fresh('Découverte de BandStudio');p['bpm']=120;p['settings'].update(gridMode='fixed',manualBPM=120,voice='Système');p['beats']=np.arange(0,duration,.5).tolist()
    for role,name,x in [('source','Original',drums+bass+other),('drums','Batterie',drums),('bass','Basse',bass),('other','Accompagnement',other)]:
        path=root/'Audio'/(role+'.wav');sf.write(path,np.column_stack((x,x)).astype('float32'),sr,subtype='FLOAT');p['tracks'].append(model.track(path,root,name,role))
    for i,name in enumerate(['Intro','Couplet','Refrain','Final']):p['sections'].append(dict(id=model.ident(),name=name,start=i*4,end=(i+1)*4,locked=True,origin='manual'))
    p['notes']='Démonstration synthétique : les pistes sont créées séparément pour tester les commandes. Ce n’est pas une séparation IA.'
    model.save(p,root)

if __name__=='__main__':create(sys.argv[1])
