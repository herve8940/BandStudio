import os
import importlib.util
from pathlib import Path
import functools
import shutil
import threading
import json
import sys
from types import SimpleNamespace
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


@pytest.mark.parametrize('fails',[False,True])
def test_structure_reports_phases_separately_from_runtime_warnings(tmp_path,monkeypatch,capsys,fails):
    output=tmp_path/'analysis/result.json'
    status=output.parent/'progress.json'
    def load():
        assert json.loads(status.read_text())['stage']=='structure-loading'
        return SimpleNamespace(device='cpu')
    def init(app):
        print('UserWarning: Skipping device NVIDIA GeForce GT 750M')
        print('  return torch._C._mps_is_available()')
    def analyze(app,audio,window):
        assert json.loads(status.read_text())=={'stage':'structure-analysis','device':'cpu'}
        if fails:raise RuntimeError('model failed')
        return [{'start':0,'end':24,'label':'verse'}]
    monkeypatch.setitem(sys.modules,'reacue_structure',SimpleNamespace(load_app=load,init_models=init,segments_from_app=analyze,ram_gb=lambda:16))
    monkeypatch.setitem(sys.modules,'soundfile',SimpleNamespace(info=lambda _:SimpleNamespace(duration=24)))
    if fails:
        with pytest.raises(RuntimeError,match='model failed'):worker.analyze('audio.wav',output,'structure',tmp_path)
        assert not output.exists()
        assert json.loads(status.read_text())['stage']=='structure-analysis'
    else:
        worker.analyze('audio.wav',output,'structure',tmp_path)
        assert json.loads(status.read_text())['stage']=='structure-saving'
        assert json.loads(output.read_text())['sections'][0]['name']=='Couplet'
    assert 'mps_is_available' in capsys.readouterr().out # Diagnostics are retained, not suppressed.


@pytest.mark.parametrize('windows',[False,True])
def test_native_ui_commands_and_project_binding(tmp_path,windows):
    from playwright.sync_api import sync_playwright,expect
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*a):pass
    web=ROOT/'desktop/studio/web'
    if windows:
        shutil.copytree(web,tmp_path/'web');web=tmp_path/'web'
        shutil.copy2(ROOT/'desktop/studio/windows/adapter.js',web/'adapter.js')
        html=web/'index.html';html.write_text(html.read_text().replace('<script src="studio.js" defer>', '<script src="adapter.js" defer></script><script src="studio.js" defer>'))
    host=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=web))
    threading.Thread(target=host.serve_forever,daemon=True).start()
    project={'id':'test-project','name':'Mon morceau <script>bad()</script>',
             'tracks':[{'id':'drums','name':'Batterie','file':'Audio/drums.caf','role':'drums','duration':100,'offset':0,'gain':.8,'muted':False,'solo':False,'peaks':[.2,.7,.1]*200}],
             'sections':[{'id':'intro','start':0,'end':3.73,'name':'Intro','locked':False}],
             'cues':[{'id':'fill','time':3.65,'name':'Fill <b>ici</b>'}],'notes':'Travail du refrain','bpm':120}
    with sync_playwright() as p:
        browser=getattr(p,os.environ.get("BANDSTUDIO_BROWSER","chromium")).launch(**({"channel":os.environ["BANDSTUDIO_BROWSER_CHANNEL"]} if os.environ.get("BANDSTUDIO_BROWSER_CHANNEL") else {}))
        try:
            page=browser.new_page(viewport={'width':1360,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>window.sent.push(m)}}};')
            if windows:page.add_init_script('window.pywebview={api:{command:m=>window.sent.push(m)}};')
            page.goto(f'http://127.0.0.1:{host.server_port}/index.html')
            if windows:
                page.get_by_role('button',name='Importer REAPER',exact=True).click()
                assert page.evaluate('window.sent.at(-1).command')=='openRPP'
                page.locator('.rail [data-view=settings]').click()
                page.get_by_role('button',name='Installer / vérifier').first.click()
                assert page.evaluate('window.sent.at(-1).args.component')=='stems'
                page.locator('.rail [data-view=studio]').click()
            expect(page.locator('#empty')).to_be_visible()
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:1})',project)
            expect(page.locator('#title')).to_have_text(project['name'])
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:1,busy:true,job:"Analyse de la structure"})',project)
            warning='UserWarning: Skipping device NVIDIA GeForce GT 750M\n  return torch._C._mps_is_available()'
            page.evaluate('detail=>window.studioReceive({type:"job",detail,elapsed:135})',warning)
            expect(page.locator('#jobDetail')).to_have_text('Traitement local en cours… · 2 min 15 s écoulées')
            page.evaluate('detail=>window.studioReceive({type:"job",stage:"structure-analysis",device:"cpu",detail,elapsed:137})',warning)
            expect(page.locator('#jobDetail')).to_have_text('Analyse sur le processeur · cela peut prendre plusieurs minutes… · 2 min 17 s écoulées')
            page.evaluate('window.studioReceive({type:"job",stage:"structure-loading",elapsed:1})')
            expect(page.locator('#jobDetail')).to_have_text('Chargement des modèles d’analyse… · 1 s écoulées')
            page.evaluate('window.studioReceive({type:"job",detail:" 42%|████ | 98/228 [01:03<01:24]",elapsed:63})')
            expect(page.locator('#jobDetail')).to_have_text('Calcul audio : 42 % · 1 min 3 s écoulées')
            page.evaluate('window.studioReceive({type:"job",stage:"separation",device:"cuda",elapsed:4})')
            expect(page.locator('#jobDetail')).to_contain_text('NVIDIA CUDA')
            page.evaluate('window.studioReceive({type:"job",stage:"smartgrid",device:"cpu",fallback:true,elapsed:5})')
            expect(page.locator('#jobDetail')).to_contain_text('Reprise sur le processeur')
            page.evaluate('window.studioReceive({type:"job",stage:"<script>bad()</script>",detail:"Traceback: fake error",elapsed:-1})')
            expect(page.locator('#jobDetail')).to_have_text('Traitement local en cours…')
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:1,busy:false})',project)
            expect(page.locator('#job')).not_to_be_visible()
            assert page.locator('.track').count()==1
            # A transport refresh between mouse-down and mouse-up used to lose WebKit clicks.
            page.evaluate("window.sent=[]")
            point=page.locator('#play').bounding_box()
            page.mouse.move(point['x']+point['width']/2,point['y']+point['height']/2)
            page.mouse.down()
            page.evaluate('window.studioReceive({type:"transport",position:0,rate:1,mode:"mix",playing:false})')
            page.mouse.up()
            assert page.evaluate('window.sent.filter(x=>x.command==="play").length')==1
            page.keyboard.press('Space')
            assert page.evaluate('window.sent.filter(x=>x.command==="play").length')==2
            page.locator('.section').click()
            assert page.locator('#loopEnd').input_value()=='3.730'
            page.locator('#loopToggle').click()
            assert page.evaluate('window.sent.at(-1)')=={'command':'loop','args':{'on':True,'start':0,'end':3.73},'projectID':'test-project'}
            page.locator('#minusInstrument').click()
            assert page.evaluate('window.sent.at(-1).args.value')=='minus:drums'
            page.locator('#addCue').click()
            page.locator('#editName').fill('Reprise précise')
            page.locator('#editStart').fill('3.655')
            page.locator('#editForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).args.time')==3.655
            page.locator('#newSection').click()
            project['id']='next-project'
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:2})',project)
            expect(page.locator('#editor')).not_to_be_visible()
            for name in ['prepare','delivery','library','settings','guides','prompter','studio']:
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
            # A manually chosen downbeat must govern both the click and the displayed measure.
            project['beats']=[1+i*.5 for i in range(20)]
            project['settings']={'firstBeat':2.5,'gridMode':'detected','beatsPerBar':4}
            project['drumHits']=[{'time':2.5,'pitch':36,'velocity':100}]
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:3})',project)
            page.locator('.rail [data-view=prompter]').click()
            for at,label in [(1,'Levée · temps 2 / 4'),(2.5,'Mesure 1 · temps 1 / 4'),(3,'Mesure 1 · temps 2 / 4'),(4.5,'Mesure 2 · temps 1 / 4')]:
                page.evaluate('position=>window.studioReceive({type:"transport",position,rate:1,mode:"mix"})',at)
                expect(page.locator('#stageBeat')).to_have_text(label)
            page.evaluate('window.studioReceive({type:"transport",position:2.5,rate:1,mode:"mix"})')
            assert page.locator('.drum-row').last.locator('.drum-cell').first.get_attribute('class').find('hit')>=0
            project['settings']['firstBeat']=6.5 # Another downbeat on the same phase leaves numbering stable.
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:4})',project)
            expect(page.locator('#stageBeat')).to_have_text('Mesure 1 · temps 1 / 4')
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
            page.locator('.rail [data-view=tools]').click()
            page.locator('#stemFormat').select_option('flac');page.locator('#exportStems').click()
            assert page.evaluate('window.sent.at(-1).args')=={'kind':'stemsexport','options':{'format':'flac'}}
            page.locator('#exportSheet').click()
            assert page.evaluate('window.sent.at(-1).args.kind')=='sheet'
            page.locator('#lyricsFile').set_input_files({'name':'paroles.lrc','mimeType':'text/plain','buffer':b'[00:01.00]Bonjour\n[00:02.00]Refrain'})
            expect(page.locator('#lyricsFile')).to_have_value('')
            assert page.evaluate('window.sent.at(-1)?.args.kind')=='lyricsimport'
            assert page.evaluate('window.sent.at(-1).args.options.replace') is False
            page.locator('.rail [data-view=guides]').click()
            page.locator('#lockGrid').check()
            assert page.evaluate('window.sent.at(-1).args.gridLocked') is True
            page.locator('.rail [data-view=prompter]').click()
            project['key']='D';project['capo']=2;project['chords']=[{'start':0,'end':100,'text':'D/F#'}]
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:6})',project)
            expect(page.locator('#stageChord')).to_have_text('C/E · capo 2')
            page.locator('#addAnnotation').click();page.locator('#annotationText').fill('Très bien')
            page.locator('#annotationStart').fill('1');page.locator('#annotationEnd').fill('3')
            page.locator('#wordEditor summary').click();page.locator('#distributeWords').click()
            page.locator('#annotationForm button[type=submit]').click()
            assert page.evaluate('window.sent.at(-1).args.words')==[{'text':'Très','start':1,'end':2},{'text':'bien','start':2,'end':3}]
            page.locator('.rail [data-view=studio]').click()
            for width in [1360,1024,960]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:6,busy:true})',project)
            expect(page.locator('#newCue')).to_be_disabled()
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:6,busy:false})',project)
            expect(page.locator('#newCue')).to_be_enabled()
            page.locator('.rail [data-view=delivery]').click()
            expect(page.locator('#sendReaper')).to_be_disabled()
            expect(page.locator('[data-action=bandpilot]')).to_have_count(0)
            expect(page.locator('[data-action=record]')).to_have_count(0)
            for key in ['reviewAudio','reviewGrid','reviewGuides']:page.locator('#'+key).check()
            page.locator('#validateProject').click()
            assert page.evaluate('window.sent.at(-1).command')=='validateProject'
            assert page.evaluate('window.sent.at(-1).args.reviewed') is True
            project['preparation']={'fingerprint':'checked','validatedAt':'2026-11-10T20:00:00Z','rate':1,'pitch':0,'mode':'mix'}
            page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:100,loaded:true,library:[],revision:7})',project)
            expect(page.locator('#sendReaper')).to_be_enabled()
            page.locator('#sendReaper').click()
            assert page.evaluate('window.sent.at(-1).command')=='reaper'
            assert page.evaluate('window.sent.at(-1).args.open') is True
            page.evaluate('window.studioReceive({type:"transport",position:0,rate:.9,pitch:0,mode:"mix"})')
            expect(page.locator('#sendReaper')).to_be_disabled()
            assert not errors,errors
        finally:browser.close();host.shutdown();host.server_close()
