"""First-import evidence: known notes and unseen keys, no remembered songs."""
import copy
from pathlib import Path
import sys
import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chord_alignment as alignment
import chord_sources as sources
import section_evidence
import structure_review
from test_studio_web_chords import song


def render(tmp_path,labels,*,transpose=0,lead=True,bass=True,seconds=2,cents=0):
    sr=16000;n=round(sr*seconds);t=np.arange(n)/sr
    harmony=np.zeros(len(labels)*n);bottom=np.zeros_like(harmony)
    for i,label in enumerate(labels):
        pitches,root=alignment.tones(label)
        for pitch in pitches:
            hz=440*2**((60+pitch+transpose+cents/100-69)/12)
            for partial in range(1,5):harmony[i*n:(i+1)*n]+=.025/partial*np.sin(2*np.pi*hz*partial*t)
        if lead:harmony[i*n:(i+1)*n]+=.16*np.sin(2*np.pi*440*2**((transpose+cents/100)/12)*t)
        hz=440*2**((36+root+transpose+cents/100-69)/12)
        for partial in range(1,7):bottom[i*n:(i+1)*n]+=.18*.7**(partial-1)*np.sin(2*np.pi*hz*partial*t)
    for name,y in [('other',harmony),('bass',bottom),('source',harmony+bottom)]:sf.write(tmp_path/(name+'.wav'),y,sr)
    p=song();p.update(_root=str(tmp_path),sections=[],beats=np.arange(0,len(harmony)/sr,.5).tolist())
    p['settings'].update(gridMode='detected',pulseUnit='quarter')
    roles=('source','other','bass') if bass else ('source','other')
    p['tracks']=[dict(id=name,role=name,file=name+'.wav',offset=0,duration=len(harmony)/sr,gain=.8,pan=0,muted=False,solo=False) for name in roles]
    return p


def transpose_label(label,steps):
    import re
    names=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];root=alignment.tones(label)[0][0]
    return re.sub(r'^[A-G][#b]?',names[(root+steps)%12],label)


@pytest.mark.parametrize('shift',[0,3,7])
def test_pitched_bass_recovers_changes_masked_by_a_loud_lead_in_unseen_keys(tmp_path,shift):
    labels=['Am','E','Dm','Am','C','G','D','A']
    p=render(tmp_path,labels,transpose=shift);expected=[transpose_label(v,shift) for v in labels]
    rows,info=alignment.place(p,tmp_path/'other.wav',list(dict.fromkeys(expected)),'https://example.test/chart')
    correct=sum(max(0,min(c['end'],(i+1)*2)-max(c['start'],i*2)) for c in rows for i,label in enumerate(expected) if c['label']==label)/16
    assert correct>=.85
    assert info['bassEvidence']
    # The repaired E is contradicted by the loud held lead: keep that doubt.
    repaired=next(c for c in rows if c['start']<=3<c['end'])
    assert repaired['label']==expected[1] and repaired['confidence']<.5
    assert all(0<=c['confidence']<=1 for c in rows)


def test_separate_bass_distinguishes_inversions_without_changing_the_vocabulary(tmp_path):
    p=render(tmp_path,['D/F#','D','D/F#','D'],lead=False)
    rows,_=alignment.place(p,tmp_path/'other.wav',['D','D/F#'],'https://example.test/chart')
    for time,label in [(1,'D/F#'),(3,'D'),(5,'D/F#'),(7,'D')]:
        assert next(c['label'] for c in rows if c['start']<=time<c['end'])==label


def test_missing_bass_retains_compatible_single_audio_path(tmp_path):
    p=render(tmp_path,['C','G','Am','F'],lead=False,bass=False)
    rows,info=alignment.place(p,tmp_path/'other.wav',['C','G','Am','F'],'https://example.test/chart')
    assert not info['bassEvidence']
    assert [next(c['label'] for c in rows if c['start']<=time<c['end']) for time in (1,3,5,7)]==['C','G','Am','F']


@pytest.mark.parametrize('missing',[True,False])
def test_unavailable_bass_file_does_not_block_the_original_audio_path(tmp_path,missing):
    p=render(tmp_path,['C','G','Am','F'],lead=False)
    if missing:(tmp_path/'bass.wav').unlink()
    else:(tmp_path/'bass.wav').write_bytes(b'interrupted audio file')
    rows,info=alignment.place(p,tmp_path/'other.wav',['C','G','Am','F'],'https://example.test/chart')
    assert not info['bassEvidence']
    assert [next(c['label'] for c in rows if c['start']<=time<c['end']) for time in (1,3,5,7)]==['C','G','Am','F']


def test_unsectioned_chart_keeps_written_order_but_tabs_are_not_a_second_score(monkeypatch):
    provider=next(p for p in sources.PROVIDERS if p['id']=='cifraclub')
    url='https://www.cifraclub.com/artist/song/'
    page='<title>Song - Artist</title><nav><b>A</b></nav><pre><b>C</b><b>G</b><b>C</b></pre>'
    monkeypatch.setattr(sources,'fetch',lambda u:(page,u))
    source=sources._read_chart(provider,'Song','Artist',url)[2]
    assert source['chordSequence']==['C','G','C'] and source['chords']==['C','G']
    page=page.replace('<pre>','<pre>e|---0---3---\n')
    assert sources._read_chart(provider,'Song','Artist',url)[2]['chordSequence']==[]


def test_incompatible_written_order_is_rejected_by_audio():
    scores=np.tile([.95,.10],(32,1))
    assert alignment.ordered_path(scores,['C','F'],['F']*8) is None


def structure_fixture():
    mid=np.arange(.125,16,.25);features=dict(middle=mid,available=np.ones(3))
    vectors=np.zeros((len(mid),12));vectors[mid<8,0]=1;vectors[mid>=8,7]=1
    for key in ('harmony','bass'):features[key]=vectors.copy()
    features['texture']=np.ones((len(mid),6));features['voiceEnergy']=features['drumsEnergy']=np.ones(len(mid))
    p=song();p.update(beats=np.arange(0,16,.5).tolist(),downbeats=[0,4,8,12],sections=[dict(id='a',start=0,end=7.4,name='Intro',origin='analysis'),dict(id='b',start=7.4,end=16,name='Couplet',origin='analysis')])
    p['tracks']=[dict(role='source',duration=16,offset=0)];p['settings']['gridMode']='detected'
    return p,features


def test_joint_harmonic_arrival_refines_only_an_unprotected_anticipation():
    p,f=structure_fixture();rows,changes=section_evidence.refine(p,f)
    assert rows[1]['start']==rows[0]['end']==8 and len(changes)==1
    assert p['sections'][1]['start']==7.4
    for field,value in [('locked',True),('reviewed',True),('origin','manual')]:
        q=copy.deepcopy(p);q['sections'][0][field]=value
        assert section_evidence.refine(q,f)[0]==q['sections']


def test_a_vocal_or_drum_fill_alone_does_not_move_a_boundary():
    p,f=structure_fixture();f['bass'][:]=f['bass'][0];f['harmony'][:]=f['harmony'][0]
    f['voiceEnergy'][f['middle']>8]=5;f['drumsEnergy'][f['middle']>8]=5
    assert section_evidence.refine(p,f)[0]==p['sections']


def test_rounded_reference_can_use_multiple_interior_landmarks_without_manual_review():
    entries=[dict(time=t,name=name) for t,name in [(1,'Intro'),(17,'Verse'),(53,'Chorus'),(71,'Verse'),(106,'Chorus'),(131,'Solo'),(148,'Chorus'),(177,'Outro')]]
    local=[dict(start=t,name=name) for t,name in [(0,'Intro'),(17.88,'Couplet'),(52.56,'Refrain'),(71.52,'Couplet'),(106.32,'Refrain'),(131.89,'Instrumental'),(147.73,'Refrain'),(178.69,'Couplet')]]
    anchors=structure_review.reference_anchors(local,entries,list(range(0,208,2)),207)
    assert len(anchors)>=4 and all(not a[2] for a in anchors)
    wrong=copy.deepcopy(local)
    for i,row in enumerate(wrong):row['start']+=i*5
    assert len(structure_review.reference_anchors(wrong,entries,list(range(0,208,2)),207))<4


def test_fast_real_changes_are_not_smoothed_into_a_long_chord(tmp_path):
    expected=['C','G','Am','F']*3
    p=render(tmp_path,expected,lead=False,seconds=.5)
    rows,_=alignment.place(p,tmp_path/'other.wav',['C','G','Am','F'],'https://example.test/chart')
    assert [next(c['label'] for c in rows if c['start']<=i*.5+.25<c['end']) for i in range(len(expected))]==expected


def test_held_bass_pedal_does_not_erase_guitar_chord_changes(tmp_path):
    p=render(tmp_path,['C','F','G','F'],lead=False)
    sr=16000;t=np.arange(sr*8)/sr;hz=440*2**((36-69)/12)
    sf.write(tmp_path/'bass.wav',sum(.18*.7**(h-1)*np.sin(2*np.pi*hz*h*t) for h in range(1,7)),sr)
    rows,_=alignment.place(p,tmp_path/'other.wav',['C','F','G'],'https://example.test/chart')
    assert [next(c['label'] for c in rows if c['start']<=time<c['end']) for time in (1,3,5,7)]==['C','F','G','F']


def test_bass_fifth_is_not_forced_as_a_new_major_chord(tmp_path):
    expected=['D','E','D','E'];p=render(tmp_path,expected,lead=False)
    sr=16000;t=np.arange(sr*2)/sr;pieces=[]
    for note in (45,40,45,40):
        hz=440*2**((note-69)/12);pieces.append(sum(.18*.7**(h-1)*np.sin(2*np.pi*hz*h*t) for h in range(1,7)))
    sf.write(tmp_path/'bass.wav',np.concatenate(pieces),sr)
    rows,_=alignment.place(p,tmp_path/'other.wav',['D','E','A'],'https://example.test/chart')
    assert [next(c['label'] for c in rows if c['start']<=time<c['end']) for time in (1,3,5,7)]==expected


def test_detuned_recording_uses_one_concert_pitch_for_harmony_and_bass(tmp_path):
    labels=['Am','E','Dm','Am','C','G','D','A'];p=render(tmp_path,labels,cents=-40)
    rows,info=alignment.place(p,tmp_path/'other.wav',list(dict.fromkeys(labels)),'https://example.test/chart')
    correct=sum(max(0,min(c['end'],(i+1)*2)-max(c['start'],i*2)) for c in rows for i,label in enumerate(labels) if c['label']==label)/16
    assert correct>=.85 and abs(info['tuningCents']+40)<8


@pytest.mark.parametrize('steps',[0,2,7])
def test_inversion_is_resolved_from_bass_without_competing_with_its_own_harmony(tmp_path,steps):
    names=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
    root=names[(2+steps)%12];third=names[(6+steps)%12]
    expected=[root+'/'+third,root,root+'/'+third,root]
    p=render(tmp_path,expected,lead=False)
    rows,_=alignment.place(p,tmp_path/'other.wav',[root,root+'/'+third,names[(7+steps)%12]],'https://example.test/chart')
    for at,label in zip((1,3,5,7),expected):
        row=next(c for c in rows if c['start']<=at<c['end'])
        assert row['label']==label and row['confidence']>=.5


def test_a_sustained_bass_does_not_become_a_new_root_at_its_last_beats():
    edges=np.arange(0,5.25,.25);chroma=np.zeros((20,12));active=np.ones(20,dtype=bool)
    chroma[:16,9]=1;chroma[16:18,7]=1;chroma[18:,6]=1
    # The last full second still belongs to the same pedal, before two short
    # genuinely different bass notes. A centred window missed this ending.
    pedal=alignment.bass_pedals(chroma,active,edges,.5)
    assert pedal[:16].all() and not pedal[16:].any()
    active[8:12]=False
    assert not alignment.bass_pedals(chroma,active,edges,.5).any()


def test_a_wrong_written_inversion_cannot_be_reported_as_certain(tmp_path):
    p=render(tmp_path,['D','D','D','D'],lead=False)
    rows,_=alignment.place(p,tmp_path/'other.wav',['D/F#','G'],'https://example.test/chart')
    assert rows and all(c['confidence']<.5 for c in rows if c['label']=='D/F#')


@pytest.mark.parametrize('expected',[['D','D4','G','D'],['C6','Am7','C6','Am7']])
def test_suspensions_and_relative_chords_are_not_merged_as_inversions(tmp_path,expected):
    p=render(tmp_path,expected,lead=False)
    rows,_=alignment.place(p,tmp_path/'other.wav',list(dict.fromkeys(expected)),'https://example.test/chart')
    assert [next(c['label'] for c in rows if c['start']<=at<c['end']) for at in (1,3,5,7)]==expected


def test_a_section_cue_does_not_pull_the_first_written_chord_forward(tmp_path):
    p=render(tmp_path,['E5','A','A','D','D','G','G','A'],lead=False,seconds=1)
    p['sections']=[dict(id='a',name='Intro',start=0,end=.5),dict(id='b',name='Refrain',start=.5,end=8)]
    before=copy.deepcopy(p['sections'])
    rows,_=alignment.place(p,tmp_path/'other.wav',['E5','A','D','G'],'https://example.test/chart',
                           sections={'chorus':['A','D','G']},sequences=[dict(kind='chorus',chords=['A','D','G','A'],repeat=1)])
    assert next(c['label'] for c in rows if c['start']<=.75<c['end'])=='E5'
    assert next(c['label'] for c in rows if c['start']<=1.25<c['end'])=='A'
    assert p['sections']==before


def test_a_passing_bass_note_cannot_create_confidence_against_the_harmony():
    candidates=[(c,alignment.tones(c)) for c in ('C','G')]
    edges=np.arange(0,2.25,.25);chroma=np.zeros((8,12));chroma[:,0]=1
    chroma[3]=0;chroma[3,11]=1
    bass=dict(chroma=chroma,active=np.ones(8,dtype=bool))
    contradiction=alignment.bass_contradictions(candidates,bass,edges,.5,np.zeros(8,dtype=bool))
    assert not contradiction[3].any()  # B is a passing note, not evidence against C.
    assert not alignment.bass_contradictions(candidates,bass,edges,.5,np.ones(8,dtype=bool)).any()


def test_inversions_work_with_only_the_harmonic_audio(tmp_path):
    p=render(tmp_path,['D/F#','D'],lead=False,bass=False)
    sr=16000;t=np.arange(sr*2)/sr;parts=[]
    for voicing in ([54,62,69],[50,66,69]):
        parts.append(sum(.08/h*np.sin(2*np.pi*440*2**((note-69)/12)*h*t) for note in voicing for h in (1,2,3)))
    sf.write(tmp_path/'other.wav',np.concatenate(parts),sr)
    rows,info=alignment.place(p,tmp_path/'other.wav',['D','D/F#','G'],'https://example.test/chart')
    assert not info['bassEvidence']
    assert [next(c['label'] for c in rows if c['start']<=at<c['end']) for at in (1,3)]==['D/F#','D']
