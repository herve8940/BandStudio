"""Opening a chart must never quantize its saved musical sections."""
import copy
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from windows import project as model
from section_grid_rollback import rollback_section_grid


@pytest.mark.parametrize('version',[None,1])
def test_open_preserves_section_positions_and_annotations(tmp_path,monkeypatch,version):
    from test_studio_services import project
    from windows.host import Api
    p=project(tmp_path)
    p['settings']={**model.GUIDE_DEFAULTS,**p['settings']}
    p['sections'][0]['end']=p['sections'][1]['start']=7.83
    p['sections'][1].update(locked=True,origin='manual',reviewed=True)
    if version is not None:p['sectionGridVersion']=version
    original=copy.deepcopy(p['sections']);settings=copy.deepcopy(p['settings'])
    model.save(p,tmp_path)
    host=Api(tmp_path/'no-runtime',tmp_path/'library')
    monkeypatch.setattr(host,'_state',lambda:None)
    try:
        for _ in range(2):
            host._load(tmp_path,prepare_guides=False)
            assert host._project['sections']==original
            saved=json.loads((tmp_path/'project.json').read_text())
            assert saved['sections']==original and saved['settings']==settings
        assert not (tmp_path/'Backups/section-grid-v1').exists()
    finally:host._audio.close()


def test_lyrics_upgrade_remains_available_without_section_migration():
    p=model.fresh();p['lyrics']=[dict(start=1,end=2,text='test',manual=False)]
    p['lyricsReference']={'status':'corrected'}
    assert not model.analysis_done(p,'lyricscorrect')
    p['lyricsReference']['alignmentVersion']=1
    assert model.analysis_done(p,'lyricscorrect')
    p['lyricsReference']=None;p['lyrics'][0]['manual']=True
    assert model.analysis_done(p,'lyricscorrect')


def migrated_project(tmp_path):
    p=model.fresh();p.pop('sectionGridVersion',None);p['sessionDuration']=30;p['bpm']=120
    p['settings'].update(gridMode='detected',firstBeat=.5)
    p['beats']=[.5+i*.5 for i in range(60)]
    edges=[0,.5,8.34,16.63,24.39,30]
    p['sections']=[dict(id=str(i),name='Avant départ' if i==0 else 'Couplet',start=a,end=b,
        locked=False,origin='analysis',announce=i!=0) for i,(a,b) in enumerate(zip(edges,edges[1:]))]
    backup=tmp_path/'Backups/section-grid-v1/project.json';backup.parent.mkdir(parents=True)
    backup.write_text(json.dumps(p));original=copy.deepcopy(p)
    p['sectionGridVersion']=1
    for i,at in [(2,8.5),(3,16.5),(4,24.5)]:
        p['sections'][i]['start']=p['sections'][i-1]['end']=at
        p['sections'][i]['reviewed']=p['sections'][i-1]['reviewed']=False
    p['lyrics']=[dict(start=8.2,end=9,text='Newest text',manual=True)]
    p['settings']['callsGain']=.7  # Independent listening edits survive recovery.
    p['guideKey']='stale'
    (tmp_path/'project.json').write_text(json.dumps(p))
    return p,original


def test_rollback_restores_exact_positions_keeps_lyrics_and_runs_once(tmp_path):
    p,original=migrated_project(tmp_path);before=(tmp_path/'project.json').read_bytes()
    lyrics=copy.deepcopy(p['lyrics']);settings=copy.deepcopy(p['settings'])
    assert rollback_section_grid(p,tmp_path)
    assert p['sections']==original['sections'] and p['lyrics']==lyrics and p['settings']==settings
    assert p['guideKey']=='' and p['sectionGridVersion']==2
    assert (tmp_path/'Backups/section-grid-rollback-v2/project.json').read_bytes()==before
    p['sections'][2]['start']=8.9
    assert not rollback_section_grid(p,tmp_path)
    assert p['sections'][2]['start']==8.9
    assert (tmp_path/'Backups/section-grid-rollback-v2/project.json').read_bytes()==before


@pytest.mark.parametrize('change',['boundary','name','locked','reviewed','grid','beats','foreign','missing','corrupt','array'])
def test_rollback_never_overwrites_later_edits_or_guesses_missing_backups(tmp_path,change):
    p,_=migrated_project(tmp_path);backup=tmp_path/'Backups/section-grid-v1/project.json'
    if change=='boundary':p['sections'][2]['start']=p['sections'][1]['end']=8.7
    if change=='name':p['sections'][2]['name']='My revised verse'
    if change=='locked':p['sections'][2]['locked']=True
    if change=='reviewed':p['sections'][2]['reviewed']=True
    if change=='grid':p['settings']['firstBeat']=1
    if change=='beats':p['beats'][2]+=.01
    if change=='foreign':p['id']='another-recording'
    if change=='missing':backup.unlink()
    if change=='corrupt':backup.write_text('{')
    if change=='array':backup.write_text('[]')
    original=copy.deepcopy(p);(tmp_path/'project.json').write_text(json.dumps(p))
    assert not rollback_section_grid(p,tmp_path)
    assert p=={**original,'sectionGridVersion':2}
