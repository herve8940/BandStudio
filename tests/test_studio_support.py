"""Regression tests for musician listening, private diagnostics and transactional updates."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import updater
import diagnostics
from listening import included,parse_mode

@pytest.mark.parametrize('instrument,roles', [('drums',['drums','drum_snare']),('vocals',['vocals','vocal_lead','vocal_backing']),('bass',['bass']),('guitar',['guitar']),('piano',['piano'])])
def test_every_instrument_has_a_complementary_mix(instrument,roles):
    for role in ['drums','drum_snare','bass','vocals','vocal_lead','vocal_backing','guitar','piano','other']:
        assert included(role,'solo:'+instrument)==(role in roles)
        assert included(role,'minus:'+instrument)==(role not in roles)
    with pytest.raises(ValueError):parse_mode('solo:unknown')

def test_report_redacts_secrets_and_does_not_include_project_files(tmp_path,monkeypatch):
    monkeypatch.setattr(diagnostics,'directory',lambda:tmp_path/'logs')
    (tmp_path/'logs').mkdir();(tmp_path/'logs/application.log').write_text('token=abcd\nhttps://example.test/private?secret=yes\n'+str(Path.home())+'/song.wav')
    (tmp_path/'project.json').write_text('private lyrics')
    report=tmp_path/'report.zip';diagnostics.export_report(report)
    with zipfile.ZipFile(report) as z:
        assert set(z.namelist())=={'system.json','application.log'}
        log=z.read('application.log').decode();assert 'abcd' not in log and 'example.test' not in log and str(Path.home()) not in log
    assert 'private lyrics' not in diagnostics.issue_url()

@pytest.mark.parametrize('path',['../escape','engine/../escape','engine/project.json','engine/.venv/test.py','engine/web/../../secret.py','engine/web/C:/foo.js','mac-app/Contents/Resources/studio.json','engine/web/evil\\file.js'])
def test_update_rejects_unsafe_or_user_data_paths(tmp_path,path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(path,'evil')
    with pytest.raises(ValueError):updater.extract(archive,tmp_path/'stage')
    assert not (tmp_path.parent/'escape').exists()

def pending(tmp_path,monkeypatch):
    folder=tmp_path/'updates';folder.mkdir();stage=folder/'stage-test';stage.mkdir();engine=tmp_path/'engine';engine.mkdir()
    (engine/'worker.py').write_text('old');(engine/'build.json').write_text('{"commit":"old"}')
    (engine/'torch-cache').mkdir();(engine/'torch-cache/weights').write_text('preserve model')
    archive=stage/'verified.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('engine/build.json',json.dumps({'commit':'a'*40}));z.writestr('engine/worker.py','new');z.writestr('engine/new.py','added')
    updater.write_json(folder/'pending.json',{'stage':str(stage),'engine':str(engine),'app':None,'commit':'a'*40,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()})
    monkeypatch.setattr(updater,'data_dir',lambda:folder)
    return folder,engine,archive

def test_update_applies_only_code_and_keeps_backup(tmp_path,monkeypatch):
    folder,engine,_=pending(tmp_path,monkeypatch)
    assert updater.apply_pending()
    assert (engine/'worker.py').read_text()=='new'
    assert (engine/'torch-cache/weights').read_text()=='preserve model'
    backup=Path(json.loads((folder/'last-update.json').read_text())['backup'])
    assert (backup/'engine/worker.py').read_text()=='old'
    assert not (folder/'pending.json').exists()

def test_update_rolls_back_all_files_after_replace_failure(tmp_path,monkeypatch):
    folder,engine,_=pending(tmp_path,monkeypatch)
    replace=updater.os.replace
    def fail(source,target):
        if Path(target).name=='worker.py':raise OSError('locked')
        return replace(source,target)
    monkeypatch.setattr(updater.os,'replace',fail)
    with pytest.raises(OSError):updater.apply_pending()
    assert (engine/'worker.py').read_text()=='old'
    assert json.loads((engine/'build.json').read_text())['commit']=='old'
    assert not (engine/'new.py').exists()
    assert (folder/'pending.json').exists()

def test_update_rejects_tampered_download_before_replacing_any_file(tmp_path,monkeypatch):
    _,engine,archive=pending(tmp_path,monkeypatch);archive.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='modifié'):updater.apply_pending()
    assert (engine/'worker.py').read_text()=='old'

def test_network_failure_keeps_installed_version_and_releases_lock(tmp_path,monkeypatch):
    monkeypatch.setattr(updater,'data_dir',lambda:tmp_path/'updates')
    monkeypatch.setattr(updater,'download',lambda *args:(_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(OSError):updater.check(tmp_path/'engine')
    assert not (tmp_path/'updates/checking').exists()
    assert not (tmp_path/'updates/pending.json').exists()
