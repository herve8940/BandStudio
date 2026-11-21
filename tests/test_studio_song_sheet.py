"""Musical positions, word timing and chord corrections in the per-song sheet."""
import copy
import functools
import os
from pathlib import Path
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sheet_page():
    from playwright.sync_api import sync_playwright
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    host = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=ROOT/'desktop/studio/web'))
    threading.Thread(target=host.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        browser = getattr(pw, os.environ.get('BANDSTUDIO_BROWSER', 'chromium')).launch(
            **({'channel': os.environ['BANDSTUDIO_BROWSER_CHANNEL']} if os.environ.get('BANDSTUDIO_BROWSER_CHANNEL') else {}))
        page = browser.new_page(viewport={'width':1360, 'height':900})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.add_init_script('window.sent=[];window.webkit={messageHandlers:{studio:{postMessage:m=>window.sent.push(m)}}};')
        page.goto(f'http://127.0.0.1:{host.server_port}/index.html')
        project = dict(id='sheet-song', name='Fiche <test>', bpm=120, key='Fm', notes='', cues=[],
                       tracks=[dict(id='audio', name='Original', role='source', file='audio.wav', offset=0,
                                    duration=20, gain=1, muted=False, solo=False, peaks=[.2]*200)],
                       settings=dict(gridMode='fixed', manualBPM=120, firstBeat=.5, beatsPerBar=4),
                       sections=[dict(id='intro', name='Intro', start=0, end=4.5),
                                 dict(id='verse', name='Couplet', start=4.5, end=20)],
                       chords=[dict(id='chord', text='Fm', start=.5, end=8.5, manual=False)],
                       lyrics=[dict(id='line', text='Paroles test', start=1, end=2, manual=False,
                                    words=[dict(text='Paroles', start=1, end=1.4), dict(text='test', start=1.5, end=2)])])
        page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:20,loaded:true,library:[],revision:1,undo:true})', project)
        page.locator('.rail [data-view=sheet]').click()
        try:
            yield page, project
            assert not errors, errors
        finally:
            browser.close()
            host.shutdown()
            host.server_close()


def test_sheet_moves_line_with_words_and_adds_chord(sheet_page):
    page, project = sheet_page
    assert page.locator('#sheetMeta').inner_text().startswith('Fiche <test>')
    assert page.locator('.sheet-section').count() == 2
    assert page.locator('.sheet-bar[data-bar="0"]').inner_text().startswith('Levée')
    page.locator('[data-annotation=line]').first.click()
    page.locator('[data-shift="bar+"]').click()
    assert page.locator('#annotationStart').input_value() == '3'
    assert page.locator('#annotationEnd').input_value() == '4'
    assert page.locator('#wordRows [data-word=start]').first.input_value() == '3'
    page.locator('#sheetStartBar').fill('5')
    page.locator('#sheetStartBar').press('Tab')
    assert page.locator('#annotationStart').input_value() == '9'
    page.locator('#annotationForm button[type=submit]').click()
    sent = page.evaluate('window.sent.at(-1)')
    assert sent['command'] == 'annotation' and sent['projectID'] == project['id']
    assert sent['args']['start'] == 9 and sent['args']['end'] == 10
    assert sent['args']['words'] == [dict(text='Paroles',start=9,end=9.4),dict(text='test',start=9.5,end=10)]
    page.locator('.sheet-bar[data-bar="2"] [data-add=chords]').click()
    page.locator('#annotationText').fill('Bbsus4')
    page.locator('#annotationForm button[type=submit]').click()
    args = page.evaluate('window.sent.at(-1).args')
    assert args.pop('id',None) is None
    assert args == dict(kind='chords',text='Bbsus4',start=2.5,end=4.5,replaceRange=True)
    # The export receives the original project and the player's transposition.
    page.evaluate('window.studioReceive({type:"transport",position:3,rate:1,pitch:2,mode:"mix"})')
    assert page.locator('[data-annotation=chord]').first.inner_text().startswith('Gm')
    assert page.locator('.sheet-bar.playing').get_attribute('data-bar') == '2'
    page.locator('#sheetExport').click()
    assert page.evaluate('window.sent.at(-1).args') == dict(kind='sheet',options=dict(pitch=2))


def test_sheet_positions_follow_detected_beats_and_first_measure(sheet_page):
    page, _ = sheet_page
    result = page.evaluate('''() => {
      const grid=bandStudioSheetGrid({bpm:120,beats:[0,.5,1,1.5,2,2.6,3.2,3.8,4.4,5,5.6],
        settings:{gridMode:'detected',firstBeat:2,beatsPerBar:4}},6);
      return {origin:grid.origin,start:grid.at(4),position:grid.position(5),
              roundtrip:[.1,1.75,2,4.73,5.9].map(t=>grid.at(grid.coordinate(t)))};
    }''')
    assert result['origin'] == 0 and result['start'] == pytest.approx(2)
    assert result['position'] == dict(bar=3,beat=2)
    assert result['roundtrip'] == pytest.approx([.1,1.75,2,4.73,5.9])


def test_held_words_are_shown_once_across_bars_and_sections(sheet_page):
    page, project = sheet_page
    project['lyrics'] = [dict(id='held', start=4.4, end=6, text='Un mot',
                             words=[dict(text='Un', start=4.4, end=5.2), dict(text='mot', start=5.3, end=6)]),
                         dict(id='plain', start=7, end=12, text='Une ligne sans horaires de mots')]
    project['chords'][0]['text']='F:min7'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:20,loaded:true,library:[],revision:2})',project)
    assert page.locator('[data-annotation=held] .sheet-entry-text').all_text_contents() == ['Un','mot']
    assert page.locator('[data-annotation=plain] .sheet-entry-text').all_text_contents() == ['Une ligne sans horaires de mots']
    assert page.locator('[data-annotation=chord] .sheet-entry-text').first.inner_text() == 'Fm7'


def test_album_identity_follows_song_and_ambiguous_names_do_not_pick_a_cover(sheet_page):
    page, project = sheet_page
    entry=dict(name=project['name'],title='Titre de l’album',artist='Le groupe',album='Notre album',path='/song')
    page.evaluate('({p,e})=>studioReceive({type:"state",project:p,duration:20,loaded:true,library:[e],revision:2})',dict(p=project,e=entry))
    assert page.locator('#sheetTitle').inner_text() == entry['title']
    assert page.locator('#sheetArtist').inner_text() == entry['artist']
    assert page.locator('#sheetAlbum').inner_text() == entry['album']
    page.evaluate('({p,e})=>studioReceive({type:"state",project:p,duration:20,loaded:true,library:[e,{...e,path:"/another"}],revision:3})',dict(p=project,e=entry))
    assert page.locator('#sheetAlbum').inner_text() == 'Ta grille de répétition'
    assert page.locator('#sheetCover').is_disabled()


def test_sheet_rejects_out_of_range_move_and_binds_to_each_song(sheet_page):
    page, project = sheet_page
    page.locator('[data-annotation=line]').first.click()
    page.locator('[data-shift="bar-"]').click()
    assert page.locator('#annotationStart').input_value() == '1.000'
    assert 'limites' in page.locator('#sheetPositionError').inner_text()
    next_song = copy.deepcopy(project)
    next_song.update(id='second-song',name='Deuxième morceau',lyrics=[],chords=[],sections=[])
    page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:20,loaded:true,library:[],revision:2})',next_song)
    assert not page.locator('#annotationEditor').is_visible()
    assert 'Deuxième morceau' in page.locator('#sheetMeta').inner_text()
    assert page.locator('[data-annotation]').count() == 0
    assert 'Aucune parole' in page.locator('#sheetHint').inner_text()
    page.locator('.sheet-bar[data-bar="1"] [data-add=lyrics]').click()
    page.locator('#annotationText').fill('Nouvelle ligne')
    page.locator('#annotationForm button[type=submit]').click()
    assert page.evaluate('window.sent.at(-1).projectID') == 'second-song'
    page.evaluate('p=>window.studioReceive({type:"state",project:p,duration:20,loaded:true,library:[],revision:3,busy:true})',next_song)
    assert page.locator('#sheetExport').is_disabled()
    assert page.locator('[data-add=lyrics]').first.is_disabled()


def test_chord_replacement_preserves_both_tails_and_undo(tmp_path):
    from test_studio_advanced import project, model, Api, ENGINE
    p = project(tmp_path)
    original_chords = copy.deepcopy(p['chords'])
    model.save(p,tmp_path)
    api = Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path;api._audio.load(p,tmp_path)
    api.command(dict(command='annotation',projectID=p['id'],args=dict(kind='chords',text='G7',start=4,end=6,replaceRange=True)))
    saved=model.load(tmp_path)
    assert [(x['start'],x['end'],x['text']) for x in saved['chords']] == [(0,4,'D/F#'),(4,6,'G7'),(6,12,'D/F#')]
    assert len({x['id'] for x in saved['chords']}) == 3
    assert all(x['manual'] for x in saved['chords'])
    api.command(dict(command='undo',projectID=p['id'],args={}))
    assert model.load(tmp_path)['chords'] == original_chords


def test_reference_search_uses_current_song_without_changing_annotations(sheet_page):
    page, project = sheet_page
    project['name']='Muse - Hysteria [Official Music Video]'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:20,loaded:true,library:[],revision:2})',project)
    for kind in ('chords','lyrics'):
        page.locator('#sheetSearch-'+kind).click()
        assert page.evaluate('window.sent.at(-1)') == dict(command='referenceSearch', projectID=project['id'],
                                                           args=dict(kind=kind,query='Muse Hysteria'))


def test_reference_search_opens_encoded_query_and_preserves_song(tmp_path, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from test_studio_advanced import project, model, Api, ENGINE
    import webbrowser
    p=project(tmp_path);model.save(p,tmp_path)
    api=Api(ENGINE,tmp_path/'library');api._project=p;api._root=tmp_path
    opened=[];monkeypatch.setattr(webbrowser,'open',lambda url:opened.append(url) or True)
    before=copy.deepcopy(p)
    for kind in ('chords','lyrics'):
        assert api.command(dict(command='referenceSearch',projectID=p['id'],args=dict(kind=kind,query='AC/DC & Muse # live')))['ok']
        parsed=urlparse(opened[-1])
        assert (parsed.scheme,parsed.netloc,parsed.path,parsed.fragment)==('https','www.google.com','/search','')
        assert parse_qs(parsed.query)['q']==['AC/DC & Muse # live'+(' chords accords' if kind=='chords' else ' lyrics paroles')]
    assert p==before and not api._history


def test_manual_lyrics_button_nudges_words_auditions_and_saves(sheet_page):
    page,p=sheet_page
    page.locator('#sheetManualLyrics').click()
    assert page.locator('#annotationEditor').is_visible()
    assert page.locator('#wordEditor').get_attribute('open') is not None
    for _ in range(3):page.locator('[data-shift-seconds="0.1"]').click()
    page.locator('[data-shift-seconds="-0.1"]').click()
    assert float(page.locator('#annotationStart').input_value())==pytest.approx(1.2)
    assert float(page.locator('#annotationEnd').input_value())==pytest.approx(2.2)
    assert float(page.locator('#wordRows [data-word=start]').first.input_value())==pytest.approx(1.2)
    page.get_by_role('button',name='Écouter cette ligne',exact=True).click()
    assert page.evaluate('sent.at(-1).command')=='audition'
    assert page.evaluate('sent.at(-1).args.start')==pytest.approx(.7)
    assert page.evaluate('sent.at(-1).args.end')==pytest.approx(2.7)
    page.get_by_role('button',name='Enregistrer le calage',exact=True).click()
    saved=page.evaluate('sent.at(-1)')
    assert saved['command']=='annotation' and saved['args']['kind']=='lyrics'
    assert saved['args']['start']==pytest.approx(1.2)
    assert saved['args']['words'][1]['start']==pytest.approx(1.7)
