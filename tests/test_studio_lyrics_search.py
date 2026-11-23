"""Search regressions use invented lyrics and small publisher-shaped pages."""
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit, quote
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import lyrics_reference as lr

TEXT = 'We follow the silver road\nWe carry the morning light\nWe reach the quiet harbour'


def page(publisher, title='Silver Road', artist='Test Artist'):
    if publisher=='Paroles.net':
        return (f'<h1>Paroles de la chanson {title} par <a>{artist}</a></h1>'
                '<article class="lyrics"><h2>Header</h2><div>'+TEXT.splitlines()[0]+'<br>'+TEXT.splitlines()[1]+
                '</div><div class="advert"><script>Never import this</script>Advertisement</div><div>'+TEXT.splitlines()[2]+
                '</div></article><aside>Unrelated words</aside>')
    return (f'<h1><a>{artist}</a> - {title} LYRICS</h1><p class="text-center"><div>'+
            TEXT.replace('\n','<br>')+'</div></p><p class="text-center">License notice</p>')


def test_chapter_title_retries_simple_title_with_unicode_normalization():
    calls=[]
    def fetch(url):
        calls.append(url)
        title=parse_qs(urlsplit(url).query).get('track_name',[''])[0]
        if title=='Silver Road':return [dict(id=12,trackName=title,artistName='Test Artist',duration=100,plainLyrics=TEXT)]
        return [] if 'lrclib' in url else {}
    sources,_=lr.lookup(dict(name='Test Artist - Silver Road (Chap. II)'),100,fetch)
    assert len(sources)==1 and sources[0]['publisher']=='LRCLIB'
    assert len(calls)==4 and not any('paroles.net' in url for url in calls)
    assert lr.title_variants('Mon e\u0301poque (Chap. II)')==['Mon époque (Chap. II)','Mon époque']


def test_release_variants_preserve_meaningful_parentheses():
    assert lr.title_variants('Silver Road (Live at Home)')[-1]=='Silver Road'
    assert lr.title_variants('Silver Road - Radio Edit')[-1]=='Silver Road'
    assert lr.title_variants('Silver Road (Where We Go)')==['Silver Road (Where We Go)']


def test_mixed_script_copy_errors_do_not_break_latin_word_alignment():
    assert lr.clean_text('Lе rivаge\nТы моя песня')=='Le rivage\nТы моя песня'


def test_other_duration_is_a_text_candidate_without_remote_timestamps():
    def fetch(url):
        return [dict(id=12,trackName='Silver Road',artistName='Test Artist',duration=180,
                     plainLyrics=TEXT,syncedLyrics='[00:10.00]'+TEXT)] if 'lrclib' in url else {}
    sources,_=lr.lookup(dict(name='Test Artist - Silver Road'),100,fetch)
    assert len(sources)==1 and sources[0]['text']==TEXT and 'lineTimes' not in sources[0]


def test_both_web_publishers_extract_complete_text_across_advertising_blocks():
    for publisher in lr.WEB_SOURCES:
        assert lr.page_lyrics(page(publisher),publisher,['Silver Road'],'Test Artist')==TEXT
        assert not lr.page_lyrics(page(publisher,artist='Wrong Artist'),publisher,['Silver Road'],'Test Artist')
        assert not lr.page_lyrics(page(publisher,title='Another Road'),publisher,['Silver Road'],'Test Artist')
        assert not lr.page_lyrics('<h1>Login required</h1>'+TEXT,publisher,['Silver Road'],'Test Artist')


def test_web_fallback_after_missing_apis_and_cache_works_offline(tmp_path):
    calls=[]
    def fetch(url):
        calls.append(url)
        for publisher,host in lr.WEB_SOURCES.items():
            if host in url:return page(publisher)
        raise HTTPError(url,404,'Not found',{},None)
    song=dict(name='Test Artist - Silver Road',_root=str(tmp_path))
    sources,_=lr.lookup(song,100,fetch,now=100)
    assert {s['publisher'] for s in sources}==set(lr.WEB_SOURCES)
    assert all(s['text']==TEXT and not s.get('confirmed') for s in sources)
    assert len(calls)==4
    assert lr.lookup(song,100,lambda _:(_ for _ in ()).throw(AssertionError('cached')),now=101)[0]==sources


def test_discovery_finds_legacy_url_but_never_imports_search_snippets():
    target='https://www.paroles.net/test-artist/paroles-silver-road-legacy'
    calls=[]
    def fetch(url):
        calls.append(url)
        if url==target:return page('Paroles.net')
        if url.startswith(lr.SEARCH_ENDPOINT):
            return '<a class="result__a" href="//duckduckgo.com/l/?uddg='+quote(target,safe='')+'">Untrusted snippet</a>'
        raise HTTPError(url,404,'Not found',{},None)
    sources,_=lr.lookup(dict(name='Test Artist - Silver Road'),100,fetch)
    assert len(sources)==1 and sources[0]['url']==target and sources[0]['text']==TEXT
    assert any(url.startswith(lr.SEARCH_ENDPOINT) for url in calls)
    assert lr.discovery_urls('<a class="result__a" href="https://evil.example/paroles-song">Words</a>')==[]


def test_artist_catalog_finds_legacy_slug_without_search_engine():
    target='https://www.paroles.net/test-artist/paroles-silver-road-chap-ii'
    calls=[]
    def fetch(url):
        calls.append(url)
        if url==target:return page('Paroles.net')
        if url=='https://www.paroles.net/test-artist':
            return '<a href="/test-artist/paroles-silver-road-chap-ii">Silver Road</a><a href="https://evil.example/paroles-track">Silver Road</a>'
        raise HTTPError(url,404,'Not found',{},None)
    sources,_=lr.lookup(dict(name='Test Artist - Silver Road'),100,fetch)
    assert len(sources)==1 and sources[0]['url']==target
    assert not any(url.startswith(lr.SEARCH_ENDPOINT) for url in calls)


def test_search_budget_is_bounded_and_old_negative_cache_is_invalidated(tmp_path,monkeypatch):
    song=dict(name='Test Artist - Silver Road (Chap. II)',_root=str(tmp_path))
    (tmp_path/'Cache').mkdir()
    (tmp_path/'Cache/lyrics-reference.json').write_text(json.dumps(dict(key='old-search',time=99,ttl=86400,sources=[],message='Old failure')))
    calls=[]
    def fetch(url):
        calls.append(url)
        return []
    times=iter([0,0,lr.NETWORK_BUDGET+1,lr.NETWORK_BUDGET+1,lr.NETWORK_BUDGET+1,lr.NETWORK_BUDGET+1,lr.NETWORK_BUDGET+1])
    monkeypatch.setattr(lr.time,'monotonic',lambda:next(times,lr.NETWORK_BUDGET+1))
    assert lr.lookup(song,100,fetch,now=100)[0]==[]
    assert len(calls)==1
