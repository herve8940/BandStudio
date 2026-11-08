import importlib.util
from pathlib import Path
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('studio_worker',ROOT/'desktop/studio/worker.py')
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_structure_keeps_short_breaks_and_exact_boundaries():
    result=worker.sections([
        {'start':0,'end':3.73,'label':'verse'},
        {'start':3.73,'end':4.1,'label':'silence'},
        {'start':4.1,'end':9,'label':'chorus'},
    ],8)
    assert [(s['start'],s['end']) for s in result]==[(0,3.73),(3.73,4.1),(4.1,8)]
    assert result[1]['name']=='Silence'
    assert len({s['id'] for s in result})==3


def test_structure_rejects_empty_and_overlapping_suggestions():
    result=worker.sections([
        {'start':-2,'end':4,'label':'intro'},
        {'start':2,'end':3,'label':'verse'},
        {'start':2,'end':6,'label':'chorus'},
        {'start':9,'end':10,'label':'outro'}],8)
    assert [(s['start'],s['end']) for s in result]==[(0,4),(4,6)]


def test_native_ui_commands_and_project_binding():
    from playwright.sync_api import sync_playwright,expect
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*a):pass
    host=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=ROOT/'desktop/studio/web'))
    threading.Thread(target=host.serve_forever,daemon=True).start()
    project={'id':'test-project','name':'Mon morceau <script>bad()</script>',
             'tracks':[{'id':'drums','name':'Batterie','file':'Audio/drums.caf','role':'drums','duration':100,'offset':0,'gain':.8,'muted':False,'solo':False,'peaks':[.2,.7,.1]*200}],
             'sections':[{'id':'intro','start':0,'end':3.73,'name':'Intro','locked':False}],
             'cues':[{'id':'fill','time':3.65,'name':'Fill <b>ici</b>'}],'notes':'Travail du refrain','bpm':120}
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page(viewport={'width':1360,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>window.sent.push(m)}}};')
            page.goto(f'http://127.0.0.1:{host.server_port}/index.html')
            expect(page.locator('#empty')).to_be_visible()
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:1})',project)
            expect(page.locator('#title')).to_have_text(project['name'])
            assert page.locator('.track').count()==1
            page.locator('.section').click()
            assert page.locator('#loopEnd').input_value()=='3.730'
            page.locator('#loopToggle').click()
            assert page.evaluate('window.sent.at(-1)')=={'command':'loop','args':{'on':True,'start':0,'end':3.73},'projectID':'test-project'}
            page.locator('[data-mode=minus]').click()
            assert page.evaluate('window.sent.at(-1).args.value')=='minus'
            page.locator('#addCue').click()
            page.locator('#editName').fill('Reprise précise')
            page.locator('#editStart').fill('3.655')
            page.locator('#editForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).args.time')==3.655
            page.locator('#newSection').click()
            project['id']='next-project'
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:2})',project)
            expect(page.locator('#editor')).not_to_be_visible()
            for name in ['prepare','takes','library','settings','guides','prompter','studio']:
                page.locator(f'.rail [data-view={name}]').click()
                expect(page.locator('#view-'+name)).to_be_visible()
            page.locator('.rail [data-view=guides]').click()
            page.locator('#setting-manualBPM').fill('96')
            page.locator('#setting-countBars').fill('1')
            page.locator('#setting-callsPan').fill('-1')
            page.locator('#guideForm button[type=submit]').click()
            value=page.evaluate('window.sent.at(-1)')
            assert value['command']=='settings' and value['args']['value']['manualBPM']==96
            assert value['args']['value']['countBars']==1 and value['args']['value']['callsPan']==-1
            assert value['args']['value']['regionCountEnabled'] is True
            page.locator('#importLink').click()
            page.locator('#linkURL').fill('https://www.youtube.com/watch?v=example')
            page.locator('#linkForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).command')=='link'
            page.locator('.rail [data-view=prompter]').click()
            page.locator('#addAnnotation').click()
            page.locator('#annotationText').fill('Paroles corrigées <b>à garder comme texte</b>')
            page.locator('#annotationStart').fill('1.25')
            page.locator('#annotationEnd').fill('2.9')
            page.locator('#annotationForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).args.start')==1.25
            page.locator('.rail [data-view=studio]').click()
            page.locator('.track-name').click()
            page.locator('#trackPan').fill('0.5')
            page.locator('#trackOffset').fill('-0.05')
            page.locator('#trackForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).args.offset')==-.05
            page.locator('.rail [data-view=library]').click()
            page.locator('#newSetlist').click()
            page.locator('#setlistName').fill('Répétition du jeudi')
            page.locator('#saveSetlist').click()
            assert page.evaluate('window.sent.at(-1).command')=='setlist'
            page.locator('.rail [data-view=studio]').click()
            for width in [1360,1024,960]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            assert not errors,errors
        finally:browser.close();host.shutdown();host.server_close()
