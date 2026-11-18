"""Reuse local model outputs, never project edits or grid-dependent sections."""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def model_signature(engine,kind):
    engine=Path(engine)
    if kind=='structure':
        files=[p for p in (engine/'structure').rglob('*')
               if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts
               and p.suffix not in ('.pyc','.lock')]
        code=engine/'reacue_structure.py'
        packages=('torch','numpy','librosa','transformers','muq')
    elif kind=='intro':
        files=[]
        code=Path(__file__).with_name('musical_timing.py')
        packages=('numpy','soundfile')
    elif kind=='grid':
        files=[]
        code=Path(__file__).with_name('worker.py')
        packages=('librosa','numpy','soundfile')
    else:
        files=[engine/'rhythm/final0.ckpt']
        code=Path(__file__).with_name('advanced.py')
        packages=('torch','torchaudio','numpy','soundfile','beat-this')
    # Unix ctime tracks changes, but Windows ctime is the creation time.
    # Hash Windows models too: an in-place replacement can keep all three
    # metadata values unchanged. Unix avoids rescanning large checkpoints.
    stamps=[]
    for path in sorted(files):
        stat=path.stat()
        stamp=(str(path.relative_to(engine)),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        if os.name=='nt':stamp+= (digest(path),)
        stamps.append(stamp)
    versions={}
    for name in packages:
        try:versions[name]=metadata.version(name)
        except metadata.PackageNotFoundError:pass
    signature=dict(files=stamps,code=digest(code),packages=versions)
    if kind=='rhythm':
        # Calibration weights and bar voting change interpretation of raw logits.
        # Never reuse confidence from a different fitted model.
        signature['calibration']={name:digest(code.with_name(name)) if code.with_name(name).is_file() else None
                                  for name in ('services.py','rhythm_quality.py','rhythm-quality.json','rhythm_adapter.py','rhythm-adapter.json')}
    return signature


class AnalysisCache:
    def __init__(self,root,kind,key,inputs):
        self.folder=Path(root)/'Cache/models'/kind/key
        self.key=key
        self.inputs=inputs

    @classmethod
    def create(cls,project,kind,audio,engine,options=None,extra_audio=()):
        if not project or not project.get('_root'):return None
        try:
            inputs=[(Path(p),digest(p)) for p in (audio,*extra_audio)]
            payload=dict(schema=2,kind=kind,audio=[value for _,value in inputs],
                         model=model_signature(engine,kind),options=options or {})
            key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            return cls(project['_root'],kind,key,inputs)
        except OSError:
            # A cache failure must not prevent an otherwise usable analysis.
            return None

    def load(self,evidence_path=None):
        try:
            record=json.loads((self.folder/'result.json').read_text())
            payload=record['payload']
            if record['key']!=self.key or hashlib.sha256(payload.encode()).hexdigest()!=record['checksum']:return None
            value=json.loads(payload)
            if not isinstance(value,dict):return None
            if record.get('evidence'):
                source=self.folder/'evidence.npz'
                if digest(source)!=record['evidence']:return None
                if evidence_path is not None:
                    Path(evidence_path).parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,evidence_path)
            return value
        except (OSError,ValueError,KeyError,TypeError):return None

    def store(self,value,evidence_path=None):
        staging=None
        try:
            # Refuse to associate an output with audio edited during inference.
            if any(digest(path)!=expected for path,expected in self.inputs):return
            self.folder.parent.mkdir(parents=True,exist_ok=True)
            staging=self.folder.with_name('.'+self.key+'-'+uuid.uuid4().hex)
            staging.mkdir()
            payload=json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True)
            record=dict(key=self.key,payload=payload,checksum=hashlib.sha256(payload.encode()).hexdigest())
            if evidence_path is not None and Path(evidence_path).is_file():
                shutil.copy2(evidence_path,staging/'evidence.npz')
                record['evidence']=digest(staging/'evidence.npz')
            (staging/'result.json').write_text(json.dumps(record))
            # Replace only this disposable cache entry; publish the manifest last.
            self.folder.mkdir(exist_ok=True)
            if 'evidence' in record:os.replace(staging/'evidence.npz',self.folder/'evidence.npz')
            os.replace(staging/'result.json',self.folder/'result.json')
        except (OSError,ValueError):pass
        finally:
            if staging is not None:shutil.rmtree(staging,ignore_errors=True)


def runtime_caches(engine,fallback):
    """Keep compilation/font caches between jobs and between different songs."""
    root=Path(engine)/'worker-cache'
    try:
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=root):pass
    except OSError:root=Path(fallback)
    os.environ['NUMBA_CACHE_DIR']=str(root/'numba')
    os.environ['MPLCONFIGDIR']=str(root/'matplotlib')
