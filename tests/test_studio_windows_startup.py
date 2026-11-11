"""Downloaded runtime recovery: only verified bundled libraries may be unblocked."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from windows.startup import MANIFEST, StartupError, unblock_bundled_libraries

DLL = 'Lib/site-packages/pythonnet/runtime/Python.Runtime.dll'
ZONE = b'[ZoneTransfer]\r\nZoneId=3\r\n'


def runtime(tmp_path):
    engine=tmp_path/'BandStudio é avec espaces/engine'
    dll=engine/'python'/DLL;dll.parent.mkdir(parents=True)
    dll.write_bytes(b'verified library from build')
    manifest=engine/'python'/MANIFEST
    value={'schema':1,'libraries':[{'path':DLL,'sha256':hashlib.sha256(dll.read_bytes()).hexdigest()}]}
    manifest.write_text(json.dumps(value),encoding='utf-8')
    stream=Path(str(dll)+':Zone.Identifier');stream.write_bytes(ZONE)
    return engine,dll,manifest,value,stream


def test_verified_library_unblocks_without_touching_user_files_and_restart_is_idempotent(tmp_path):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    unrelated=engine/'python/unlisted.dll';unrelated.write_bytes(b'user library')
    unrelated_stream=Path(str(unrelated)+':Zone.Identifier');unrelated_stream.write_bytes(ZONE)
    result=unblock_bundled_libraries(engine)
    assert result=={'manifest':'verified','checked':1,'unblocked':1}
    assert dll.read_bytes()==b'verified library from build' and not stream.exists()
    assert unrelated_stream.read_bytes()==ZONE
    assert unblock_bundled_libraries(engine)['unblocked']==0


def test_tampered_library_is_not_unblocked(tmp_path):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    dll.write_bytes(b'changed after packaging')
    # Truncating the unnamed stream can clear ADS on Windows; mark the changed
    # file again so this actually exercises a tampered, downloaded library.
    stream.write_bytes(ZONE)
    with pytest.raises(StartupError,match='modifiée'):unblock_bundled_libraries(engine)
    assert stream.read_bytes()==ZONE


@pytest.mark.parametrize('path',['../outside.dll','/outside.dll','C:/outside.dll','Lib/../outside.dll','Lib\\outside.dll','Lib/outside.dll:other','Lib/part./outside.dll','Lib/start.py'])
def test_manifest_cannot_unblock_paths_outside_approved_runtime(tmp_path,path):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    value['libraries'].append({'path':path,'sha256':'0'*64})
    manifest.write_text(json.dumps(value))
    with pytest.raises(StartupError):unblock_bundled_libraries(engine)
    assert stream.read_bytes()==ZONE


def test_manifest_cannot_follow_symlink_outside_runtime(tmp_path):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    external=tmp_path/'outside.dll';external.write_bytes(b'external')
    link=engine/'python/link.dll'
    try:link.symlink_to(external)
    except OSError:pytest.skip('Symlink creation needs Windows developer mode')
    value['libraries'].append({'path':'link.dll','sha256':hashlib.sha256(external.read_bytes()).hexdigest()})
    manifest.write_text(json.dumps(value))
    with pytest.raises(StartupError):unblock_bundled_libraries(engine)
    assert stream.read_bytes()==ZONE


def test_read_only_runtime_gives_actionable_error(tmp_path,monkeypatch):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    original=Path.unlink
    def denied(path,*args,**kwargs):
        if str(path).endswith(':Zone.Identifier'):raise PermissionError('read only')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',denied)
    with pytest.raises(StartupError,match='nouveau dossier accessible en écriture'):unblock_bundled_libraries(engine)
    assert stream.read_bytes()==ZONE


def test_old_runtime_without_inventory_is_left_untouched(tmp_path):
    engine,dll,manifest,value,stream=runtime(tmp_path)
    manifest.unlink()
    assert unblock_bundled_libraries(engine)=={'manifest':'absent','checked':0,'unblocked':0}
    assert stream.read_bytes()==ZONE
