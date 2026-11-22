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
    # Unequal acoustic timings must survive the reference replacement exactly.
    return [dict(id=j['id'],score=.8,words=[dict(w=w,t=j['t0']+i*.33,end=j['t0']+i*.33+.2,score=.9)
            for i,w in enumerate(lr.tokens(j['text']))]) for j in jobs]


def test_reference_replaces_every_automatic_line_and_preserves_acoustic_timestamps(song,tmp_path):
    original=transcript()
    result=lr.correct(song,original,'vocals.wav',tmp_path,fetcher=provider,aligner=aligned)
    assert original==transcript()
    assert [s['text'] for s in result['segments']]==['We follow the silver road','We carry the morning light']
    words=[w for s in result['segments'] for w in s['words']]
    assert words[1]['t']-words[0]['t']==pytest.approx(.33)
    assert words[0]['end']-words[0]['t']==pytest.approx(.2)
    assert result['lyricsReference']['corrected']==2
    assert result['segments'][0]['sourceURL']=='https://lrclib.net/api/get/12'


@pytest.mark.parametrize('failure',['error','outside','overlap','missing','nan'])
def test_alignment_failure_keeps_confirmed_text_without_fabricated_word_timings(song,tmp_path,failure):
    def broken(*args):
        rows=aligned(*args)
        if failure=='error':raise RuntimeError('unavailable')
        if failure=='outside':rows[0]['words'][0]['t']=-1
        if failure=='overlap':rows[0]['words'][0]['end']=13
        if failure=='missing':rows[0]['words'].pop()
        if failure=='nan':rows[0]['words'][0]['end']=float('nan')
        return rows
    result=lr.correct(song,transcript(),'vocals',tmp_path,fetcher=provider,aligner=broken)
    assert result['segments'][0]['text']=='We follow the silver road'
    assert all(not s['words'] for s in result['segments'])
    assert result['lyricsReference']['timingReview']==2


def test_weak_acoustics_never_restore_wrong_asr_words(song,tmp_path):
    def weak(*args):
        rows=aligned(*args);rows[0]['words'][0]['score']=.01;return rows
    result=lr.correct(song,transcript(),'vocals',tmp_path,fetcher=provider,aligner=weak)
    assert result['segments'][0]['text']=='We follow the silver road'
    assert result['lyricsReference']['timingReview']==1


def test_manual_corrections_are_retained_verbatim(song,tmp_path):
    original=transcript();original['segments'][0]['manual']=True
    result=lr.correct(song,original,'vocals',tmp_path,fetcher=provider,aligner=aligned)
    assert original['segments'][0] in result['segments']


def test_multilingual_reference_is_sent_to_acoustic_aligner(song,tmp_path):
    original=transcript();original['language']='es';languages=[]
    def capture(audio,jobs,language,folder):
        languages.append(language);return aligned(audio,jobs,language,folder)
    result=lr.correct(song,original,'vocals',tmp_path,fetcher=provider,aligner=capture)
    assert languages==['es'] and result['lyricsReference']['corrected']==2


def test_competing_references_are_resolved_automatically_and_imported_in_full(song,tmp_path):
    full='We follow the silver road\n(Keep moving)\nWe carry the morning light'
    def variants(url):
        if 'lrclib' in url:return [{**provider(url)[0],'plainLyrics':full}]
        return dict(lyrics='We follow the silver load\nWe carry morning lights')
    compared=[]
    def score(audio,proposals,segments,language,folder):
        compared.extend(p['texts'] for p in proposals)
        return [-.1 if p['texts']==full.splitlines() else -.3 for p in proposals]
    result=lr.correct(song,transcript(),'vocals',tmp_path,fetcher=variants,aligner=aligned,reference_scorer=score)
    assert len(compared)==2
    assert [s['text'] for s in result['segments']]==full.splitlines()
    assert result['lyricsReference']['status']=='corrected'
    assert result['lyricsReference']['sources']==['LRCLIB']
    assert 'automatiquement' in result['lyricsReference']['message']


@pytest.mark.parametrize('scores',[None,[-.1,-.105],[float('nan'),-.1],[-.1]])
def test_inconclusive_audio_uses_recognized_content_instead_of_blocking_or_short_text_bias(tmp_path,scores):
    # A shorter, misspelt source can have a slightly higher ASR ratio while
    # explaining fewer distinctive words. Regression for the Uprising block.
    full=(.797,dict(publisher='Complete'),dict(confirmed=True,supported=89))
    short=(.802,dict(publisher='Short'),dict(confirmed=True,supported=84))
    def scorer(*args):
        if scores is None:raise RuntimeError('No acoustic model')
        return scores
    chosen,reason=lr.select_reference([short,full],'audio',[],'en',tmp_path,scorer)
    assert chosen==full and 'mots reconnus' in reason


def test_explicit_reference_is_not_replaced_by_automatic_selection(tmp_path):
    chosen=(.5,dict(confirmed=True),dict(confirmed=True,supported=10))
    assert lr.select_reference([chosen,(.9,{},dict(confirmed=True,supported=20))],
        'audio',[],'en',tmp_path,lambda *a:pytest.fail('explicit selection'))[0]==chosen


def test_full_vocals_are_used_with_their_own_offset_and_project_boundaries(tmp_path):
    (tmp_path/'vocals.wav').touch();(tmp_path/'lead.wav').touch()
    song=dict(_root=str(tmp_path),tracks=[dict(role='vocal_lead',file='lead.wav',offset=2),
                                        dict(role='vocals',file='vocals.wav',offset=5)])
    assert lr.correction_audio(song,tmp_path/'lead.wav')==(str(tmp_path/'vocals.wav'),5)
    song['tracks'][1]['file']='../outside.wav'
    assert lr.correction_audio(song,tmp_path/'lead.wav')==(str(tmp_path/'lead.wav'),2)
    assert lr.correction_audio({},tmp_path/'lead.wav',3)==(str(tmp_path/'lead.wav'),3)


def test_worker_translates_asr_anchors_to_full_vocals_then_back_to_project_time(tmp_path,monkeypatch):
    import json,os
    from types import SimpleNamespace
    import worker,compute,analysis_cache
    monkeypatch.setattr(os,'environ',os.environ.copy())
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setattr(compute,'versions',lambda *a:None)
    monkeypatch.setattr(analysis_cache,'runtime_caches',lambda *a:None)
    monkeypatch.setattr(worker,'progress',lambda *a,**kw:None)
    (tmp_path/'lead.wav').touch();(tmp_path/'vocals.wav').touch()
    p=dict(_root=str(tmp_path),tracks=[dict(role='vocal_lead',file='lead.wav',offset=2),dict(role='vocals',file='vocals.wav',offset=5)],
           lyrics=[dict(start=12,end=14,text='Silver road',manual=False,words=[dict(start=12,end=13,text='Silver')])])
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    def correct(project,transcription,audio,folder):
        assert audio==str(tmp_path/'vocals.wav')
        assert transcription['segments'][0]['t']==7 and transcription['segments'][0]['words'][0]['t']==7
        return transcription
    monkeypatch.setattr(lr,'correct',correct)
    output=tmp_path/'result.json'
    worker.execute(SimpleNamespace(engine=str(tmp_path),input=str(tmp_path/'lead.wav'),output=str(output),
        project=str(snapshot),command='lyricscorrect',language='en'))
    saved=json.loads(output.read_text())['segments'][0]
    assert saved['t']==12 and saved['end']==14 and saved['words'][0]['t']==12


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
