"""The printed rehearsal chart preserves the edited musical content and its grid."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'desktop/studio'))
from advanced import practice_grid, practice_sheet


def song():
    return dict(name='Grille de répétition', bpm=120, key='D', capo=2,
                settings=dict(gridMode='fixed', manualBPM=120, firstBeat=.5, beatsPerBar=4),
                tracks=[dict(role='source', offset=0, duration=10.5)],
                sections=[dict(name='Intro', start=0, end=2.5), dict(name='Couplet', start=2.5, end=10.5)],
                chords=[dict(text='D:maj/F#', start=0, end=3.5), dict(text='E:min7', start=3.5, end=4.5),
                        dict(text='N', start=4.5, end=6.5), dict(text='A:maj', start=6.5, end=10.5)],
                lyrics=[dict(start=2, end=5, text='Un mot tenu', words=[dict(start=2, end=3, text='Un'),
                         dict(start=3, end=4.7, text='mot'),dict(start=4.7, end=5, text='tenu')])],
                cues=[dict(time=6.5,name='Arrêt & reprise')], notes='Dernier accord : laisser sonner.')


def test_grid_preserves_words_once_and_splits_chords_without_mutating_song():
    p=song();original=copy.deepcopy(p)
    result=practice_grid(p, dict(pitch=0))
    assert p == original
    cells=[c for group in result['groups'] for c in group['cells']]
    assert [(c['number'], c['start'], c['end']) for c in cells] == [(0,0,.5),(1,.5,2.5),(2,2.5,4.5),(3,4.5,6.5),(4,6.5,8.5),(5,8.5,10.5)]
    assert [c['lyrics'] for c in cells] == ['', 'Un', 'mot', 'tenu', '', '']
    assert cells[2]['chords'] == ['C/E','Dm7']
    assert cells[3]['chords'] == ['N.C.']
    assert cells[4]['cues'] == ['Arrêt & reprise']
    assert result['key'] == 'D' and result['capo'] == 2
    assert practice_grid(p,dict(pitch=2))['groups'][0]['cells'][0]['chords'] == ['D/F#']


def test_detected_grid_assigns_the_entrance_to_its_section_once():
    p=song();p['settings'].update(gridMode='detected',firstBeat=2)
    p['beats']=[0,.5,1,1.5,2,2.6,3.2,3.8,4.4,5,5.6]
    p['sections']=[dict(name='A',start=0,end=3),dict(name='B',start=3,end=10.5)]
    data=practice_grid(p)
    a,b=data['groups']
    assert (a['cells'][0]['number'],a['cells'][0]['end']) == (1,2)
    assert a['cells'][-1]['end'] == 3 and a['cells'][-1]['partial']
    entry=b['cells'][0]
    assert entry['start']==3 and entry['end']==pytest.approx(4.4)
    assert entry['continuation'] and entry['number']==2 and entry['startBeat']==pytest.approx(2+2/3)
    assert entry['lyrics']=='mot' and a['cells'][-1]['lyrics']=='Un'
    numbers=[c['number'] for g in data['groups'] for c in g['cells'] if not c['continuation']]
    assert len(numbers)==len(set(numbers))
    assert ' '.join(c['lyrics'] for g in data['groups'] for c in g['cells']).split() == ['Un','mot','tenu']


def test_short_sections_share_only_their_exact_interval_in_a_single_bar():
    p=song()
    p['sections']=[dict(name=n,start=a,end=b) for n,a,b in [('A',0,3),('Break',3,3.5),('B',3.5,10.5)]]
    p['cues']=[dict(name='Go',time=3.5)]
    a,short,b=practice_grid(p)['groups']
    assert short['cells'][0]['start']==3 and short['cells'][0]['end']==3.5
    assert short['cells'][0]['lyrics']=='mot' and short['cells'][0]['cues']==[]
    assert b['cells'][0]['cues']==['Go'] and b['cells'][0]['lyrics']==''
    assert b['cells'][0]['chords']==['Dm7'] and a['cells'][-1]['end']==3


def test_pdf_supports_long_text_dense_chords_and_empty_analysis(tmp_path):
    p=song();p['name']='Titre long & caractères <à préserver> '*5
    p['lyrics']=[dict(start=3,end=5,text='Texte corrigé très long. '*130)]
    p['chords']=[dict(start=2.5+i*.2,end=2.5+(i+1)*.2,text=c) for i,c in enumerate(['D:maj','A:maj','E:min','C:maj7','G:maj','B:min','F#:dim','N'])]
    target=tmp_path/'long.pdf';practice_sheet(p,target,{})
    assert target.read_bytes().startswith(b'%PDF')
    p.update(lyrics=[],chords=[],sections=[],notes='')
    target=tmp_path/'empty.pdf';practice_sheet(p,target,{})
    assert target.read_bytes().startswith(b'%PDF')


def test_unsynchronized_line_is_kept_whole_at_its_start():
    p=song();p['lyrics']=[dict(start=3,end=8,text='Une ligne à recaler entièrement')]
    cells=[c for g in practice_grid(p)['groups'] for c in g['cells']]
    assert [c['lyrics'] for c in cells if c['lyrics']] == ['Une ligne à recaler entièrement']
