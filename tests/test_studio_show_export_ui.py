from test_studio_manual_editor import manual_page


def test_export_selection_order_setlist_and_word_marker(manual_page):
    page, project = manual_page
    project.update(lyrics=[dict(start=1,text='À demain',words=[dict(start=1,text='À'),dict(start=1.5,text='demain')])],
                   chords=[dict(start=2,text='Am')])
    state = dict(type='state',project=project,revision=2,duration=32,loaded=True,setlists=[],
                 library=[dict(name='Premier',path='/lib/one'),dict(name='Finale',path='/lib/two')])
    page.evaluate('s=>studioReceive(s)',state)
    page.get_by_role('button',name='Régie QLab + grandMA3',exact=True).click()
    panel=page.locator('#view-regie')
    assert panel.get_by_label('Prompteur paroles en régie').count() == 0
    panel.get_by_text('Repère depuis une parole',exact=False).click()
    panel.get_by_label('Parole ou accord',exact=True).select_option('1')
    assert panel.get_by_label('Nom du repère').input_value() == 'demain'
    panel.get_by_label('Nom du repère').fill('Départ vidéo')
    panel.get_by_role('button',name='Ajouter au morceau').click()
    assert page.evaluate('sent.at(-1).args') == dict(time=1.5,name='Départ vidéo',announce=False)
    panel.get_by_label('Morceaux à exporter').select_option('selection')
    panel.get_by_label('Nom du concert').fill('Le concert')
    for title in ('Premier','Finale'):
        panel.get_by_role('checkbox',name=title).check()
    panel.get_by_role('button',name='Monter · Finale').click()
    panel.get_by_role('button',name='Enregistrer la setlist').click()
    saved=page.evaluate('sent.at(-1).args')
    assert saved['paths']==['/lib/two','/lib/one']
    state['setlists']=[saved]
    page.evaluate('s=>studioReceive(s)',state)
    assert panel.get_by_label('Morceaux à exporter').input_value()=='set:'+saved['id']
    panel.get_by_label('Timecode grandMA3').select_option('songs')
    panel.get_by_label('Cadence LTC').select_option('30')
    panel.get_by_role('button',name='Exporter pour la régie').click()
    sent=page.evaluate('sent.at(-1)')
    assert sent['command']=='exportShow' and sent['args']==dict(kind='regie',layout='songs',sound='both',fps=30,paths=saved['paths'],name='Le concert',setlist=saved['id'])
    page.get_by_role('button',name='Projet Ableton Live',exact=True).click()
    live=page.locator('#view-live')
    assert not live.get_by_label('Cadence LTC').is_visible()
    live.get_by_role('button',name='Exporter le projet Live').click()
    msg=page.evaluate('sent.at(-1).args')
    assert msg['kind']=='live' and msg['paths']==saved['paths']


def test_mark_at_keypress_in_lyrics_and_adjust_in_regie(manual_page):
    page, p = manual_page
    page.evaluate("openStudioEditor('lyrics')")
    assert page.locator('#newCue').is_visible()
    page.evaluate("""studioReceive({type:'transport',playing:true,position:9.25,rate:1,mode:'mix'});
        document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'m',code:'Semicolon',bubbles:true}));""")
    capture = page.evaluate('sent.at(-1)')
    assert capture['command'] == 'captureCuePosition'
    page.evaluate("""m => studioReceive({type:'cuePosition',request:m.args.request,projectID:m.projectID,time:9.28})""",capture)
    assert page.locator('#editStart').input_value() == '9.280'
    page.locator('#editName').fill('Départ lumière')
    page.locator('#editName').press('Enter')
    saved = page.evaluate('sent.at(-1)')
    assert saved['command'] == 'cue' and saved['args']['time'] == 9.28
    assert page.get_by_role('button',name='Paroles',exact=True).first.is_visible()
    p['cues'].append(dict(id='new',**saved['args']))
    p['settings']['exportCount']=False
    page.evaluate('p=>studioReceive({type:"state",loaded:true,project:p,duration:32,revision:2,library:[]})',p)
    page.locator('#cues').get_by_role('button',name='Départ lumière').click()
    page.get_by_role('button',name='Modifier le repère sélectionné').click()
    assert page.locator('#editName').input_value() == 'Départ lumière'
    page.locator('#closeEditor').click()
    page.get_by_role('button',name='Régie QLab + grandMA3',exact=True).click()
    row = page.locator('.show-rundown tbody tr').first
    assert row.locator('td').first.inner_text()=='00:00:11:07'
    assert row.locator('td').nth(1).inner_text()=='Refrain'
    row.get_by_role('button',name='Écouter').click()
    preview = page.evaluate("sent.at(-1)")
    assert preview["command"] == "audition"
    assert abs(preview["args"]["start"]-7.28)<1e-9 and abs(preview["args"]["end"]-11.28)<1e-9
    page.get_by_label('Cadence LTC').select_option('30')
    row.get_by_role('button',name='Départ lumière').click()
    page.get_by_role('button',name='+1 image',exact=True).click()
    assert abs(float(page.locator('#editStart').input_value()) - (9.28+1/30))<.0005
    page.locator('#editName').fill('Refrain')
    page.locator('#editName').press('Enter')
    assert page.evaluate('sent.at(-1).args.id')=='new'


def test_m_ignores_typing_and_late_native_capture(manual_page):
    page,_=manual_page
    page.get_by_role('button',name='Régie QLab + grandMA3',exact=True).click()
    page.evaluate("studioReceive({type:'transport',playing:true,position:5,rate:1,mode:'mix'})")
    mark=page.get_by_role('button',name='Poser un repère (M)')
    mark.focus()
    mark.press('Control+m')
    mark.dispatch_event('keydown',dict(key=',',code='KeyM',bubbles=True))
    mark.dispatch_event('keydown',dict(key='m',code='KeyM',bubbles=True,repeat=True))
    assert not page.locator('#editor').is_visible()
    mark.press('m')
    capture=page.evaluate('sent.at(-1)')
    page.locator('#editStart').fill('4.500')
    page.evaluate("""m=>studioReceive({type:'cuePosition',request:m.args.request,projectID:m.projectID,time:6})""",capture)
    assert float(page.locator('#editStart').input_value())==4.5
    page.locator('#closeEditor').click()
    panel=page.locator('#view-regie')
    panel.get_by_text('Repère depuis une parole',exact=False).click()
    panel.get_by_label('Nom du repère').press('m')
    assert not page.locator('#editor').is_visible()
