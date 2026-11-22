import json
from pathlib import Path
import pytest
import chord_sources as web


@pytest.mark.parametrize('title',['Apocalypse - Cigarettes After Sex','Cigarettes After Sex - Apocalypse'])
def test_tagged_artist_resolves_title_artist_in_either_order(tmp_path,title):
    (tmp_path/'Artwork.json').write_text(json.dumps(dict(title=title,artist='Cigarettes After Sex')))
    assert web.identity(dict(name=title+' [sElE_BfQ67s]',_root=str(tmp_path)))==('Apocalypse','Cigarettes After Sex')


def test_catalog_and_fallback_have_the_same_sources():
    assert json.loads((Path(web.__file__).parent/'chord-providers.json').read_text())==web.PROVIDERS


def test_ukulele_index_resolves_exact_song_and_validates_identity(monkeypatch):
    provider=next(p for p in web.PROVIDERS if p['id']=='ukuleletabs')
    index=web.provider_url(provider,'Song','Some Artist')
    assert index.endswith('/Some%2BArtist-uke-tabs.html')
    target='https://www.ukulele-tabs.com/uke-songs/some-artist/song-uke-tab-12345.html'
    pages={index:'<a href="https://evil.test/song-uke-tab-1.html">Song</a><a href="/uke-songs/some-artist/wrong-uke-tab-2.html">Another Song</a><a href="'+target+'">Song</a>',
           target:'<title>Song Uke tab by Some Artist - Ukulele Tabs</title><nav><a class="chord">D</a></nav><pre>[Intro]<a class="chord">C</a><a class="chord">G</a></pre>'}
    calls=[]
    def fetch(url):calls.append(url);return pages[url],url
    monkeypatch.setattr(web,'fetch',fetch)
    _,status,source=web._read_chart(provider,'Song','Some Artist',index)
    assert status=='found' and source['url']==target and source['chords']==['C','G']
    assert calls==[index,target]
    pages[target]=pages[target].replace('Some Artist','Different Artist')
    assert web._read_chart(provider,'Song','Some Artist',index)[1]=='not_found'


def test_khmer_capo_is_converted_and_navigation_is_excluded(monkeypatch):
    provider=next(p for p in web.PROVIDERS if p['id']=='khmerchords')
    page='<title>Song Chords - Artist | KhmerChords.Com</title><span class="c">B</span><div id="lc-content" data-capo="2"><span class="c">C</span><span class="c">G/B</span></div>'
    monkeypatch.setattr(web,'fetch',lambda url:(page,url))
    _,status,source=web._read_chart(provider,'Song','Artist',web.provider_url(provider,'Song','Artist'))
    assert status=='found' and source['chords']==['D','A/C#']
