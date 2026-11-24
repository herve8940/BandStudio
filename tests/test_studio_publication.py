"""Public release navigation and bilingual tutorials remain usable on both engines."""
import functools
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit,unquote

import pytest

ROOT=Path(__file__).resolve().parents[1]
PAGES=['index.html','en.html','tutoriel.html','tutorial.html','fiche-morceau.html','song-sheet.html']


def test_public_pages_have_resolving_local_assets_and_translated_tutorials():
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key not in ('href','src') or not value:continue
                link=urlsplit(value)
                if link.scheme or link.netloc or not link.path:continue
                assert (ROOT/'site'/unquote(link.path)).exists(),value
    for name in PAGES:
        text=(ROOT/'site'/name).read_text(encoding='utf-8');Links().feed(text)
        assert '/Users/' not in text and 'file://' not in text
    sitemap=(ROOT/'site/sitemap.xml').read_text()
    assert 'tutorial.html' in sitemap and 'song-sheet.html' in sitemap
    latest_notes=max((ROOT/'docs').glob('RELEASE_????-??-??.md'))
    assert latest_notes.name in (ROOT/'tools/publish_studio_release.py').read_text()


def test_packaged_release_contains_all_preparation_modules_and_visual_assets():
    import importlib.util
    spec=importlib.util.spec_from_file_location('release_package',ROOT/'tools/package_studio_windows.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={p.name for p in module.source_files()}
    assert names.isdisjoint({'session.html', 'session.js', 'session.css', 'session-score.js'})
    assert {'lyrics_reference.py','chord_choice.py','chart_sections.py','section_functions.py','structure-compare.js','structure-compare.css','section-style.js','experience.js','experience.css'}<=names


@pytest.fixture(scope='module')
def public_browser():
    from playwright.sync_api import sync_playwright
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    host=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=ROOT/'site'))
    threading.Thread(target=host.serve_forever,daemon=True).start()
    with sync_playwright() as pw:
        name=os.environ.get('BANDSTUDIO_BROWSER','chromium');channel=os.environ.get('BANDSTUDIO_BROWSER_CHANNEL')
        browser=getattr(pw,name).launch(**({'channel':channel} if channel and name=='chromium' else {}))
        try:yield browser,f'http://127.0.0.1:{host.server_port}'
        finally:browser.close();host.shutdown();host.server_close()


@pytest.mark.parametrize('filename,lang',[('tutoriel.html','fr'),('tutorial.html','en'),('fiche-morceau.html','fr'),('song-sheet.html','en')])
def test_tutorial_navigates_all_steps_reloads_deep_link_and_fits_mobile(public_browser,filename,lang):
    browser,url=public_browser;page=browser.new_page(viewport=dict(width=1280,height=900));errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto(url+'/'+filename)
        assert page.locator('html').get_attribute('lang')==lang
        assert page.locator('#tutorialPrevious').is_disabled()
        for index in range(8):
            assert page.locator('.tutorial-step:visible').count()==1
            assert page.locator(f'#step-{index+1}').is_visible()
            assert page.locator('[aria-current=step]').count()==1
            if index<7:page.locator('#tutorialNext').click()
        assert page.locator('#tutorialNext').is_disabled()
        page.reload();assert page.locator('#step-8').is_visible()
        page.locator('[data-step-link="2"]').click();assert page.locator('#step-3').is_visible()
        page.set_viewport_size(dict(width=375,height=812))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('header nav').is_visible()
        page.locator('#tutorialPrevious').click();assert page.locator('#step-2').is_visible()
        assert not errors
    finally:page.close()


@pytest.mark.parametrize('filename',['index.html','en.html'])
def test_homepage_comparison_and_download_links(public_browser,filename):
    browser,url=public_browser;page=browser.new_page(viewport=dict(width=375,height=812))
    try:
        page.goto(url+'/'+filename)
        image=page.locator('.work-view:visible .release-preview img');image.scroll_into_view_if_needed()
        page.wait_for_function('document.querySelector(".release-preview img").naturalWidth>0')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('header nav').is_visible()
        assert page.locator('a[href$="BandStudio-1.1.0-Windows-x64.zip"]').count()==1
        assert page.locator('#nouveautes a[href*="RELEASE_"]').count()==1
        for index in (1,2,0):
            page.locator(f'.view-switch [data-view="{index}"]').click()
            assert page.locator(f'#view-{index}').is_visible()
            assert page.locator('.work-view:visible').count()==1
        assert page.locator('#guides a[href="'+('tutorial.html' if filename=='en.html' else 'tutoriel.html')+'"]').count()==1
    finally:page.close()
