"""Audible regressions: gaps, pickup entries, overlapping voices and short regions."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import services
from test_studio_services import project


def render(p,root,monkeypatch,length=.8):
    def voice(text,folder,settings):
        path=folder/(str(abs(hash(text)))+'.wav')
        sf.write(path,np.full((round(length*44100),2),.2),44100,subtype='FLOAT')
        return path
    monkeypatch.setattr(services,'voice_wav',voice)
    services.atomic(root/'snapshot.json',p)
    services.guides(root/'snapshot.json',root/'result.json')
    return json.loads((root/'result.json').read_text())


def test_detected_gap_does_not_rewind_a_cue_to_a_previous_passage():
    beats=[0,.5,1,1.5,2,8,8.5,9,9.5,10]
    assert services.before_beat(6,4,beats,120)==4
    assert services.before_beat(8.5,4,beats,120)==6.5
    assert services.region_count_beats(6,4,beats)==[]
    assert [(e['number'],e['time']) for e in services.region_count_beats(8.5,4,beats)]==[(4,8)]


def test_detected_gap_keeps_the_same_regular_subdivision_clicks(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections']=[];p['cues']=[];p['bpm']=120
    p['settings'].update(gridMode='detected',subdivision=4,countVoice=False)
    p['beats']=[0,.5,1,1.5,2,8,8.5,9,9.5,10]
    r=render(p,tmp_path,monkeypatch)
    x,sr=sf.read(r['files']['click'])
    active=np.flatnonzero(abs(x[:,0])>1e-5)
    starts=active[np.r_[True,np.diff(active)>sr*.02]]
    np.testing.assert_allclose(starts/sr,np.arange(0,12,.125),atol=2/sr)


def test_close_regions_and_long_announcements_never_mix_spoken_voices(tmp_path,monkeypatch):
    p=project(tmp_path)
    p['sections']=[dict(id='a',name='Couplet',start=8,end=9),dict(id='b',name='Refrain',start=9,end=12)]
    p['cues']=[dict(id='c',name='Attention à la reprise',time=11)]
    p['settings']['countClick']=False
    r=render(p,tmp_path,monkeypatch)
    waves=[sf.read(r['files'][key])[0] for key in ('calls','cues','counts')]
    assert max(sum((abs(x[:,0])>.001).astype(int) for x in waves))==1
    assert len(r['events'])==3 and not r['guideWarnings']
    assert [e['target'] for e in r['events']]==[8,9,11]
    assert [e['time'] for e in r['events']]==sorted(e['time'] for e in r['events'])
    last=[e for e in r['countEvents'] if e['section']=='b']
    assert [(e['number'],e['time']) for e in last]==[(3,8),(4,8.5)]
    assert np.max(abs(waves[0]))<=.201 and np.max(abs(waves[1]))<=.201 and np.max(abs(waves[2]))<=.201


def test_anticipated_long_cue_finishes_before_its_target(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections']=[];p['cues']=[dict(id='c',name='Attention à la reprise',time=8)]
    p['settings'].update(leadBeats=2,countVoice=False)
    r=render(p,tmp_path,monkeypatch,length=1.8)
    assert r['events'][0]['end']<8
    assert r['events'][0]['time'] in r['beats']


def test_impossible_announcement_is_reported_instead_of_overlapping(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections']=[dict(id='a',name='Refrain',start=1,end=12)];p['cues']=[]
    r=render(p,tmp_path,monkeypatch,length=1.2)
    assert r['guideWarnings'][0]['id']=='a'
    assert r['events']==[] and r['files']['call:a']


def test_first_pickup_call_is_reserved_for_the_native_initial_count(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections']=[dict(id='intro',name='Intro',start=.26,end=12)];p['cues']=[]
    p['settings'].update(firstBeat=.26,countBars=2)
    r=render(p,tmp_path,monkeypatch,length=.8)
    assert not r['guideWarnings'] and not r['events']
    assert Path(r['files']['call:intro']).is_file()


def test_count_voice_does_not_cross_an_early_offbeat_entry(tmp_path,monkeypatch):
    p=project(tmp_path);p['sections']=[dict(id='a',name='Refrain',start=7.8,end=12)];p['cues']=[]
    r=render(p,tmp_path,monkeypatch,length=.7)
    x,sr=sf.read(r['files']['counts'])
    assert np.max(abs(x[round(7.8*sr):]))==0
    assert r['countEvents'][-1]['end']==7.8


def test_real_slow_passage_does_not_get_removed_as_a_gap():
    beats=[0,.5,1,1.5,2,3.5,5,6.5,8,9.5,11]
    assert len(services.region_count_beats(9.5,4,beats))==4
