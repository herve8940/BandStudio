"""Owner-local, opt-in BandPilot command mailbox, separate from the REAPER bridge."""
import json
import os
from pathlib import Path
import time
import uuid
from services import atomic
from windows import recording,project as model

class Bridge:
    def __init__(self,folder=None):
        base=Path(os.environ.get('APPDATA',Path.home()/'AppData/Roaming'))
        self.folder=Path(folder) if folder else base/'BandStudio/Bridge';self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.owner=(self.folder/'owner.lock').open('a+b');self.owner.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                if not self.owner.read(1):self.owner.write(b'0');self.owner.flush()
                self.owner.seek(0);msvcrt.locking(self.owner.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.owner.close();raise ValueError('Une autre fenêtre BandStudio utilise la connexion BandPilot.')
        self.session=str(uuid.uuid4());self.processed=set();self.pulse=0
        for prefix in ('request-','response-'):
            for file in self.folder.glob(prefix+'*.json'):file.unlink()
    def state(self,host):
        a=host._audio;p=host._project;c=recording.state(host)
        return dict(version=1,session=self.session,updated=time.time(),projectID=p['id'],name=p['name'],loaded=host._root is not None,duration=model.duration(p),position=c['elapsed'] if host._record and c['settings']['mode']=='live' else a.position,playing=a.running,recording=bool(host._record),pending=False,busy=host._busy,notice=host._notice,rate=a.rate,pitch=a.pitch,loop=a.loop,loopStart=a.loopStart,loopEnd=a.loopEnd,capture=c,sections=p['sections'],cues=p['cues'])
    def update(self,host):
        now=time.time()
        if now-self.pulse>.25:atomic(self.folder/'state.json',self.state(host));self.pulse=now
        for file in self.folder.glob('response-*.json'):
            if now-file.stat().st_mtime>60:file.unlink(missing_ok=True)
        for file in list(self.folder.glob('request-*.json'))[:8]:
            ident=file.stem.removeprefix('request-')
            try:uuid.UUID(ident)
            except ValueError:continue
            try:
                if file.is_symlink() or file.stat().st_size>100000:raise ValueError('Requête invalide.')
                data=json.loads(file.read_text(encoding='utf-8'));file.unlink()
                if ident in self.processed:raise ValueError('Commande déjà traitée.')
                if len(self.processed)>=10000:raise ValueError('Reconnecte BandPilot pour une nouvelle session.')
                self.processed.add(ident)
                if data.get('id')!=ident or data.get('session')!=self.session or data.get('projectID')!=host._project['id'] or abs(now-float(data.get('created',0)))>=10:raise ValueError('Connexion expirée ou projet changé. Actualise BandPilot.')
                recording.command(host,data['args']);result=dict(ok=True,state=self.state(host));host._state()
            except Exception as error:result=dict(ok=False,error=str(error))
            file.unlink(missing_ok=True);atomic(self.folder/('response-'+ident+'.json'),result)
    def close(self):
        (self.folder/'state.json').unlink(missing_ok=True);self.owner.close()
