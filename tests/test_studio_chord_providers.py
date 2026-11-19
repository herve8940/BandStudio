"""Multiple public charts stay separate, bounded and explicitly selectable."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chord_sources as web
import chord_alignment
from test_studio_web_chords import song
from test_studio_manual_editor import manual_page

MARKUP={
 'cifraclub':'<pre>[Intro]<b>C</b><b>G</b><b>C</b></pre>',
 'echords':'<song-chord><pre><span data-chord="C">C</span><span data-chord="G">G</span><span data-chord="C">C</span></pre></song-chord>',
 'explorer':'<pre class="tab-container"><span class="chord" data-chord="C">C</span><span class="chord" data-chord="G">G</span><span class="chord" data-chord="C">C</span></pre>',
 'acordesweb':'<pre id="chordsPre">[Intro]<a>C</a><a>G</a><a>C</a></pre>',
 'chordsworld':'<span class="capo--Value">0</span><div class="chord-short-code-wrap"><music-part>Intro</music-part><c-2>C</c-2><c-2>G</c-2><c-2>C</c-2></div>',
}

def page(provider,title='Song',artist='Artist'):
    return f'<title>{title} Chords - {artist}</title><nav><b>A</b><span data-chord="D">D</span></nav>'+MARKUP[provider]

def fake_fetch(url):
    provider=next(p for p in web.PROVIDERS if p.get('template') and urlsplit(url).hostname in (p['domain'],'www.'+p['domain']))
    return page(provider['id']),url

@pytest.mark.parametrize('provider',list(MARKUP))
def test_provider_parsers_only_read_scoped_chord_markup(provider):
    chart=web.Chart(provider);chart.feed(page(provider))
    assert chart.chords==['C','G']
    assert chart.transitions==[['C','G'],['G','C']]

def test_all_sources_are_separate_and_previous_choice_survives_refresh(monkeypatch):
    monkeypatch.setattr(web,'fetch',fake_fetch)
    p=song();result=web.lookup(p)
    assert len(result['reference']['sources'])==5
    assert len({s['publisher'] for s in result['reference']['sources']})==5
    assert all(c['status']=='found' for c in result['reference']['checks'])
    assert result['reference']['catalogVersion']==web.CATALOG_VERSION
    chosen=result['reference']['sources'][2]['url'];p['chordReference']={**result['reference'],'selectedURL':chosen}
    assert web.lookup(p,reanalyze=True)['reference']['selectedURL']==chosen

def test_provider_failure_does_not_prevent_other_charts(monkeypatch):
    def fetch(url):
        if 'cifraclub' in url:raise HTTPError(url,403,'unavailable',{},None)
        if 'e-chords' in url:raise TimeoutError('slow')
        return fake_fetch(url)
    monkeypatch.setattr(web,'fetch',fetch)
    result=web.lookup(song())['reference']
    assert result['status']=='found' and len(result['sources'])==3
    assert result['sources'][0]['publisher']=='GuitarTabsExplorer'
    assert [c['status'] for c in result['checks'][:2]]==['unavailable','unavailable']

def test_old_single_provider_cache_is_expanded(monkeypatch):
    monkeypatch.setattr(web,'fetch',fake_fetch)
    p=song();p['chordReference']=dict(query='Artist Song',status='found',sources=[dict(url='https://www.cifraclub.com/artist/song/')])
    result=web.lookup(p)
    assert not result['cacheHit'] and len(result['reference']['sources'])==5

def test_selection_uses_only_chosen_chart_and_does_not_repeat_network(monkeypatch):
    monkeypatch.setattr(web,'fetch',fake_fetch);p=song();p['chordReference']=web.lookup(p)['reference']
    selected=p['chordReference']['sources'][1];selected['chords']=['F','Bb']
    monkeypatch.setattr(web,'fetch',lambda url:pytest.fail('Cached source selection made a network request'))
    called=[]
    def place(project,audio,chords,url,*args):
        called.append((chords,url));return [],dict(status='proposed',message='Proposé')
    monkeypatch.setattr(chord_alignment,'place',place)
    result=web.analyze(p,'audio.wav',reanalyze=True,source_url=selected['url'])
    assert called==[(['F','Bb'],selected['url'])]
    assert result['reference']['selectedURL']==selected['url']
    with pytest.raises(ValueError,match='sources trouvées'):web.analyze(p,'audio.wav',source_url='https://evil.test/chart')

def test_title_artist_validation_for_every_provider(monkeypatch):
    for provider in [p for p in web.PROVIDERS if p.get('template')]:
        monkeypatch.setattr(web,'fetch',lambda url:(page(provider['id'],artist='Another Artist'),url))
        # "Artist" in "Another Artist" must not be accepted as an exact identity.
        identifier,status,source=web._read_provider(provider,'Song','Artist')
        assert status=='not_found' and source is None
        monkeypatch.setattr(web,'fetch',lambda url:(page(provider['id'],title='Another Song'),url))
        assert web._read_provider(provider,'Song','Artist')[1]=='not_found'

def test_real_heading_conventions_and_apostrophe_slugs():
    assert web.matches_heading('Highway To Hell (acordes) - AC/DC - Cifra Club','Highway to Hell','AC/DC')
    assert web.matches_heading('Highway To Hell - AC/DC: Acordes para Guitarra, Piano y Ukelele | AcordesWeb','Highway to Hell','AC/DC')
    assert web.matches_heading('I Know It’s Over Chords - The Smiths | E-CHORDS',"I Know It's Over",'The Smiths')
    provider=next(p for p in web.PROVIDERS if p['id']=='echords')
    assert web.provider_url(provider,'I Know It’s Over','The Smiths').endswith('/the-smiths/i-know-its-over')
    assert web.provider_url(provider,'Roman Holiday','Fontaines D.C.').endswith('/fontaines-dc/roman-holiday')
    explorer=next(p for p in web.PROVIDERS if p['id']=='explorer')
    assert web.provider_url(explorer,'Roman Holiday','Fontaines D.C.').endswith('/fontaines-d.c./roman-holiday-chords')
    assert web.matches_heading('Roman Holiday Chords - Fontaines DC | E-CHORDS','Roman Holiday','Fontaines D.C.')

def test_browser_search_catalog_and_query_encoding():
    assert len(web.public_catalog())==13
    assert sum(p['automatic'] for p in web.public_catalog())==5
    for provider in web.PROVIDERS:
        url=web.search_url('AC/DC & été #test',provider=provider['id']);parsed=urlsplit(url)
        assert parsed.hostname=='www.google.com' and parsed.scheme=='https'
        assert parse_qs(parsed.query)['q']==['AC/DC & été #test chords accords site:'+provider['domain']]
    with pytest.raises(ValueError):web.search_url('Song',provider='unknown')

def test_redirects_cannot_substitute_another_publisher():
    request=Request('https://www.e-chords.com/chords/artist/song')
    with pytest.raises(ValueError):web.Redirects().redirect_request(request,None,302,'',{},'https://www.cifraclub.com/artist/song/')
    assert not web.safe_url('https://www.e-chords.com:invalid/path')

def test_slow_sources_have_one_global_budget_and_three_connections(monkeypatch):
    gate=threading.Event();started=[];lock=threading.Lock()
    def blocked(url):
        with lock:started.append(url)
        gate.wait(2)
        raise TimeoutError('slow')
    monkeypatch.setattr(web,'fetch',blocked);monkeypatch.setattr(web,'NETWORK_BUDGET',.1)
    start=time.monotonic()
    try:
        reference=web.lookup(song())['reference']
        assert time.monotonic()-start<.6
        assert len(started)==3 and all(c['status']=='unavailable' for c in reference['checks'])
    finally:gate.set()

def test_explicit_capo_is_converted_to_sounding_chords(monkeypatch):
    provider=next(p for p in web.PROVIDERS if p['id']=='chordsworld')
    html=page('chordsworld').replace('capo--Value">0','capo--Value">2')
    monkeypatch.setattr(web,'fetch',lambda url:(html,url))
    _,status,source=web._read_provider(provider,'Song','Artist')
    assert status=='found' and source['chords']==['D','A']
    assert source['transitions']==[['D','A'],['A','D']] and 'capo 2' in source['note']

def test_multiple_sources_and_targeted_search_in_ui(manual_page,monkeypatch):
    monkeypatch.setattr(web,'fetch',fake_fetch)
    page_ui,p=manual_page;p['chordReference']=web.lookup(song())['reference']
    page_ui.evaluate('data=>studioReceive({type:"state",...data})',dict(project=p,loaded=True,duration=32,revision=2,chordProviders=web.public_catalog()))
    page_ui.locator('.rail [data-view=prompter]').click();panel=page_ui.locator('#chordReferencePrompter')
    assert panel.locator('.chord-source').count()==5
    assert panel.get_by_role('button',name='Utiliser cette grille',exact=True).count()==4
    panel.get_by_role('button',name='Utiliser cette grille',exact=True).first.click()
    assert page_ui.evaluate('sent.at(-1).args.sourceURL')==p['chordReference']['sources'][1]['url']
    panel.locator('summary').click()
    assert panel.locator('.chord-provider').count()==13
    panel.get_by_role('button',name='Rechercher sur Ultimate Guitar',exact=True).click()
    assert page_ui.evaluate('sent.at(-1)')==dict(command='referenceSearch',projectID='manual',args=dict(kind='chords',provider='ultimate',query='Artist Song'))


def test_downloaded_file_names_give_the_real_artist_and_title():
    """Names from download tools used to be searched verbatim: "Full_Oasis" /
    "Wonderwall (128kbit_AAC)" exists on no chord site, so every song failed."""
    cases={'Full_Last Train - Between Wounds (128kbit_AAC)':('Between Wounds','Last Train'),
        'Full_Oasis - Wonderwall (128kbit_AAC)':('Wonderwall','Oasis'),
        '01_The_Cranberries_-_Zombie (Official Music Video)':('Zombie','The Cranberries'),
        'Eagles - Hotel California (2013 Remaster) [HD]':('Hotel California','Eagles'),
        'Queen - Bohemian Rhapsody (Official Video Remastered)':('Bohemian Rhapsody','Queen'),
        'AC/DC - Highway to Hell (320 kbps)':('Highway to Hell','AC/DC'),
        'The Beatles - Let It Be (Remastered 2009) (128kbit_AAC)':('Let It Be','The Beatles'),
        'Oasis - Wonderwall [bx1Bh8ZvH84]':('Wonderwall','Oasis'),
        'Muse - Uprising (Live)':('Uprising (Live)','Muse'),
        '21 Pilots - Stressed Out':('Stressed Out','21 Pilots')}
    for name,expected in cases.items():assert web.identity({'name':name})==expected,name


def test_heading_without_apostrophes_still_matches():
    assert web.matches_heading('Knockin On Heavens Door Chords by Bob Dylan | GuitarTabsExplorer',"Knockin' On Heaven's Door",'Bob Dylan')
    assert not web.matches_heading('Knockin On Heavens Door Chords by Bob Dylan | GuitarTabsExplorer','Heavens','Bob Dylan')
