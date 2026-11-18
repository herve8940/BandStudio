"""Musical edits survive reload/undo and never schedule model inference."""
import copy
import functools
import os
from pathlib import Path
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_studio_advanced import project, model, Api, ENGINE

ROOT = Path(__file__).resolve().parents[1]


def test_existing_results_and_empty_completed_analysis_are_reused(tmp_path, monkeypatch):
    p=project(tmp_path)
    p['analysesCompleted']=['structure','drums']
    p['drumHits']=[]
    p['preparation']={'fingerprint':'validated','rate':1,'pitch':0,'mode':'mix'}
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path
    monkeypatch.setattr(api,'_work',lambda *a,**kw:pytest.fail('Unexpected analysis'))
    before=copy.deepcopy(p)
    for kind in ('structure','grid','drums','lyrics','chords','separate'):
        api._analysis(kind,{})
    from windows.advanced_host import advanced_task
    for kind in ('smartgrid','key'):advanced_task(api,kind,{})
    assert p==before
    assert not set(api._plan())&{'grid','smartgrid','structure','lyrics','chords','key','separate'}


def test_manual_boundary_is_atomic_persistent_and_undoable(tmp_path):
    p=project(tmp_path);p['sections'][0]['reviewed']=True
    p['sections'][1]['reviewed']=True
    model.save(p,tmp_path)
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path;api._audio.load(p,tmp_path)
    def send(command,**args):return api.command(dict(command=command,projectID=p['id'],args=args))
    send('moveMarker',kind='section',id='b',time=5.25)
    saved=model.load(tmp_path)
    assert saved['sections'][0]['end']==saved['sections'][1]['start']==5.25
    assert all(s['locked'] and s['origin']=='manual' and s['reviewed'] is False for s in saved['sections'])
    send('reviewMarker',kind='section',id='b')
    assert model.load(tmp_path)['sections'][1]['reviewed'] is True
    saved=copy.deepcopy(api._project)
    send('moveMarker',kind='section',id='b',time=0)
    assert api._project==saved
    send('undo')
    assert model.load(tmp_path)['sections'][1]['reviewed'] is False
    send('undo')
    assert model.load(tmp_path)['sections'][1]['start']==6


def test_volume_and_review_do_not_invalidate_rendered_guides(tmp_path):
    p=project(tmp_path);before=model.guide_key(p)
    p['settings'].update(clickGain=.1,callsGain=.2,cuesGain=.3,countGain=.4,clickEnabled=True)
    model.edit_marker(p,dict(kind='section',id='b'),review=True)
    assert model.guide_key(p)==before
    model.edit_marker(p,dict(kind='section',id='b',time=5.25))
    assert model.guide_key(p)!=before
    p['cues']=[dict(id='cue',name='Stop',time=9,reviewed=True)]
    model.edit_marker(p,dict(kind='cue',id='cue',time=9.25))
    assert p['cues'][0]['reviewed'] is False
    model.edit_marker(p,dict(kind='cue',id='cue'),review=True)
    model.save(p,tmp_path)
    assert model.load(tmp_path)['cues'][0]['reviewed'] is True


@pytest.fixture
def manual_page():
    from playwright.sync_api import sync_playwright
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*a):pass
    host=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=ROOT/'desktop/studio/web'))
    threading.Thread(target=host.serve_forever,daemon=True).start()
    with sync_playwright() as pw:
        browser=getattr(pw,os.environ.get('BANDSTUDIO_BROWSER','chromium')).launch(**({'channel':os.environ['BANDSTUDIO_BROWSER_CHANNEL']} if os.environ.get('BANDSTUDIO_BROWSER_CHANNEL') else {}))
        page=browser.new_page(viewport={'width':1360,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>window.sent.push(m)}}};')
        page.goto(f'http://127.0.0.1:{host.server_port}/index.html')
        p=dict(id='manual',name='Structure à vérifier',notes='',bpm=120,beats=[],cues=[dict(id='fill',name='Fill',time=12.5)],
               settings=dict(gridMode='fixed',manualBPM=120,firstBeat=.5,beatsPerBar=4),
               tracks=[dict(id='source',name='Original',role='source',offset=0,duration=32,gain=.8,peaks=[.2,.4,.1]*240)],
               sections=[dict(id='a',name='Couplet',start=.5,end=8.5,locked=False,origin='analysis'),dict(id='b',name='Refrain',start=8.5,end=32,locked=False,origin='analysis')])
        page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:1})',p)
        try:yield page,p;assert not errors
        finally:browser.close();host.shutdown();host.server_close()


def test_zoom_seeking_volumes_and_one_by_one_validation(manual_page):
    page,p=manual_page
    page.locator('#markerChoice').select_option('1')
    page.locator('#zoomIn').click()
    assert page.evaluate('viewport().span')==16
    v=page.evaluate('viewport()');box=page.locator('canvas[data-track=source]').bounding_box()
    page.mouse.click(box['x']+box['width']/2,box['y']+50)
    assert page.evaluate('sent.at(-1).args.time')==pytest.approx(v['start']+8,abs=.05)
    page.locator('[data-marker-step="-1"][data-unit=bar]').click()
    assert page.evaluate('sent.at(-1)')==dict(command='moveMarker',projectID='manual',args=dict(kind='section',id='b',time=6.5))
    p['sections'][0]['end']=6.5;p['sections'][1]['start']=6.5
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('#markerListen').click()
    assert page.evaluate('sent.at(-1).command')=='audition'
    assert page.evaluate('sent.at(-1).args.start')==.5
    page.locator('#markerValidate').click()
    assert page.evaluate('sent.at(-1).command')=='reviewMarker'
    p['sections'][1]['reviewed']=True
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#markerName').inner_text()=='Fill'
    assert page.locator('#markerProgress').inner_text()=='1 / 3 repères validés'
    page.locator('#workspaceMix').click()
    page.locator('#mix-cuesGain').evaluate('(e)=>e.value=0.35')
    page.locator('#mix-cuesGain').dispatch_event('change')
    assert page.evaluate('sent.at(-1)')==dict(command='guideMix',projectID='manual',args=dict(key='cuesGain',value=.35))
    for width in (1360,1024,960):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')


def test_calibration_status_and_precise_settings_can_be_saved(manual_page):
    page,p=manual_page
    p['settings'].update(firstBeat=1.1813151927437642,clickGain=1.28)
    p['analysisNote']='« 1 » à vérifier à l’écoute · mesures non confirmées'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert 'à vérifier' in page.locator('#gridCalibration').inner_text()
    assert page.locator('#guideForm').evaluate('(e)=>e.checkValidity()')
    p['gridLocked']=True
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#gridCalibration').inner_text()=='Calage manuel protégé'


def test_variable_tempo_drag_and_project_binding(manual_page):
    page,p=manual_page
    p['beats']=[.5,1,1.5,2,2.5,3.1,3.7,4.3,4.9,5.5]
    p['settings']['gridMode']='detected'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    result=page.evaluate('''() => {const g=musicalGrid(state.project);return {next:g.at(g.coordinate(2.5)+4),roundtrip:[0,2.5,4.4,8].map(t=>g.at(g.coordinate(t)))}}''')
    assert result['next']==pytest.approx(4.9)
    assert result['roundtrip']==pytest.approx([0,2.5,4.4,8])
    page.locator('#markerChoice').select_option('2')
    page.locator('#markerSnap').select_option('beat')
    cue=page.locator('#cues [data-id=fill]').bounding_box();width=page.locator('#cues').bounding_box()['width']
    page.mouse.move(cue['x']+5,cue['y']+10);page.mouse.down();page.mouse.move(cue['x']+5+width*.6/32,cue['y']+10,steps=5);page.mouse.up()
    assert page.evaluate('sent.at(-1).command')=='moveMarker'
    assert page.evaluate('sent.at(-1).args.time')==pytest.approx(13.3)
    p.update(id='another',sections=[],cues=[])
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#markerValidate').is_disabled()
    assert page.locator('#markerProgress').inner_text()=='0 / 0 repères validés'


def test_wheel_zoom_keeps_mouse_anchor_and_plain_wheel_still_scrolls(manual_page):
    page,p=manual_page
    page.locator('#zoomFollow').uncheck()
    def wheel(delta,**modifiers):
        return page.locator('.track-wave').evaluate('''(lane, args) => {
            const r=lane.getBoundingClientRect();
            const event=new WheelEvent('wheel',{bubbles:true,cancelable:true,clientX:r.left+r.width*.3,deltaY:args.delta,...args.modifiers});
            const ratio=(event.clientX-r.left)/r.width;
            lane.dispatchEvent(event);return {prevented:event.defaultPrevented,ratio};
        }''',dict(delta=delta,modifiers=modifiers))
    assert not wheel(-120)['prevented']
    assert page.evaluate('viewport().span')==32
    event=wheel(-120,ctrlKey=True)
    assert event['prevented']
    first=page.evaluate('viewport()')
    assert 2<first['span']<32
    assert first['start']+event['ratio']*first['span']==pytest.approx(32*event['ratio'])
    assert wheel(120,metaKey=True)['prevented']
    assert page.evaluate('viewport().span')==pytest.approx(32)
    for _ in range(10):wheel(-1000,ctrlKey=True)
    assert page.evaluate('viewport().span')==2
    page.evaluate('state.busy=true')
    assert not wheel(120,ctrlKey=True)['prevented']
    assert page.evaluate('viewport().span')==2


def test_zoom_toolbar_remains_visible_below_many_tracks(manual_page):
    page,p=manual_page
    p['tracks']=[{**p['tracks'][0],'id':str(i),'name':f'Piste {i}'} for i in range(16)]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('main').evaluate('(e)=>e.scrollTop=650')
    page.wait_for_function('document.querySelector("main").scrollTop>=650')
    main=page.locator('main').bounding_box();bar=page.locator('.editor-zoom').bounding_box()
    assert main['y']<=bar['y']<=main['y']+40
    assert bar['y']+bar['height']<main['y']+main['height']


def test_manual_analysis_buttons_request_recalculation_and_vocals_are_findable(manual_page):
    page,p=manual_page
    page.locator('.rail [data-view=prepare]').click()
    page.locator('#view-prepare [data-studio-task=smartgrid]').click()
    assert page.evaluate('sent.at(-1).args.options.reanalyze') is True
    page.locator('[data-analysis=structure]').click()
    assert page.evaluate('sent.at(-1).args.reanalyze') is True
    assert page.locator('#view-prepare #splitVocals').is_visible()
    assert page.locator('#splitVocals').is_disabled()  # A separated vocal track is required.
    p['tracks'].append({**p['tracks'][0],'id':'vocals','role':'vocals','name':'Chant'})
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('#splitVocals').click()
    assert page.evaluate('sent.at(-1).args.kind')=='vocalsplit'
