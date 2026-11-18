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
openAnnotation=function(item){annotationBeforeChordSnap(item);snapChord.hidden=annotationEdit.kind!=='chords';};
function renderChordReferences(){
 const p=state.project,reference=p.chordReference;
 for(const [id,editable] of [['chordReferencePrepare',false],['chordReferencePrompter',true]]){
  const box=$(id);box.replaceChildren();
  if(!state.loaded)continue;
  if(editable)box.append(node('h3','','Grille d’accords Internet'));
  const old=(p.chords||[]).filter(c=>!c.manual&&!c.sourceURL).length;
  box.append(node('p','',reference?.message||(old?'Les anciens accords automatiques restent à remplacer par une grille publiée.':'Recherche une grille publiée et cale ses accords sur les temps du morceau.')));
  const chosen=selectedChordSource(p);
  for(const source of (reference?.sources||[]).slice(0,10)){
   const card=node('div','chord-source');
   const active=source.url===chosen?.url;
   card.append(node('strong','',source.publisher+(active?' · utilisée pour le calage':'')),node('p','',source.title));
   if(source.note)card.append(node('small','',source.note));
   card.append(button('Ouvrir la grille',()=>send('chordSourceOpen',{url:source.url})));
   if(!active){const use=button('Utiliser cette grille',()=>send('analyze',{kind:'chords',model:$('model').value,reanalyze:true,sourceURL:source.url}));use.disabled=state.busy;card.append(use);}
   const palette=node('div','annotation-toolbar');
   for(const chord of (source.chords||[]).slice(0,60)){
    if(editable){
     const add=button(chord,()=>{
      $('annotationKind').value='chords';openAnnotation(null);$('annotationText').value=chord;
     });
     add.title='Placer '+chord+' à la position du lecteur';add.disabled=state.busy;palette.append(add);
    }else palette.append(node('span','status-pill',chord));
   }
   card.append(palette);box.append(card);
  }
  if(reference?.sources?.length)box.append(node('small','','Accords de la source. Calage proposé sur ta grille rythmique, à vérifier à l’écoute.'));
  if(editable&&reference?.sources?.length)box.append(node('p','','Pour corriger un changement : modifie son horaire dans la liste ou place le lecteur et clique sur un accord.'));
  const catalog=state.chordProviders||[];
  if(catalog.length){
   const more=node('details','chord-catalog'),summary=node('summary','',catalog.length+' sources · recherches ciblées');more.append(summary);
   more.append(node('p','','Les sources trouvées ci-dessus peuvent être calées. Les recherches ci-dessous ouvrent le navigateur ; elles ne garantissent pas qu’une grille soit disponible.'));
   const labels={found:'Grille trouvée',not_found:'Aucune correspondance',unavailable:'Indisponible ou délai dépassé'};
   for(const provider of catalog){
    const row=node('div','chord-provider'),status=reference?.checks?.find(c=>c.id===provider.id)?.status;
    row.append(button('Rechercher sur '+provider.publisher,()=>send('referenceSearch',{kind:'chords',provider:provider.id,query:reference?.query||p.name})),node('small','',provider.automatic?(labels[status]||'Recherche automatique disponible'):'Recherche dans le navigateur'));
    more.append(row);
   }
   box.append(more);
  }
  const actions=node('div','annotation-toolbar');
  if(editable){const search=button('Rechercher une grille Internet',findChordReference);search.disabled=state.busy;actions.append(search);}
  actions.append(button('Autres sources sur Internet',()=>send('referenceSearch',{kind:'chords',query:reference?.query||p.name})));
  box.append(actions);
 }
}
const featuresBeforeChordReferences=renderFeatures;
renderFeatures=function(){featuresBeforeChordReferences();renderChordReferences();};
const chordStageStatus=node('small','');chordStageStatus.id='stageChordStatus';$('stageChord').after(chordStageStatus);
const stageBeforeChordReferences=renderStage;
renderStage=function(){
 stageBeforeChordReferences();
 const at=transport.position||0,chord=(state.project.chords||[]).find(c=>c.start<=at&&at<c.end);
 chordStageStatus.hidden=!chord;
 chordStageStatus.textContent=chord?.manual?'Corrigé manuellement':chord?.sourceURL?(chord.confidence<.5?'Accord proposé · calage incertain':'Grille Internet · calage proposé'):chord?'Ancienne détection audio · à remplacer':'';
};
