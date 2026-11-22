"""Invented lyrics test damaged transcripts, code switching and missing passages."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import lyrics_alignment as la
import lyrics_reference as lr


def timed(text,start):
    words=lr.tokens(text)
    return dict(t=start,end=start+len(words)*.4,text=text,
                words=[dict(w=w,t=start+i*.4,end=start+i*.4+.3) for i,w in enumerate(words)])


def test_sparse_recognizable_words_confirm_reference_without_asr_majority():
    clean=['violet windows beside the railway','golden lanterns along the river',
           'silver mountains beyond the forest','distant thunder above the valley',
           'winter gardens behind the station','morning sunlight beneath the branches']
    damaged=['violet windows nonsense broken noise','golden lanterns nonsense broken noise',
             'silver mountains nonsense broken noise','distant thunder nonsense broken noise',
             'winter gardens nonsense broken noise','morning sunlight nonsense broken noise']
    segments=[timed(row,5+i*10) for i,row in enumerate(damaged)]
    p=la.plan(segments,'\n'.join(clean))
    assert .2<=p['agreement']<.45 and p['confirmed']
    assert len(p['anchors'])>=6
    jobs,_=la.windows(segments,p,70)
    assert [w for j in jobs for w in lr.tokens(j['text'])]==p['words']
    assert all(0<=j['t0']<j['t1']<=70 for j in jobs)


def test_common_words_do_not_identify_unrelated_reference():
    segments=[timed('the moon and the forest in the night',5),timed('the river and the meadow in the rain',20)]
    p=la.plan(segments,'a city by the sea with the hotel\na station for the train from the north')
    assert not p['confirmed']


def test_split_apostrophes_and_missing_word_cannot_become_fake_anchors():
    row=dict(t=2,end=5,text="l'oiseau voit la rivière",words=[
        dict(w='l',t=2,end=2.1),dict(w="'oiseau",t=2.1,end=2.8),
        dict(w='la',t=3.5,end=3.6),dict(w='rivière',t=3.6,end=4.5)])
    words=la.observed_words([row])
    assert words[0]['timed'] and words[0]['t']==2 and words[0]['end']==2.8
    assert not words[1]['timed']
    assert words[-1]['t']==3.6


def test_credits_do_not_extend_alignment_into_instrumental_tail():
    segments=[timed('golden lanterns follow the morning',10),
              timed('Sous-titres réalisés par la communauté Amara.org',90)]
    p=la.plan(segments,'golden lanterns follow the morning')
    jobs,_=la.windows(segments,p,100)
    assert jobs[-1]['t1']<20


def test_missing_words_and_repeated_refrains_stay_in_reference_order():
    text='bright lanterns in the station\nnew verses behind the clouds\nbright lanterns in the station'
    segments=[timed('bright lanterns in the station',3),timed('bright lanterns in the station',30)]
    p=la.plan(segments,text);jobs,_=la.windows(segments,p,40)
    assert [w for j in jobs for w in lr.tokens(j['text'])]==lr.tokens(text)


def test_selected_reference_is_bound_to_song_and_survives_offline(tmp_path):
    (tmp_path/'References').mkdir()
    selected=dict(title='Silver Road',artist='Test Artist',text='Correct reference words',
                  confirmed=True,url='https://example.org/song',publisher='Chosen source')
    (tmp_path/'References/lyrics-selected.json').write_text(json.dumps(selected))
    project=dict(name='Test Artist - Silver Road',_root=str(tmp_path))
    sources,_=lr.lookup(project,100,lambda url:pytest.fail('must work offline'))
    assert sources[0]['text']==selected['text'] and sources[0]['confirmed']
    project['name']='Another Artist - Another Song'
    assert not lr.lookup(project,100,lambda url:{})[0]


def test_code_switching_selects_multilingual_alignment():
    assert la.language_for('aqui para nosotros','fr')=='es'
    assert la.language_for('les lumières dans la forêt','fr')=='fr'


def test_backing_responses_do_not_penalize_complete_reference_during_source_comparison():
    text='bright lanterns in the station\n(Keep moving)\nnew verses behind the clouds'
    proposal=la.plan([timed('bright lanterns in the station',3)],text)
    assert la.comparison_words(proposal)==lr.tokens('bright lanterns in the station new verses behind the clouds')
    assert proposal['texts']==text.splitlines()  # Import still includes backing lyrics.
    parenthesized=la.plan([timed('keep moving',3)],'(Keep moving)')
    assert la.comparison_words(parenthesized)==['Keep','moving']


def test_backing_responses_are_aligned_between_primary_phrases_without_moving_them(tmp_path,monkeypatch):
    segments=[timed('sky shines',1),timed('moon rises',8)]
    proposal=la.plan(segments,'sky shines\n(Stay)\n(Stay)\nmoon rises\n(Stay)')
    calls=[]
    def align(audio,jobs,language,folder):
        calls.append(jobs)
        if len(calls)==1:
            assert jobs[0]['text']=='sky shines moon rises'
            return [dict(id=jobs[0]['id'],score=.9,words=[dict(w=w,t=a,end=b,score=.9)
                for w,a,b in [('sky',1,1.2),('shines',1.5,4.5),('moon',8,8.2),('rises',8.5,9)]])]
        assert [(j['text'],j['t0'],j['t1']) for j in jobs]==[('Stay Stay',4.5,8),('Stay',9,12)]
        return [dict(id=j['id'],score=.8,words=[dict(w=w,t=j['t0']+.2+k*.4,end=j['t0']+.4+k*.4,score=.8)
            for k,w in enumerate(j['text'].split())]) for j in jobs]
    monkeypatch.setattr(la,'acoustic_align',align)
    monkeypatch.setattr(la,'refine',lambda audio,p,jobs,aligned,*args:(jobs,aligned))
    p,jobs,aligned,position=la.align_reference('audio',segments,proposal,12,'en',tmp_path)
    rows,review=la.reconstruct(segments,p,jobs,aligned,position,dict(url='source'))
    assert [r['text'] for r in rows]==proposal['texts']
    assert rows[0]['words'][-1]['end']==4.5 and rows[3]['words'][0]['t']==8
    assert review==0 and all(a['end']<=b['t'] for a,b in zip(rows,rows[1:]))


def test_long_sung_note_remains_inside_refined_window(tmp_path,monkeypatch):
    proposal=la.plan([timed('golden mountains',1)],'golden mountains')
    jobs=[dict(id='0',text='golden mountains',first=0,last=2,t0=0,t1=7)]
    aligned=[dict(id='0',score=.9,words=[dict(w='golden',t=1,end=1.5,score=.9),
                                      dict(w='mountains',t=2,end=5.5,score=.8)])]
    captured=[]
    monkeypatch.setattr(la,'ctc_align',lambda audio,group,*args:captured.extend(group) or [])
    la.refine('audio',proposal,jobs,aligned,'en',tmp_path)
    assert captured[0]['t1']>5.5


def test_repeat_count_rejects_words_stretched_over_unsung_passages():
    def candidate(n,score,length):
        return dict(count=n,pathScore=score,words=[dict(w='lanterns',t=1,end=1+length)])
    variants=[candidate(2,-.1,13),candidate(3,-.11,12),candidate(4,-.15,.5),candidate(9,-.7,.1)]
    assert la.choose_repetition(variants,9)['count']==4
    assert la.choose_repetition([candidate(4,-.15,.5),candidate(9,-.17,.5)],9) is None


def test_bad_boundary_removes_word_timing_instead_of_faking_it():
    source=dict(url='https://example.org/song')
    proposal=dict(words=['golden','lanterns'],rows=[['golden'],['lanterns']])
    jobs=[dict(id='0',first=0,last=1,t0=0,t1=2),dict(id='1',first=1,last=2,t0=1,t1=3)]
    aligned=[dict(id='0',score=.9,words=[dict(w='golden',t=.2,end=1.8,score=.9)]),
             dict(id='1',score=.9,words=[dict(w='lanterns',t=1.6,end=2.5,score=.9)])]
    rows,review=la.reconstruct([],proposal,jobs,aligned,lambda x:x,source)
    assert rows[0]['end']==rows[1]['t']
    assert review==2 and all(not r['words'] for r in rows)
