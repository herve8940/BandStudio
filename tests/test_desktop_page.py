"""Exercise the production Desktop UI against an isolated fake REAPER API."""
import json
from pathlib import Path

import pytest

from test_desktop import host  # noqa: F401 - shared real HTTP fixture

pytest.importorskip('playwright')


def test_desktop_ui_project_binding_controls_and_layout(host):
    from playwright.sync_api import sync_playwright, expect
    d,b,s=host
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page(viewport={'width':1340,'height':920})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(s.origin+'/?token='+d.token)
            page.wait_for_selector('#connection:not(.off)')
            assert page.locator('.section').count()==4
            assert page.locator('.stem').count()==3
            assert all(c[0]=='state' for c in b.calls), 'Opening the app must not change REAPER'
            page.locator('[data-section="3"]').first.click()
            expect(page.locator('#focus-name')).to_have_text('Refrain')
            assert page.locator('#loop-first').input_value()=='9'
            page.locator('[data-listen="minus"]').click()
            page.locator('[data-listen=minus].active').wait_for()
            assert any(c==('listen',{'mode':'minus'},'project-A') for c in b.calls)
            page.locator('#loop-toggle').click()
            page.locator('#loop-toggle[aria-pressed=true]').wait_for()
            assert any(c==('loop',{'start':16,'finish':24},'project-A') for c in b.calls)
            # A dialog belonging to an old project must close as soon as REAPER switches.
            page.locator('#practice-tabs [data-tab=structure]').click()
            page.locator('[data-edit="3"]').click()
            assert page.locator('#section-dialog').is_visible()
            b.state['project_id']='project-B';b.state['title']='Autre projet'
            page.locator('#section-dialog').wait_for(state='hidden')
            assert page.locator('#song-title').text_content()=='Autre projet'
            assert not any(c[0]=='region' for c in b.calls)
            for name in ['prepare','takes','settings','bandpilot','library']:
                page.locator(f'[data-page={name}]').click()
                assert page.locator(f'[data-view={name}]').is_visible()
            page.locator('[data-page=practice]').click()
            page.locator('#practice-tabs [data-tab=work]').click()
            for width in [1340,1024,390]:
                page.set_viewport_size({'width':width,'height':920})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            assert not errors,errors
        finally:browser.close()


def test_legacy_fetches_are_bound_and_downloads_work(host):
    from playwright.sync_api import sync_playwright, expect
    d,b,s=host
    from test_desktop import request
    export=d.published/'reacue_exports';export.mkdir(parents=True)
    (export/'test.wav').write_bytes(b'RIFF-test')
    assert request(s,'/legacy/reacue_exports/test.wav')[1]==b'RIFF-test'
    assert request(s,'/legacy/reacue_exports/%2e%2e/reacue_song.json')[0]==404
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page();page.goto(s.origin+'/?token='+d.token)
            page.wait_for_selector('#connection:not(.off)')
            page.locator('#practice-tabs [data-tab=studio]').click()
            frame=page.frame_locator('#studio-frame')
            frame.locator('#nav').wait_for()
            expect(frame.locator('meta[name=reacue-project]')).to_have_attribute('content','project-A')
            inner=page.locator('#studio-frame').element_handle().content_frame()
            inner.evaluate("fetch('/_/SET/EXTSTATE/ReaCue/remote/note%7Cintro%3Bfinal')")
            assert any(c==('web_api',{'commands':'SET/EXTSTATE/ReaCue/remote/note%7Cintro%3Bfinal'},'project-A') for c in b.calls)
        finally:browser.close()
