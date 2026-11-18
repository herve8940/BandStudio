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
