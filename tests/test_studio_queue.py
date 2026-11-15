"""Queue ownership, resumable checkpoints, worker lifecycle and browser controls."""
import functools
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop/studio'))
import batch_queue as batch
import batch_project
from services import atomic
from platform_tools import executable
from windows import project as model


@pytest.fixture
def queue_setup(tmp_path):
    engine, library = tmp_path / 'Engine', tmp_path / 'Bibliothèque é'
    engine.mkdir(); library.mkdir()
    source = tmp_path / 'Morceau é.wav'
    samples = np.sin(2 * np.pi * 440 * np.arange(4410) / 44100) * .1
    sf.write(source, np.column_stack([samples, samples]), 44100, subtype='FLOAT')
    work = batch.PreparationQueue(engine, library)
    work.command(dict(action='add', kind='file', sources=[str(source)]))
    return work, source


def second_file(source):
    other = source.with_name('Deuxième morceau.wav')
    shutil.copy2(source, other)
    return other


def heartbeat(work):
    work.command(dict(action='heartbeat', ready=True))


def fake_workers(monkeypatch, work, source, failures=None):
    """Real files and result application; model inference itself is deterministic here."""
    calls = []
    failures = failures if failures is not None else set()
    monkeypatch.setattr(batch_project, 'plan', lambda engine: ['import', 'separate', 'grid', 'guides'])
    def launch(args, **kwargs):
        kind = args[2]
        result = Path(args[args.index('--output') + 1])
        item = next(e for e in work.items if e['status'] == 'pending')
        calls.append((item['id'], kind))
        if (item['id'], kind) in failures:
            kwargs['stderr'].write(b'Analysis failed for this song\n');kwargs['stderr'].flush()
            return type('Process', (), dict(returncode=1, poll=lambda self: 1))()
        if kind == 'decode':
            dest = result.parent / 'import.wav';shutil.copy2(source, dest)
            value = dict(audio=str(dest), title=item['title'])
        elif kind == 'separate':
            tracks = []
            for role in ('vocals', 'bass', 'drums', 'other'):
                dest = result.parent / (role + '.wav');shutil.copy2(source, dest)
                tracks.append(dict(path=str(dest), role=role))
            value = dict(tracks=tracks)
        elif kind == 'grid':
            value = dict(beats=[0, .05], bpm=120)
        else:
            files = {}
            for index, key in enumerate(('click', 'calls', 'counts', 'number:1', 'call:section')):
                dest = result.parent / (str(index) + '.wav');shutil.copy2(source, dest);files[key] = str(dest)
            value = dict(files=files)
        atomic(result, value)
        return type('Process', (), dict(returncode=0, poll=lambda self: 0))()
    monkeypatch.setattr(batch.subprocess, 'Popen', launch)
    return calls, failures


def finish(work):
    for _ in range(50):
        heartbeat(work);work.tick()
        if not work.enabled:
            return
    raise AssertionError('Queue failed to drain')


def test_file_sources_wait_for_explicit_start_and_publish_separate_projects(queue_setup, monkeypatch):
    work, source = queue_setup
    work.command(dict(action='add', kind='file', sources=[str(second_file(source))]))
    calls, _ = fake_workers(monkeypatch, work, source)
    heartbeat(work);work.tick()
    assert not calls and not list(work.library.glob('*.bandstudio'))
    work.command(dict(action='start'));finish(work)
    assert [e['status'] for e in work.items] == ['done', 'done']
    assert [kind for _, kind in calls] == ['decode', 'separate', 'grid', 'guides'] * 2
    for item in work.items:
        p = model.load(item['project'])
        assert len(p['tracks']) == 8
        assert p['_queueCompleted'] == ['import', 'separate', 'grid', 'guides']
        assert (Path(item['project']) / p['guideFiles']['number:1']).is_file()
        assert (Path(item['project']) / p['guideFiles']['call:section']).is_file()
        assert not p['preparation'].get('validatedAt')
        assert not work.root(item).exists()
    assert source.is_file() and work.items[1]['title'] == 'Deuxième morceau'


def test_failure_does_not_block_next_song_and_retry_preserves_successful_steps(queue_setup, monkeypatch):
    work, source = queue_setup
    first = work.items[0]
    work.command(dict(action='add', kind='file', sources=[str(second_file(source))]))
    calls, failures = fake_workers(monkeypatch, work, source, {(first['id'], 'separate')})
    work.command(dict(action='start'));finish(work)
    assert [e['status'] for e in work.items] == ['error', 'done']
    assert first['completed'] == ['import'] and 'failed' in first['error']
    failures.clear();work.command(dict(action='retry', id=first['id']))
    heartbeat(work);work.tick();assert first['status'] == 'pending'  # Still manual start.
    work.command(dict(action='start'));finish(work)
    assert first['status'] == 'done'
    assert calls.count((first['id'], 'decode')) == 1


def test_checkpoint_recovers_after_crash_and_never_restarts_automatically(queue_setup, monkeypatch):
    work, source = queue_setup
    calls, _ = fake_workers(monkeypatch, work, source)
    work.command(dict(action='start'));heartbeat(work);work.tick()
    # Simulate commit succeeded but the queue file was not updated.
    item = work.items[0]
    batch_project.apply(item, 'import', work.root(item), work.directory / item['id'] / 'work', work.library)
    # A crashed process releases its handles; Windows cannot remove an open log.
    work.log.close()
    recovered = batch.PreparationQueue(work.engine, work.library)
    heartbeat(recovered);recovered.tick()
    assert not recovered.enabled and recovered.items[0]['completed'] == ['import']
    assert len(calls) == 1
    calls, _ = fake_workers(monkeypatch, recovered, source)
    recovered.command(dict(action='start'));finish(recovered)
    assert calls[0][1] == 'separate'


def test_publish_recovery_and_remove_history_never_delete_finished_audio(queue_setup, monkeypatch):
    work, source = queue_setup
    fake_workers(monkeypatch, work, source)
    work.command(dict(action='start'));finish(work)
    item = work.items[0];target = Path(item['project'])
    item['status'] = 'pending';work.save()
    recovered = batch.PreparationQueue(work.engine, work.library)
    assert recovered.items[0]['status'] == 'done'
    recovered.command(dict(action='remove', id=item['id']))
    assert (target / 'Audio/original.wav').is_file()


def test_duplicate_inputs_and_invalid_batch_are_atomic(queue_setup):
    work, source = queue_setup
    work.command(dict(action='add', kind='file', sources=[str(source), str(source)]))
    assert len(work.items) == 1
    other = second_file(source)
    with pytest.raises(ValueError):
        work.command(dict(action='add', kind='file', sources=[str(other), str(source.with_name('absent.wav'))]))
    assert len(work.items) == 1
    with pytest.raises(ValueError):
        work.command(dict(action='add', kind='url', sources=['https://example.com/song.mp3']))
    assert len(work.items) == 1
    with pytest.raises(ValueError):
        work.command(dict(action='add', kind='file', sources=[str(other)], options={'model': '../bad'}))


def test_busy_host_and_missing_heartbeat_prevent_work(queue_setup, monkeypatch):
    work, source = queue_setup
    calls, _ = fake_workers(monkeypatch, work, source)
    work.command(dict(action='start'));work.tick();assert not calls
    work.command(dict(action='heartbeat', ready=False));work.tick();assert not calls
    heartbeat(work);work.heartbeat -= 5;work.tick();assert not calls
    heartbeat(work);work.tick();assert len(calls) == 1


def test_missing_separation_engine_leaves_the_entire_list_pending(queue_setup):
    work, source = queue_setup
    work.command(dict(action='add', kind='file', sources=[str(second_file(source))]))
    work.command(dict(action='start'));heartbeat(work);work.tick()
    assert not work.enabled and work.proc is None and 'Installe' in work.message
    assert all(item['status'] == 'pending' for item in work.items)


def test_pause_stops_real_worker_and_retains_pending_task(queue_setup, monkeypatch):
    work, source = queue_setup
    monkeypatch.setattr(batch_project, 'plan', lambda engine: ['import'])
    monkeypatch.setattr(batch_project, 'request', lambda *a: [sys.executable, '-c', 'import time; time.sleep(60)'])
    work.command(dict(action='start'));heartbeat(work);work.tick()
    proc = work.proc
    work.command(dict(action='pause'))
    assert proc.poll() is not None and work.proc is None
    assert work.items[0]['status'] == 'pending' and not work.enabled


def test_real_decode_step_and_staging_remain_outside_visible_library(queue_setup):
    work, source = queue_setup
    engine = Path(os.environ.get('BANDSTUDIO_TEST_ENGINE', ROOT / 'desktop-build/standalone/Engine'))
    if not executable(engine, 'ffmpeg').is_file():
        pytest.skip('Prepared audio engine required')
    item = work.items[0];folder = work.directory / item['id'] / 'work';folder.mkdir(parents=True)
    args = batch_project.request(item, 'import', work.root(item), folder, engine, work.library)
    subprocess.run(args, check=True, capture_output=True, timeout=60)
    p = batch_project.apply(item, 'import', work.root(item), folder, work.library)
    assert p['tracks'][0]['duration'] == pytest.approx(.1)
    assert not list(work.library.glob('*.bandstudio'))
    assert sf.info(work.root(item) / 'Audio/original.wav').subtype == 'FLOAT'


def test_pipe_service_persists_entries_and_reopens_paused(queue_setup, monkeypatch):
    work, source = queue_setup
    for name in ('batch_queue.py', 'batch_project.py', 'services.py', 'listening.py', 'platform_tools.py', 'musical_timing.py'):
        shutil.copy2(ROOT / 'desktop/studio' / name, work.engine / name)
    (work.engine / 'windows').mkdir()
    for name in ('project.py', '__init__.py'):
        shutil.copy2(ROOT / 'desktop/studio/windows' / name, work.engine / 'windows' / name)
    monkeypatch.setattr(batch, 'python_for', lambda engine: Path(sys.executable))
    launch = subprocess.Popen
    diagnostic = work.directory / 'service-test.log'
    def capture_service(*args, **kwargs):
        with diagnostic.open('ab') as log:
            return launch(*args, **{**kwargs, 'stderr': log})
    monkeypatch.setattr(batch.subprocess, 'Popen', capture_service)
    messages = queue.Queue()
    client = batch.Client(work.engine, work.library, messages.put)
    def receive(client):
        try:
            return messages.get(timeout=10)
        except queue.Empty:
            pytest.fail(f'Queue service returned no state (exit={client.proc.poll()}): '
                        + diagnostic.read_text(encoding='utf-8', errors='replace'))
    try:
        assert receive(client)['enabled'] is False
        client.send(dict(action='add', kind='file', sources=[str(second_file(source))]))
        state = receive(client)
        assert len(state['items']) == 2 and state['enabled'] is False
        client.send(dict(action='start'))
        state = receive(client)
        assert state['enabled'] is True and not state['running']  # No host heartbeat.
    finally:
        client.close()
    assert client.proc.returncode == 0
    reopened = batch.Client(work.engine, work.library, messages.put)
    try:
        state = receive(reopened)
        assert len(state['items']) == 2 and state['enabled'] is False
    finally:
        reopened.close()


def test_foreground_project_is_unchanged_by_queue_commands(queue_setup, monkeypatch):
    from windows.host import Api
    work, source = queue_setup
    host = Api(work.engine, work.library)
    before = json.dumps(host._project, sort_keys=True)
    sent = []
    host._batch = type('Client', (), dict(send=lambda self, value: sent.append(value)))()
    monkeypatch.setattr(host, '_dialog', lambda *a, **k: [str(source)])
    host._busy = True  # Files can be queued while another preparation runs.
    host._command(dict(command='batchQueue', args=dict(action='files')))
    assert sent[0]['action'] == 'add' and sent[0]['sources'] == [str(source)]
    assert sent[-1] == dict(action='heartbeat', ready=False)
    assert json.dumps(host._project, sort_keys=True) == before and host._root is None


def test_packagers_include_queue_and_shared_project_model():
    import importlib.util
    spec = importlib.util.spec_from_file_location('windows_package', ROOT / 'tools/package_studio_windows.py')
    package = importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    names = {p.name for p in package.source_files()}
    assert {'batch_queue.py', 'batch_project.py', 'batch.js', 'batch.css', 'project.py'} <= names
    source = (ROOT / 'tools/build_studio_mac.py').read_text()
    assert "'StudioQueue.swift'" in source and "'batch_project.py'" in source and "'project.py'" in source
    assert "BUILD/'Engine/windows'/name" in (ROOT / 'tools/install_studio_mac.py').read_text()


@pytest.mark.parametrize('browser_name', [os.environ['BANDSTUDIO_BROWSER']] if os.environ.get('BANDSTUDIO_BROWSER') else ['chromium', 'webkit'])
def test_queue_ui_adds_files_and_requires_start(tmp_path, browser_name):
    from playwright.sync_api import sync_playwright, expect
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    host = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=ROOT / 'desktop/studio/web'))
    threading.Thread(target=host.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = getattr(p, browser_name).launch(**({'channel':os.environ['BANDSTUDIO_BROWSER_CHANNEL']} if os.environ.get('BANDSTUDIO_BROWSER_CHANNEL') else {}))
            page = browser.new_page(viewport={'width': 1360, 'height': 900})
            errors = [];page.on('pageerror', lambda e: errors.append(str(e)))
            page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>sent.push(m)}}};')
            page.goto(f'http://127.0.0.1:{host.server_port}/index.html')
            page.locator('.rail [data-view=queue]').click()
            expect(page.locator('#queueStart')).to_be_disabled()
            assert page.locator('#queueLinks').count() == 0
            page.locator('#queueFiles').click()
            assert page.evaluate('sent.at(-1).args.action') == 'files'
            assert not page.evaluate('sent.some(m=>m.args.action==="start")')
            item = dict(id='a', title='Titre <script>bad()</script>', source='/musique/un.wav', status='pending', completed=0, total=0)
            page.evaluate('v=>studioReceive({type:"batchQueue",items:[v],enabled:false,status:"En pause",message:"1 morceau(x) ajouté(s)."})', item)
            expect(page.locator('.queue-info h3')).to_have_text(item['title'])
            page.locator('#queueStart').click()
            assert page.evaluate('sent.at(-1).args.action') == 'start'
            item.update(status='error', error='Erreur simulée', completed=1, total=4)
            page.evaluate('item=>studioReceive({type:"batchQueue",items:[item],enabled:false})', item)
            page.get_by_role('button', name='Réessayer', exact=True).click()
            assert page.evaluate('sent.at(-1).args') == {'action': 'retry', 'id': 'a'}
            page.locator('#queueFiles').click()
            assert page.evaluate('sent.at(-1).args.action') == 'files'
            page.set_viewport_size({'width': 960, 'height': 720})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors
            page.evaluate('document.querySelector("main").scrollTop=0')
            page.screenshot(path=str(tmp_path / ('queue-' + browser_name + '.png')), full_page=True)
            browser.close()
    finally:
        host.shutdown();host.server_close()
