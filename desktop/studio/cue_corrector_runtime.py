"""Explicitly approved cue correctors for fresh SongFormer analyses.

The approval bundle binds the model, implementation, SongFormer weights and
analysis window. Missing, unapproved or incompatible bundles leave proposals
unchanged. Raw SongFormer caches never contain corrected sections.
"""
from __future__ import annotations
import copy
import ast
import hashlib
import json
from pathlib import Path
import uuid


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(2**20),b''):h.update(block)
    return h.hexdigest()


def stamp(path):
    stat=Path(path).stat()
    return dict(size=stat.st_size,mtime=stat.st_mtime_ns,ctime=stat.st_ctime_ns)


def load_portable(engine, window):
    """Read literal release data without executing it; verify relocated weights.

    The .py data container also travels through older code-only updaters. Local
    timestamps are only a cache key, never part of the portable approval.
    """
    tree=ast.parse((engine/'cue_corrector_bundle.py').read_text(encoding='utf-8'))
    assignments=[n for n in tree.body if isinstance(n,ast.Assign) and
                 len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='BUNDLE']
    if len(assignments)!=1:return None,'invalid-release-bundle'
    bundle=ast.literal_eval(assignments[0].value);approval=bundle['approval']
    if approval.get('schema')!=2 or approval.get('approved') is not True or approval.get('enabled') is not True:
        return None,'not-approved'
    if approval['windowSeconds']!=window:return None,'different-analysis-window'
    from cue_corrector import __file__ as implementation
    if digest(implementation)!=approval['correctorSourceSHA256'] or digest(__file__)!=approval['runtimeSourceSHA256']:
        return None,'different-corrector-code'
    if digest(engine/'reacue_structure.py')!=approval['structureWrapperSHA256']:
        return None,'different-structure-code'
    encoded=bundle['modelJSON'].encode('utf-8')
    if hashlib.sha256(encoded).hexdigest()!=approval['modelSHA256']:return None,'changed-corrector-weights'
    model=json.loads(encoded)
    if model.get('approved') is not True or model.get('version')!='cue-corrector-v2' or not model.get('uncertaintyGuard'):
        return None,'not-approved'
    if not approval['structureFiles']:return None,'missing-structure-provenance'
    cache_path=engine/'worker-cache/cue-corrector-provenance.json'
    try:cached=json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):cached={}
    verified={}
    for name,expected in approval['structureFiles'].items():
        path=(engine/name).resolve()
        if not path.is_relative_to((engine/'structure').resolve()):raise ValueError('Invalid model provenance path')
        before=stamp(path)
        key=dict(path=str(path),stamp=before,sha256=expected['sha256'])
        if cached.get(name)!=key:
            if digest(path)!=expected['sha256'] or stamp(path)!=before:return None,'different-structure-weights'
        verified[name]=key
    temporary=cache_path.with_name('.'+uuid.uuid4().hex+'.tmp')
    try:
        cache_path.parent.mkdir(parents=True,exist_ok=True)
        temporary.write_text(json.dumps(verified),encoding='utf-8');temporary.replace(cache_path)
    except OSError:
        pass  # Read-only installations can still use fully verified weights.
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass
    return model,'approved'


def load_approved(engine,window):
    engine=Path(engine);bundle=engine/'cue-corrector';approval_path=bundle/'approval.json'
    if (engine/'cue_corrector_bundle.py').is_file():
        # Preserve an explicit local opt-out when migrating an installation.
        if approval_path.is_file():
            local=json.loads(approval_path.read_text(encoding='utf-8'))
            if local.get('enabled') is False:return None,'not-approved'
        return load_portable(engine,window)
    if not approval_path.is_file():return None,'not-installed'
    approval=json.loads(approval_path.read_text())
    if approval.get('schema')!=1 or approval.get('approved') is not True or approval.get('enabled') is not True:
        return None,'not-approved'
    if approval['windowSeconds']!=window:return None,'different-analysis-window'
    from cue_corrector import __file__ as implementation
    if digest(implementation)!=approval['correctorSourceSHA256'] or digest(__file__)!=approval['runtimeSourceSHA256']:
        return None,'different-corrector-code'
    if digest(engine/'reacue_structure.py')!=approval['structureWrapperSHA256']:
        return None,'different-structure-code'
    for name,expected in approval['structureFiles'].items():
        path=(engine/name).resolve()
        if not path.is_relative_to(engine.resolve()/'structure'):
            raise ValueError('Invalid model provenance path')
        # These stamps are recorded only after full hashes are verified at install.
        # A changed timestamp causes safe fallback, not use of untested weights.
        if stamp(path)!=expected['stamp']:return None,'different-structure-weights'
    if not approval['structureFiles']:return None,'missing-structure-provenance'
    model_path=bundle/'model.json'
    if digest(model_path)!=approval['modelSHA256']:return None,'changed-corrector-weights'
    model=json.loads(model_path.read_text())
    if model.get('approved') is not True or model.get('version')!='cue-corrector-v2' or not model.get('uncertaintyGuard'):
        return None,'not-approved'
    return model,'approved'


def eligibility(sections,duration,project=None):
    if not 120<=duration<=600:return 'outside-validated-duration'
    if project and any(s.get('reviewed') or s.get('locked') or s.get('origin')=='manual' for s in project.get('sections',[])):
        return 'protected-project-sections'
    if not sections or any(s.get('reviewed') or s.get('locked') or s.get('origin')!='analysis' for s in sections):
        return 'protected-sections'
    if any(abs(a['end']-b['start'])>1e-6 for a,b in zip(sections,sections[1:])):
        return 'preserve-section-gaps'
    if sections[-1]['end']>duration+.01:return 'invalid-section-duration'
    return None


def apply_model(sections,features,model,duration):
    """The same transform is used by the fresh holdout and production worker."""
    reason=eligibility(sections,duration)
    if reason:return copy.deepcopy(sections),[]
    from cue_corrector import correct
    # Keep the exact observed outer edge, including a short undecoded MP3 tail.
    return correct(sections,features,model,min(duration,sections[-1]['end']))


def adapt(audio,sections,engine,duration,window,project=None):
    original=copy.deepcopy(sections)
    try:
        model,reason=load_approved(engine,window)
        if model is None:return original,dict(applied=False,reason=reason)
        reason=eligibility(sections,duration,project)
        if reason:return original,dict(applied=False,reason=reason,version=model['version'])
        from cue_corrector import audio_features,boundary_features
        before=digest(audio)
        descriptors=audio_features(audio)
        if abs(descriptors['duration']-duration)>=1.5:return original,dict(applied=False,reason='audio-duration-mismatch')
        features=boundary_features(sections,descriptors,duration)
        corrected,changes=apply_model(sections,features,model,duration)
        if digest(audio)!=before:return original,dict(applied=False,reason='audio-changed')
        return corrected,dict(applied=bool(changes),version=model['version'],changes=changes,
                              audioSHA256=before,maximumShiftSeconds=model['maximumShiftSeconds'])
    except (OSError,ValueError,KeyError,TypeError,ImportError,RuntimeError,SyntaxError) as error:
        return original,dict(applied=False,reason='corrector-unavailable',detail=type(error).__name__)
