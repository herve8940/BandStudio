"""Verify audible regularity, full-song coverage and count/transport parity."""
import copy
import json
import math
import numpy as np
import pytest
import soundfile as sf
from test_studio_services import project, generate, services
from musical_timing import count_plan, metronome_grid
from windows import project as model


@pytest.mark.parametrize('subdivision',[1,2,3,4])
@pytest.mark.parametrize('first',[6.62,-.3,12.5])
def test_rendered_click_is_regular_through_missing_intro_beats_and_outro(tmp_path,monkeypatch,subdivision,first):
    p=project(tmp_path);p['bpm']=93.75
    p['beats']=[.38,1.08,6.62,9.32,10.02,10.64]
    p['settings'].update(gridMode='detected',firstBeat=first,subdivision=subdivision,countVoice=False)
    original=copy.deepcopy(p)
    result=generate(p,tmp_path,monkeypatch)
    click,sr=sf.read(result['files']['click'])
    active=np.flatnonzero(abs(click[:,0])>1e-5)
    starts=active[np.r_[True,np.diff(active)>round(sr*.02)]]
    spacing=.64/subdivision
    expected=[first+i*spacing for i in range(math.ceil(-first/spacing-1e-9),math.ceil((12-first)/spacing-1e-9))]
    np.testing.assert_allclose(starts/sr,expected,atol=2/sr)
    np.testing.assert_allclose(np.diff(starts),spacing*sr,atol=1)
    assert starts[0]/sr<spacing+2/sr and 12-starts[-1]/sr<=spacing+2/sr
    assert p['beats']==original['beats'] and p['sections']==original['sections']
    assert p['settings']==original['settings']
    for at in (0,1.08,6.62,10.7):
        plan=count_plan(p,at)
        assert all(e['end']-e['time']==pytest.approx(.64) for e in plan['events'])
        assert model.period(p,at)==pytest.approx(.64)
        assert (plan['target']-first)/.64==pytest.approx(round((plan['target']-first)/.64))


def test_reaper_retains_one_tempo_and_original_region_times(tmp_path):
    p=project(tmp_path);p['settings'].update(gridMode='detected',exportCount=False,exportGuides=False)
    p['bpm']=93.75;p['beats']=[.38,1.08,6.62,9.32,10.02,10.64]
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    out=tmp_path/'result.json';services.export_reaper(snapshot,out)
    text=__import__('pathlib').Path(json.loads(out.read_text())['path']).read_text()
    assert 'TEMPO 93.75 4 4' in text and 'TEMPOENVEX' not in text
    assert 'MARKER 2 8.000000000' in text


def test_fixed_compound_clock_extends_before_anchor_and_after_detected_end(tmp_path):
    p=project(tmp_path);p['settings'].update(gridMode='fixed',manualBPM=113,pulseUnit='dottedQuarter',firstBeat=7.98)
    p['beats']=[1,2,4]
    pulses=metronome_grid(p,12)
    np.testing.assert_allclose(np.diff(pulses),90/113,atol=1e-12)
    assert 0<=pulses[0]<90/113 and 0<12-pulses[-1]<=90/113
