"""Recorded timing is preserved; fixed tempo is an explicit mode."""
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
def test_explicit_fixed_click_is_regular_through_intro_and_outro(tmp_path,monkeypatch,subdivision,first):
    p=project(tmp_path);p['bpm']=93.75
    p['beats']=[.38,1.08,6.62,9.32,10.02,10.64]
    p['settings'].update(gridMode='fixed',manualBPM=93.75,firstBeat=first,subdivision=subdivision,countVoice=False)
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


def test_reaper_exports_detected_tempo_without_moving_regions(tmp_path):
    p=project(tmp_path);p['settings'].update(gridMode='detected',exportCount=False,exportGuides=False)
    p['bpm']=93.75;p['beats']=[.38,1.08,6.62,9.32,10.02,10.64]
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    out=tmp_path/'result.json';services.export_reaper(snapshot,out)
    text=__import__('pathlib').Path(json.loads(out.read_text())['path']).read_text()
    assert 'TEMPOENVEX' in text
    assert 'PT 0.380000000000' in text and 'PT 6.620000000000' in text
    assert 'MARKER 2 8.000000000' in text


def test_fixed_compound_clock_extends_before_anchor_and_after_detected_end(tmp_path):
    p=project(tmp_path);p['settings'].update(gridMode='fixed',manualBPM=113,pulseUnit='dottedQuarter',firstBeat=7.98)
    p['beats']=[1,2,4]
    pulses=metronome_grid(p,12)
    np.testing.assert_allclose(np.diff(pulses),90/113,atol=1e-12)
    assert 0<=pulses[0]<90/113 and 0<12-pulses[-1]<=90/113


def test_detected_click_and_subdivisions_follow_recording_and_fill_missing_pulses(tmp_path,monkeypatch):
    from musical_timing import BeatClock
    p=project(tmp_path);p['bpm']=120;p['gridLocked']=True
    p['beats']=[.2,.7,1.22,1.75,2.3,4.5,5.1]
    p['settings'].update(gridMode='detected',firstBeat=.2,subdivision=2,countVoice=False)
    expected=[.2,.7,1.22,1.75,2.3,2.85,3.4,3.95,4.5,5.1]
    result=generate(p,tmp_path,monkeypatch)
    data,sr=sf.read(result['files']['click'])
    active=np.flatnonzero(abs(data[:,0])>1e-5)
    starts=active[np.r_[True,np.diff(active)>round(sr*.02)]]/sr
    wanted=sorted(expected+[a+(b-a)/2 for a,b in zip(expected,expected[1:])])
    np.testing.assert_allclose(starts[starts<=5.11],wanted,atol=2/sr)
    assert 12-starts[-1]<.4
    assert result['timingGrid']['beats']==metronome_grid(p,12)
    assert [x for x in p['beats'] if x not in result['timingGrid']['beats']]==[]
    clock=BeatClock(p)
    for pos in (0,1.23,2.9,9):
        plan=count_plan(p,pos)
        assert clock.coordinate(plan['target'])==pytest.approx(round(clock.coordinate(plan['target'])))
        for event in plan['events']:
            source=event['time']+pos-plan['lead']
            assert clock.coordinate(source)==pytest.approx(round(clock.coordinate(source)))


def recorded_grids():
    from pathlib import Path
    return json.loads((Path(__file__).parent/'fixtures/recorded_timing_grids.json').read_text())


@pytest.mark.parametrize('p',recorded_grids(),ids=lambda p:p['name'][:32])
def test_saved_recordings_keep_every_pulse_with_full_song_coverage(p):
    from musical_timing import BeatClock
    clock=BeatClock(p);duration=p['sessionDuration']
    assert set(t for t in p['beats'] if 0<=t<duration)<=set(clock.beats)
    assert 0<=clock.beats[0]<clock.head+1e-8
    assert 0<duration-clock.beats[-1]<=clock.tail+1e-8
    assert np.all(np.diff(clock.beats)>0)
    times=np.linspace(-3,duration+3,200)
    np.testing.assert_allclose([clock.at(clock.coordinate(t)) for t in times],times,atol=1e-9)
    if p['gridLocked']:
        nearest=min(clock.beats,key=lambda t:abs(t-p['settings']['firstBeat']))
        assert clock.coordinate(nearest)%clock.meter==pytest.approx(0)


def test_apocalypse_missing_intro_beats_do_not_shift_later_bar_accents():
    from musical_timing import BeatClock
    p=next(p for p in recorded_grids() if p['name'].startswith('Apocalypse'))
    clock=BeatClock(p)
    assert clock.at(0)==pytest.approx(.38)
    assert clock.coordinate(11.28)==pytest.approx(16)
    assert clock.coordinate(14)==pytest.approx(20)
    assert clock.confidence>.99
    p['gridLocked']=True
    assert BeatClock(p).coordinate(p['settings']['firstBeat'])%4==pytest.approx(0)


@pytest.mark.parametrize('count',[False,True])
@pytest.mark.parametrize('compound',[False,True])
def test_export_tempo_integrates_exactly_to_the_next_recorded_pulse(tmp_path,count,compound):
    from musical_timing import BeatClock,tempo_envelope,pulse_scale
    p=project(tmp_path);p['beats']=[.2,.7,1.22,1.75,2.3,4.5,5.1];p['bpm']=120
    p['settings'].update(firstBeat=.7,gridMode='detected',pulseUnit='dottedQuarter' if compound else 'quarter')
    clock=BeatClock(p);lead=count_plan(p)['lead'] if count else 0
    points=tempo_envelope(p,lead);scale=pulse_scale(p['settings'])
    def integrated(a,b):
        stops=sorted(set([a,b]+[v['time'] for v in points if a<v['time']<b]));total=0
        for start,end in zip(stops,stops[1:]):
            active=next(v for v in reversed(points) if v['time']<=start+1e-9)
            total+=(end-start)*active['bpm']/60
        return total
    for a,b in zip(clock.beats,clock.beats[1:]):
        assert integrated(a+lead,b+lead)==pytest.approx(scale,abs=1e-9)
