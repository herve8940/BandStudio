"""Reference-assisted completion preserves the musician's existing workspace."""
import copy
import json
import os
from pathlib import Path
import sys
import uuid

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import structure_review as review
import chord_alignment
import chord_sources
from cue_feedback import references
from services import atomic, read_rpp
from test_studio_services import project, ENGINE
from test_studio_manual_editor import manual_page

FIXTURES=ROOT/'tests/fixtures/structure'
URL='https://drumy.app/drums/hysteria-muse'


def hysteria():
    p=json.loads((FIXTURES/'hysteria-local.json').read_text())
    reference=review.parse((FIXTURES/'hysteria-map.html').read_text(),'Hysteria','Muse',URL)
    return p,reference


def proposal(p):
    return dict(schema=1,id=str(uuid.uuid4()),fingerprint=review.fingerprint(p),createdAt=0,
        status='proposed',message='Préparation actuelle conservée.',sources=[],anchors=0,
        changes=[],warnings=[],sections=copy.deepcopy(p['sections']),chords=copy.deepcopy(p['chords']),
        chordReference=None,chordUpdate=False)


def test_hysteria_adds_the_two_missing_entries_without_moving_existing_starts():
    p,ref=hysteria();before=copy.deepcopy(p)
    sections,changes,warnings,anchors=review.complete_sections(p,ref)
    assert p==before
    assert anchors==5
    inserted=[c for c in changes if c['kind']=='insert']
    assert [c['after'] for c in inserted]==['Couplet','Solo']
    assert [c['time'] for c in inserted]==pytest.approx([95.4385941043,146.9644897959])
    assert {s['start'] for s in before['sections']} <= {s['start'] for s in sections}
    assert any('anticipation' in w for w in warnings)
    assert all(not s.get('reviewed') for s in sections)


@pytest.mark.parametrize('flag,value',[('locked',True),('reviewed',True),('origin','manual'),('origin','reference')])
def test_protected_sections_survive_even_when_reference_would_split_them(flag,value):
    p,ref=hysteria();target=p['sections'][7];target[flag]=value
    if value=='reference':target['locked']=True
    before=copy.deepcopy(target)
    sections,changes,_,_=review.complete_sections(p,ref)
    assert before in sections
    assert not any(c['kind']=='insert' and before['start']<c['time']<before['end'] for c in changes)


@pytest.mark.parametrize('case',['wrong_version','missing_bars','missing_anchors','reversed_bars'])
def test_unreliable_reference_or_grid_abstains(case):
    p,ref=hysteria()
    if case=='wrong_version':ref['duration']+=45
    if case=='missing_bars':p['downbeats']=[]
    if case=='missing_anchors':p['sections']=[p['sections'][0],p['sections'][7]]
    if case=='reversed_bars':p['downbeats']=p['downbeats'][::-1]
    sections,changes,warnings,_=review.complete_sections(p,ref)
    assert sections==p['sections'] and not changes and warnings


def test_map_requires_identity_order_and_ignores_other_lists():
    page=(FIXTURES/'hysteria-map.html').read_text()
    ref=review.parse(page,'Hysteria','Muse',URL)
    assert len(ref['entries'])==11
    with pytest.raises(ValueError,match='artiste'):review.parse(page,'Hysteria','Other',URL)
    with pytest.raises(ValueError,match='exploitable'):review.parse(page.replace('1:33','0:01'),'Hysteria','Muse',URL)


@pytest.mark.parametrize('url',['http://drumy.app/drums/song','https://evil.test/drums/song',
    'https://drumy.app@evil.test/drums/song','https://drumy.app/drums/song?url=file:///etc/passwd',
    'https://drumy.app:444/drums/song','file:///tmp/song'])
def test_reference_network_is_bounded_to_public_provider(url):
    assert not review.address(url)


def test_cached_structure_is_available_offline_but_not_for_another_artist(tmp_path,monkeypatch):
    p=project(tmp_path);p['name']='Muse - Hysteria'
    page=(FIXTURES/'hysteria-map.html').read_text()
    monkeypatch.setattr(review,'fetch',lambda url:(page,url))
    reference,_=review.lookup(p)
    monkeypatch.setattr(review,'fetch',lambda url:(_ for _ in ()).throw(OSError('offline')))
    cached,note=review.lookup(p)
    assert cached==reference and 'enregistrée' in note
    p['name']='Other - Hysteria'
    assert review.lookup(p)[0] is None


def test_proposal_does_not_clear_existing_chords_when_web_reference_is_missing(tmp_path,monkeypatch):
    p=project(tmp_path);p['chords']=[dict(id='ch',text='Am',start=0,end=8,manual=False)]
    monkeypatch.setattr(review,'lookup',lambda p:(None,'Indisponible'))
    before=copy.deepcopy(p);result=review.propose(p)
    assert result['chords']==p['chords'] and p==before
    assert result['warnings'] and result['chordUpdate'] is False


def test_failed_chord_preparation_preserves_existing_automatic_and_manual_entries(tmp_path):
    p=project(tmp_path);p['chords']=[dict(id='ch',text='Am',start=0,end=8,manual=False)]
    before=copy.deepcopy(p['chords'])
    chord_sources.apply(p,dict(engine='web-reference',segments=[],reference=dict(status='unavailable')))
    assert p['chords']==before


def test_mac_document_validation_does_not_require_windows_capture_module(tmp_path,monkeypatch):
    p=project(tmp_path);p['capture']={}
    monkeypatch.setitem(sys.modules,'windows.recording',None)
    review.validate_document(p)


def test_saved_three_four_measures_and_variable_tempo_are_used_without_four_four_assumption():
    p,_=hysteria();p['settings'].update(gridMode='fixed',beatsPerBar=3,manualBPM=120,firstBeat=.5)
    bars,_=review.measures(p)
    assert bars[:3]==pytest.approx([.5,2,3.5])
    p['settings']['gridMode']='detected';p['downbeats']=[.5,2.01,3.56,5.12]
    assert review.measures(p)[0]==p['downbeats']


@pytest.mark.parametrize('change',['section','chord','media','mix','rate','reference','identity'])
def test_outdated_proposal_cannot_be_applied_or_exported(tmp_path,change):
    p=project(tmp_path);p['structureProposal']=proposal(p)
    if change=='section':p['sections'][0]['name']='Changed'
    if change=='chord':p['chords']=[dict(id='x',text='D',start=0,end=1,manual=True)]
    if change=='media':(tmp_path/p['tracks'][0]['file']).touch()
    if change=='mix':p['tracks'][0]['gain']=.2
    if change=='rate':p['_rate']=.8
    if change=='reference':p['chordReference']={'selectedURL':'https://example.test/another-chart'}
    if change=='identity':atomic(tmp_path/'Artwork.json',dict(title='Another song',artist='Another artist'))
    with pytest.raises(ValueError,match='changé'):review.apply_proposal(p)


def test_saved_proposal_cannot_overwrite_protected_sections_or_manual_chords(tmp_path):
    p=project(tmp_path);p['structureProposal']=proposal(p)
    p['structureProposal']['sections'][0]['name']='Wrong'
    with pytest.raises(ValueError,match='protégée'):review.apply_proposal(p)
    p['chords']=[dict(id='c',text='C',start=0,end=1,manual=True)]
    p['structureProposal']=proposal(p);p['structureProposal']['chords']=[]
    with pytest.raises(ValueError,match='manuel'):review.apply_proposal(p)


def test_ordered_chart_preserves_duplicates_occurrences_and_explicit_repeats():
    chart=chord_sources.Chart()
    chart.feed('<pre>[Verse 1]<b>Am</b><b>Am</b><b>F</b> x2 [Chorus]<b>C</b><b>G</b>[Verse 2]<b>Dm</b><b>F</b></pre>')
    assert [s['chords'] for s in chart.sectionSequences]==[['Am','Am','F'],['C','G'],['Dm','F']]
    repeated=chord_sources.Chart();repeated.feed('<pre>[Verse]<b>Am</b><b>F</b> (2x)</pre>')
    assert repeated.sectionSequences[0]['repeat']==2


def test_ordered_alignment_accepts_audio_support_and_abstains_on_conflict():
    scores=np.array([[.9,.2],[.85,.3],[.3,.9],[.2,.95]])
    assert chord_alignment.ordered_path(scores,['Am','F'],['Am','F'])==[0,0,1,1]
    assert chord_alignment.ordered_path(scores,['Am','F'],['F','Am']) is None
    assert chord_alignment.ordered_path(scores,['Am','F'],['Am','Unsupported']) is None


def test_unknown_section_does_not_extend_the_previous_written_sequence():
    chart=chord_sources.Chart()
    chart.feed('<pre>[Verse]<b>Am</b><b>F</b>[Unlabelled riff]<b>C</b><b>G</b></pre>')
    assert chart.sectionSequences[0]['chords']==['Am','F']
    assert chart.chords==['Am','F','C','G']


def test_single_export_creates_readable_chord_items_and_a_weak_feedback_receipt(tmp_path):
    p=project(tmp_path);p['settings'].update(exportGuides=False,exportCount=False)
    p['chords']=[dict(id='c',text='Am',start=1,end=4,manual=False,confidence=.3)]
    p['structureProposal']=proposal(p)
    saved=tmp_path/'project.json';atomic(saved,p);original=saved.read_bytes()
    work=tmp_path/'work';work.mkdir();output=work/'result.json'
    review.export_proposal(saved,output,ENGINE)
    result=json.loads(output.read_text());assert saved.read_bytes()==original
    assert 'structureProposal' not in result['project']
    tree=read_rpp(Path(result['path']))
    chords=next(t for t in tree['children'] if ['NAME','Accords'] in t['lines'])
    assert ['MUTESOLO','1','0','0'] in chords['lines']
    item=chords['children'][0]
    assert any(row[:2]==['NAME','Am · à vérifier'] for row in item['lines'])
    assert any(c['kind']=='NOTES' for c in item['children'])
    assert float(next(row[1] for row in item['lines'] if row[0]=='POSITION'))==1
    assert not references(result['project'])
    receipt=json.loads(next((tmp_path/'Learning/structure-reviews').glob('*.json')).read_text())
    assert receipt['action']=='accepted_for_export' and 'no marker' in receipt['labelPolicy']


def test_failed_export_leaves_original_project_and_proposal_untouched(tmp_path,monkeypatch):
    import preparation
    p=project(tmp_path);p['settings'].update(exportGuides=False,exportCount=False)
    p['structureProposal']=proposal(p);saved=tmp_path/'project.json';atomic(saved,p)
    before=saved.read_bytes();work=tmp_path/'work';work.mkdir()
    monkeypatch.setattr(preparation,'export_validated',lambda *a:(_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError,match='disk full'):review.export_proposal(saved,work/'result.json',ENGINE)
    assert saved.read_bytes()==before and not (tmp_path/'Learning/structure-reviews').exists()


def test_structure_export_keeps_cues_and_rebuilds_audible_calls_for_changed_sections(tmp_path,monkeypatch):
    import services
    import soundfile as sf
    p=project(tmp_path)
    p['sections'][0].update(locked=False,origin='analysis')
    p['sections'][1]['callText']='Refrain, tous ensemble'
    p['cues'][0]['callText']='Stop, attention à la reprise'
    p['structureProposal']=proposal(p)
    proposed=p['structureProposal']['sections']
    proposed[0]['end']=4
    proposed.insert(1,dict(id='bridge',name='Pont',start=4,end=8,locked=True,
                           origin='reference',callText='Pont, batterie seule'))
    spoken=[]
    def voice(text,folder,settings):
        spoken.append(text)
        target=folder/(str(len(spoken))+'.wav')
        sf.write(target,np.full((5292,2),.25,dtype='float32'),44100,subtype='FLOAT')
        return target
    monkeypatch.setattr(services,'voice_wav',voice)
    saved=tmp_path/'project.json';atomic(saved,p);original=saved.read_bytes()
    work=tmp_path/'work';work.mkdir();output=work/'result.json'
    review.export_proposal(saved,output,ENGINE)
    result=json.loads(output.read_text());updated=result['project']
    assert saved.read_bytes()==original
    assert updated['cues']==p['cues'] and updated['settings']==p['settings']
    assert updated['sections']==proposed
    assert {'Pont, batterie seule','Refrain, tous ensemble','Stop, attention à la reprise',
            'un','deux','trois','quatre'} <= set(spoken)
    guides=json.loads((work/'review-guides.json').read_text())
    assert {(e['id'],e['target']) for e in guides['events']}=={('bridge',4),('chorus',8),('stop',11)}
    for key in ('calls','cues','counts'):
        audio,sr=sf.read(tmp_path/updated['guideFiles'][key])
        assert sr==44100 and np.max(np.abs(audio))>.2
    counts,_=sf.read(tmp_path/updated['guideFiles']['counts'])
    for event in guides['countEvents']:
        at=round(event['time']*sr)
        assert np.max(np.abs(counts[at:at+4410]))>.2
    tree=read_rpp(Path(result['path']))
    tracks={next(row[1] for row in t['lines'] if row[0]=='NAME'):t
            for t in tree['children'] if t['kind']=='TRACK'}
    for name in ('Appels de régions','Cues','Décomptes'):
        assert ['MUTESOLO','0','0','0'] in tracks[name]['lines']
    count_in,_=sf.read(Path(result['folder'])/'Audio/count-in.wav')
    assert np.max(np.abs(count_in))>.2
    metadata=json.loads((Path(result['folder'])/'bandstudio-project.json').read_text())
    offset=metadata['exportPreroll']
    assert offset>0
    markers=[r for r in tree['lines'] if r[0]=='MARKER']
    assert any(r[3]=='Stop' and float(r[2])==pytest.approx(11+offset) for r in markers)
    assert any(r[3]=='Pont' and float(r[2])==pytest.approx(4+offset) for r in markers)


def test_host_applies_exports_and_undoes_through_the_existing_history(tmp_path,monkeypatch):
    from windows.host import Api
    from windows import project as model
    p=project(tmp_path);p['settings'].update(exportGuides=False,exportCount=False)
    p['sections'][0].update(locked=False,origin='analysis')
    p['structureProposal']=proposal(p)
    p['structureProposal']['sections'][0].update(name='Riff',locked=True,origin='reference',reviewed=False)
    model.save(p,tmp_path)
    host=Api(ENGINE,tmp_path/'library');host._root=tmp_path;host._project=p;host._audio.load(p,tmp_path)
    monkeypatch.setattr(host,'_op',lambda title,work,**kw:work())
    def work(kind,*args,**kwargs):
        assert kind=='structureExport'
        folder=tmp_path/'work';folder.mkdir()
        snapshot=folder/'snapshot.json';atomic(snapshot,{**host._project,'_root':str(tmp_path)})
        output=folder/'result.json';review.export_proposal(snapshot,output,ENGINE)
        return output,json.loads(output.read_text())
    monkeypatch.setattr(host,'_work',work)
    try:
        host.command(dict(command='exportStructure',projectID=p['id'],args=dict(reviewed=True,proposalID=p['structureProposal']['id'])))
        assert model.load(tmp_path)['sections'][0]['name']=='Riff'
        assert Path(host._last_export).is_file() and len(host._history)==1
        exported=Path(host._last_export).read_bytes()
        host.command(dict(command='undo',projectID=p['id'],args={}))
        assert model.load(tmp_path)['sections'][0]['name']=='Intro'
        assert Path(host._last_export).read_bytes()==exported
    finally:host._audio.close()


def test_dismissal_journals_a_batch_decision_without_rewriting_music(tmp_path,monkeypatch):
    from windows.host import Api
    from windows import project as model
    p=project(tmp_path);p['structureProposal']=proposal(p);before=copy.deepcopy(p['sections'])
    host=Api(ENGINE,tmp_path/'library');host._root=tmp_path;host._project=p
    host.command(dict(command='dismissStructure',projectID=p['id'],args=dict(proposalID=p['structureProposal']['id'])))
    saved=model.load(tmp_path)
    assert saved['sections']==before and 'structureProposal' not in saved
    event=json.loads(next((tmp_path/'Learning/structure-reviews').glob('*.json')).read_text())
    assert event['action']=='kept_current' and not references(saved)
    host._audio.close()


def test_structure_review_does_not_require_lyrics_key_or_early_guides(tmp_path,monkeypatch):
    from windows.host import Api
    from windows import advanced_host
    p=project(tmp_path)
    host=Api(ENGINE,tmp_path/'library');host._root=tmp_path;host._project=p
    events=[]
    monkeypatch.setattr(host,'_plan',lambda:['separate','grid','structure','key','lyrics','chords','guides'])
    monkeypatch.setattr(host,'_op',lambda title,work,**kw:work())
    monkeypatch.setattr(host,'_state',lambda:None)
    def analyze(kind,args):
        assert kind!='lyrics', 'Structure review must not start a transcription.'
        events.append(kind)
    def unrelated(*args):
        pytest.fail('Unrelated analysis or early guide rendering blocks structure review.')
    monkeypatch.setattr(host,'_analysis',analyze)
    monkeypatch.setattr(host,'_guides',unrelated)
    monkeypatch.setattr(advanced_host,'advanced_task',unrelated)
    def work(kind):
        events.append(kind);return tmp_path/'result.json',({'proposal':None} if kind=='structureMemory' else proposal(host._project))
    monkeypatch.setattr(host,'_work',work)
    try:
        host.command(dict(command='reviewStructure',projectID=p['id'],args={}))
        assert events==['structureMemory','separate','grid','structure','chords','structureReview']
        assert host._project['structureProposal']['status']=='proposed'
        assert host._notice=='Aucune amélioration proposée — préparation actuelle conservée.'
        assert host._project['lyrics']==p['lyrics']
    finally:host._audio.close()


def ui_proposal(p):
    return dict(id='preview',schema=1,status='proposed',message='Prête',sources=[],anchors=5,
        changes=[dict(id='new',kind='insert',time=15,before='Instrumental',after='Solo',reason='Mesure concordante.')],
        warnings=['Accords à vérifier.'],chordUpdate=True)


def test_optional_workspace_review_keeps_old_flow_and_exports_in_one_action(manual_page):
    page,p=manual_page
    assert page.locator('#prepareAllStructure').is_visible()
    assert page.locator('#reviewStructure').is_visible()
    page.locator('#reviewStructure').click()
    assert page.evaluate('sent.at(-1).command')=='reviewStructure'
    p['structureProposal']=ui_proposal(p)
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert '1 section à ajouter' in page.locator('#structureReviewSummary').inner_text()
    page.locator('#exportStructure').click()
    assert page.evaluate('sent.at(-1)')==dict(command='exportStructure',projectID='manual',args=dict(proposalID='preview',reviewed=True))
    assert page.locator('#validationForm input[required]').count()==3
    assert page.locator('#structureReview').evaluate('(e)=>!!e.closest("#workspace")')


def test_review_ui_rejects_stale_preview_and_unsaved_edits_and_escapes_source_text(manual_page):
    page,p=manual_page;p['structureProposal']=ui_proposal(p)
    p['structureProposal']['changes'][0]['after']='<img src=x onerror=alert(1)>'
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('#structureReview').get_by_text('Voir les changements',exact=True).click()
    assert page.locator('#structureReview img').count()==0
    page.locator('#notes').fill('Unfinished note')
    assert page.locator('#exportStructure').is_disabled()
    page.locator('#notes').fill('')
    assert page.locator('#exportStructure').is_enabled()
    p.pop('structureProposal')
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#exportStructure').is_hidden()


def test_empty_review_reports_no_improvement_and_exports_current_preparation(manual_page):
    page,p=manual_page;p['structureProposal']={**ui_proposal(p),'changes':[],'chordUpdate':False}
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    assert page.locator('#structureReviewSummary').inner_text()=='Aucune amélioration proposée — préparation actuelle conservée.'
    assert page.locator('#exportStructure').inner_text()=='Exporter la préparation actuelle vers REAPER'
    assert page.locator('#listenStructure').is_disabled()
    page.locator('#exportStructure').click()
    assert page.evaluate('sent.at(-1).command')=='exportStructure'
    p['structureProposal'].update(id='real-change',chordUpdate=True)
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:3})',p)
    assert page.locator('#exportStructure').inner_text()=='Valider et exporter vers REAPER'


def test_available_chords_are_distinct_from_missing_timestamps_in_old_reviews(manual_page):
    page,p=manual_page;p['structureProposal']=ui_proposal(p)
    p['structureProposal'].update(chordReference=dict(sources=[dict(publisher='Cifra Club'),dict(publisher='E-Chords')]),
        sources=[dict(publisher='Cifra Club',format='types',sectionNames=['Intro'])],anchors=0,
        warnings=['Aucune structure Internet exploitable trouvée : comparaison à partir des autres sources disponibles.'])
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    summary=page.locator('#structureReviewSourceSummary').inner_text()
    assert '2 grilles d’accords trouvées' in summary and 'exemples de passages' in summary
    assert '0 repère' not in summary
    assert page.locator('#structureReviewWarnings').inner_text()=='Repères minutés non récupérés auprès de DRUMY.'


def test_review_listening_uses_real_transport_and_stops_after_last_excerpt(manual_page):
    page,p=manual_page;p['structureProposal']=ui_proposal(p)
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:32,loaded:true,library:[],revision:2})',p)
    page.locator('#listenStructure').click()
    assert page.evaluate('sent.at(-1).command')=='audition'
    assert page.evaluate('sent.at(-1).args')==dict(start=12,end=19)
    page.evaluate('studioReceive({type:"transport",position:13,playing:true,rate:1,pitch:0,mode:"original",loop:true,loopStart:12,loopEnd:19})')
    page.evaluate('studioReceive({type:"transport",position:18.9,playing:true,rate:1,pitch:0,mode:"original",loop:true,loopStart:12,loopEnd:19})')
    assert page.evaluate('sent.slice(-2).map(m=>m.command)')==['stop','loop']
    assert page.locator('#listenStructure').inner_text()=='Écouter les passages'


def test_hysteria_workspace_remains_readable_and_the_existing_navigation_is_unchanged(manual_page):
    page,p=manual_page;local,ref=hysteria()
    sections,changes,warnings,anchors=review.complete_sections(local,ref)
    p.update(id='hysteria-ui',bpm=local['bpm'],cues=[],name='Muse - Hysteria',sections=local['sections'],beats=local['beats'],downbeats=local['downbeats'],settings=local['settings'])
    p['tracks'][0]['duration']=226.56873015873015
    p['structureProposal']={**ui_proposal(p), 'changes':changes,'warnings':warnings,'anchors':anchors,'chordUpdate':False,
                           'sources':[dict(publisher='DRUMY',title='Hysteria — Muse',url=URL)]}
    page.evaluate('p=>studioReceive({type:"state",project:p,duration:226.56873015873015,loaded:true,library:[],revision:2})',p)
    for width in (1360,1024,960):
        page.set_viewport_size(dict(width=width,height=1000))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert page.locator('#structureReview').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        assert page.locator('#prepareAllStructure').is_visible()
    if os.environ.get('BANDSTUDIO_REVIEW_SCREENSHOT'):
        page.set_viewport_size(dict(width=1440,height=1080))
        page.screenshot(path=os.environ['BANDSTUDIO_REVIEW_SCREENSHOT'],full_page=True)
