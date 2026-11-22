"""Multitrack section evidence on rendered audio with known musical arrivals."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import musical_patterns as patterns
import section_evidence as evidence
from test_studio_first_import import structure_fixture


def ensemble(root,*,offset=0,shift=0,stereo=False,change='piano',missing=()):
    sr=8000;t=np.arange(16*sr)/sr;after=t>=8
    def tone(note):return np.sin(2*np.pi*440*2**((note+shift-69)/12)*t)
    signals=dict(guitar=.15*tone(69),piano=.10*np.where(after,tone(62),tone(60)),
                 bass=.15*np.where(after,tone(38),tone(36)),vocals=np.zeros(len(t)),
                 drums=.12*tone(48)*(np.mod(t,.5)<.05))
    if change=='guitar':signals['guitar']=.15*np.where(after,tone(69),tone(67));signals['piano'][:]=0
    if change=='drums':
        signals['piano']=.10*tone(60);signals['bass']=.15*tone(36)
        signals['drums']*=np.where(after,1,.05)
    signals['source']=sum(signals.values())
    p,_=structure_fixture();p['_root']=str(root);p['tracks']=[]
    for role,y in signals.items():
        if role in missing:continue
        if stereo and role in ('guitar','piano','bass'):y=np.column_stack([y,-y])
        sf.write(root/(role+'.wav'),y,sr,subtype='FLOAT')
        p['tracks'].append(dict(role=role,file=role+'.wav',offset=offset,duration=16))
    p['beats']=(np.arange(0,16,.5)+offset).tolist();p['downbeats']=(np.arange(0,16,4)+offset).tolist()
    for s in p['sections']:s['start']+=offset;s['end']+=offset
    return p


@pytest.mark.parametrize('meter,unit,at', [(4,'quarter',8.),(3,'quarter',7.5),(2,'dottedQuarter',8.)])
def test_late_bar_arrival_uses_local_attack_without_moving_pickups_or_protected_edges(tmp_path,meter,unit,at):
    p=ensemble(tmp_path);p['settings'].update(beatsPerBar=meter,pulseUnit=unit)
    p['downbeats']=p['beats'][::meter]
    p['lyrics']=[]
    p['sections'][0]['end']=p['sections'][1]['start']=at+.17
    original=copy.deepcopy(p)
    rows,changes=evidence.align_bar_arrivals(p)
    assert p==original and len(changes)==1 and rows[0]['end']==rows[1]['start']==at
    assert evidence.align_bar_arrivals({**p,'sections':rows})[0]==rows
    for field in ('locked','reviewed','origin'):
        q=copy.deepcopy(p);q['sections'][0][field]='manual' if field=='origin' else True
        assert evidence.align_bar_arrivals(q)[0]==q['sections']
    for old in (at-.17,at+.6):
        q=copy.deepcopy(p);q['sections'][0]['end']=q['sections'][1]['start']=old
        assert evidence.align_bar_arrivals(q)[0]==q['sections']
    # A reliable line beginning precisely at the later marker can be a musical offbeat.
    p['lyrics']=[dict(words=[dict(start=at+.17)])]
    assert evidence.align_bar_arrivals(p)[0]==p['sections']
    p['lyrics']=[];p['downbeats']=[]
    assert evidence.align_bar_arrivals(p)[0]==p['sections']


def test_section_arrival_needs_evidence_and_a_full_measure_on_both_sides(tmp_path):
    p=ensemble(tmp_path);p['settings'].update(beatsPerBar=4)
    p['downbeats']=p['beats'][::4];p['tracks']=[dict(role='source',duration=16,offset=0)]
    p['lyrics']=[];p['sections'][0]['end']=p['sections'][1]['start']=8.18
    assert evidence.align_bar_arrivals(p)[0]==p['sections']
    p['lyrics']=[dict(words=[dict(start=8.01)])]
    assert evidence.align_bar_arrivals(p)[0][1]['start']==8
    p['sections'][0]['start']=7.9
    assert evidence.align_bar_arrivals(p)[0]==p['sections']


@pytest.mark.parametrize('shift',[0,3,7])
def test_piano_arrival_hidden_by_held_guitar_is_used_with_bass(tmp_path,shift):
    p=ensemble(tmp_path,shift=shift);f=patterns.describe(p)
    rows,changes=evidence.refine(p,f)
    assert rows[1]['start']==rows[0]['end']==8 and len(changes)==1
    assert {'guitar','piano','bass','vocals','drums'}<=set(patterns.used_roles(f))
    assert 'source' not in patterns.used_roles(f)  # Mix is not an extra vote.
    assert p['sections'][1]['start']==7.4


@pytest.mark.parametrize('missing',[('vocals',),('drums',),('vocals','drums')])
def test_missing_optional_family_does_not_disable_harmonic_arrival(tmp_path,missing):
    p=ensemble(tmp_path,missing=missing)
    assert evidence.refine(p)[0][1]['start']==8


def test_stereo_phase_and_media_offset_preserve_musical_arrival(tmp_path):
    p=ensemble(tmp_path,stereo=True,offset=1.25)
    assert evidence.refine(p)[0][1]['start']==9.25
    f=patterns.describe(p)
    assert f['harmonyEnergy'].max()>.8
    assert not f['harmonyCoverage'][f['middle']<1].any()


def test_late_model_estimate_can_move_back_but_an_onbeat_cue_is_preserved(tmp_path):
    p=ensemble(tmp_path)
    p['sections'][0]['end']=p['sections'][1]['start']=8.6
    assert evidence.refine(p)[0][1]['start']==8
    p['sections'][0]['end']=p['sections'][1]['start']=8.5
    assert evidence.refine(p)[0]==p['sections']


def test_four_drum_parts_do_not_count_as_four_instruments(tmp_path):
    p=ensemble(tmp_path,change='drums')
    for role in patterns.DRUM_ROLES[1:]:
        sf.write(tmp_path/(role+'.wav'),sf.read(tmp_path/'drums.wav')[0],8000)
        p['tracks'].append(dict(role=role,file=role+'.wav',offset=0,duration=16))
    f=patterns.describe(p)
    assert not evidence.supports_change(p,8,f)
    assert not evidence.refine(p,f)[1]


def test_broken_optional_media_is_skipped_and_retried(tmp_path):
    p=ensemble(tmp_path,change='guitar');(tmp_path/'piano.wav').write_bytes(b'broken')
    assert evidence.refine(p)[0][1]['start']==8
    assert 'piano' not in patterns.used_roles(patterns.describe(p))
    sf.write(tmp_path/'piano.wav',np.zeros(16*8000),8000)
    assert 'piano' in patterns.used_roles(patterns.describe(p))


def test_each_harmonic_stem_invalidates_cache_but_mix_controls_do_not(tmp_path,monkeypatch):
    p=ensemble(tmp_path);first=patterns.describe(p)
    for track in p['tracks']:track.update(muted=True,solo=True,gain=0)
    original=patterns.track_features
    monkeypatch.setattr(patterns,'track_features',lambda *a,**k:pytest.fail('Mixer settings must reuse acoustic descriptors'))
    second=patterns.describe(p)
    np.testing.assert_array_equal(first['harmony'],second['harmony'])
    monkeypatch.setattr(patterns,'track_features',original)
    sf.write(tmp_path/'piano.wav',np.zeros(16*8000),8000)
    assert not np.array_equal(first['harmony'],patterns.describe(p)['harmony'])
    assert not evidence.refine(p)[1]


def test_protected_sections_and_gaps_survive_multitrack_review(tmp_path):
    p=ensemble(tmp_path);f=patterns.describe(p)
    for key,value in [('reviewed',True),('locked',True),('origin','manual')]:
        q=copy.deepcopy(p);q['sections'][0][key]=value
        assert evidence.refine(q,f)[0]==q['sections']
    p['sections'][0]['end']-=.5
    assert evidence.refine(p,f)[0]==p['sections']


def test_piano_variation_vetoes_a_repeated_guitar_phrase(tmp_path):
    p=ensemble(tmp_path)
    f=patterns.describe(p)
    # Same held guitar/bass/rhythm; piano alone changes the progression.
    f['bass'][:]=f['bass'][4];f['texture'][:]=f['texture'][4];f['harmony'][:]=f['harmony'][4]
    result=patterns.compare(f,dict(start=1,end=7),dict(start=9,end=15))
    assert result['harmony']>.99 and result['bass']>.99
    assert result['stemChecks']['piano'] is False and not result['matches']


def test_uncovered_audio_is_not_a_musical_change_and_aliases_are_not_votes(tmp_path):
    p=ensemble(tmp_path);f=patterns.describe(p)
    f['bassCoverage'][f['middle']>=8]=False
    assert not evidence.refine(p,f)[1]
    p['tracks']=[dict(role=r,file='bass.wav',offset=0,duration=16) for r in ('bass','other','source')]
    f=patterns.describe(p)
    assert len(patterns.used_roles(f))==1 and not evidence.refine(p,f)[1]
