"""Invented texts exercise correction without a copyrighted/network fixture."""
import copy
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import lyrics_reference as lr


@pytest.fixture
def song():
    return dict(name='Test Artist - Silver Road (Official Video)', tracks=[dict(role='source',duration=100)],lyrics=[])


def transcript():
    return dict(language='en',segments=[dict(t=10,end=14,text='we follow the silver load',words=[]),
           dict(t=20,end=24,text='we carry the morning light',words=[])])


def provider(url):
    text='We follow the silver road\nWe carry the morning light'
    if 'lrclib' in url:
        return [dict(id=12,artistName='Test Artist',trackName='Silver Road',duration=100,plainLyrics=text)]
    return dict(lyrics=text)


def aligned(audio,jobs,language,folder):
    # Unequal synthetic timings: acceptance must preserve the aligner's output.
    return [dict(id=j['id'],score=.4 if j['id'].startswith('original:') else .9,words=[dict(w=w,t=j['t0']+i*.33,end=j['t0']+i*.33+.2,score=.9)
            for i,w in enumerate(lr.tokens(j['text']))]) for j in jobs]


def test_corrects_only_supported_words_and_uses_acoustic_timestamps(song,tmp_path):
    original=transcript()
    result=lr.correct(song,original,'vocals.wav',tmp_path,fetcher=provider,aligner=aligned)
    assert original==transcript()
    assert result['segments'][0]['text']=='We follow the silver road'
    assert result['segments'][0]['words'][1]['t']==pytest.approx(9.98)
    assert result['segments'][1]==original['segments'][1]
    assert result['lyricsReference']['corrected']==1
    assert result['segments'][0]['sourceURL']=='https://lrclib.net/api/get/12'


@pytest.mark.parametrize('failure',['error','weak','outside','overlap','missing','weak_line'])
def test_bad_alignment_never_replaces_existing_text_or_timings(song,tmp_path,failure):
    original=transcript()
    def broken(*args):
        rows=aligned(*args)
        if failure=='error':raise RuntimeError('unavailable')
        if failure=='weak':rows[0]['words'][0]['score']=.01
        if failure=='outside':rows[0]['words'][0]['t']=-1
        if failure=='overlap':rows[0]['words'][0]['end']=13
        if failure=='missing':rows[0]['words'].pop()
        if failure=='weak_line':rows[0]['score']=.1
        return rows
    result=lr.correct(song,original,'vocals',tmp_path,fetcher=provider,aligner=broken)
    assert result['segments']==original['segments']
    assert result['lyricsReference']['corrected']==0


def test_manual_corrections_and_unknown_languages_are_retained(song,tmp_path):
    original=transcript();original['segments'][0]['manual']=True
    result=lr.correct(song,original,'vocals',tmp_path,fetcher=provider,aligner=lambda *a:pytest.fail('manual alignment'))
    assert result['segments']==original['segments']
    original=transcript();original['language']='de'
    result=lr.correct(song,original,'vocals',tmp_path,fetcher=provider,aligner=lambda *a:pytest.fail('wrong language'))
    assert result['segments']==original['segments']


def test_catalog_agreement_does_not_claim_independent_acoustic_confidence(song,tmp_path):
    def plausible(*args):
        rows=aligned(*args);rows[0]['score']=.3;return rows
    result=lr.correct(song,transcript(),'vocals',tmp_path,fetcher=provider,aligner=plausible)
    assert result['lyricsReference']['corrected']==1
    assert result['lyricsReference']['timingReview']==1
    result=lr.correct(song,transcript(),'vocals',tmp_path,
                      fetcher=lambda url:provider(url) if 'lrclib' in url else {},aligner=plausible)
    assert result['lyricsReference']['corrected']==0


def test_wrong_artist_live_version_and_duration_are_rejected(song):
    def wrong(url):
        if 'lyrics.ovh' in url:return {}
        rows=provider(url)
        return [{**rows[0],'artistName':'Someone Else'}, {**rows[0],'trackName':'Silver Road Live'}, {**rows[0],'duration':180}]
    assert lr.lookup(song,100,wrong)[0]==[]


def test_cache_and_throttle_do_not_retry_on_immediate_repeat(song,tmp_path):
    song['_root']=str(tmp_path);calls=[]
    def limited(url):
        calls.append(url)
        raise HTTPError(url,429,'Slow down',{'Retry-After':'900'},None)
    assert lr.lookup(song,100,limited,now=100)[0]==[]
    assert lr.lookup(song,100,limited,now=800)[0]==[]
    assert len(calls)==2
    lr.lookup(song,100,limited,now=1001)
    assert len(calls)==4


def test_offline_and_unrelated_text_leave_the_transcript_intact(song,tmp_path):
    for fetcher in (lambda url:dict(lyrics='Completely unrelated text about a distant country'),
                    lambda url:(_ for _ in ()).throw(OSError('offline'))):
        original=transcript()
        result=lr.correct(song,original,'vocals',tmp_path,fetcher=fetcher,aligner=lambda *a:pytest.fail('unmatched'))
        assert result['segments']==original['segments']


def test_repeated_choruses_keep_order_and_missing_verses_are_not_invented():
    original=[dict(t=2,end=6,text='follow my silver load'),dict(t=50,end=54,text='follow my silver load')]
    jobs,agreement=lr.proposals(original,'follow my silver road\nfollow my silver road')
    assert [j['t0'] for j in jobs]==[1.65,49.65]
    assert len(jobs)==2 and agreement>.5
    jobs,_=lr.proposals(original,'a long unheard introduction never sung here\nfollow my silver road\nfollow my silver road')
    assert all('unheard' not in job['text'] for job in jobs)


def test_existing_words_are_converted_to_audio_time_without_mutation(song):
    song['lyrics']=[dict(start=11,end=15,text='we follow your light and the road',words=[dict(start=11.2,end=11.5,text='we')])]
    saved=copy.deepcopy(song)
    value=lr.existing_transcription(song,1)
    assert song==saved and value['language']=='en'
    assert value['segments'][0]['t']==10
    assert value['segments'][0]['words'][0]['t']==pytest.approx(10.2)


@pytest.mark.parametrize('url',['http://lrclib.net/api/search','https://evil.example/','https://lrclib.net@evil.example/','https://lrclib.net:444/'])
def test_provider_addresses_are_restricted(url):
    assert not lr.safe_url(url)


def test_host_correction_persists_provenance_and_undo_restores_original(tmp_path,monkeypatch):
    from test_studio_windows import fixture,Api,ENGINE
    root=tmp_path/'song';p=fixture(root)
    p['lyrics']=[dict(id='manual',start=0,end=.4,text='my manual words',manual=True),
                 dict(id='auto',start=.8,end=1.5,text='we take the load',manual=False)]
    api=Api(ENGINE,tmp_path);api._root=root;api._project=p;api._audio.load(p,root)
    result=dict(segments=[dict(t=0,end=.4,text='should not replace',words=[]),
        dict(t=.8,end=1.5,text='we take the road',words=[dict(t=.8,end=.9,w='we')],sourceURL='https://lrclib.net/api/get/12')],
        lyricsReference=dict(status='corrected',message='Une ligne corrigée.',sources=['LRCLIB'],corrected=1,review=0))
    def work(kind,audio,args):
        assert kind=='lyricscorrect' and str(audio).endswith('source.wav')
        return root/'result.json',result
    monkeypatch.setattr(api,'_work',work)
    api._analysis('lyricscorrect',dict(reanalyze=True))
    from windows import project as model
    saved=model.load(root)
    assert saved['lyrics'][0]['text']=='my manual words'
    assert saved['lyrics'][1]['text']=='we take the road'
    assert saved['lyricsReference']==result['lyricsReference']
    api.command(dict(command='undo',projectID=p['id'],args={}))
    assert api._project['lyrics'][1]['text']=='we take the load'


def test_manual_timing_is_saved_and_protected_from_later_online_correction(tmp_path,monkeypatch):
    from test_studio_windows import fixture,Api,ENGINE
    from windows import project as model
    root=tmp_path/'song';p=fixture(root)
    p['lyrics']=[dict(id='line',start=.5,end=1.5,text='Silver road',manual=False)]
    api=Api(ENGINE,tmp_path);api._root=root;api._project=p;api._audio.load(p,root)
    api.command(dict(command='annotation',projectID=p['id'],args=dict(kind='lyrics',id='line',
        text='Silver road',start=.6,end=1.6,words=[dict(text='Silver',start=.6,end=1),dict(text='road',start=1.1,end=1.6)])))
    stored=model.load(root)['lyrics'][0]
    assert stored['manual'] is True and stored['start']==.6 and stored['words'][1]['start']==1.1
    result=dict(segments=[dict(t=.5,end=1.5,text='New guess',words=[])],lyricsReference=dict(
        status='review',message='À vérifier',sources=['LRCLIB'],corrected=0,review=1))
    monkeypatch.setattr(api,'_work',lambda *a:(root/'result.json',result))
    api._analysis('lyricscorrect',dict(reanalyze=True))
    assert model.load(root)['lyrics']==[stored]
