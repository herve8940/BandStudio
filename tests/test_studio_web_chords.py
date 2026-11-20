"""Web identities, bounded failures, rhythmic placement and manual protection."""
import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import chord_sources as web
from chord_alignment import place,tones
from windows import project as model
from test_studio_manual_editor import manual_page

PAGE='<title>Song - Artist - Cifra Club</title><b>G</b><pre><b>C</b> words <b>G</b> <b>Am</b> <b>C</b><b>Refrain</b></pre>'
URL='https://www.cifraclub.com/artist/song/'

@pytest.fixture(autouse=True)
def no_live_discovery(monkeypatch):
    monkeypatch.setattr(web,'fetch_discovery',lambda query:'<div class="no-results"></div>')
    monkeypatch.setattr(web,'catalog_urls',lambda *args:[])

def song():
    p=model.fresh('Artist - Song (Official Video) [abcdefghijk]')
    p['sessionDuration']=5
    return p

def test_matching_page_extracts_only_chord_facts_and_cache(monkeypatch):
    p=song();calls=[]
    def fetch(url):calls.append(url);return PAGE,url
    monkeypatch.setattr(web,'fetch',fetch)
    result=web.lookup(p)
    source=result['reference']['sources'][0]
    expected=[web.provider_url(p,'Song','Artist') for p in web.PROVIDERS if p.get('template')]
    assert sorted(calls)==sorted(expected)
    assert source['chords']==['C','G','Am']
    assert source['transitions']==[['C','G'],['G','Am'],['Am','C']]
    assert 'words' not in json.dumps(result)
    assert result['segments']==[] and result['reference']['status']=='found'
    p['chordReference']=result['reference']
    assert web.lookup(p)['cacheHit'] is True and len(calls)==len(expected)
    web.lookup(p,reanalyze=True)
    assert len(calls)==2*len(expected)

def test_artwork_identity_strips_duplicate_artist(tmp_path):
    (tmp_path/'Artwork.json').write_text(json.dumps(dict(title='AC/DC - Highway to Hell (Official Video)',artist='AC/DC')))
    assert web.identity(dict(_root=str(tmp_path),name='fallback'))==('Highway to Hell','AC/DC')


@pytest.mark.parametrize('artist,title,uploader',[
    ('Muse','Plug In Baby','MrMuseLyrics'),('Oasis','Wonderwall','MusicVideos'),
    ('AC/DC','Highway to Hell','RockChannel')])
def test_video_uploader_does_not_override_matching_filename_identity(tmp_path,artist,title,uploader):
    full=f'{artist} - {title} [HD]'
    (tmp_path/'Artwork.json').write_text(json.dumps(dict(title=full,artist=uploader)))
    p=dict(_root=str(tmp_path),name=full+' [5rf1Sj6EIFE]')
    assert web.identity(p)==(title,artist)


@pytest.mark.parametrize('metadata,name,expected',[
    (dict(title='Song - Part II',artist='Performer'),'Performer - Song - Part II',('Song - Part II','Performer')),
    (dict(title='Original - Song',artist='Cover Artist',source='https://musicbrainz.org/release-group/verified'),
     'Original - Song',('Original - Song','Cover Artist')),
    (dict(title='Song',artist='Cover Artist'),'Original - Song',('Song','Cover Artist')),
])
def test_curated_identities_covers_and_titles_with_dashes_are_preserved(tmp_path,metadata,name,expected):
    (tmp_path/'Artwork.json').write_text(json.dumps(metadata))
    assert web.identity(dict(_root=str(tmp_path),name=name))==expected


@pytest.mark.parametrize('name', ['The Wallflowers | Heroes (HD Video)', 'The Wallflowers — Heroes (4K Video)', 'The Wallflowers - Heroes [HQ Audio]'])
def test_video_filename_separators_and_quality_tags(name):
    assert web.identity(dict(name=name))==('Heroes','The Wallflowers')


def test_old_uploader_failure_retries_with_correct_provider_urls(tmp_path,monkeypatch):
    (tmp_path/'Artwork.json').write_text(json.dumps(dict(title='Muse - Plug In Baby [HD]',artist='MrMuseLyrics')))
    p=song();p.update(_root=str(tmp_path),name='Muse - Plug In Baby [HD] [5rf1Sj6EIFE]',
        chordReference=dict(query='MrMuseLyrics Muse - Plug In Baby',status='unavailable',sources=[]))
    calls=[]
    def fetch(url):
        calls.append(url)
        return PAGE.replace('Song - Artist','Plug In Baby - Muse'),url
    monkeypatch.setattr(web,'fetch',fetch)
    result=web.lookup(p)
    assert result['reference']['query']=='Muse Plug In Baby'
    assert result['reference']['status']=='found'
    assert sorted(calls)==sorted(web.provider_url(provider,'Plug In Baby','Muse')
                                 for provider in web.PROVIDERS if provider.get('template'))

@pytest.mark.parametrize('page',[PAGE.replace('Song - Artist','Other Song - Elsewhere'),'<title>Song - Artist</title><b>C</b>',PAGE.replace('Song - Artist','Songbook - Artist')])
def test_wrong_identity_and_non_chart_markup_do_not_produce_chords(monkeypatch,page):
    monkeypatch.setattr(web,'fetch',lambda url:(page,url))
    result=web.lookup(song())
    assert result['reference']['status']=='not_found' and result['segments']==[]

def test_missing_artist_and_network_failure_are_explicit(monkeypatch):
    monkeypatch.setattr(web,'fetch',lambda *a:pytest.fail('A title without artist must not be guessed'))
    assert web.lookup(dict(name='unidentified'))['reference']['status']=='not_found'
    def fail(url):raise TimeoutError('offline')
    monkeypatch.setattr(web,'fetch',fail)
    result=web.lookup(song())
    assert result['reference']['status']=='unavailable' and not result['segments']

def test_offline_retry_reuses_only_matching_previously_found_reference(monkeypatch):
    p=song();monkeypatch.setattr(web,'fetch',lambda url:(PAGE,url))
    p['chordReference']=web.lookup(p)['reference']
    def fail(url):raise TimeoutError('offline')
    monkeypatch.setattr(web,'fetch',fail)
    result=web.lookup(p,reanalyze=True)
    assert result['cachedAfterFailure'] and result['reference']==p['chordReference']
    p['name']='Artist - Another Song'
    assert web.lookup(p)['reference']['status']=='unavailable'

def test_section_facts_are_extracted_without_lyrics_or_tab_contents():
    chart=web.Chart();chart.feed('<pre>[Intro]<b>A</b><b>D/F#</b><b>G</b>[Primera Parte]words<b>E5</b>[Estribillo]<b>A</b><b>D</b>[Solo]<b>A</b><b>G</b></pre>')
    assert chart.sections==dict(intro=['A','D/F#','G'],verse=['E5'],chorus=['A','D'],instrumental=['A','G'])

def test_reference_redirect_is_limited_to_public_publisher():
    assert web.safe_url(URL)
    for url in ('http://www.cifraclub.com/a/b','https://evil.test/a','https://user@www.cifraclub.com/a','https://www.cifraclub.com:8080/a'):
        assert not web.safe_url(url)
        with pytest.raises(ValueError):web.Redirects().redirect_request(None,None,302,'',{},url)

@pytest.mark.parametrize('label,expected',[('CM7',[0,4,7,11]),('Cm7+',[0,3,7,11]),('D/F#',[2,6,9]),('E5',[4,11]),('Bdim',[11,2,5]),('Am7(b5)',[9,0,3,7])])
def test_chord_spelling(label,expected):assert tones(label)[0]==expected

def synth(path,changes,duration,detune=-.3):
    sr=11025;t=np.arange(round(duration*sr))/sr;y=np.zeros(len(t))
    for a,b,label in changes:
        selected=(t>=a)&(t<b);local=t[selected]-a
        notes=tones(label)[0]
        signal=sum(sum(.08/(h*h)*np.sin(2*np.pi*440*2**((48+pc-69+detune)/12)*h*local) for h in (1,2,3)) for pc in notes)
        y[selected]=signal*np.minimum(1,local/.01)*np.minimum(1,(b-t[selected])/.01)
    sf.write(path,y,sr)

def test_web_chords_follow_variable_grid_and_offbeats(tmp_path):
    p=song();p['beats']=[.25,.75,1.30,1.80,2.4,2.9,3.4,4.,4.5];p['bpm']=120
    p['tracks']=[dict(role='source',duration=5,offset=0)]
    audio=tmp_path/'chords.wav';changes=[(.25,1.55,'C'),(1.55,2.9,'G'),(2.9,4.5,'Am')]
    synth(audio,changes,5)
    segments,alignment=place(p,audio,['C','G','Am'],URL,transitions=[['C','G'],['G','Am']])
    assert [s['label'] for s in segments]==['C','G','Am']
    assert [s['start'] for s in segments]==pytest.approx([.25,1.55,2.9])
    assert alignment['subdivision']==2 and alignment['status']=='proposed'
    assert alignment['tuningCents']==pytest.approx(-30,abs=6)
    grid=set(p['beats']+[(a+b)/2 for a,b in zip(p['beats'],p['beats'][1:])]+[5])
    assert all(s['start'] in grid and s['end'] in grid and s['sourceURL']==URL for s in segments)

def test_alignment_streams_across_blocks_and_respects_track_offset(tmp_path):
    p=song();p['sessionDuration']=26;p['settings'].update(gridMode='fixed',manualBPM=120,firstBeat=.25)
    p['tracks']=[dict(role='source',duration=24,offset=.25)]
    audio=tmp_path/'blocks.wav';synth(audio,[(0,20,'C'),(20,24,'G')],24,detune=0)
    segments,_=place(p,audio,['C','G'],URL,offset=.25)
    assert [s['label'] for s in segments]==['C','G']
    assert segments[0]['start']==.25 and segments[1]['start']==20.25
    assert segments[-1]['end']<=24.5

def test_compound_pulse_keeps_three_eighth_notes_per_beat(tmp_path):
    p=song();p['tracks']=[dict(role='source',duration=5,offset=0)]
    p['settings'].update(gridMode='fixed',manualBPM=100,firstBeat=.1,pulseUnit='dottedQuarter')
    audio=tmp_path/'compound.wav';synth(audio,[(.1,1.3,'C'),(1.3,2.8,'G'),(2.8,4.6,'Am')],5)
    segments,alignment=place(p,audio,['C','G','Am'],URL)
    assert alignment['subdivision']==3
    assert [s['label'] for s in segments]==['C','G','Am']
    assert [s['start'] for s in segments]==pytest.approx([.1,1.3,2.8])

def test_silence_produces_no_invented_chords(tmp_path):
    p=song();p['settings'].update(gridMode='fixed',manualBPM=120)
    p['tracks']=[dict(role='source',duration=1,offset=0)]
    audio=tmp_path/'silence.wav';sf.write(audio,np.zeros(11025),11025)
    segments,alignment=place(p,audio,['C','G'],URL)
    assert not segments and alignment['status']=='no_audio'

def test_application_replaces_legacy_model_preserving_manual_and_metadata(tmp_path):
    p=song();manual=dict(id='manual',start=0,end=1,text='Am',manual=True)
    p['chords']=[manual,dict(id='bad',start=1,end=5,text='Ab',manual=False)]
    result=dict(engine='web-reference',reference=dict(query='Artist Song',status='found',sources=[],checkedAt=1,message='proposed'),segments=[dict(start=.5,end=1.5,label='C',sourceURL=URL,confidence=.9),dict(start=2,end=3,label='G',sourceURL=URL,confidence=.7)])
    before=copy.deepcopy(p);web.apply(p,result)
    assert p['chords'][0]==manual and len(p['chords'])==2
    assert p['chords'][1]['text']=='G' and p['chords'][1]['sourceURL']==URL
    model.save(p,tmp_path);loaded=model.load(tmp_path)
    assert loaded['chords']==p['chords'] and loaded['chordReference']==result['reference']
    assert p['settings']==before['settings'] and p['beats']==before['beats']
    with pytest.raises(ValueError,match='désactivée'):web.apply(p,dict(segments=[]))

def test_preparation_migrates_old_model_results_but_preserves_validated_work():
    p=song();p['chords']=[dict(start=0,end=3,text='Ab',manual=False)];p['analysesCompleted']=['chords']
    assert not model.analysis_done(p,'chords')
    p['preparation']=dict(fingerprint='approved')
    assert model.analysis_done(p,'chords')

def test_worker_routes_chords_to_web_without_importing_the_legacy_model(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import worker
    p=song();snapshot=tmp_path/'project.json';snapshot.write_text(json.dumps(p))
    output=tmp_path/'job/result.json';expected=dict(engine='web-reference',reference=dict(status='not_found'),segments=[])
    called=[]
    def analyze(project,audio,*,reanalyze,source_url=''):called.append((project,audio,reanalyze));return expected
    monkeypatch.setattr(web,'analyze',analyze)
    monkeypatch.setattr(sys,'path',sys.path.copy())
    monkeypatch.setitem(sys.modules,'reacue_chords',None)
    worker.execute(SimpleNamespace(command='chords',engine=str(tmp_path),input=str(tmp_path/'audio.wav'),output=str(output),project=str(snapshot),reanalyze=True))
    assert json.loads(output.read_text())==expected and called[0][0]==p and called[0][2]

def test_reference_ui_opens_source_and_places_manual_chord_on_grid(manual_page):
    page,p=manual_page
    p['chordReference']=dict(query='Artist Song',status='found',checkedAt=1,message='Calage proposé',sources=[dict(title='<script>bad</script>',publisher='Cifra Club',url=URL,chords=['C','G','Am'])])
    p['chords']=[dict(id='c',start=.5,end=2,text='C',manual=False,sourceURL=URL,confidence=.2)]
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('[data-view="prompter"]').first.click()
    panel=page.locator('#chordReferencePrompter')
    assert panel.locator('script').count()==0
    panel.get_by_role('button',name='Ouvrir la grille',exact=True).click()
    assert page.evaluate('sent.at(-1)')==dict(command='chordSourceOpen',projectID='manual',args=dict(url=URL))
    page.evaluate('transport.position=1.13')
    page.evaluate('renderStage()')
    assert page.locator('#stageChordStatus').inner_text()=='Accord proposé · calage incertain'
    panel.get_by_role('button',name='C',exact=True).click()
    assert float(page.locator('#annotationStart').input_value())==1.25
    assert float(page.locator('#annotationEnd').input_value())==1.75
    assert page.locator('#annotationText').input_value()=='C'
    page.locator('#annotationStart').fill('1.41');page.locator('#annotationEnd').fill('2.22')
    page.locator('#snapChordToGrid').click()
    assert float(page.locator('#annotationStart').input_value())==1.5
    assert float(page.locator('#annotationEnd').input_value())==2.25
    page.locator('#annotationEditor').evaluate('(e)=>e.close()')
    page.locator('.rail [data-view=sheet]').click()
    assert page.locator('[data-annotation=c]').first.locator('.sheet-entry-text').inner_text()=='C ?'
    assert 'Cifra Club' in page.locator('#sheetChordSource').inner_text()
    page.locator('#sheetSearch-chords').click()
    assert page.evaluate('sent.at(-1).args.url')==URL
