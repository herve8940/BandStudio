"""Exercise the workspace through user actions and actual host commands."""
import pytest
from test_studio_manual_editor import manual_page


def test_structure_navigation_fit_and_loop_use_same_section(manual_page):
    page,p=manual_page
    page.locator('[data-workspace-mode=structure]').click()
    page.locator('.structure-row[data-id=b] .structure-name').click()
    assert page.evaluate('sent.at(-1).args.time')==8.5
    assert page.locator('#selectionName').inner_text()=='Refrain'
    page.locator('#zoomSelection').click()
    v=page.evaluate('viewport()')
    assert v['start']<=8.5 and v['end']>=32
    page.locator('[aria-label="Boucler Refrain"]').click()
    assert page.evaluate('sent.at(-1)')==dict(command='loop',projectID='manual',args=dict(on=True,start=8.5,end=32))
    page.locator('.structure-row[data-id=b] .structure-actions button').last.click()
    assert page.locator('#editor').is_visible()
    assert page.locator('#editStart').input_value()=='8.500'


def test_filters_density_and_focus_do_not_change_audio_state(manual_page):
    page,p=manual_page
    p['tracks'] += [{**p['tracks'][0],'id':'bass','role':'bass','name':'Basse'},
                    {**p['tracks'][0],'id':'click','role':'guide_click','name':'Click'}]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.evaluate('sent.length=0')
    page.locator('#workspaceFilter').select_option('instruments')
    assert page.locator('#tracks .track:visible').count()==1
    assert page.locator('#tracks .track:visible').get_attribute('data-id')=='bass'
    page.locator('#workspaceSearch').fill('introuvable')
    assert page.locator('.workspace-empty:visible').inner_text()=='Aucune piste ne correspond à ce filtre.'
    page.locator('#workspaceSearch').fill('')
    page.locator('#workspaceCompact').click()
    assert page.locator('.track-wave:visible canvas').bounding_box()['height']==74
    before=page.locator('.arrangement').bounding_box()['width']
    page.locator('#workspaceFocus').click()
    assert not page.locator('.inspector').is_visible()
    assert page.locator('.arrangement').bounding_box()['width']>before
    assert page.evaluate('sent')==[]


def test_shortcuts_ignore_text_and_modal_and_structure_has_no_overflow(manual_page):
    page,p=manual_page
    page.locator('#workspaceSearch').fill('f')
    page.locator('#workspaceSearch').press('l')
    assert page.locator('#workspaceSearch').input_value()=='fl'
    page.locator('#workspaceSearch').fill('')
    page.locator('[data-workspace-mode=structure]').click()
    page.locator('.structure-name').first.click()
    page.keyboard.press('f')
    assert page.evaluate('viewport().span')==pytest.approx(9.2)
    page.keyboard.press('Alt+ArrowRight')
    assert page.locator('#markerName').inner_text()=='Refrain'
    assert page.locator('#selectionName').inner_text()=='Refrain'
    assert page.locator('#loopStart').input_value()=='8.500'
    assert not page.locator('#zoomSelection').is_disabled()
    for width in (1600,1360,1024,960):
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert page.locator('#structureTable').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')


def test_arbitrary_section_names_are_text_and_manual_protection_is_visible(manual_page):
    page,p=manual_page
    p['sections'][0].update(name='<img src=x onerror=alert(1)>',locked=True,reviewed=True)
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('[data-workspace-mode=structure]').click()
    assert page.locator('#structureTable img').count()==0
    assert page.locator('.structure-status').first.inner_text()=='✓ Validée\nProtégée'
    assert page.locator('.overview-section').first.inner_text()==p['sections'][0]['name']


def test_sidebar_collapses_persists_and_restores_without_changing_section(manual_page):
    page,p=manual_page
    page.locator('[data-workspace-mode=structure]').click()
    page.locator('.structure-row[data-id=b] .structure-name').click()
    page.locator('#zoomSelection').click()
    selected=page.evaluate('({id:selected,start:viewport().start,span:viewport().span})')
    page.evaluate('sent.length=0')
    for width in (1360,960):
        page.set_viewport_size({'width':width,'height':1000})
        before=page.locator('.arrangement').bounding_box()['width']
        page.locator('#sidebarToggle').click()
        assert not page.locator('.rail').is_visible()
        assert page.locator('#sidebarToggle').get_attribute('aria-expanded')=='false'
        assert page.locator('.arrangement').bounding_box()['width']>before+100
        assert page.evaluate('({id:selected,start:viewport().start,span:viewport().span})')==selected
        assert page.locator('#structureTable').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('#sidebarToggle').click()
        assert page.locator('.rail').is_visible()
    assert page.evaluate('sent')==[]
    page.locator('#sidebarToggle').click()
    page.reload()
    assert not page.locator('.rail').is_visible()
    page.locator('#sidebarToggle').click()
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('.rail [data-view=studio]').click()
    page.locator('[data-workspace-mode=rhythm]').click()
    assert page.locator('#editorRhythm').is_visible()
    assert page.locator('#sidebarToggle').is_visible()


def test_online_lyric_correction_is_available_from_the_sheet(manual_page):
    page,p=manual_page
    page.evaluate("view('sheet')")
    page.locator('#sheetCorrectLyrics').click()
    assert page.evaluate('sent.at(-1)')==dict(command='analyze',projectID='manual',args=dict(kind='lyricscorrect',model='htdemucs',language='auto',reanalyze=True))
    p['lyricsReference']=dict(status='corrected',message='Deux lignes recalées.',sources=['LRCLIB'],corrected=2,review=0)
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3,busy:true})',p)
    assert page.locator('#correctLyrics').is_disabled()
    assert page.locator('#lyricsReferenceStatus').inner_text()=='Deux lignes recalées. Sources : LRCLIB'


def test_editor_is_the_only_home_for_song_controls(manual_page):
    page,p=manual_page
    page.locator('[data-workspace-mode=lyrics]').click()
    assert page.locator('#editorAnnotations').is_visible()
    assert page.locator('#editorAnnotations #lyricsTools').count()==1
    assert page.locator('#view-prompter input,#view-prompter select,#view-prompter .annotation-row').count()==0
    page.locator('[data-workspace-mode=chords]').click()
    assert page.locator('#editorHarmonySettings').is_visible()
    page.locator('[data-workspace-mode=rhythm]').click()
    assert page.locator('#editorRhythm #guideForm').is_visible()
    assert page.locator('#guideForm').count()==1
    page.evaluate("view('prompter')")
    page.get_by_role('button',name='Modifier dans l’éditeur',exact=True).click()
    assert page.locator('#workspace').get_attribute('data-editor')=='lyrics'


def test_guide_draft_merges_latest_mix_and_cannot_leak_to_another_song(manual_page):
    page,p=manual_page
    page.locator('[data-workspace-mode=rhythm]').click()
    page.locator('#setting-leadBeats').fill('6')
    p['settings']['clickGain']=.17
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert page.locator('#setting-leadBeats').input_value()=='6'
    assert page.locator('#setting-clickGain').input_value()=='0.17'
    page.locator('#guideForm button[type=submit]').click()
    sent=page.evaluate('sent.at(-1)')
    assert sent['args']['value']['clickGain']==.17
    assert sent['args']['value']['leadBeats']==6
    page.locator('#setting-manualBPM').fill('90')
    p.update(id='another');p['settings']['manualBPM']=110
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.evaluate('guideDirty') is False
    assert page.locator('#setting-manualBPM').input_value()=='110'


def test_import_starts_full_quality_preparation_and_export_runs_preflight(manual_page):
    page,p=manual_page
    page.locator('[data-action=import]').first.click()
    assert page.evaluate('sent.at(-1).args')==dict(prepare=True)
    page.locator('#workflowExport').click()
    assert page.locator('#validationForm').is_hidden()
    page.locator('#saveReaper').click()
    assert page.evaluate('sent.at(-1)')==dict(command='reaper',projectID='manual',args=dict(open=False,preflight=True))


def test_full_preparation_opens_review_with_no_web_chords_and_no_approval(manual_page):
    page,p=manual_page
    p['chordReference']=dict(status='unavailable',sources=[],message='Indisponible')
    p['chords']=[]
    def update(busy,task=''):
        page.evaluate('s=>studioReceive(s)',dict(type='state',project=p,duration=32,loaded=True,library=[],
            revision=3,busy=busy,jobTask=task,jobPlan=['prepareReview','guides'] if busy else [],analysisPlan=[]))
    page.locator('.rail [data-view=prepare]').click()
    update(True,'guides')
    assert page.locator('#prepareAllStructure').get_attribute('aria-current')=='step'
    page.evaluate("studioReceive({type:'preparationFinished',projectID:'manual'})")
    assert page.locator('#view-prepare').is_visible()
    update(False)
    assert page.locator('#view-studio').is_visible() and page.locator('#structureTable').is_visible()
    review=page.locator('#workflowReview')
    assert review.is_enabled() and review.get_attribute('aria-current')=='step'
    assert page.locator('#prepareAllStructure').get_attribute('aria-current') is None
    assert not page.evaluate("sent.some(m=>['play','reviewMarker','validateProject'].includes(m.command))")
    page.locator('.rail [data-view=delivery]').click()
    page.evaluate("studioReceive({type:'preparationFinished',projectID:'different-project'})")
    update(False)
    assert page.locator('#view-delivery').is_visible()


def test_partial_preparation_can_be_reviewed_without_waiting_for_missing_results(manual_page):
    page,p=manual_page
    p.update(beats=[],sections=[],chords=[],lyrics=[])
    page.evaluate("p=>studioReceive({type:'state',project:p,duration:32,loaded:true,library:[],analysisPlan:['prepareReview'],revision:2})",p)
    assert page.locator('#prepareAllStructure').get_attribute('aria-current')=='step'
    page.locator('#workflowReview').click()
    assert page.locator('#workflowReview').get_attribute('aria-current')=='step'
    assert page.locator('#workspace').get_attribute('data-editor')=='tracks'


def test_word_warning_focuses_a_short_context_inside_a_long_line(manual_page):
    page,p=manual_page
    p['lyrics']=[dict(id='phrase',start=2,end=13,text='Hold the note',timingReview=True,words=[
        dict(text='Hold',start=2,end=4),dict(text='the',start=7,end=7.4,timingReview=True),
        dict(text='note',start=8,end=13)])]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('#songReviewListen').click()
    assert page.evaluate('sent.at(-1).args')==dict(start=5.5,end=8.9)
    page.locator('#songReviewEdit').click()
    assert page.locator('#wordRows .word-timing-review').input_value()=='the'


def test_targeted_lyric_listening_needs_no_structure_proposal_and_restores_loop(manual_page):
    page,p=manual_page
    p['lyrics']=[dict(id='uncertain',start=2,end=4,text='Line to check',manual=False,timingReview=True,confidence=.9),
                 dict(id='aligned',start=6,end=8,text='Aligned line',manual=False,timingReview=False,confidence=0),
                 dict(id='manual',start=10,end=12,text='Protected',manual=True,timingReview=True)]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert page.locator('#songReviewCount').inner_text()=='1 passage signalé'
    page.evaluate('studioReceive({type:"transport",position:9,playing:false,rate:1,pitch:0,mode:"original",loop:true,loopStart:8,loopEnd:12})')
    page.locator('#songReviewListen').click()
    assert page.evaluate('sent.at(-1)')==dict(command='audition',projectID='manual',args=dict(start=.5,end=5.5))
    assert page.locator('#workspace').get_attribute('data-editor')=='lyrics'
    page.evaluate('studioReceive({type:"transport",position:1,playing:true,rate:1,pitch:0,mode:"original",loop:true,loopStart:.5,loopEnd:5.5})')
    page.evaluate('studioReceive({type:"transport",position:5.4,playing:true,rate:1,pitch:0,mode:"original",loop:true,loopStart:.5,loopEnd:5.5})')
    assert page.evaluate('sent.at(-1)')==dict(command='loop',projectID='manual',args=dict(on=True,start=8,end=12))
    assert page.locator('#songReviewListen').inner_text()=='Écouter ce passage'
    assert page.locator('#songReviewCount').inner_text()=='1 passage signalé'
    assert page.evaluate('state.project.lyrics')==p['lyrics']
    assert page.locator('#annotations .annotation-row small').first.inner_text()=='Auto · calage incertain'
    page.evaluate("view('sheet')")
    assert page.locator('#songSheet .sheet-entry[data-annotation=uncertain].uncertain').count()>0
    assert page.locator('#songSheet .sheet-entry[data-annotation=aligned].uncertain').count()==0
    page.evaluate("view('studio')")
    page.locator('#songReviewEdit').click()
    assert page.locator('#annotationEditor').is_visible()
    assert page.locator('#annotationText').input_value()=='Line to check'
    page.locator('#annotationText').fill('Corrected line')
    page.locator('#annotationForm button[type=submit]').click()
    assert page.evaluate('sent.at(-1).command')=='annotation'
    assert page.evaluate('sent.at(-1).args.id')=='uncertain'


def test_review_navigation_uses_current_project_and_clears_corrected_warnings(manual_page):
    page,p=manual_page
    p['lyrics']=[dict(id='line',start=2,end=4,text='<img src=x onerror=alert(1)>',manual=False,timingReview=True)]
    p['chords']=[dict(id='chord',start=15,end=16,text='Am',manual=False,confidence=.2)]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert page.locator('#songReview img').count()==0
    assert page.locator('#songReviewChoice option').count()==2
    page.locator('#songReviewNext').click()
    assert page.locator('#workspace').get_attribute('data-editor')=='chords'
    assert page.evaluate('sent.at(-1).args.time')==13.5
    page.locator('#songReviewEdit').click()
    assert page.locator('#annotationText').input_value()=='Am'
    page.locator('[data-close=annotationEditor]').click()
    p['chords'][0]['manual']=True
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#songReviewChoice option').count()==1
    page.locator('[data-workspace-mode=rhythm]').click()
    page.locator('#setting-leadBeats').fill('6')
    assert page.locator('#songReviewListen').is_disabled()
    assert page.locator('#songReviewEdit').is_disabled()
    p.update(id='new-song',lyrics=[],chords=[])
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:4})',p)
    assert page.locator('#songReview').is_hidden()
    assert not page.locator('#annotationEditor').is_visible()


def test_english_editor_preserves_song_text_and_native_commands(manual_page):
    page, song = manual_page
    page.add_init_script("window.bandStudioLanguage = 'en'")
    page.reload()
    assert page.locator('html').get_attribute('lang') == 'en'
    assert page.get_by_role('button', name='My songs', exact=True).is_visible()
    page.get_by_role('button', name='Settings', exact=True).click()
    assert page.locator('#interfaceLanguage').input_value() == 'en'
    page.locator('#interfaceLanguage').select_option('fr')
    assert page.evaluate('sent.at(-1).command') == 'uiLanguage'
    assert page.evaluate('sent.at(-1).args') == {'language': 'fr'}
    page.get_by_role('button', name='My songs', exact=True).click()
    page.locator('header [data-action=import]').click()
    assert page.evaluate('sent.at(-1).command') == 'import'

    song.update(name='Réglages', notes='Mon refrain à vérifier')
    song['sections'][1].update(name='Mes morceaux', origin='manual')
    song['lyrics'] = [dict(id='line', text='Ouvrir', start=8.5, end=12, manual=True)]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:1})', song)
    page.get_by_role('button', name='Song editor', exact=True).click()
    assert page.locator('#title').text_content() == 'Réglages'
    assert page.locator('#notes').input_value() == 'Mon refrain à vérifier'
    page.locator('[data-workspace-mode=structure]').click()
    page.locator('.structure-row[data-id=b] .structure-name').click()
    assert page.locator('#selectionName').text_content() == 'Mes morceaux'
    page.get_by_role('button', name='Loop Mes morceaux', exact=True).click()
    assert page.evaluate('sent.at(-1).command') == 'loop'
    page.get_by_role('button', name='Song sheet', exact=True).click()
    assert page.get_by_role('button', name='Export PDF song sheet').is_visible()
    assert page.locator('#view-sheet').get_by_text('Ouvrir', exact=True).first.is_visible()
