"""One rehearsal section/announcement per continuous model function, not per phrase."""
import copy,json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import worker,services
from windows import project as model
from analysis_cache import AnalysisCache


def test_adjacent_phrases_join_without_moving_outer_boundaries():
    raw=[dict(start=0,end=13.56,label='verse'),dict(start=13.56,end=27.6,label='verse'),
         dict(start=27.6,end=40.8,label='chorus'),dict(start=40.8,end=54.6,label='verse'),
         dict(start=54.6,end=80.16,label='verse')]
    before=copy.deepcopy(raw);result=worker.sections(raw,80.16)
    assert raw==before
    assert [(s['name'],s['start'],s['end']) for s in result]==[
        ('Couplet',0,27.6),('Refrain',27.6,40.8),('Couplet',40.8,80.16)]
    assert all(s['origin']=='analysis' and not s['locked'] for s in result)


@pytest.mark.parametrize('middle',['silence','bridge','inst','solo'])
def test_short_different_passage_is_never_swallowed(middle):
    result=worker.sections([dict(start=0,end=3.73,label='verse'),
                            dict(start=3.73,end=3.93,label=middle),
                            dict(start=3.93,end=10,label='verse')],10)
    assert len(result)==3 and result[1]['end']-result[1]['start']==pytest.approx(.2)
    assert result[0]['end']==3.73 and result[2]['start']==3.93


def test_gap_and_long_sections_are_not_forced_to_four_bar_phrases():
    raw=[dict(start=0,end=80,label='verse'),dict(start=80,end=160,label='verse'),
         dict(start=160.2,end=220,label='verse')]
    result=worker.sections(raw,220)
    assert [(s['start'],s['end']) for s in result]==[(0,160),(160.2,220)]


def test_protected_manual_boundary_survives_grouped_proposal():
    p=model.fresh();p['sessionDuration']=20
    p['sections']=[dict(id='manual',name='Break ajouté',start=9,end=9.3,locked=True,origin='manual')]
    keep=copy.deepcopy(p['sections'][0]);settings=copy.deepcopy(p['settings'])
    proposal=worker.sections([dict(start=0,end=10,label='verse'),dict(start=10,end=20,label='verse')],20)
    model.apply_sections(p,proposal)
    assert p['sections'][1]==keep and p['settings']==settings
    assert [(s['start'],s['end']) for s in p['sections']]==[(0,9),(9,9.3),(9.3,20)]


def test_cache_reprocessed_without_model_and_guides_only_announce_groups(tmp_path,monkeypatch):
    engine=tmp_path/'engine';(engine/'structure').mkdir(parents=True)
    (engine/'structure/model.pt').write_bytes(b'model');(engine/'reacue_structure.py').write_text('# cached model')
    source=tmp_path/'source.wav';sf.write(source,np.zeros(24*8000),8000)
    p=model.fresh();p['_root']=str(tmp_path)
    p['tracks']=[dict(role='source',file='source.wav',duration=24,offset=0)]
    p['settings'].update(countVoice=False,regionCountEnabled=False)
    raw=[dict(start=0,end=6,label='verse'),dict(start=6,end=12,label='verse'),
         dict(start=12,end=18,label='chorus'),dict(start=18,end=24,label='chorus')]
    cache=AnalysisCache.create(p,'structure',source,engine,dict(window=420));cache.store(dict(segments=raw))
    monkeypatch.setattr(sys,'path',sys.path.copy())
    for key in ('REACUE_STRUCTURE_DIR','REAPER_RESOURCE_PATH','HF_HUB_OFFLINE','REACUE_CPU_THREADS'):monkeypatch.setenv(key,'')
    monkeypatch.setitem(sys.modules,'reacue_structure',SimpleNamespace(choose_window=lambda:420,load_app=lambda:pytest.fail('Unnecessary model rerun')))
    snap=tmp_path/'project.json';services.atomic(snap,p);out=tmp_path/'job/result.json'
    worker.analyze(source,out,'structure',engine,snap)
    result=json.loads(out.read_text());assert result['cacheHit'] and len(result['sections'])==2
    assert cache.load()['segments']==raw  # Raw model evidence remains recoverable.
    p['sections']=result['sections'];services.atomic(snap,p)
    spoken=[]
    def voice(text,folder,settings):
        spoken.append(text);path=folder/(str(len(spoken))+'.wav');sf.write(path,np.zeros((441,2)),44100);return path
    monkeypatch.setattr(services,'voice_wav',voice)
    guides=tmp_path/'guides/result.json';services.guides(snap,guides)
    assert spoken==['Couplet','Refrain']
    files=json.loads(guides.read_text())['files']
    assert len([k for k in files if k.startswith('call:')])==2
