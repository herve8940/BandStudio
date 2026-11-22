'use strict';
// Source names and grid-aligned placements remain distinguishable from manual edits.
function findChordReference(){send('analyze',{kind:'chords',model:$('model').value,reanalyze:true});}
function selectedChordSource(project){const r=project.chordReference;return r?.sources?.find(s=>s.url===r.selectedURL)||r?.sources?.[0];}
function chordGridUnit(){return state.project.settings?.pulseUnit==='dottedQuarter'?1/3:.5;}
const annotationBeforeChordGrid=openAnnotation;
openAnnotation=function(item){
 annotationBeforeChordGrid(item);
 if(!item&&annotationEdit.kind==='chords'){
  const grid=musicalGrid(state.project),position=transport.position||0;
  const start=Math.max(0,Math.min(state.duration,grid.snap(position,chordGridUnit())));
  $('annotationStart').value=start.toFixed(3);
  $('annotationEnd').value=Math.min(state.duration,grid.at(grid.coordinate(start)+1)).toFixed(3);
 }
};
const snapChord=button('Caler sur le temps / contretemps',()=>{
 const grid=musicalGrid(state.project),unit=chordGridUnit(),start=Math.max(0,grid.snap(Number($('annotationStart').value),unit));
 const end=Math.min(state.duration,Math.max(grid.at(grid.coordinate(start)+unit),grid.snap(Number($('annotationEnd').value),unit)));
 $('annotationStart').value=Math.min(start,end).toFixed(3);$('annotationEnd').value=end.toFixed(3);
});
snapChord.type='button';snapChord.id='snapChordToGrid';$('annotationEnd').parentElement.after(snapChord);
const annotationBeforeChordSnap=openAnnotation;
const chordPreview=node('small','');
chordPreview.id='annotationPlayedChord';$('annotationText').after(chordPreview);
function previewPlayedChord(){
 const text=$('annotationText').value.trim();
 chordPreview.hidden=annotationEdit.kind!=='chords'||!text||!(transport.pitch||state.project.capo);
 if(!chordPreview.hidden)chordPreview.textContent='À jouer · '+playingChord(text);
}
$('annotationText').addEventListener('input',previewPlayedChord);
openAnnotation=function(item){
 annotationBeforeChordSnap(item);
 snapChord.hidden=annotationEdit.kind!=='chords';
 $('annotationText').parentElement.firstChild.nodeValue=annotationEdit.kind==='chords'?'Accord d’origine':'Paroles';
 previewPlayedChord();
};
let palettePitch, paletteCapo, paletteKey;
function refreshChordPalettes(rebuilt=false){
 const p=state.project,pitch=transport.pitch||0,capo=p.capo||0;
 if(!rebuilt&&pitch===palettePitch&&capo===paletteCapo&&p.key===paletteKey)return;
 palettePitch=pitch;paletteCapo=capo;paletteKey=p.key;
 const box=$('chordReferencePrompter');
 for(const name of box.querySelectorAll('[data-palette-key]')){
  const key=p.key?'tonalité entendue '+transposeChord(chordLabel(p.key),pitch):'';
  name.textContent=['Accords à jouer',key,capo?'capo '+capo:''].filter(Boolean).join(' · ');
 }
 for(const add of box.querySelectorAll('[data-source-chord]')){
  const original=add.dataset.sourceChord;
  add.textContent=playingChord(original);
  add.title='Placer '+add.textContent+' au curseur'+(add.textContent!==original?' · accord d’origine '+original:'');
 }
 if($('annotationEditor').open)previewPlayedChord();
}
function renderChordReferences(){
 const p=state.project,reference=p.chordReference;
 for(const [id,editable] of [['chordReferencePrepare',false],['chordReferencePrompter',true]]){
  const box=$(id),chosen=selectedChordSource(p);
  const preview=box.dataset.project===p.id&&box.dataset.selected===chosen?.url?box.querySelector('#chordEdition')?.value:null;
  box.replaceChildren();
  box.dataset.project=p.id;box.dataset.selected=chosen?.url||'';
  if(!state.loaded)continue;
  if(editable)box.append(node('h3','','Grille d’accords Internet'));
  const old=(p.chords||[]).filter(c=>!c.manual&&!c.sourceURL).length;
  const sources=reference?.sources||[];
  if(editable&&chosen){
   const count=sources.length;
   box.append(node('p','',count+(count===1?' grille trouvée':' grilles trouvées')+' · calage avec '+chosen.publisher));
  }else box.append(node('p','',reference?.message||(old?'Les anciens accords automatiques restent à remplacer par une grille publiée.':'Recherche une grille publiée et cale ses accords sur les temps du morceau.')));
  if(!editable){box.append(button('Choisir une grille dans l’éditeur',()=>openStudioEditor('chords')));continue;}
  if(chosen){
   const card=node('div','chord-source');
   const source=sources.find(s=>s.url===preview)||chosen;
   if(sources.length>1){
    const label=node('label','chord-edition','Grille à consulter'),select=node('select');
    select.id='chordEdition';
    for(const edition of sources){
     const option=node('option','',edition.publisher+(edition.url===chosen.url?' · utilisée':''));
     option.value=edition.url;select.append(option);
    }
    select.value=source.url;
    select.onchange=()=>{show(sources.find(s=>s.url===select.value));refreshChordPalettes(true);};
    label.append(select);box.append(label);
   }
   box.append(card);show(source);
   function show(source){
    card.replaceChildren();
    const active=source.url===chosen?.url;
    card.append(node('strong','',source.title));
    if(source.note)card.append(node('small','',source.note));
    card.append(button('Ouvrir la grille',()=>send('chordSourceOpen',{url:source.url})));
    if(!active){const use=button('Utiliser cette grille',()=>send('analyze',{kind:'chords',model:$('model').value,reanalyze:true,sourceURL:source.url}),'primary');use.disabled=state.busy;card.append(use);}
    const heading=node('small','');heading.dataset.paletteKey='';
    const palette=node('div','annotation-toolbar');
    const shift=active?(reference.alignment?.chartTranspose||0):0;
    if(shift)card.append(node('small','','Grille transposée de '+(shift>0?'+':'')+shift+' demi-tons pour cet enregistrement.'));
    for(const written of (source.chords||[]).slice(0,60)){
     const chord=transposeChord(written,shift);
     const add=button('',()=>{
      $('annotationKind').value='chords';openAnnotation(null);$('annotationText').value=chord;previewPlayedChord();
     });
     add.dataset.sourceChord=chord;add.disabled=state.busy;palette.append(add);
    }
    card.append(heading,palette);
   }
  }
  if(chosen&&reference.message){
   const rationale=node('details','chord-alignment-details');
   rationale.append(node('summary','','Détails du calage'),node('p','',reference.message));box.append(rationale);
  }
  const catalog=state.chordProviders||[];
  if(catalog.length){
   const more=node('details','chord-catalog'),summary=node('summary','',catalog.length+' sources · recherches ciblées');more.append(summary);
   more.append(node('p','','Choisis un site pour ouvrir sa recherche dans ton navigateur.'));
   const labels={found:'Grille trouvée',not_found:'Aucune correspondance',unavailable:'Indisponible ou délai dépassé'};
   for(const provider of catalog){
    const row=node('div','chord-provider'),status=reference?.checks?.find(c=>c.id===provider.id)?.status;
    row.append(button('Rechercher sur '+provider.publisher,()=>send('referenceSearch',{kind:'chords',provider:provider.id,query:reference?.query||p.name})),node('small','',provider.automatic?(labels[status]||'Recherche automatique disponible'):'Recherche dans le navigateur'));
    more.append(row);
   }
   box.append(more);
  }
  const actions=node('div','annotation-toolbar');
  const search=button(chosen?'Actualiser les grilles':'Rechercher une grille Internet',findChordReference);
  search.disabled=state.busy;actions.append(search);
  actions.append(button('Autres sources sur Internet',()=>send('referenceSearch',{kind:'chords',query:reference?.query||p.name})));
  box.append(actions);
 }
 refreshChordPalettes(true);
}
const featuresBeforeChordReferences=renderFeatures;
renderFeatures=function(){featuresBeforeChordReferences();renderChordReferences();};
const chordStageStatus=node('small','');chordStageStatus.id='stageChordStatus';$('stageChord').after(chordStageStatus);
const stageBeforeChordReferences=renderStage;
renderStage=function(){
 stageBeforeChordReferences();
 refreshChordPalettes();
 const at=transport.position||0,chord=(state.project.chords||[]).find(c=>c.start<=at&&at<c.end);
 chordStageStatus.hidden=!chord;
 chordStageStatus.textContent=chord?.manual?'Corrigé manuellement':chord?.sourceURL?(annotationNeedsReview(chord)?'Accord proposé · calage incertain':'Grille Internet · calage proposé'):chord?'Ancienne détection audio · à remplacer':'';
};
