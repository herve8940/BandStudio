"""Measured progress must survive model passes, retries and failed result writes."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import analysis_progress as progress


def status(output):
    return json.loads((output.parent/'progress.json').read_text())


@pytest.mark.parametrize('passes',[1,4,8])
def test_demucs_passes_are_global_and_100_waits_for_result(tmp_path,passes):
    out=tmp_path/'result.json';samples=[]
    with progress.reporting(out,'separate'):
        def notify(info):
            progress.emit(info);samples.append(status(out))
        counter=progress.PassProgress(passes,notify)
        for index in range(passes):
            assert list(counter.wrap([1,2,3,4]))==[1,2,3,4]
        assert samples[-1]['progress']==99
        assert samples[-1]['passIndex']==passes
        assert samples[-1]['passCount']==passes
        assert all(a['progress']<=b['progress'] for a,b in zip(samples,samples[1:]))
        if passes>1:assert samples[5]['progress']==pytest.approx(100/passes)
        out.write_text('{}')
    assert status(out)['progress']==100 and status(out)['finished']


def test_failed_chunk_is_not_counted_and_wrapper_is_restored(tmp_path):
    out=tmp_path/'result.json';original=object();module=SimpleNamespace(tqdm=original)
    with pytest.raises(RuntimeError,match='inference'):
        with progress.reporting(out,'separate'),progress.PassProgress(4).track(module):
            for _ in module.tqdm.tqdm([1,2]):raise RuntimeError('inference')
    assert module.tqdm is original
    assert status(out)['progress']==0 and status(out)['failed']
    assert not status(out).get('finished')


def test_gpu_retry_and_loading_do_not_reset_progress(tmp_path):
    out=tmp_path/'result.json'
    with progress.reporting(out,'structure'):
        progress.emit(completed=3,total=4,device='cuda')
        progress.emit(device='cpu',fallback='out of memory',indeterminate=True)
        progress.emit(completed=1,total=4)
        assert status(out)['progress']==75
        assert status(out)['device']=='cpu' and status(out)['fallback']
        out.write_text('{}')


def test_missing_result_cannot_finish(tmp_path):
    out=tmp_path/'result.json'
    with pytest.raises(RuntimeError,match='résultat'):
        with progress.reporting(out,'lyrics'):progress.emit(completed=1,total=1)
    assert status(out)['progress']==99 and status(out)['failed']


def test_legacy_engine_status_is_translated_without_diagnostic_text(tmp_path):
    calls=[];module=SimpleNamespace(_write_status=lambda *a,**k:calls.append((a,k)))
    original=module._write_status;out=tmp_path/'result.json'
    with progress.reporting(out,'lyrics'),progress.legacy_status(module):
        module._write_status(None,'running',step='2/4',done=1,total=4)
        assert status(out)['progress']==25
        assert status(out)['progressLabel']=='Extrait 2 sur 4'
        module._write_status(None,'error',message='private diagnostic')
        assert 'private diagnostic' not in json.dumps(status(out))
        out.write_text('{}')
    assert module._write_status is original and len(calls)==2


def test_beat_chunks_and_structure_hooks_preserve_results(tmp_path,monkeypatch):
    out=tmp_path/'result.json'
    module=SimpleNamespace(split_piece=lambda:([10,20,30],[0,10,20]))
    split=module.split_piece
    with progress.reporting(out,'smartgrid'),progress.track_beat_chunks(module):
        chunks,starts=module.split_piece()
        assert [x*2 for x in chunks]==[20,40,60] and starts==[0,10,20]
        assert status(out)['progress']==99
        out.write_text('{}')
    assert module.split_piece is split
    out=tmp_path/'structure/result.json'
    app=SimpleNamespace(muq_model=SimpleNamespace(forward=lambda x:x),musicfm_model=SimpleNamespace(get_predictions=lambda x:x),msa_model=SimpleNamespace(infer=lambda x:x))
    def process_audio(*a,**k):
        for chunks in [2,1]:
            for _ in range(chunks+1):app.muq_model.forward(1);app.musicfm_model.get_predictions(1)
            app.msa_model.infer(1)
        return 'audio','sections'
    app.process_audio=process_audio
    monkeypatch.setitem(sys.modules,'soundfile',SimpleNamespace(info=lambda _:SimpleNamespace(duration=65)))
    with progress.reporting(out,'structure'),progress.track_structure(app,'song.wav',60):
        assert app.process_audio()==('audio','sections')
        assert status(out)['completed']==status(out)['total']==12
        out.write_text('{}')
    assert app.process_audio is process_audio


def test_progress_ui_passes_cards_plan_queue_and_cancel(tmp_path):
    import functools
    import threading
    from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
    from playwright.sync_api import sync_playwright,expect
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=ROOT/'desktop/studio/web'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    project=dict(id='progress-test',name='Morceau de test',tracks=[],sections=[],cues=[],notes='',bpm=120)
    plan=['separate','smartgrid','structure','key','lyrics','chords','guides']
    errors=[]
    try:
        with sync_playwright() as p:
            browser=getattr(p,os.environ.get('BANDSTUDIO_BROWSER','chromium')).launch(**({'channel':os.environ['BANDSTUDIO_BROWSER_CHANNEL']} if os.environ.get('BANDSTUDIO_BROWSER_CHANNEL') else {}));page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>window.sent.push(m)}}};')
            page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            page.evaluate('p=>window.studioReceive(p)',dict(type='state',project=project,duration=348,loaded=True,library=[],revision=1,busy=True,job='Séparation',jobTask='separate',jobID='job-1',jobPlan=plan,jobPlanIndex=0))
            page.evaluate("window.studioReceive({type:'job',task:'separate',jobID:'job-1',stage:'separation',progress:51,passIndex:3,passCount:4,passProgress:4,progressLabel:'Passage 3 sur 4',plan:"+json.dumps(plan)+",planIndex:0})")
            expect(page.locator('#jobDetail')).to_contain_text('51 %')
            assert page.locator('#jobProgressBar progress').evaluate('(e)=>e.value')==51
            expect(page.locator('[data-task=separate]')).to_contain_text('Passage 3 sur 4')
            expect(page.locator('#overallProgress')).to_contain_text('7 % des étapes')
            page.evaluate("window.studioReceive({type:'job',task:'separate',jobID:'job-1',progress:2,progressLabel:'Reprise sur le processeur'})")
            assert page.locator('#jobProgressBar progress').evaluate('(e)=>e.value')==51
            expect(page.locator('#jobDetail')).to_contain_text('51 %')
            page.locator('.rail [data-view=prepare]').click()
            page.screenshot(path=str(tmp_path/'progress.png'),full_page=True)
            page.evaluate("window.studioReceive({type:'job',task:'separate',jobID:'job-1',failed:true,progress:0})")
            expect(page.locator('[data-task=separate]')).to_contain_text('Interrompu · 51 %')
            assert page.locator('[data-task=separate] progress').evaluate('(e)=>e.value')==51
            page.evaluate("window.studioReceive({type:'batchQueue',items:[{id:'one',title:'Morceau en file',source:'song.wav',status:'running',completed:2,total:4,stage:'Paroles',progress:{progress:50,progressLabel:'Extrait 3 sur 6'}}]})")
            expect(page.locator('.queue-info')).to_contain_text('62 % des étapes')
            expect(page.locator('.queue-info')).to_contain_text('Paroles · 50 %')
            project.update(bpm=200,gridLocked=True,settings=dict(gridMode='fixed',manualBPM=75))
            page.evaluate('p=>window.studioReceive(p)',dict(type='state',project=project,duration=348,loaded=True,library=[],revision=2,busy=False))
            expect(page.locator('#bpmValue')).to_have_text('75.0')
            expect(page.locator('#bpmKind')).to_have_text('BPM · noire · fixe')
            expect(page.locator('#unlockTempo')).to_be_visible()
            page.locator('#unlockTempo').click()
            assert page.evaluate('window.sent.at(-1).args.gridLocked') is False
            project['gridLocked']=False
            page.evaluate('p=>window.studioReceive(p)',dict(type='state',project=project,duration=348,loaded=True,library=[],revision=3,busy=False))
            expect(page.locator('#unlockTempo')).to_be_hidden()
            page.locator('#view-prepare [data-studio-task=smartgrid]').click()
            assert page.evaluate('window.sent.at(-1).args.options.reanalyze') is True
            page.locator('#editTempo').click()
            expect(page.locator('#view-guides')).to_be_visible()
            expect(page.locator('#setting-referenceBPM')).to_be_focused()
            project.update(bpm=75,beats=[.18,.98,1.78,2.58,3.38,4.18],settings=dict(
                gridMode='detected',manualBPM=113,pulseUnit='dottedQuarter',referenceBPM=113,
                beatsPerBar=2,firstBeat=.98))
            page.evaluate('p=>window.studioReceive(p)',dict(type='state',project=project,duration=348,loaded=True,library=[],revision=4,busy=False))
            expect(page.locator('#bpmValue')).to_have_text('113.0')
            expect(page.locator('#bpmKind')).to_have_text('BPM · noire · référence')
            expect(page.locator('#guideTempoDetail')).to_contain_text('112.5 BPM à la noire')
            expect(page.locator('#guideTempoDetail')).to_contain_text('75.0 pulsations/min')
            expect(page.locator('#setting-pulseUnit')).to_have_value('dottedQuarter')
            expect(page.locator('#setting-firstBeat')).to_have_value('0.98')
            page.locator('#setting-referenceBPM').fill('')
            page.locator('#guideForm button[type=submit]').click()
            submitted=page.evaluate('window.sent.at(-1).args.value')
            assert submitted['referenceBPM'] is None
            assert submitted['firstBeat']==.98 and submitted['pulseUnit']=='dottedQuarter'
            assert submitted['gridMode']=='detected'
            assert not errors
            browser.close()
    finally:server.shutdown();server.server_close()
