"""Known headings help only where the musician's confirmed landmarks allow it."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chord_sources
import structure_sources as sources
import structure_review as review
from test_studio_services import project
from test_studio_structure_review import hysteria, ui_proposal
from test_studio_manual_editor import manual_page


def arrangement():
    return dict(sections=[dict(id=str(i),name=name,start=i*10,end=(i+1)*10,
        origin='analysis',reviewed=i in (1,3),locked=False)
        for i,name in enumerate(['Instrumental','Couplet','Instrumental','Refrain','Instrumental'])])


def ordered(names,publisher='Cifra Club'):
    return dict(publisher=publisher,format='order',entries=names,title='Song',url='https://www.cifraclub.com/muse/hysteria/')


def test_chart_preserves_chordless_headers_and_repeated_occurrences():
    chart=chord_sources.Chart()
    chart.feed('<pre>[Intro]<b>Am</b>[Verse 1]<b>Am</b>[Bridge]\n[Chorus]<b>C</b>[Solo]\n[Verse 2]<b>Am</b></pre>')
    assert chart.sectionOrder==['Intro','Verse 1','Bridge','Chorus','Solo','Verse 2']
    ref=dict(sources=[dict(title='Hysteria',publisher='Cifra Club',url='https://www.cifraclub.com/muse/hysteria/',
                          sectionOrder=chart.sectionOrder)])
    found,checks=sources.chart_references(ref)
    assert found[0]['format']=='order' and found[0]['entries']==chart.sectionOrder
    assert checks[0]['status']=='found'


def test_old_chord_sequences_are_not_a_complete_arrangement():
    source=dict(title='Hysteria',publisher='Cifra Club',url='https://www.cifraclub.com/muse/hysteria/',
                sectionSequences=[dict(kind='verse'),dict(kind='chorus'),dict(kind='instrumental')])
    found,_=sources.chart_references(dict(sources=[source]))
    assert found[0]['format']=='types'
    source['sectionOrder']=['Verse',None,'Chorus']
    found,_=sources.chart_references(dict(sources=[source]))
    assert found[0]['format']=='types'


def test_order_only_renames_existing_passage_between_confirmed_anchors():
    p=arrangement();before=copy.deepcopy(p)
    changes,warnings,count=review.ordered_completion(p,ordered(['Intro','Verse','Solo','Chorus','Outro']))
    assert [(c['time'],c['after']) for c in changes]==[(20,'Solo')]
    assert count==2 and p==before and not warnings


@pytest.mark.parametrize('mode',['unconfirmed','batch','ambiguous'])
def test_incomplete_or_ambiguous_order_abstains(mode):
    p=arrangement();names=['Intro','Verse','Solo','Chorus','Outro']
    if mode!='ambiguous':
        for s in p['sections']:s.update(reviewed=False,origin='reference' if mode=='batch' else 'analysis',locked=mode=='batch')
    else:names.insert(3,'Bridge')
    changes,warnings,_=review.ordered_completion(p,ordered(names))
    assert not changes and warnings


def test_missing_section_signals_gap_without_inventing_a_timestamp():
    p=arrangement();p['sections'].pop(2)
    changes,warnings,count=review.ordered_completion(p,ordered(['Intro','Verse','Solo','Chorus','Outro']))
    assert not changes and count==2
    assert any('Position non établie' in w and 'Solo' in w for w in warnings)


def test_conflicting_sources_preserve_the_complete_structure(monkeypatch):
    p=arrangement();before=copy.deepcopy(p)
    monkeypatch.setattr(review,'measures',lambda p:([0,10,20,30,40],50))
    a=ordered(['Intro','Verse','Solo','Chorus','Outro'])
    b=ordered(['Intro','Verse','Bridge','Chorus','Outro'],'E-Chords')
    sections,changes,warnings,_=review.combine_references(p,None,[a,b])
    assert sections==p['sections'] and not changes and p==before
    assert any('désaccord' in w for w in warnings)


def test_section_examples_are_not_used_as_order(monkeypatch):
    p=arrangement()
    monkeypatch.setattr(review,'measures',lambda p:([0,10,20,30,40],50))
    source={**ordered(['Intro','Verse','Solo','Chorus','Outro']),'format':'types'}
    sections,changes,_,_=review.combine_references(p,None,[source])
    assert sections==p['sections'] and not changes


def test_two_confirmed_offbeat_anchors_bound_timed_completion(monkeypatch):
    p=arrangement()
    p['sections'][1]['start']=10.4;p['sections'][0]['end']=10.4
    p['sections'][3]['start']=30.4;p['sections'][2]['end']=30.4
    # Different named, unconfirmed passage can be split only between confirmed anchors.
    p['sections'][2].update(name='Couplet',start=18);p['sections'][1]['end']=18
    before=copy.deepcopy(p)
    monkeypatch.setattr(review,'measures',lambda p:(list(range(0,50,2)),50))
    ref=dict(duration=50,entries=[dict(time=i*10,name=name) for i,name in enumerate(['Intro','Verse','Solo','Chorus','Outro'])])
    sections,changes,_,count=review.complete_sections(p,ref)
    assert count==2 and p==before
    assert [(c['time'],c['after']) for c in changes]==[(20,'Solo')]
    assert all(s in sections for s in p['sections'] if s['reviewed'])
    assert sections[0]==p['sections'][0] and sections[-1]==p['sections'][-1]


def test_confirmed_generic_section_is_not_a_confirmed_solo_anchor():
    local=[dict(start=0,name='Intro'),dict(start=20,name='Instrumental',reviewed=True),dict(start=40,name='Chorus',reviewed=True)]
    entries=[dict(time=0,name='Intro'),dict(time=20,name='Solo'),dict(time=40,name='Chorus')]
    anchors=review.reference_anchors(local,entries,[0,10,20,30,40],50)
    assert not any(a[0]==20 and a[2] for a in anchors)


def test_hysteria_continuation_keeps_its_boundary_and_becomes_solo():
    p,ref=hysteria();sections,changes,_,_=review.complete_sections(p,ref)
    continuation=next(s for s in sections if 167<s['start']<168)
    original=next(s for s in p['sections'] if s['id']==continuation['id'])
    assert continuation['name']=='Solo'
    assert (continuation['start'],continuation['end'])==(original['start'],original['end'])
    assert any(c['kind']=='rename' and c['time']==continuation['start'] for c in changes)


HOOK='https://www.hooktheory.com/theorytab/view/muse/hysteria'
HOOK_HTML='''<html><head><title>Hysteria by Muse Chords, Melody, and Music Theory Analysis - Hooktheory</title></head>
<body><svg><title>Social logo</title></svg><a class="tb-section-tab" href="#">All Sections</a>
<a class="tb-section-tab active" href="#intro">Intro</a><a class="tb-section-tab" href="#verse">Verse</a>
<a class="tb-section-tab" href="#chorus"><span>Chorus</span></a><a href="#other">Unrelated</a></body></html>'''


def mock_hook(monkeypatch,html):
    class Response:
        status=200;url=HOOK
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,limit):return html.encode()[:limit]
    class Opener:
        def open(self,request,timeout):
            assert timeout<=6 and sources.hook_address(request.full_url)
            return Response()
    monkeypatch.setattr(sources,'build_opener',lambda *a:Opener())


def test_hooktheory_distinguishes_examples_and_validates_identity_and_cache(tmp_path,monkeypatch):
    p=project(tmp_path);p['name']='Muse - Hysteria'
    mock_hook(monkeypatch,HOOK_HTML)
    ref,check=sources.hook_lookup(p)
    assert ref['entries']==['Intro','Verse','Chorus'] and ref['format']=='types' and check['status']=='found'
    monkeypatch.setattr(sources,'build_opener',lambda *a:(_ for _ in ()).throw(OSError('offline')))
    cached,check=sources.hook_lookup(p)
    assert cached==ref and check['status']=='cached'
    p['name']='Other - Hysteria'
    assert sources.hook_lookup(p)[0] is None


def test_hooktheory_rejects_different_song_and_oversized_page(tmp_path,monkeypatch):
    p=project(tmp_path);p['name']='Muse - Hysteria'
    for html in (HOOK_HTML.replace('Hysteria by Muse','Hysteria by Other'),HOOK_HTML+'x'*sources.MAX_BYTES):
        mock_hook(monkeypatch,html)
        assert sources.hook_lookup(p)[0] is None


@pytest.mark.parametrize('url',['https://evil.test/theorytab/view/muse/hysteria','https://www.hooktheory.com@evil.test/theorytab/view/muse/hysteria',
    HOOK+'?redirect=elsewhere',HOOK.replace('https:','http:'),HOOK.replace('.com/','.com:444/'),'file:///tmp/chart'])
def test_hooktheory_bounded_urls(url):
    assert not sources.hook_address(url)


def test_noop_chord_alignment_is_not_advertised_as_a_change(tmp_path,monkeypatch):
    p=project(tmp_path);p['chords']=[dict(id='old',text='Am',start=0,end=12,manual=False)]
    chart=dict(sources=[dict(title='Song',publisher='Cifra Club',url='https://www.cifraclub.com/muse/hysteria/')])
    monkeypatch.setattr(sources,'collect',lambda *a:dict(timed=None,note='',chart=chart,sources=[],checks=[]))
    monkeypatch.setattr(chord_sources,'analyze',lambda *a,**k:dict(segments=[dict(start=0,end=12,text='Am')],reference=chart))
    monkeypatch.setattr(chord_sources,'apply',lambda p,r:p.update(chords=[dict(id='new',text='Am',start=0,end=12,manual=False,confidence=.7)]))
    result=review.propose(p)
    assert not result['chordUpdate'] and result['message']=='Préparation actuelle conservée.'


def test_new_reader_ships_in_both_native_packages():
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('windows_package',root/'tools/package_studio_windows.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    assert root/'desktop/studio/structure_sources.py' in package.source_files()
    assert "'structure_sources.py'" in (root/'tools/build_studio_mac.py').read_text()
    for name in ('song_memory.py','musical_patterns.py','chord_features.py','section_evidence.py'):
        assert root/'desktop/studio'/name in package.source_files()
        assert repr(name) in (root/'tools/build_studio_mac.py').read_text()


def test_sources_ui_is_optional_distinguishes_examples_and_preserves_export(manual_page):
    page,p=manual_page
    page.locator('[data-workspace-mode=structure]').click()
    p['structureProposal']=ui_proposal(p)
    p['structureProposal'].update(confirmedSections=2,sources=[dict(publisher='Hooktheory',format='types',sectionNames=['Intro','Verse','Chorus'])],
        sourceChecks=[dict(publisher='DRUMY',status='found',format='timed'),dict(publisher='Hooktheory',status='found',format='types')])
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    details=page.locator('#structureReviewSources')
    assert not details.evaluate('(e)=>e.open')
    details.locator('summary').click()
    assert 'sans ordre complet' in details.inner_text() and 'Intro · Verse · Chorus' in details.inner_text()
    assert '2 repères confirmés conservés' in page.locator('#structureReviewSourceSummary').inner_text()
    page.locator('#exportStructure').click()
    assert page.evaluate('sent.at(-1).command')=='exportStructure'
    assert page.locator('#validationForm input[required]').count()==3
