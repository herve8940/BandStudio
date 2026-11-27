"""Explore without seeking and verify that saved arrangements carry audio and annotations."""
import copy
import json

import numpy as np
import pytest
import soundfile as sf
from test_studio_manual_editor import manual_page
from test_studio_advanced import project
from musical_timing import BeatClock
from passage_edit import align, variant


def test_pan_without_seeking_and_explicit_return(manual_page):
    page,_=manual_page
    page.locator('#zoomIn').click()
    page.evaluate('studioReceive({type:"transport",position:1,playing:true,rate:1,mode:"original"})')
    frame=page.locator('.explore-frame').bounding_box()
    x,y=frame['x']+frame['width']/2,frame['y']+10
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+frame['width']*.8,y,steps=4);page.mouse.up()
    v=page.evaluate('viewport()')
    assert v['start']>10 and v['span']==16
    assert not page.locator('#zoomFollow').is_checked()
    page.evaluate('studioReceive({type:"transport",position:2,playing:true,rate:1,mode:"original"})')
    assert page.evaluate('viewport()')==v
    assert page.evaluate('sent.filter(m=>m.command==="seek")')==[]
    page.locator('#exFollow').click()
    assert page.evaluate('viewport().start')<=2 and page.locator('#zoomFollow').is_checked()
    page.locator('#exBack').click()
    assert page.evaluate('viewport().start')==pytest.approx(v['start'])
    box=page.locator('#ruler').bounding_box()
    page.mouse.click(box['x']+box['width']/2,box['y']+6)
    assert page.evaluate('sent.at(-1).args.time')==pytest.approx(v['start']+8,abs=.1)


def test_range_search_bookmarks_and_native_actions(manual_page):
    page,p=manual_page
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,exploreAdaptation:true})',p)
    page.locator('#openExplorer').click()
    page.locator('#markerSnap').select_option('free')
    page.locator('#exRange').scroll_into_view_if_needed()
    box=page.locator('#exRange').bounding_box()
    y=box['y']+10
    page.mouse.move(box['x']+box['width']/4,y);page.mouse.down()
    page.mouse.move(box['x']+box['width']/2,y,steps=8);page.mouse.up()
    a,b=[float(page.locator(k).input_value()) for k in ('#exA','#exB')]
    assert (a,b)==pytest.approx((8,16),abs=.15)
    for key,command in [('#exListen','auditionOnce'),('#exReplay','auditionOnce'),('#exLoop','audition'),('#exJoin','previewJoin')]:
        page.locator(key).click()
        msg=page.evaluate('sent.at(-1)')
        assert msg['command']==command
        assert [msg['args'][k] for k in ('start','end')]==pytest.approx((a,b),abs=.001)
    page.locator('#exFit').click();page.locator('#exMark').click()
    v=page.evaluate('viewport()')
    page.locator('#exQuery').fill('M12');page.locator('#exGo').click()
    assert page.evaluate('viewport().start')>v['start']
    page.locator('#exQuery').fill('refrain');page.locator('#exQuery').press('Enter')
    assert 'Refrain' in page.locator('#exResults').inner_text()
    page.locator('#exRecall').click()
    assert page.evaluate('viewport()')==v
    page.locator('#exBars').fill('4');page.locator('#exGrid').click()
    assert page.evaluate('sent.at(-1).args.bars')==4
    p['id']='another'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,exploreAdaptation:true})',p)
    assert page.locator('#exRecall').is_disabled() and page.locator('#exJoin').is_disabled()


@pytest.mark.parametrize('edit,expected', [('cut',8),('repeat',16)])
def test_variant_audio_words_cues_and_offsets(tmp_path,edit,expected):
    p=project(tmp_path)
    p['tracks'][1]['offset']=.125
    p['lyrics'][0]['end']=3
    p['cues']=[dict(id='c',name='test',time=3)]
    before=copy.deepcopy(p)
    out=tmp_path/'Variant.bandstudio'
    variant(p,dict(start=2,end=6,edit=edit),out)
    v=json.loads((out/'project.json').read_text())
    assert p==before and v['id']!=p['id']
    assert len(v['cues'])==(0 if edit=='cut' else 2)
    assert all(0<=w['start']<w['end']<=line['end'] for line in v['lyrics'] for w in line['words'])
    assert all(t['duration']==pytest.approx(expected+.125,abs=1/44100) for t in v['tracks'])
    source,sr=sf.read(tmp_path/p['tracks'][1]['file'],always_2d=True)
    timeline=np.pad(source,((round(.125*sr),0),(0,0)))
    pieces=[timeline[:2*sr],timeline[6*sr:]] if edit=='cut' else [timeline[:6*sr],timeline[2*sr:6*sr],timeline[6*sr:]]
    result,_=sf.read(out/v['tracks'][1]['file'],always_2d=True)
    np.testing.assert_allclose(result,np.concatenate(pieces),atol=1e-7)


def test_local_meter_and_beats_after_alignment(tmp_path):
    p=project(tmp_path);p['settings']['gridMode']='fixed'
    clock=BeatClock(p)
    new=align(p,dict(start=2,end=5,bars=2,meter=3))
    p.update(new,gridLocked=True);p['settings']['gridMode']='detected'
    updated=BeatClock(p)
    assert [t for t in clock.beats if t<2 or t>5]==[t for t in updated.beats if t<2 or t>5]
    assert [updated.bar_phase(t) for t in (2,2.5,3.5,5)]==[(0,3),(1,3),(0,3),(0,4)]
    with pytest.raises(ValueError):align(p,dict(start=0,end=.05,bars=256,meter=12))


def test_overview_drag_resize_and_trackpad(manual_page):
    page,_=manual_page
    page.locator('#zoomIn').click()
    page.locator('#workspaceOverview').scroll_into_view_if_needed()
    rect=page.locator('#workspaceOverview .overview-window').bounding_box()
    x=rect['x']+rect['width']/2;y=rect['y']+10
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+rect['width']/2,y,steps=6);page.mouse.up()
    v=page.evaluate('viewport()')
    assert v['start']>7 and v['span']==16
    grip=page.locator('.explore-frame [data-edge=end]').bounding_box()
    x=grip['x']+grip['width']/2;y=grip['y']+8
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x-70,y,steps=4);page.mouse.up()
    smaller=page.evaluate('viewport()')
    assert smaller['span']<v['span'] and smaller['start']==pytest.approx(v['start'])
    page.locator('.track-wave').first.dispatch_event('wheel',dict(deltaX=80,deltaY=1))
    assert page.evaluate('viewport().start')>smaller['start']
    assert page.evaluate('sent.filter(m=>m.command==="seek")')==[]
