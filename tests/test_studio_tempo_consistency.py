"""Tempo subdivision changes must not dominate the song or silently lock edits."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
from advanced import musical_grid


def sample_grid(*,subdivisions=False,real_tempo_change=False,missing=False):
    beats=[];downbeats=[];start=0.
    for bar in range(21):
        fast=4<=bar<9 or 13<=bar<17
        period=.8/3 if fast and real_tempo_change else .8
        factor=3 if fast and subdivisions else 1
        downbeats.append(start)
        for j in range(2*factor):
            if missing and factor==3 and j==1:continue
            beats.append(start+j*period/factor)
        start+=period*2
    return np.asarray(beats),np.asarray(downbeats),start


@pytest.mark.parametrize('missing',[False,True])
def test_triplet_subdivisions_are_folded_to_existing_pulses_with_correct_phase(missing):
    beats,bars,duration=sample_grid(subdivisions=True,missing=missing)
    result=musical_grid(beats,bars,duration)
    assert result['bpm']==pytest.approx(75)
    assert result['beatsPerBar']==2
    assert result['firstBeat']==pytest.approx(0)
    assert result['tempoNote']
    np.testing.assert_allclose(result['beats'],np.arange(42)*.8)
    assert set(result['beats']).issubset(set(beats))


def test_genuine_tempo_change_with_shorter_bars_is_preserved():
    beats,bars,duration=sample_grid(real_tempo_change=True)
    result=musical_grid(beats,bars,duration)
    np.testing.assert_allclose(result['beats'],beats)
    assert not result['tempoNote']


def test_consistently_fast_music_is_not_halved_or_thirded():
    beats=np.arange(126)*.8/3
    result=musical_grid(beats,beats[::6],34)
    assert result['bpm']==pytest.approx(225)
    np.testing.assert_allclose(result['beats'],beats)
    assert not result['tempoNote']
