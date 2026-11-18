"""Saved grids, audible entrances and real count-in rendering without model inference."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from musical_timing import count_plan,align_intro_sections,audio_entry,cached_audio_entry
from windows.audio import Audio,SR
from windows import project as model


def song(first=2.68,period=.64,phase=0):
    p=model.fresh('Intro');p['bpm']=60/period;p['beats']=[first+i*period for i in range(40)]
    p['settings'].update(gridMode='detected',firstBeat=p['beats'][phase],countBars=2,
                         countVoice=False,callsEnabled=False,regionCountEnabled=False)
    p['sections']=[dict(id='intro',name='Intro',start=0,end=8,origin='analysis',locked=False),
                   dict(id='intro2',name='Intro',start=8,end=15,origin='analysis',locked=False),
                   dict(id='verse',name='Couplet',start=15,end=24,origin='manual',locked=True,reviewed=True)]
    return p


@pytest.mark.parametrize('first,period,phase',[(2.68,.64,0),(.56,.62,1),(1.01,.54,3),(.26,.5,0),(12,.5,0)])
def test_full_count_hands_over_at_first_downbeat_with_pickup_preserved(first,period,phase):
    p=song(first,period,phase);plan=count_plan(p)
    assert plan['target']==pytest.approx(first+phase*period)
    assert plan['end']-plan['lead']==pytest.approx(plan['target'])
    assert [e['number'] for e in plan['events']]==[1,2,3,4]*2
    assert plan['events'][-1]['end']==plan['end']
    assert all(e['end']-e['time']==pytest.approx(period) for e in plan['events'])
    assert plan['lead']>=0 and plan['events'][0]['time']>=0


def test_seek_uses_saved_variable_tempo_and_beat_phase():
    p=song();p['beats']=[.2,.7,1.22,1.75,2.3,2.82,3.38,3.94,4.52,5.1];p['settings']['firstBeat']=.7
    plan=count_plan(p,3.8)
    assert plan['target']==3.94
    assert plan['events'][-1]['number']==2
    assert plan['events'][-1]['end']-plan['events'][-1]['time']==pytest.approx(.56)
    exact=count_plan(p,3.94)
    assert exact['target']==3.94
    p['settings']['countBars']=0
    assert count_plan(p,3.8)==dict(lead=0,end=0,target=3.8,events=[])


def test_fixed_grid_count_is_anchored_to_its_saved_first_beat():
    p=song();p['settings'].update(gridMode='fixed',manualBPM=120,firstBeat=.26)
    plan=count_plan(p)
    assert plan['lead']==pytest.approx(3.74) and plan['end']==4


@pytest.mark.parametrize('meter,phase',[(2,1),(3,1),(4,1),(4,3)])
def test_opening_voice_counts_every_beat_including_pickup(tmp_path,meter,phase):
    p=song(.08,.8,phase);p['settings'].update(beatsPerBar=meter,countBars=1,
                                           countClick=False,countVoice=True)
    p['guideFiles']={}
    # Distinct amplitudes verify that the final spoken number is actually
    # rendered, including when it overlaps the music's opening pickup.
    for number in range(1,meter+1):
        name=f'{number}.wav';sf.write(tmp_path/name,np.full((SR//8,2),number/10,np.float32),SR,subtype='FLOAT')
        p['guideFiles']['number:'+str(number)]=name
    a=Audio(tmp_path);a.project=p;a.root=tmp_path
    wave=a.make_count(0);plan=count_plan(p)
    spoken=list(range(1,meter+1))
    assert [e['number'] for e in plan['events'] if e['spoken']]==spoken
    assert plan['lead']==pytest.approx((meter-phase)*.8-.08)
    assert len(wave)==round((plan['lead']+p['settings']['firstBeat'])*SR)
    for e,number in zip(plan['events'],spoken):
        assert wave[round(e['time']*SR),0]==pytest.approx(number/10*p['settings']['countGain'])
    last=plan['events'][-1]
    assert last['time']>=plan['lead']+.08-1e-7
    assert np.any(wave[round(last['time']*SR):])
    assert p['settings']['firstBeat']==pytest.approx(.08+phase*.8)


def test_count_display_counts_real_events_instead_of_rounded_average_tempo(tmp_path):
    p=song(1.01,.54,3);p['bpm']=120
    a=Audio(tmp_path);a.project=p;a.root=tmp_path;a.play(hardware=False)
    assert a.remaining()==8
    a.block(round(.54*SR));assert a.remaining()==7
    a.pause()


def test_intro_changes_only_opening_boundaries_and_respects_validation():
    p=song(.26,.5);before=copy.deepcopy(p)
    p['sections'][0]['reviewed']=True
    assert align_intro_sections(p,.235)==p
    corrected=align_intro_sections(p,.235,force=True)
    assert corrected['sections'][0]['name']=='Avant départ' and corrected['sections'][0]['announce'] is False
    assert corrected['sections'][1]['start']==.26
    assert corrected['sections'][2]['start']==corrected['sections'][1]['end']==8.26
    assert corrected['sections'][-1]==before['sections'][-1]
    assert corrected['settings']==p['settings'] and corrected['beats']==p['beats']
    assert corrected['sections'][1]['reviewed'] is False
    assert align_intro_sections(corrected,.235,force=True)==corrected


def test_pickup_is_preserved_and_repair_is_idempotent():
    p=song(.56,.62,1);p['sections'][0]['end']=p['sections'][1]['start']=1.4977
    corrected=align_intro_sections(p,1.02)
    assert [s['name'] for s in corrected['sections'][:3]]==['Avant départ','Levée','Intro']
    assert [s['start'] for s in corrected['sections'][:3]]==pytest.approx([0,1.02,1.18])
    assert corrected['sections'][1]['announce'] is False
    assert align_intro_sections(corrected,1.02,force=True)==corrected


def test_audio_entry_cache_does_not_reanalyse_valid_audio(tmp_path,monkeypatch):
    import musical_timing
    path=tmp_path/'sound.wav';x=np.zeros((SR*3,2),np.float32);x[SR:]=.05
    sf.write(path,x,SR,subtype='FLOAT')
    assert audio_entry(path)==pytest.approx(1,abs=.015)
    p={'_root':str(tmp_path)};entry=cached_audio_entry(path,p,tmp_path)
    monkeypatch.setattr(musical_timing,'audio_entry',lambda _:pytest.fail('Cached entrance analysed again'))
    assert cached_audio_entry(path,p,tmp_path)==entry


@pytest.mark.parametrize('with_count',[True,False])
def test_render_keeps_full_music_and_no_duplicate_clicks_during_pickup(tmp_path,with_count):
    p=song(.25,.5,1);p['settings'].update(clickEnabled=True,clickPan=-1,countPan=-1,countGain=.6,clickGain=.6,countVoice=False,subdivision=1)
    # Original right channel is a time-varying signal; guide clicks live on the left.
    source=np.zeros((3*SR,2),np.float32);source[:,1]=np.arange(3*SR)/SR*.02
    clicks=np.zeros_like(source)
    for t in p['beats']:
        i=round(t*SR)
        if i<len(clicks):clicks[i:i+20]=.2
    p['tracks']=[]
    for role,data in [('source',source),('guide_click',clicks)]:
        path=tmp_path/(role+'.wav');sf.write(path,data,SR,subtype='FLOAT');p['tracks'].append(model.track(path,tmp_path,role,role))
    a=Audio(tmp_path);a.load(p,tmp_path);a.mode='original';target=tmp_path/'render.wav';a.render(target,0,3,with_count)
    rendered,_=sf.read(target);plan=count_plan(p);lead=round(plan['lead']*SR) if with_count else 0
    assert len(rendered)==len(source)+lead
    np.testing.assert_allclose(rendered[lead:,1],source[:,1]*p['tracks'][0]['gain']*.85,atol=1e-7)
    if with_count:
        # During the pickup only the count-in sounds: do not double its click
        # with the guide. The generated metronome takes over on the downbeat.
        count=a.make_count(0)
        i=lead+round(.25*SR)
        np.testing.assert_allclose(rendered[i:i+20,0],count[i:i+20,0]*.85,atol=1e-7)
        assert len(count)==lead+round(.75*SR)
        i=lead+round(plan['target']*SR)
        np.testing.assert_allclose(rendered[i:i+20,0],.2*.6*.85,atol=1e-7)
        assert rendered[lead+round(.75*SR),0]==pytest.approx(.2*.6*.85)


def test_reaper_count_overlaps_silent_head_and_keeps_source_position(tmp_path):
    from test_studio_services import project
    import services
    p=project(tmp_path);p['settings'].update(gridMode='detected',firstBeat=2.68,countVoice=False,callsEnabled=False)
    p['beats']=[2.68+i*.64 for i in range(15)];p['bpm']=93.75
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p));out=tmp_path/'result.json'
    services.export_reaper(snapshot,out)
    result=json.loads(out.read_text());assert result['preroll']==pytest.approx(2.44)
    rpp=Path(result['path']);assert 'POSITION 2.440000000' in rpp.read_text()
    count,sr=sf.read(rpp.parent/'Audio/count-in.wav');assert len(count)==pytest.approx(5.12*sr,abs=1)
