"""Window subdivision errors must not move the audible first beat or later bars."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from advanced import grid_from_frames, repair_opening_pulses
from services import calibrate_grid


def frames(beats, downbeats, duration, extra=(), weak_downbeats=()):
    beat=np.full(round(duration*50)+1, -8.)
    down=np.full_like(beat, -8.)
    for times, strength, target in ((extra, 5., beat), (beats, 9., beat),
                                     (weak_downbeats, .25, down), (downbeats, 8., down)):
        for t in times:target[round(t*50)]=strength
    return beat, down


@pytest.mark.parametrize('meter,phase', [(2,1), (3,2), (4,3)])
def test_pickup_and_missing_downbeat_do_not_reset_phase_to_first_pulse(meter,phase):
    beats=np.arange(97)*.8+.1
    downbeats=beats[phase::meter]
    downbeats=np.delete(downbeats,[5,10])
    raw=frames(beats,downbeats,79,weak_downbeats=[beats[0]])
    result=grid_from_frames(*raw,79)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['firstBeat']==pytest.approx(beats[phase])
    assert result['beatsPerBar']==meter
    assert not result['gridReviewRequired']
    assert result==calibrate_grid(result)  # worker + Windows apply it again


def test_variable_tempo_and_subdivision_window_seams_keep_every_bar_aligned():
    beats=np.round(np.cumsum(np.r_[.08,np.linspace(.9,.76,120)])*50)/50
    extras=[]
    for i in range(len(beats)-1):
        if i<20 or 40<=i<60 or i>=100:
            extras.extend(beats[i]+np.array([1,2])*(beats[i+1]-beats[i])/3)
    bars=beats[1::2]
    bars=np.delete(bars,[12,21,38])
    beat,down=frames(beats,bars,beats[-1]+1,extra=extras,weak_downbeats=beats[[0,18,102]])
    result=grid_from_frames(beat,down,beats[-1]+1)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['firstBeat']==pytest.approx(.98)
    assert result['beatsPerBar']==2 and not result['gridReviewRequired']
    assert result['tempoNote']
    # Both the first and final accents use the same phase, without tempo flattening.
    assert result['beats'][1::2]==pytest.approx(beats[1::2])
    assert np.diff(result['beats'])[-1]<np.diff(result['beats'])[0]


def test_fast_regular_music_keeps_its_tempo_and_meter():
    beats=np.arange(120)*.24+.1
    result=grid_from_frames(*frames(beats,beats[::6],30),30)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['bpm']==pytest.approx(250)
    assert result['beatsPerBar']==6 and not result['tempoNote']


def test_unconfirmed_duple_meter_is_not_replaced_with_four():
    beats=np.arange(81)*.8+.1
    result=calibrate_grid(dict(beats=beats.tolist(),downbeats=beats[[0,2,4,6,9,11,13,15,17]].tolist()))
    assert result['gridReviewRequired']
    assert result['beatsPerBar']==2


def test_silence_is_not_given_a_confident_grid():
    result=grid_from_frames(np.full(500,-8.),np.full(500,-8.),10)
    assert result['beats']==[] and result['bpm']==0 and result['gridReviewRequired']


def test_attack_at_audio_start_is_kept():
    beats=np.arange(64)*.5
    result=grid_from_frames(*frames(beats,beats[::4],32),32)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['firstBeat']==0 and not result['gridReviewRequired']


def test_weak_opening_double_click_and_displaced_pulses_preserve_every_later_beat():
    opening=[.6,1.04,1.44,1.86,2.3,2.76,3.1,3.52,3.7,3.94,4.36,4.78,5.2,5.66]
    stable=np.round(5.96+np.arange(80)*.44,2)
    beats=np.r_[opening,stable]
    raw,down=frames(beats,stable[1::4],42)
    for t in opening:raw[round(t*50)]=1.
    corrected,changed=repair_opening_pulses(beats,raw,50)
    assert changed
    start=int(np.searchsorted(corrected,stable[0]))
    np.testing.assert_allclose(np.diff(corrected[:start+1]),.44,atol=1e-10)
    np.testing.assert_array_equal(corrected[start:],stable)
    again,changed_again=repair_opening_pulses(corrected,raw,50)
    np.testing.assert_array_equal(again,corrected)
    assert not changed_again
    result=grid_from_frames(raw,down,42)
    assert result['introCorrected']
    decoded=np.array(result['beats']);start=np.searchsorted(decoded,stable[0])
    np.testing.assert_array_equal(decoded[start:],stable)
    np.testing.assert_allclose(np.diff(decoded[:start+1]),.44,atol=1e-10)


@pytest.mark.parametrize('opening',[
    np.r_[.1,.1+np.cumsum(np.linspace(.39,.44,16))],  # quiet accelerando
    np.r_[np.arange(14)*.54+.22,8.02,8.56,9.1,9.64],  # a real gap/phase change
])
def test_weak_drifting_or_discontinuous_intro_is_not_extrapolated(opening):
    beats=np.r_[opening,opening[-1]+.44+np.arange(80)*.44]
    raw,_=frames(beats,beats[::4],60)
    for t in opening:raw[round(t*50)]=.5
    corrected,changed=repair_opening_pulses(beats,raw,50)
    np.testing.assert_array_equal(corrected,beats)
    assert not changed


def test_precision_benchmark_does_not_hide_the_first_five_seconds():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    from rhythm_benchmark import score,precision_metrics
    reference=np.arange(40)*.5
    wrong=reference.copy();wrong[:10]+=.06
    assert score(reference,wrong)==1
    result=precision_metrics(reference,wrong)
    assert result['introF1_20ms']==pytest.approx(.5)
    assert result['nearestP95Ms']==pytest.approx(60)


@pytest.mark.parametrize('opening',[
    np.arange(24)*.22+.1,  # genuinely faster opening, not isolated doubles
    np.array([.1,.6,1.1,1.6,1.9,2.1,2.6,3.1]),  # strong expressive subdivision
])
def test_confirmed_opening_pulses_and_real_tempo_changes_are_not_smoothed(opening):
    beats=np.r_[opening,opening[-1]+.44+np.arange(80)*.44]
    raw,_=frames(beats,beats[::4],50)
    corrected,changed=repair_opening_pulses(beats,raw,50)
    np.testing.assert_array_equal(corrected,beats)
    assert not changed


def test_weak_beats_and_stronger_offbeats_do_not_shift_subsequent_bars():
    beats=np.arange(160)*.52+.22
    beat,down=frames(beats,beats[::4],84)
    # A syncopated break: true pulses drop below threshold, extra offbeats
    # become positive. All later accents must retain their original phase.
    for i in (50,51,53):beat[round(beats[i]*50)]=-1.
    for i in (50,52,53):beat[round((beats[i]+.26)*50)]=2.
    result=grid_from_frames(beat,down,84)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['firstBeat']==pytest.approx(.22)
    assert result['beatsPerBar']==4 and not result['gridReviewRequired']
    assert result['continuityCorrected']


def test_sparse_hits_in_free_outro_do_not_create_random_clicks():
    beats=np.arange(100)*.52+.22
    beat,down=frames(beats,beats[::4],68)
    for t in (54.1,57.8,63.9,67.2):
        beat[round(t*50)]=.5;down[round(t*50)]=.5
    result=grid_from_frames(beat,down,68)
    np.testing.assert_allclose(result['beats'],beats)
    assert result['continuityCorrected']


def test_strong_rhythm_after_long_silence_is_not_discarded():
    beats=np.r_[np.arange(60)*.5+.1,np.arange(60)*.5+45.1]
    result=grid_from_frames(*frames(beats,beats[::4],76),76)
    np.testing.assert_allclose(result['beats'],beats)


def test_genuine_abrupt_tempo_change_keeps_all_strong_pulses():
    beats=np.r_[np.arange(32)*.8+.1,np.arange(32)*.26+25.7,np.arange(32)*.8+34.02]
    beats=np.round(beats*50)/50
    result=grid_from_frames(*frames(beats,beats[::4],60),60)
    np.testing.assert_allclose(result['beats'],beats)


def test_rendered_click_accents_follow_the_decoded_phase(tmp_path):
    import soundfile as sf
    import services
    from windows import project
    beats=np.arange(40)*.4+.1
    result=grid_from_frames(*frames(beats,beats[1::2],16,weak_downbeats=[.1]),16)
    p=project.fresh()
    p['tracks']=[dict(role='source',duration=16,offset=0)]
    p['settings']['countVoice']=False
    project.apply_grid(p,result)
    assert p['settings']['firstBeat']==.5 and p['settings']['beatsPerBar']==2
    services.atomic(tmp_path/'project.json',p)
    services.guides(tmp_path/'project.json',tmp_path/'result.json')
    import json
    output=json.loads((tmp_path/'result.json').read_text())
    audio,sr=sf.read(output['files']['click'])
    for i,beat in enumerate(beats):
        pulse=audio[round(beat*sr):round(beat*sr)+int(.035*sr),0]
        t=np.arange(len(pulse))/sr
        hi=abs(np.sum(pulse*np.exp(-2j*np.pi*1760*t)))
        lo=abs(np.sum(pulse*np.exp(-2j*np.pi*1100*t)))
        assert (hi>lo)==(i%2==1)
