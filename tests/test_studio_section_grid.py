"""Legacy repairs and export phase must match the saved, variable musical grid."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from musical_timing import align_section_grid,migrate_section_grid
from windows import project as model


def fixture():
    p=model.fresh();p['bpm']=120;p['sessionDuration']=30
    p['settings'].update(gridMode='detected',firstBeat=.5)
    p['beats']=[.5+i*.5 for i in range(60)]
    edges=[0,.5,8.34,16.63,24.39,30]
    p['sections']=[dict(id=str(i),name='Avant départ' if i==0 else 'Couplet',start=a,end=b,
                        locked=False,origin='analysis',announce=i!=0)
                   for i,(a,b) in enumerate(zip(edges,edges[1:]))]
    return p


def test_even_whole_bars_shared_edges_and_idempotence():
    p=fixture();before=copy.deepcopy(p);rows,changes=align_section_grid(p)
    assert [s['start'] for s in rows]==[0,.5,8.5,16.5,24.5]
    assert len(changes)==3 and p==before
    assert all(a['end']==b['start'] for a,b in zip(rows,rows[1:]))
    assert align_section_grid({**p,'sections':rows})==(rows,[])
    p['sections'][2]['locked']=True
    rows,_=align_section_grid(p)
    assert rows[2]==p['sections'][2]


def test_single_bar_breaks_gaps_and_free_outros_survive():
    p=fixture();p['sections'][2]['end']=p['sections'][3]['start']=10.4
    rows,_=align_section_grid(p)
    assert rows[2]['start']==8.5 and rows[2]['end']==10.5
    p['sections'][2]['end']=10.2
    rows,_=align_section_grid(p)
    assert rows[2]['end']==10.2 and rows[3]['start']==10.4
    p['beats']=p['beats'][:10]
    assert align_section_grid(p)[0]==p['sections']


def test_migration_backs_up_once_preserves_annotations_and_later_edits(tmp_path):
    p=fixture();p.pop('sectionGridVersion',None);p['lyrics']=[dict(start=8.3,end=9.1,text='Held',manual=True)]
    p['preparation']=dict(rate=1,pitch=0,mode='mix',fingerprint='old',validatedAt='old')
    p['guideKey']='old';p['sections'][2].update(locked=True,reviewed=True)
    path=tmp_path/'project.json';path.write_text(json.dumps(p));before=path.read_bytes()
    assert migrate_section_grid(p,tmp_path)
    assert (tmp_path/'Backups/section-grid-v1/project.json').read_bytes()==before
    assert p['lyrics']==json.loads(before)['lyrics'] and p['beats']==json.loads(before)['beats']
    assert p['guideKey']=='' and 'fingerprint' not in p['preparation']
    p['sections'][2]['start']=8.7
    assert not migrate_section_grid(p,tmp_path)
    assert p['sections'][2]['start']==8.7


@pytest.mark.parametrize('count',[True,False])
@pytest.mark.parametrize('fixed',[True,False])
def test_export_sets_initial_tempo_and_downbeat_phase(tmp_path,count,fixed):
    import services
    from test_studio_services import project
    p=project(tmp_path);p['settings'].update(gridMode='fixed' if fixed else 'detected',firstBeat=.72,
        countVoice=False,callsEnabled=False,exportCount=count)
    p['beats']=[.2,.72,1.23,1.77,2.3,2.82,3.34,3.86,4.39,4.92]
    p['bpm']=111
    snap=tmp_path/'snap.json';services.atomic(snap,p);out=tmp_path/'result.json';services.export_reaper(snap,out)
    result=json.loads(out.read_text());text=Path(result['path']).read_text()
    points=[l.split()[1:] for l in text.splitlines() if l.strip().startswith('PT ')]
    assert float(points[0][0])==0
    anchor=next(x for x in points if len(x)>3)
    assert float(anchor[0])==pytest.approx(.72+result['preroll'])
    assert anchor[3]=='262148'
    if not fixed:
        assert float(points[0][1])==pytest.approx(60/.52)
        # Integrate the exported envelope from its explicit bar anchor.
        active=[x for x in points if float(x[0])>=float(anchor[0])-1e-9]
        qn=0
        for left,right in zip(active,active[1:]):
            qn+=(float(right[0])-float(left[0]))*float(left[1])/60
            assert qn==pytest.approx(round(qn),abs=1e-8)


def test_old_lyrics_reference_is_upgraded_once_and_manual_text_is_exempt():
    p=fixture();p['lyrics']=[dict(start=1,end=2,text='test',manual=False)]
    p['lyricsReference']={'status':'corrected'}
    assert not model.analysis_done(p,'lyricscorrect')
    p['lyricsReference']['alignmentVersion']=1
    assert model.analysis_done(p,'lyricscorrect')
    p['lyricsReference']=None;p['lyrics'][0]['manual']=True
    assert model.analysis_done(p,'lyricscorrect')


def test_windows_open_upgrades_legacy_once_without_reanalysing_media(tmp_path,monkeypatch):
    from test_studio_services import project
    from windows.host import Api
    p=project(tmp_path);p['sections'][0]['end']=p['sections'][1]['start']=7.83
    model.save(p,tmp_path)
    host=Api(tmp_path/'no-runtime',tmp_path/'library')
    monkeypatch.setattr(host,'_state',lambda:None)
    try:
        host._load(tmp_path,prepare_guides=False)
        assert host._project['sections'][1]['start']==8
        assert host._project['sectionGridVersion']==1
        assert (tmp_path/'Backups/section-grid-v1/project.json').exists()
        host._project['sections'][0]['end']=host._project['sections'][1]['start']=7.9
        model.save(host._project,tmp_path)
        host._load(tmp_path,prepare_guides=False)
        assert host._project['sections'][1]['start']==7.9
    finally:host._audio.close()
