"""Artist slugs are publisher addresses, never a substitute for musical identity."""
from html import escape
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chord_sources as web
CATALOG_URLS=web.catalog_urls


def provider(name='cifraclub'):
    return next(p for p in web.PROVIDERS if p['id']==name)


def chart(title,artist,kind='cifraclub'):
    chords='<b>A</b><b>C</b><b>G</b>' if kind=='cifraclub' else '<span data-chord="A">A</span><span data-chord="C">C</span>'
    return f'<title>{escape(title)} - {escape(artist)} - Cifra Club</title><pre>{chords}</pre>'


def results(*urls):
    return ''.join('<a class="result__a" href="'+escape(url,quote=True)+'">Result</a>' for url in urls)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    fetch_discovery=web.fetch_discovery
    web._network.__dict__.clear()
    monkeypatch.setattr(web,'fetch',lambda url:pytest.fail('Unexpected publisher request: '+url))
    monkeypatch.setattr(web,'fetch_discovery',lambda query:pytest.fail('Unexpected discovery: '+query))
    monkeypatch.setattr(web,'catalog_urls',lambda *args:[])
    yield fetch_discovery
    web._network.__dict__.clear()


@pytest.mark.parametrize('title,artist',[("L'Homme pressé",'Noir Désir'),('L’Homme pressé','Noir Desir')])
def test_noir_desir_uses_verified_publisher_address_and_original_identity(monkeypatch,title,artist):
    canonical='https://www.cifraclub.com/desir-noir/lhomme-presse/'
    calls=[]
    def fetch(url):
        calls.append(url)
        assert url==canonical
        return chart("L'homme Pressé",'Noir Désir'),url
    monkeypatch.setattr(web,'fetch',fetch)
    identifier,status,source=web._read_provider(provider(),title,artist)
    assert status=='found' and calls==[canonical]
    assert source['url']==canonical and source['chords']==['A','C','G']
    assert source['title']==title+' — '+artist
    assert '/noir-desir/' in web.provider_url(provider('echords'),title,artist)


def test_oasis_keeps_working_without_a_search_engine_request(monkeypatch):
    def fetch(url):
        assert url=='https://www.cifraclub.com/oasis/supersonic/'
        return chart('Supersonic','Oasis'),url
    monkeypatch.setattr(web,'fetch',fetch)
    assert web._read_provider(provider(),'Supersonic','Oasis')[1]=='found'


@pytest.mark.parametrize('kind,canonical',[
    ('cifraclub','https://www.cifraclub.com/legacy-performer-name/123456/'),
    ('echords','https://www.e-chords.com/chords/another-publisher-id/song-version'),
])
def test_unknown_artist_and_song_slugs_are_discovered_then_verified(monkeypatch,kind,canonical):
    p=provider(kind);title='A Song';artist='An Artist';direct=web.provider_url(p,title,artist)
    calls=[];queries=[]
    def fetch(url):
        calls.append(url)
        if url==direct:raise HTTPError(url,404,'missing',{},None)
        assert url==canonical
        return chart(title,artist,kind),url
    monkeypatch.setattr(web,'fetch',fetch)
    def search(query):queries.append(query);return results('//duckduckgo.com/l/?'+urlencode({'uddg':canonical}))
    monkeypatch.setattr(web,'fetch_discovery',search)
    _,status,source=web._read_provider(p,title,artist)
    assert status=='found' and source['url']==canonical
    assert calls==[direct,canonical]
    assert queries==['site:'+p['domain']+' "An Artist" "A Song"']


def test_wrong_artist_and_wrong_song_in_search_results_are_rejected(monkeypatch):
    p=provider();direct=web.provider_url(p,'Song','Artist')
    candidates=['https://www.cifraclub.com/other/song/','https://www.cifraclub.com/artist/other/','https://www.cifraclub.com/real-id/song/']
    pages=[chart('Song','Another Artist'),chart('Another Song','Artist'),chart('Song','Artist')]
    def fetch(url):
        if url==direct:return '<title>Not found</title>',url
        return pages[candidates.index(url)],url
    monkeypatch.setattr(web,'fetch',fetch)
    monkeypatch.setattr(web,'fetch_discovery',lambda query:results(*candidates))
    _,status,source=web._read_provider(p,'Song','Artist')
    assert status=='found' and source['url']==candidates[-1]


def test_search_snippets_are_not_used_as_chords(monkeypatch):
    direct=web.provider_url(provider(),'Song','Artist')
    alternate='https://www.cifraclub.com/other-id/song/'
    def fetch(url):
        if url==direct:raise HTTPError(url,404,'missing',{},None)
        return '<title>Song - Artist</title><p>No chart</p>',url
    monkeypatch.setattr(web,'fetch',fetch)
    monkeypatch.setattr(web,'fetch_discovery',lambda query:results(alternate)+chart('Song','Artist'))
    assert web._read_provider(provider(),'Song','Artist')[1:] == ('not_found',None)


def test_discovery_filters_links_before_any_download_and_bounds_candidates():
    valid='https://www.cifraclub.com/real-artist/song/'
    untrusted=['http://www.cifraclub.com/a/b/','https://www.cifraclub.com.evil.test/a/b/',
               'https://www.e-chords.com/chords/a/b','https://user@www.cifraclub.com/a/b/',
               'https://www.cifraclub.com:8080/a/b/','https://127.0.0.1/a/b/',
               '//duckduckgo.com/l/?'+urlencode({'uddg':'file:///tmp/secret'}),
               'https://www.cifraclub.com:invalid/a/b/']
    parsed=web.SearchLinks(provider())
    parsed.feed(results(*untrusted,valid,valid+'#chorus',*(f'https://www.cifraclub.com/a/{i}/' for i in range(8))))
    assert parsed.urls==[valid,'https://www.cifraclub.com/a/0/','https://www.cifraclub.com/a/1/']


@pytest.mark.parametrize('status',[403,429,503])
def test_publisher_access_errors_do_not_trigger_more_requests(monkeypatch,status):
    def fetch(url):raise HTTPError(url,status,'unavailable',{},None)
    monkeypatch.setattr(web,'fetch',fetch)
    assert web._read_provider(provider(),'Song','Artist')[1:] == ('unavailable',None)


def test_discovery_timeout_and_challenge_are_explicit(monkeypatch):
    def missing(url):raise HTTPError(url,404,'missing',{},None)
    monkeypatch.setattr(web,'fetch',missing)
    for search in (lambda query:'<form id="challenge">Verify you are human</form>',
                   lambda query:(_ for _ in ()).throw(TimeoutError('slow'))):
        monkeypatch.setattr(web,'fetch_discovery',search)
        assert web._read_provider(provider(),'Song','Artist')[1:] == ('unavailable',None)


def test_deadline_stops_discovery_before_it_starts(monkeypatch):
    def fetch(url):
        web._network.deadline=time.monotonic()-1
        raise HTTPError(url,404,'missing',{},None)
    monkeypatch.setattr(web,'fetch',fetch)
    assert web._read_provider(provider(),'Song','Artist')[1:] == ('unavailable',None)


def test_deadline_stops_late_search_result_downloads(monkeypatch):
    def missing(url):raise HTTPError(url,404,'missing',{},None)
    def search(query):
        web._network.deadline=time.monotonic()-1
        return results('https://www.cifraclub.com/new-id/song/')
    monkeypatch.setattr(web,'fetch',missing);monkeypatch.setattr(web,'fetch_discovery',search)
    assert web._read_provider(provider(),'Song','Artist')[1:] == ('unavailable',None)


def test_search_request_and_redirects_are_separate_from_chart_hosts(monkeypatch,offline):
    monkeypatch.setattr(web,'fetch_discovery',offline)
    captured=[]
    class Response:
        status=200;url=web.SEARCH_ENDPOINT
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return results('https://www.cifraclub.com/new-id/song/').encode()
    class Opener:
        def open(self,request,timeout):captured.append((request.full_url,timeout));return Response()
    monkeypatch.setattr(web,'build_opener',lambda *handlers:Opener())
    web._network.deadline=time.monotonic()+.5
    assert web.discover_urls(provider(),'Song & More','Artist')==['https://www.cifraclub.com/new-id/song/']
    url,timeout=captured[0]
    assert parse_qs(urlsplit(url).query)['q']==['site:cifraclub.com "Artist" "Song & More"']
    assert 0<timeout<=.5 and not web.safe_url(url)
    for target in ['https://evil.test/html/','https://duckduckgo.com/l/?uddg=bad','https://html.duckduckgo.com:invalid/html/',
                   'https://user@html.duckduckgo.com/html/','http://html.duckduckgo.com/html/']:
        with pytest.raises(ValueError):web.SearchRedirects().redirect_request(Request(url),None,302,'',{},target)


def test_discovered_source_is_reused_without_network(monkeypatch):
    import types
    monkeypatch.setitem(sys.modules,'artwork',types.SimpleNamespace(read=lambda root:{}))
    p={'name':'Artist - Song'};canonical='https://www.cifraclub.com/publisher-id/song/'
    monkeypatch.setattr(web,'PROVIDERS',[provider()])
    def fetch(url):
        if url==canonical:return chart('Song','Artist'),url
        raise HTTPError(url,404,'missing',{},None)
    monkeypatch.setattr(web,'fetch',fetch)
    monkeypatch.setattr(web,'fetch_discovery',lambda query:results(canonical))
    p['chordReference']=web.lookup(p)['reference']
    assert p['chordReference']['sources'][0]['url']==canonical
    monkeypatch.setattr(web,'fetch',lambda url:pytest.fail('Cache hit fetched a page'))
    assert web.lookup(p)['cacheHit']


def test_direct_requests_get_priority_over_fallbacks(monkeypatch):
    import threading
    import types
    monkeypatch.setitem(sys.modules,'analysis_progress',types.SimpleNamespace(emit=lambda **kwargs:None))
    lock=threading.Lock();seen=[]
    def fetch(url):
        with lock:seen.append(url)
        raise HTTPError(url,404,'missing',{},None)
    def search(query):
        with lock:assert len(seen)==5
        return '<div class="no-results"></div>'
    monkeypatch.setattr(web,'fetch',fetch)
    monkeypatch.setattr(web,'fetch_discovery',search)
    found=web._search('Song','Artist')
    assert len(found)==5 and all(status=='not_found' for status,source in found.values())


@pytest.mark.parametrize('artist,slug,initial',[
    ('Noir Désir','desir-noir','N'),('Q-B-O','q-o','Q'),('The New Band','old-catalog-id','N'),
])
def test_native_artist_catalog_resolves_display_names_without_search_engine(monkeypatch,artist,slug,initial):
    import io
    monkeypatch.setattr(web,'ARTIST_SLUGS',{})
    monkeypatch.setattr(web,'catalog_urls',CATALOG_URLS)
    index='https://www.cifraclub.com/letra/'+initial+'/lista/'
    title="L'Homme pressé";canonical='https://www.cifraclub.com/'+slug+'/lhomme-presse/'
    class Response(io.BytesIO):
        status=200;url=index
    class Opener:
        def open(self,request,timeout):
            assert request.full_url==index
            # Exact artist matching, nested labels and split UTF-8 characters.
            return Response((f'<a href="/wrong/">Another {artist}</a><a href="/{slug}/"><span>{artist}</span></a>').encode())
    monkeypatch.setattr(web,'build_opener',lambda *handlers:Opener())
    def fetch(url):
        if url==canonical:return chart(title,artist),url
        raise HTTPError(url,404,'missing',{},None)
    monkeypatch.setattr(web,'fetch',fetch)
    _,status,source=web._read_provider(provider(),title,artist)
    assert status=='found' and source['url']==canonical


def test_artist_index_ignores_foreign_and_non_artist_links():
    p=web.ArtistLinks('https://www.cifraclub.com/letra/N/lista/','Noir Désir')
    p.feed('<a href="https://evil.test/artist/">Noir Désir</a>'
           '<a href="/artist/song/">Noir Désir</a><a href="/wrong/">Noir Désir Tribute</a>'
           '<a href="/desir-noir/"><span>Noir Désir</span></a>')
    assert p.urls==['https://www.cifraclub.com/desir-noir/']


def test_catalog_streaming_is_bounded_and_stops_on_match(monkeypatch):
    import io
    monkeypatch.setattr(web,'MAX_CATALOG_BYTES',80)
    reads=[]
    class Response(io.BytesIO):
        status=200;url='https://www.cifraclub.com/letra/N/lista/'
        def read(self,n):reads.append(n);return super().read(min(n,1))
    class Opener:
        def open(self,*args,**kwargs):return Response(b'<a href="/id/">Noir D\xc3\xa9sir</a>'+b' '*1000)
    monkeypatch.setattr(web,'build_opener',lambda *handlers:Opener())
    assert CATALOG_URLS(provider(),'Song','Noir Désir')==['https://www.cifraclub.com/id/song/']
    assert len(reads)<80
    reads.clear()
    assert CATALOG_URLS(provider(),'Song','Never Present')==[] and len(reads)==80
