"""Tempo notation must never stretch the detected click or move its bar phase."""
import copy,json,sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from musical_timing import pulse_bpm,tempo_info,count_plan
from services import beat_grid,import_settings,export_reaper,atomic
from advanced import grid_from_frames,practice_grid
from windows import project as model
from test_studio_rhythm_decoder import frames


def compound():
    p=model.fresh();p['sessionDuration']=32
    p['tracks']=[dict(id='source',name='source',role='source',file='source.wav',duration=32,offset=0,
                      gain=.8,pan=0,muted=False,solo=False,peaks=[])]
    p['settings'].update(pulseUnit='dottedQuarter',referenceBPM=113,manualBPM=113,
                         beatsPerBar=2,firstBeat=.98,countVoice=False,exportCount=False)
    p['bpm']=75;p['beats']=(np.arange(40)*.8+.18).tolist()
    return p


def test_reference_changes_display_without_moving_any_detected_pulse():
    p=compound();before=copy.deepcopy(p)
    assert tempo_info(p)==dict(bpm=113,estimatedBPM=112.5,pulseBPM=75,source='reference')
    assert beat_grid(p)[0]==p['beats']
    assert count_plan(p)['target']==pytest.approx(.98)
    key=model.guide_key(p)
    p['settings']['referenceBPM']=114
    assert model.guide_key(p)==key
    assert p['beats']==before['beats']
    p['settings']['referenceBPM']=None
    assert tempo_info(p)['bpm']==112.5
    assert model.guide_key(p)==key


def test_fixed_quarter_tempo_converts_to_dotted_pulses_everywhere():
    p=compound();p['settings']['gridMode']='fixed'
    assert tempo_info(p)['bpm']==113 and tempo_info(p)['source']=='manual'
    assert pulse_bpm(p)==pytest.approx(113/1.5)
    beats,_=beat_grid(p)
    assert beats[:3]==pytest.approx([.98,.98+90/113,.98+180/113])
    assert model.period(p,0)==pytest.approx(90/113)
    assert count_plan(p)['events'][1]['time']-count_plan(p)['events'][0]['time']==pytest.approx(90/113)
    sheet=practice_grid(p)
    assert sheet['bpm']==113 and sheet['timeSignature']=='6/8'
    cell=next(c for g in sheet['groups'] for c in g['cells'] if c['start']==pytest.approx(.98))
    assert cell['end']-cell['start']==pytest.approx(180/113)


def test_unit_proposal_requires_triplets_not_just_duple_meter_or_swing():
    beats=np.arange(100)*.8+.1;bars=beats[1::2]
    for inner,expected in [([], 'quarter'),([2/3],'quarter'),([1/3,2/3],'dottedQuarter')]:
        extras=[beats[i]+part*.8 for i in range(1,30) for part in inner]
        result=grid_from_frames(*frames(beats,bars,81,extra=extras),81)
        assert result['pulseUnit']==expected
        assert result['firstBeat']==pytest.approx(.9)
        np.testing.assert_allclose(result['beats'],beats)


def test_reference_and_unit_are_song_specific_and_legacy_projects_stay_readable():
    p=compound();s=import_settings(p['settings'])
    assert s['referenceBPM'] is None and s['pulseUnit'] is None
    model.validate(p)
    for key in ('pulseUnit','referenceBPM'):p['settings'].pop(key)
    model.validate(p);assert pulse_bpm(p)==75 and tempo_info(p)['bpm']==75
    for value in (-1,0,401,float('nan')):
        p['settings']['referenceBPM']=value
        with pytest.raises(ValueError):model.validate(p)


def test_reanalysis_keeps_reference_and_applies_unit_without_locking():
    p=compound();result=dict(beats=p['beats'],downbeats=p['beats'][1::2],bpm=75,
                            pulseUnit='dottedQuarter')
    model.apply_grid(p,result,reanalyze=True)
    assert p['settings']['referenceBPM']==113 and p['settings']['pulseUnit']=='dottedQuarter'
    assert not p['gridLocked'] and p['settings']['firstBeat']==pytest.approx(.98)


def test_reaper_uses_quarter_tempo_and_compound_meter(tmp_path):
    p=compound();p['tracks']=[];p['settings']['gridMode']='fixed'
    # The export requires media duration; a muted source is enough for this fixture.
    import soundfile as sf
    sf.write(tmp_path/'source.wav',np.zeros(8000),8000)
    p['tracks']=[model.track(tmp_path/'source.wav',tmp_path,'source','source')]
    p['settings']['firstBeat']=0
    atomic(tmp_path/'project.json',p);export_reaper(tmp_path/'project.json',tmp_path/'result.json')
    result=json.loads((tmp_path/'result.json').read_text())
    text=Path(result['path']).read_text()
    assert 'TEMPO 113 6 8' in text
