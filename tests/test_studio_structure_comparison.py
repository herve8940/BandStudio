"""Visual comparisons use real project geometry and existing audio commands."""
import copy
import pytest
from test_studio_manual_editor import manual_page
from test_studio_structure_review import ui_proposal


def display(page,p,prepared=False):
    draft=ui_proposal(p);draft['sections']=[copy.deepcopy(p['sections'][0]),dict(id='break',name='Break',start=8.5,end=8.75),dict(id='end',name='Refrain',start=8.75,end=32)]
    draft['changes']=[dict(id='change',kind='insert',time=8.75,before='Refrain',after='Refrain',reason='Audio <script> sûr')]
    if prepared:
        draft.update(status='prepared',beforeSections=copy.deepcopy(p['sections']));p['sections']=copy.deepcopy(draft['sections'])
    p['structureProposal']=draft
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)


def test_exact_shared_geometry_short_break_zoom_and_safe_read_only_selection(manual_page):
    page,p=manual_page;display(page,p)
    assert page.locator('#comparisonDetail').is_hidden()
    for lane in ('current','proposed'):
        b=page.locator(f'[data-comparison-lane={lane}] [data-section-id=a]')
        assert b.evaluate('e=>parseFloat(e.style.left)')==pytest.approx(.5/32*100)
        assert b.evaluate('e=>parseFloat(e.style.width)')==pytest.approx(8/32*100)
    assert page.locator('[data-section-id=break]').evaluate('e=>parseFloat(e.style.width)')==pytest.approx(.25/32*100)
    page.locator('#comparisonChanges button').click();assert page.locator('#comparisonDetail').is_visible()
    page.locator('.comparison-reason summary').click()
    assert '<script>' in page.locator('.comparison-reason p').inner_text()
    page.locator('#comparisonZoom').click()
    assert page.locator('#comparisonZoom').get_attribute('aria-pressed')=='true'
    current=page.locator('[data-comparison-lane=current] [data-section-id=b]').bounding_box()
    proposed=page.locator('[data-section-id=break]').bounding_box()
    assert current['x']==pytest.approx(proposed['x'])
    assert not page.evaluate('sent.some(m=>["applyStructure","seek","play"].includes(m.command))')


def test_selected_listening_restores_loop_and_space_does_not_toggle_global_playback(manual_page):
    page,p=manual_page;display(page,p)
    page.evaluate('transport.loop=true;transport.loopStart=2;transport.loopEnd=5')
    page.locator('#comparisonChanges button').click()
    page.locator('#comparisonListen').focus();page.keyboard.press('Space')
    assert page.evaluate('sent.at(-1)')==dict(command='audition',projectID=p['id'],args=dict(start=5.75,end=14.75))
    assert not page.evaluate('sent.some(m=>m.command==="play")')
    page.locator('.rail [data-view=prompter]').click()
    assert page.evaluate('sent.slice(-2).map(m=>m.command)')==['stop','loop']
    assert page.evaluate('sent.at(-1).args')==dict(on=True,start=2,end=5)


@pytest.mark.parametrize('width',[760,960,1024,1360])
def test_prepared_before_after_responsive_and_no_second_apply(manual_page,width):
    page,p=manual_page;page.set_viewport_size(dict(width=width,height=1000));display(page,p,True)
    assert page.locator('.comparison-current .comparison-label strong').inner_text()=='AVANT'
    assert page.locator('.comparison-proposed .comparison-label strong').inner_text()=='PRÉPARÉE'
    assert page.locator('[data-comparison-lane=current] .comparison-section').count()==2
    assert page.locator('[data-comparison-lane=proposed] .comparison-section').count()==3
    assert page.locator('#applyStructure').is_hidden() and page.locator('#dismissStructure').is_hidden()
    assert page.locator('#prepareAllStructure').is_visible()
    assert page.locator('#structureReview').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    page.locator('#comparisonChanges button').click()
    assert page.locator('#comparisonDetail').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    page.locator('#exportStructure').click();assert page.locator('#view-delivery').is_visible()
    assert not page.evaluate('sent.some(m=>["applyStructure","exportStructure"].includes(m.command))')


def test_dirty_state_blocks_preparation_and_comparison_then_resets_header(manual_page):
    page,p=manual_page;display(page,p,True)
    page.locator('#notes').fill('unsaved')
    assert page.locator('#comparisonZoom').is_disabled() and page.locator('#prepareAllStructure').is_disabled()
    p.pop('structureProposal');page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert 'Une nouvelle lecture' in page.locator('.structure-review-heading').inner_text()
