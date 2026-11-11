import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
from platform_tools import python_for,creation_flags
from services import atomic


class PhoneSession:
    def __init__(self,engine):
        self.folder=Path(tempfile.mkdtemp(prefix='bandstudio-phone-'));self.revision=-1;self.announced=False;self.pulse=0
        self.process=subprocess.Popen([str(python_for(engine)),str(Path(engine)/'phone.py'),'--folder',str(self.folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=creation_flags())
    def close(self):
        if self.process.poll() is None:self.process.terminate()
    def update(self,host):
        if self.process.poll() is not None:
            host._phone=None;host._send(dict(type='phone',active=False,error='Le prompteur réseau s’est arrêté.'));return
        if time.monotonic()-self.pulse<.25:return
        self.pulse=time.monotonic()
        if self.revision!=host._revision:
            keys=['name','sections','lyrics','chords','beats','bpm','settings','key','capo']
            atomic(self.folder/'project.json',{k:copy.deepcopy(host._project[k]) for k in keys});self.revision=host._revision
        a=host._audio;atomic(self.folder/'transport.json',dict(position=a.position,playing=a.running,rate=a.rate,pitch=a.pitch,countRemaining=a.remaining() if a.project else 0))
        if not self.announced and (self.folder/'info.json').is_file():
            host._send(dict(type='phone',active=True,**json.loads((self.folder/'info.json').read_text())));self.announced=True
