"""A release must work after relocation and through the original updater."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'desktop/studio'),str(ROOT/'tools')]
import cue_corrector_runtime as runtime
import cue_corrector as core
from test_cue_corrector_release import approved_bundle, sections, mock_features


def portable_bundle(tmp_path):
    engine,model=approved_bundle(tmp_path)
    approval=json.loads((engine/'cue-corrector/approval.json').read_text())
    model_json=(engine/'cue-corrector/model.json').read_text()
    approval['schema']=2
    for entry in approval['structureFiles'].values():entry.pop('stamp')
    bundle=dict(approval=approval,modelJSON=model_json)
    (engine/'cue_corrector_bundle.py').write_text('BUNDLE = '+repr(bundle),encoding='utf-8')
    shutil.rmtree(engine/'cue-corrector')
    return engine,model


def test_relocated_release_verifies_hashes_once_then_invalidates_cache(tmp_path,monkeypatch):
    engine,model=portable_bundle(tmp_path/'first')
    relocated=tmp_path/'different drive'/'BandStudio engine'
    shutil.copytree(engine,relocated)
    calls=[];digest=runtime.digest
    def recording(path):
        calls.append(Path(path));return digest(path)
    monkeypatch.setattr(runtime,'digest',recording)
    assert runtime.load_approved(relocated,60)==(model,'approved')
    assert relocated/'structure/test.bin' in calls
    calls.clear()
    assert runtime.load_approved(relocated,60)==(model,'approved')
    assert relocated/'structure/test.bin' not in calls
    (relocated/'structure/test.bin').write_bytes(b'changed')
    assert runtime.load_approved(relocated,60)==(None,'different-structure-weights')


def test_portable_uses_same_transform_and_respects_window_and_opt_out(tmp_path,monkeypatch):
    engine,model=portable_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'a');mock_features(monkeypatch)
    result,meta=runtime.adapt(audio,sections(),engine,150.,60)
    assert result[1]['start']==30.15 and meta['applied']
    assert runtime.adapt(audio,sections(),engine,150.,30)[0]==sections()
    (engine/'cue-corrector').mkdir()
    (engine/'cue-corrector/approval.json').write_text('{"enabled": false}')
    assert runtime.load_approved(engine,60)==(None,'not-approved')


def test_corrupt_portable_data_cannot_execute_or_modify_sections(tmp_path,monkeypatch):
    engine,model=portable_bundle(tmp_path);audio=tmp_path/'audio';audio.write_bytes(b'a');mock_features(monkeypatch)
    path=engine/'cue_corrector_bundle.py'
    bundle=ast.literal_eval(ast.parse(path.read_text()).body[0].value)
    bundle['modelJSON']='{}';path.write_text('BUNDLE = '+repr(bundle))
    assert runtime.load_approved(engine,60)==(None,'changed-corrector-weights')
    path.write_text('BUNDLE = __import__("os").remove("should-never-run")')
    result,meta=runtime.adapt(audio,sections(),engine,150.,60)
    assert result==sections() and meta['reason']=='corrector-unavailable'


def test_release_artifact_matches_frozen_implementation_and_original_payload():
    from cue_corrector_bundle import BUNDLE
    approval=BUNDLE['approval'];model=json.loads(BUNDLE['modelJSON'])
    assert approval['correctorSourceSHA256']==runtime.digest(core.__file__)
    assert approval['runtimeSourceSHA256']==runtime.digest(runtime.__file__)
    assert approval['structureWrapperSHA256']==runtime.digest(ROOT/'reacue_structure.py')
    assert hashlib.sha256(BUNDLE['modelJSON'].encode()).hexdigest()==approval['modelSHA256']
    assert approval['modelSHA256']=='30aa2cd7c03316195c5691622610ab5e4ab113db3ee50a23ae876948308a8735'
    assert model['maximumShiftSeconds']==.25 and model['deleteThreshold']==0
    assert approval['schema']==2 and all('stamp' not in f for f in approval['structureFiles'].values())
    assert '/Users/' not in repr(BUNDLE)


@pytest.mark.parametrize('platform',['windows-x64','macos-x64','macos-arm64'])
def test_update_contains_model_and_can_use_original_code_only_allowlist(tmp_path,platform):
    from package_studio_update import build
    from updater import allowed_path
    build(tmp_path,platform)
    with zipfile.ZipFile(tmp_path/('BandStudio-update-'+platform+'.zip')) as z:
        assert all(allowed_path(p) for p in z.namelist())
        for name in ('cue_corrector.py','cue_corrector_runtime.py','cue_corrector_bundle.py','chord_provider_defaults.py'):
            assert z.read('engine/'+name)==(ROOT/'desktop/studio'/name).read_bytes()
        # The original updater permits top-level .py, but not arbitrary JSON/data folders.
        assert not any(p.startswith('engine/cue-corrector/') for p in z.namelist())
        extracted=tmp_path/'extracted';z.extractall(extracted)
    result=subprocess.run([sys.executable,'-c','import chord_sources; assert len(chord_sources.PROVIDERS)==22; assert sum(bool(p.get("template")) for p in chord_sources.PROVIDERS)==8'],
                          cwd=extracted/'engine',capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_catalog_fallback_matches_native_catalog():
    from chord_provider_defaults import PROVIDERS
    assert PROVIDERS==json.loads((ROOT/'desktop/studio/chord-providers.json').read_text())
