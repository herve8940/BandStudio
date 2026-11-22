import copy
import json
from pathlib import Path
import pytest
from test_studio_manual_editor import manual_page
from test_studio_services import project, ENGINE
from windows.host import Api
from windows import project as model
import catalog
import preparation


def test_library_rename_preserves_project_media_and_setlists(tmp_path):
    root=tmp_path/'song.bandstudio';root.mkdir();p=project(root)
    p['futureField']={'keep':True};model.save(p,root)
    original=json.loads((root/'project.json').read_text())
    listing=tmp_path/'setlists.json';listing.write_text(json.dumps([{'paths':[str(root)]}]))
    media=(root/'Audio/source.wav').read_bytes()
    assert catalog.rename(tmp_path,root,'  Répétition / Été  ' )=='Répétition / Été'
    renamed=json.loads((root/'project.json').read_text())
    assert renamed=={**original,'name':'Répétition / Été'}
    assert (root/'Audio/source.wav').read_bytes()==media
    assert json.loads(listing.read_text())[0]['paths']==[str(root)]
    assert catalog.entry(root)['name']=='Répétition / Été'
    for value in ('   ','x'*201,'bad\nname',None):
        with pytest.raises(ValueError):catalog.rename(tmp_path,root,value)
        assert json.loads((root/'project.json').read_text())==renamed


def test_rename_open_project_does_not_restart_audio_or_invalidate_preparation(tmp_path,monkeypatch):
    root=tmp_path/'song.bandstudio';root.mkdir();p=project(root)
    p['preparation']={'fingerprint':'validated','rate':1,'pitch':0,'mode':'mix'};p['guideKey']='cached';model.save(p,root)
    api=Api(ENGINE,tmp_path);api._project=p;api._root=root;api._audio.project=p
    api._history=[copy.deepcopy(p)];before=copy.deepcopy(p)
    monkeypatch.setattr(api,'_reload',lambda:pytest.fail('Rename reloaded audio'))
    result=api.command(dict(command='renameProject',projectID=p['id'],args=dict(path=str(root),name='Nouveau titre')))
    assert result['ok'] and api._project=={**before,'name':'Nouveau titre'}
    assert api._history[0]['name']=='Nouveau titre'
    assert json.loads((root/'project.json').read_text())['name']=='Nouveau titre'


def test_rename_dialog_submits_name_and_cancel_does_nothing(manual_page):
    page,p=manual_page
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[{path:"/music/song.bandstudio",name:"Ancien titre"}],revision:2})',p)
    page.evaluate('view("library")')
    page.get_by_role('button',name='Renommer',exact=True).click()
    page.locator('#renameProjectName').fill('  Nouveau titre  ')
    page.locator('#renameProjectDialog').get_by_role('button',name='Enregistrer').click()
    assert page.evaluate('sent.at(-1)')==dict(command='renameProject',projectID=p['id'],args=dict(path='/music/song.bandstudio',name='Nouveau titre'))
    count=page.evaluate('sent.length')
    page.get_by_role('button',name='Renommer',exact=True).click()
    page.locator('#renameProjectDialog').get_by_role('button',name='Annuler').click()
    assert page.evaluate('sent.length')==count


@pytest.mark.parametrize('stale',[False,True])
def test_renaming_keeps_only_a_current_musical_approval(tmp_path,stale):
    root=tmp_path/'song.bandstudio';root.mkdir();p=project(root)
    p['settings'].update(exportGuides=False,exportCount=False)
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    checked=tmp_path/'checked.json';preparation.validate_project(snapshot,checked)
    p['preparation']=json.loads(checked.read_text())['preparation']
    if stale:p['tracks'][0]['gain']=.1
    model.save(p,root)
    api=Api(ENGINE,tmp_path);api._project=p;api._root=root;api._audio.project=p
    assert api.command(dict(command='renameProject',projectID=p['id'],args=dict(path=str(root),name='Titre corrigé')))['ok']
    saved=json.loads((root/'project.json').read_text());saved['_root']=str(root)
    assert api._project['preparation']==saved['preparation']
    assert (preparation.fingerprint(saved)==saved['preparation']['fingerprint']) is not stale
