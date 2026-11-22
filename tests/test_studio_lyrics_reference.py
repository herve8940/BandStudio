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


def test_progress_separates_transcription_web_lookup_and_alignment(song,tmp_path):
    from types import SimpleNamespace
    import json
    import analysis_progress as progress
    out=tmp_path/'result.json';module=SimpleNamespace(_write_status=lambda *a,**kw:None)
    def read():return json.loads((tmp_path/'progress.json').read_text())
    def lookup(url):
        assert read()['progress']==pytest.approx(100/3) and 'Internet' in read()['progressLabel']
        return provider(url)
    def listening(*args):
        assert read()['progress']==pytest.approx(200/3) and 'Recalage' in read()['progressLabel']
        return aligned(*args)
    with progress.reporting(out,'lyrics'):
        with progress.legacy_status(module,phases=3):
            module._write_status(None,'running',step='2/4',done=1,total=4)
            assert read()['progress']==pytest.approx(100/12)
            module._write_status(None,'done')
            assert read()['progress']==pytest.approx(100/3)
        out.write_text(json.dumps(lr.correct(song,transcript(),'vocals',tmp_path,fetcher=lookup,aligner=listening)))
        assert not read().get('finished')
    assert read()['progress']==100 and read()['finished']


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


def test_correct_empty_lyrics_transcribes_before_verifying_online_reference(tmp_path,monkeypatch):
    import json,os
    from types import SimpleNamespace
    import worker,compute,analysis_cache
    monkeypatch.setattr(os,'environ',os.environ.copy())
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setattr(compute,'versions',lambda *a:None)
    monkeypatch.setattr(analysis_cache,'runtime_caches',lambda *a:None)
    monkeypatch.setattr(worker,'progress',lambda *a,**kw:None)
    p=dict(tracks=[dict(role='source',offset=0)],lyrics=[])
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(p))
    events=[]
    def transcribe(audio,output,**options):
        assert options['model_name']=='same-quality-model'
        events.append('transcribe')
        Path(output).write_text(json.dumps(dict(language='en',segments=[dict(t=1,end=2,text='Recognized words')])));
        return 0
    module=SimpleNamespace(transcribe=transcribe,selected_model=lambda:'same-quality-model',_write_status=lambda *a,**kw:None)
    monkeypatch.setitem(sys.modules,'reacue_transcribe',module)
    def correct(project,transcription,audio,folder):
        assert transcription['segments'][0]['text']=='Recognized words'
        events.append('verify-reference');return transcription
    monkeypatch.setattr(lr,'correct',correct)
    output=tmp_path/'result.json'
    worker.execute(SimpleNamespace(engine=str(tmp_path),input=str(tmp_path/'source.wav'),output=str(output),
                   project=str(snapshot),command='lyricscorrect',language='en'))
    assert events==['transcribe','verify-reference']
    assert json.loads(output.read_text())['segments'][0]['t']==1


def test_wrong_artist_and_different_song_are_rejected(song):
    def wrong(url):
        if 'lrclib' not in url:return {}
        rows=provider(url)
        return [{**rows[0],'artistName':'Someone Else'}, {**rows[0],'trackName':'Another Road'}]
    assert lr.lookup(song,100,wrong)[0]==[]


def test_cache_and_throttle_do_not_retry_on_immediate_repeat(song,tmp_path):
    song['_root']=str(tmp_path);calls=[]
    def limited(url):
        calls.append(url)
        raise HTTPError(url,429,'Slow down',{'Retry-After':'900'},None)
    assert lr.lookup(song,100,limited,now=100)[0]==[]
    assert lr.lookup(song,100,limited,now=800)[0]==[]
    assert len(calls)==4  # Once per publisher; title variants do not retry a 429.
    lr.lookup(song,100,limited,now=1001)
    assert len(calls)==8


def test_offline_and_unrelated_text_leave_the_transcript_intact(song,tmp_path):
    for fetcher in (lambda url:dict(lyrics='Completely unrelated text about a distant country'),
                    lambda url:(_ for _ in ()).throw(OSError('offline'))):
        original=transcript()
        result=lr.correct(song,original,'vocals',tmp_path,fetcher=fetcher,aligner=lambda *a:pytest.fail('unmatched'))
        assert result['segments']==original['segments']


def test_offline_after_a_success_reuses_only_the_matching_edition(song,tmp_path):
    song['_root']=str(tmp_path)
    original,_=lr.lookup(song,100,provider,now=1)
    assert {s['publisher'] for s in original}=={'LRCLIB','lyrics.ovh'}
    def failure(url):
        if 'lrclib' in url:raise HTTPError(url,404,'removed',{},None)
        raise TimeoutError('temporarily offline')
    cached,_=lr.lookup(song,100,failure,now=86402)
    assert len(cached)==1 and cached[0]['publisher']=='lyrics.ovh' and cached[0]['cachedCopy']
    assert cached[0]['text']==original[1]['text']
    assert lr.lookup(song,100,lambda _:pytest.fail('retry too early'),now=86403)[0]==cached
    assert lr.lookup(song,140,failure,now=86404)[0]==[]


def test_synchronized_edition_checks_local_line_starts_and_preserves_word_timing(song):
    lines=['Morning at the crossing','Pines along the road','Step into the water',
           'Sail across the harbour','Morning at the crossing','Quiet in the bay','Lantern at the gate']
    stamps=[5,13,25,34,48,56,65]
    synced='\n'.join(f'[{t//60:02}:{t%60:02}.00]{text}' for t,text in zip(stamps,lines))
    def publish(url):
        if 'lrclib' in url:return [{**provider(url)[0],'plainLyrics':'\n'.join(lines),'syncedLyrics':synced}]
        return {}
    sources,_=lr.lookup(song,100,publish)
    segments=[dict(t=t+2,end=t+5,text=text,words=[dict(t=t+2,end=t+3,w=text)],
                   timingReview=(i==0)) for i,(t,text) in enumerate(zip(stamps,lines))]
    segments[3]['t']+=2.4;segments[3]['end']+=2.4
    manual=dict(t=71,end=73,text='My correction',words=[dict(t=71,end=73,w='correction')],manual=True)
    segments.append(manual)
    before=copy.deepcopy(segments)
    check=lr.check_line_starts(segments,sources)
    assert check==dict(publisher='LRCLIB',url='https://lrclib.net/api/get/12',compared=7,consistent=6,offsetSeconds=2.)
    before[3]['timingReview']=True
    before[3]['words'][0]['timingReview']=True
    assert segments==before  # Local timestamps, existing weak words and manual edits all survive.
    different=copy.deepcopy(sources)
    for i,row in enumerate(different[0]['lineTimes']):row[1]+=i*1.8
    assert lr.check_line_starts(segments,different) is None and segments==before
    assert lr.check_line_starts(segments[:3],sources) is None


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
        dict(t=.8,end=1.5,text='we take the road',words=[dict(t=.8,end=.9,w='we',timingReview=True)],sourceURL='https://lrclib.net/api/get/12',timingReview=True,confidence=.8)],
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
    assert saved['lyrics'][1]['timingReview'] is True and saved['lyrics'][1]['confidence']==.8
    assert saved['lyrics'][1]['words'][0]['timingReview'] is True
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


def test_long_video_intro_can_guide_missing_repetitions_but_never_supply_word_times(tmp_path):
    texts=['Morning at the crossing','Pines along the road','Step into the water','Sail across the harbour',
           'Light above the valley','Quiet in the bay','Lantern at the gate','Stars over the garden']
    times=[5,13,21,29,37,45,53,61]
    sources=[dict(publisher='LRCLIB',url='https://lrclib.net/api/get/12',
                  lineTimes=[[lr.key(text),t] for text,t in zip(texts,times)])]
    rows=[dict(t=t+11,end=t+14,text=text,words=[dict(w=text,t=t+11,end=t+14,score=.9)],timingReview=False)
          for t,text in zip(times,texts)]
    rows[4].update(t=47,end=47.1,words=[],timingReview=True)
    rows[5].update(t=47.2,end=47.4,timingReview=True)
    original=copy.deepcopy(rows)
    requests=[]
    def acoustic(audio,jobs,language,folder):
        requests.extend(jobs)
        return [dict(id=j['id'],score=.9,words=[dict(w=w,t=j['t0']+.31+n*.4,end=j['t0']+.55+n*.4,score=.9)
                for n,w in enumerate(lr.tokens(j['text']))]) for j in jobs]
    assert lr.recover_line_windows('audio',rows,sources,90,'en',tmp_path,acoustic)==2
    assert [job['id'] for job in requests]==['4','5']
    assert rows[4]['t']==pytest.approx(47.81)  # Measured, not the online 37 + offset 11.
    assert rows[5]['t']==pytest.approx(55.81)
    assert all(rows[i]==original[i] for i in [0,1,2,3,6,7])
    assert lr.check_line_starts(rows,sources)['consistent']==8
    failed=copy.deepcopy(original)
    assert lr.recover_line_windows('audio',failed,sources,90,'en',tmp_path,lambda *a:[])==0
    assert failed==original


def test_divergent_online_edition_cannot_move_local_words(tmp_path):
    rows=[dict(t=i*10,end=i*10+2,text=f'Invented phrase number {i}',words=[dict(w='phrase')]) for i in range(8)]
    sources=[dict(publisher='LRCLIB',url='https://lrclib.net/api/get/12',
                  lineTimes=[[lr.key(row['text']),i*14] for i,row in enumerate(rows)])]
    before=copy.deepcopy(rows)
    assert lr.recover_line_windows('audio',rows,sources,90,'en',tmp_path,lambda *a:pytest.fail('unmatched edition'))==0
    assert rows==before
