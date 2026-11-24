'use strict';

// The sheet edits the project's existing annotations; it has no separate saved copy.
(() => {
 const EPS = 1e-7;
 function sheetGrid(project, duration) {
  const clock=musicalGrid(project),{at,coordinate,meter}=clock;
  const bpm=pulseTempo(project),origin=at(0),detected=clock.detected;
  function position(t) {
   // Round only floating-point noise, not the actual position of a word or chord.
   const value=Math.round(coordinate(t)*1e6)/1e6, bar=Math.floor(value/meter);
   return {bar:bar+1, beat:value-bar*meter+1};
  }
  const bars=[];
  if (origin>EPS) bars.push({number:0,start:0,end:Math.min(origin,duration)});
  for(let n=0; n<20000 && at(n*meter)<duration-EPS; n++) {
   const start=Math.max(0,at(n*meter)), end=Math.min(duration,at((n+1)*meter));
   if(end>start+EPS)bars.push({number:n+1,start,end});
  }
  return {at,coordinate,position,bars,meter,origin,bpm:tempoSummary(project).bpm,pulseBPM:bpm,timeSignature:pulseScale(project)===1.5?(meter*3)+'/8':meter+'/4',detected};
 }
 window.bandStudioSheetGrid = sheetGrid;

 const nav=button('',()=>view('sheet'),'nav');nav.dataset.view='sheet';
 nav.append(node('b','','▦'),document.createTextNode(uiText('Fiche morceau')));
 document.querySelector('.rail [data-view=prompter]').before(nav);
 const sheet=node('section','view');sheet.id='view-sheet';sheet.hidden=true;
 const heading=node('div','sheet-hero');
 const identity=node('div','sheet-identity');
 const artist=node('p','sheet-artist');artist.id='sheetArtist';
 const songTitle=node('h2','sheet-title');songTitle.id='sheetTitle';
 const album=node('p','sheet-album');album.id='sheetAlbum';
 const cover=button('',()=>{const entry=libraryEntry();if(entry&&typeof openArtwork==='function')openArtwork(entry);},'sheet-cover');cover.id='sheetCover';
 identity.append(node('div','sheet-kicker',uiText('BANDSTUDIO / FICHE MORCEAU')),artist,songTitle,album);
 heading.append(identity,cover);
 const meta=node('p','sheet-meta');meta.id='sheetMeta';
 const stats=node('div','sheet-stats');stats.id='sheetStats';
 const toolbar=node('div','sheet-toolbar');
 const sections=node('select');sections.id='sheetSection';sections.setAttribute('aria-label',uiText('Passage de la fiche'));
 const exportButton=button(uiText('Exporter la fiche PDF'),()=>$('exportSheet').click(),'primary');exportButton.id='sheetExport';
 const undo=button(uiText('↶ Annuler'),()=>send('undo'));undo.id='sheetUndo';
 const redo=button(uiText('↷ Rétablir'),()=>send('redo'));redo.id='sheetRedo';
 const importButton=button(uiText('Importer des paroles'),()=>{view('tools');$('importLyrics').click();});importButton.id='sheetImportLyrics';
 const details=button(uiText('Détails'),()=>{const on=sheet.classList.toggle('sheet-details');details.setAttribute('aria-pressed',String(on));});details.id='sheetDetails';details.setAttribute('aria-pressed','false');
 toolbar.append(sections,details,undo,redo,importButton,exportButton);
 const hint=node('p','sheet-hint');hint.id='sheetHint';
 const calibration=button(uiText('Vérifier le calage'),()=>view('guides'),'sheet-calibration');
 const sheetHelp=node('div','sheet-help');sheetHelp.append(hint,calibration);
 const references=node('div','sheet-toolbar');
 const searches=[];
 for(const [kind,label] of [['chords',uiText('Accords sur Internet ↗')],['lyrics',uiText('Paroles sur Internet ↗')]]) {
  const search=button(label,()=>{
   const source=selectedChordSource(state.project);
   if(kind==='chords'&&source)send('chordSourceOpen',{url:source.url});
   else send('referenceSearch',{kind,query:[artist.textContent,songTitle.textContent].filter(Boolean).join(' ')});
  });
  search.id='sheetSearch-'+kind;search.title=uiText('Ouvrir une recherche dans ton navigateur pour comparer les propositions');
  searches.push(search);references.append(search);
 }
 references.append(node('small','',uiText('Compare la version et la tonalité, puis corrige la fiche.')));
 references.append(button(uiText('Comparer les sources d’accords'),()=>{openStudioEditor('chords');$('chordReferencePrompter').scrollIntoView({block:'nearest'});}));
 const correctLyrics=button(uiText('Corriger les paroles et recaler'),()=>{view('tools');$('correctLyrics').click();});correctLyrics.id='sheetCorrectLyrics';references.append(correctLyrics);
 const manualLyrics=button(uiText('Recaler à la main'),()=>$('manualLyrics').click());manualLyrics.id='sheetManualLyrics';references.append(manualLyrics);
 const chordLegend=node('small','');chordLegend.id='sheetChordSource';references.append(chordLegend);
 const content=node('div','song-sheet');content.id='songSheet';
 sheet.append(heading,stats,meta,toolbar,sheetHelp,references,content);document.querySelector('main').append(sheet);
 sections.onchange=()=>renderSheet();
 let sheetProject='', highlighted=null, currentPitch=null;

 function libraryEntry() {
  correctLyrics.disabled=manualLyrics.disabled=!state.loaded||state.busy;
  const p=state.project, entries=state.library||[], byID=entries.find(e=>e.id===p.id);
  if(byID)return byID;
  const matches=entries.filter(e=>e.name===p.name);
  return matches.length===1?matches[0]:null;
 }
 function renderIdentity() {
  const p=state.project, entry=libraryEntry();
  const clean=String(p.name||uiText('Ton morceau')).replace(/\s*[\[(](?:official (?:music )?(?:video|audio)|lyrics?|hd|hq)[\])]/gi,'').trim();
  const parts=clean.split(/\s+[-–—]\s+/);
  artist.textContent=entry?.artist||(parts.length>1?parts[0]:'');
  songTitle.textContent=entry?.title&&entry.title!==p.name?entry.title:parts.slice(parts.length>1?1:0).join(' - ');
  album.textContent=entry?.album||uiText('Ta grille de répétition');
  cover.replaceChildren();
  if(entry?.artwork?.startsWith('data:image/jpeg;base64,')) {
   const img=node('img');img.src=entry.artwork;img.alt=uiText('Pochette')+(entry.album?uiText(' de ')+entry.album:uiText(' du morceau'));cover.append(img);
  } else cover.append(node('span','sheet-record','♪'));
  cover.disabled=!entry||!!state.busy;
  cover.title=entry?.artwork?uiText('Changer la pochette'):uiText('Choisir une pochette');
  cover.setAttribute('aria-label',cover.title);
 }

 function positionLabel(grid,t) {
  const p=grid.position(t);
  return (p.bar<1?uiText('Levée'):uiText('mes. ')+p.bar)+uiText(' · temps ')+Number(p.beat.toFixed(2));
 }
 function editEntry(kind,item,start,end) {
  if(state.busy)return;
  $('annotationKind').value=kind;
  openAnnotation(item || {start,end,text:''});
 }
 function entryButton(kind,item,start,end,grid) {
  const continuation=item.start<start-EPS;
  let label=item.text;
  if(kind==='chords')label=playingChord(label);
  else if(item.words?.length)label=item.words.filter(w=>w.start>=start&&w.start<end).map(w=>w.text).join(' ');
  else if(continuation)return null;
  if(!label)return null;
  const uncertain=annotationNeedsReview(item);
  const b=button('',()=>editEntry(kind,item),'sheet-entry sheet-'+kind+(item.manual?' manual':'')+(uncertain?' uncertain':''));
  b.dataset.annotation=item.id;b.dataset.kind=kind;b.disabled=!!state.busy;
  b.append(node('span','sheet-entry-text',label+(uncertain?' ?':'')));
  const pos=positionLabel(grid,Math.max(start,item.start));
  b.append(node('small','',pos+' · '+(item.manual?uiText('corrigé'):item.sourceURL?uiText('Internet · ')+(uncertain?uiText('calage incertain'):uiText('proposé')):'auto')));
  b.title=uiText('Modifier ')+(kind==='chords'?'l’accord':uiText('la ligne'))+' : '+item.text+' ('+positionLabel(grid,item.start)+')';
  if(item.sourceURL&&!item.manual)b.title+=' · '+(uncertain?uiText('Calage incertain, à vérifier'):kind==='chords'?uiText('Calage proposé depuis une grille Internet'):uiText('Calage proposé depuis les paroles de référence'));
  return b;
 }
 function groups(project,duration) {
  const result=[];let end=0;
  for(const s of [...(project.sections||[])].sort((a,b)=>a.start-b.start)) {
   const a=Math.max(end,s.start,0), b=Math.min(duration,s.end);
   if(a>end+EPS)result.push({name:uiText('Sans section'),start:end,end:a,id:'gap-'+end});
   if(b>a+EPS){result.push({...s,start:a,end:b});end=b;}
  }
  if(end<duration-EPS)result.push({name:result.length?uiText('Sans section'):uiText('Le morceau'),start:end,end:duration,id:'gap-'+end});
  return result;
 }
 function renderSheet() {
  const p=state.project, duration=state.duration||0, opened=state.loaded&&duration>0;
  const chordSource=typeof selectedChordSource==='function'?selectedChordSource(p):p.chordReference?.sources?.[0];
  chordLegend.textContent=chordSource?uiText('Accords : ')+chordSource.publisher+uiText(' · calage proposé sur ta grille. ? = accord ou placement à vérifier.'):'';
  const disabled=!opened||!!state.busy;
  exportButton.disabled=importButton.disabled=sections.disabled=calibration.disabled=details.disabled=disabled;
  searches.forEach(b=>b.disabled=!opened);
  undo.disabled=disabled||!state.undo;redo.disabled=disabled||!state.redo;
  if(sheet.hidden)return;
  renderIdentity();
  content.replaceChildren();highlighted=null;
  if(!opened){meta.textContent='';hint.textContent=uiText('Ouvre un morceau pour afficher sa fiche.');sections.replaceChildren();return;}
  if(state.sheetClockPending){stats.replaceChildren();meta.textContent='';sections.replaceChildren();hint.textContent=uiText('Calcul des mesures du morceau…');return;}
  const grid=sheetGrid(p,duration);
  stats.replaceChildren();
  for(const [label,value] of [['TEMPO',Number(grid.bpm.toFixed(1))+' BPM'],[uiText('TONALITÉ'),p.key?transposeChord(chordLabel(p.key),transport.pitch||0):uiText('À préciser')],[uiText('MESURE'),grid.timeSignature],[uiText('DURÉE'),time(duration)]]) {
   const stat=node('div','sheet-stat');stat.append(node('small','',label),node('strong','',value));stats.append(stat);
  }
  const all=groups(p,duration), chosen=p.id===sheetProject?sections.value:'';
  sheetProject=p.id;sections.replaceChildren();
  const option=node('option','',uiText('Tout le morceau'));option.value='';sections.append(option);
  for(const group of all){const o=node('option','',group.name);o.value=group.id;sections.append(o);}
  sections.value=all.some(s=>s.id===chosen)?chosen:'';
  const shift=(transport.pitch||0)-(p.capo||0);currentPitch=transport.pitch||0;
  meta.textContent=[p.name,Number(grid.bpm.toFixed(1))+' BPM',grid.timeSignature,p.key?uiText('Tonalité : ')+transposeChord(p.key,transport.pitch||0):'',p.capo?'Capo '+p.capo:''].filter(Boolean).join(' · ');
  hint.textContent=uiText('Clique sur un accord ou des paroles pour les corriger. Les numéros repèrent les mesures.')+(shift?uiText(' Accords transposés ; l’éditeur montre les accords source.'):'')+(!(p.lyrics||[]).length?uiText(' Aucune parole : utilise + Paroles ou importe un fichier LRC/SRT.'):'');
  for(const group of all.filter(s=>!sections.value||s.id===sections.value)) {
   const article=node('article','sheet-section');article.dataset.section=group.id;
   const head=node('div','sheet-section-heading');
   const title=button(group.name,()=>send('seek',{time:group.start}),'sheet-section-title');
   title.title=uiText('Aller au début de ')+group.name;
   const groupBars=grid.bars.filter(b=>Math.min(group.end,b.end)>Math.max(group.start,b.start)+EPS);
   const numbered=groupBars.filter(b=>b.start>=group.start-EPS);
   const first=numbered[0]?.number,last=numbered.at(-1)?.number;
   const range=first===undefined?'':(first===0?uiText('Levée'):uiText('M. ')+first)+(first===last?'':' – '+last);
   head.append(node('span','sheet-section-number',String(all.indexOf(group)+1).padStart(2,'0')),title,node('small','',range));
   head.title=positionLabel(grid,group.start)+' → '+time(group.end,true);
   const originalSection=(p.sections||[]).find(s=>s.id===group.id);
   if(originalSection) {const edit=button(uiText('Modifier la section'),()=>openEditor('section',originalSection));edit.disabled=!!state.busy;head.append(edit);}
   article.append(head);
   const row=node('div','sheet-bars');
   for(const bar of groupBars) {
    const start=Math.max(group.start,bar.start),end=Math.min(group.end,bar.end),entry=start>bar.start+EPS;
    const cell=node('div','sheet-bar'+(entry?' sheet-entry-fragment':''));cell.dataset.start=start;cell.dataset.end=end;cell.dataset.bar=bar.number;
    const top=node('div','sheet-bar-heading');
    const label=entry?uiText('Entrée · ')+positionLabel(grid,start).replace(/(\d)\.(\d)/,'$1,$2'):
     (bar.number?uiText('M. ')+bar.number:uiText('Levée'))+(end<bar.end-EPS?uiText(' · début'):'');
    const seek=button(label,()=>send('seek',{time:start}));
    seek.setAttribute('aria-label',uiText('Écouter ')+label);
    seek.title=uiText('Écouter à partir de ')+time(start,true);top.append(seek);
    top.append(node('small','',time(start,true)));cell.append(top);
    for(const kind of ['chords','lyrics']) {
     const lane=node('div','sheet-lane sheet-lane-'+kind);lane.setAttribute('aria-label',kind==='chords'?uiText('Accords'):uiText('Paroles'));
     for(const item of (p[kind]||[]).filter(e=>e.start<end-EPS&&e.end>start+EPS).sort((a,b)=>a.start-b.start)) {
      const b=entryButton(kind,item,start,end,grid);if(b)lane.append(b);
     }
     const add=button(kind==='chords'?uiText('+ Accord'):uiText('+ Paroles'),()=>editEntry(kind,null,start,end),'sheet-add');
     add.dataset.add=kind;add.disabled=!!state.busy;
     lane.classList.toggle('has-entries',!!lane.children.length);lane.append(add);cell.append(lane);
    }
    if(entry)article.append(cell);else row.append(cell);
   }
   article.append(row);content.append(article);
  }
  highlight();
 }
 function highlight() {
  if(sheet.hidden)return;
  const at=transport.position||0;
  if(highlighted&&at>=Number(highlighted.dataset.start)&&at<Number(highlighted.dataset.end))return;
  highlighted?.classList.remove('playing');
  highlighted=[...content.querySelectorAll('.sheet-bar')].find(e=>at>=Number(e.dataset.start)&&at<Number(e.dataset.end));
  highlighted?.classList.add('playing');
 }
 const baseView=view;view=function(name){const entering=sheet.hidden;baseView(name);document.body.classList.toggle('sheet-open',name==='sheet');if(name==='sheet'){renderSheet();if(entering)document.querySelector('main').scrollTop=0;}};
 const baseLibrary=renderLibrary;renderLibrary=function(){baseLibrary();if(!sheet.hidden)renderIdentity();};
 const baseFeatures=renderFeatures;renderFeatures=function(){baseFeatures();renderSheet();};
 const baseReceive=window.studioReceive;window.studioReceive=data=>{
  baseReceive(data);
  if(data.type==='transport'){if(currentPitch!==(transport.pitch||0)&&!sheet.hidden)renderSheet();else highlight();}
 };

 // Position controls share the existing editor and its word-level validation.
 const placement=node('fieldset','sheet-placement');placement.id='sheetPlacement';
 placement.append(node('legend','',uiText('Placement dans le morceau')));
 const fields=node('div','sheet-position-fields');
 for(const [id,label] of [['sheetStartBar',uiText('Mesure de début')],['sheetStartBeat',uiText('Temps')],['sheetEndBar',uiText('Mesure de fin')],['sheetEndBeat',uiText('Temps')]]) {
  const l=node('label','',label), input=node('input');input.id=id;input.type='number';input.step=id.endsWith('Beat')?'0.001':'1';l.append(input);fields.append(l);
 }
 const move=node('div','sheet-move');
 for(const [label,beats] of [[uiText('← 1 mesure'),'bar-'],[uiText('← 1 temps'),-1],[uiText('1 temps →'),1],[uiText('1 mesure →'),'bar+']]) {
  const b=button(label,()=>{const g=editorGrid(),amount=beats==='bar-'?-g.meter:beats==='bar+'?g.meter:beats;moveTo(g.at(g.coordinate(Number($('annotationStart').value))+amount));});
  b.dataset.shift=beats;move.append(b);
 }
 for(const [label,delta] of [['← 100 ms',-.1],['100 ms →',.1]]) {
  const control=button(label,()=>moveTo(Number($('annotationStart').value)+delta));control.dataset.shiftSeconds=delta;move.append(control);
 }
 move.append(button(uiText('Placer au curseur'),()=>moveTo(transport.position||0)),button(uiText('Écouter cette ligne'),()=>{
  const start=Math.max(0,Number($('annotationStart').value)-.5),end=Math.min(state.duration,Number($('annotationEnd').value)+.5);
  if(Number.isFinite(start)&&Number.isFinite(end)&&end>start)send('audition',{start,end});
 }),button('Pause',()=>{if(transport.playing)send('play');}));
 const help=node('small','',uiText('Les flèches déplacent toute la ligne avec ses mots. Enregistrer sauvegarde tes horaires dans le morceau et les protège des analyses automatiques. Mesure 0 : levée avant la mesure 1.'));
 const error=node('p','sheet-error');error.id='sheetPositionError';error.setAttribute('role','status');
 const replaceLabel=node('label','checkbox'), replace=node('input');replace.id='sheetReplaceChords';replace.type='checkbox';replace.checked=true;
 replaceLabel.id='sheetReplaceLabel';replaceLabel.append(replace,document.createTextNode(uiText('Remplacer les accords présents sur cette plage')));
 placement.append(fields,move,help,replaceLabel,error);
 $('annotationText').parentElement.after(placement);
 function editorGrid(){return sheetGrid(state.project,state.duration);}
 function refreshPosition() {
  const g=editorGrid();
  for(const side of ['Start','End']) {
   const p=g.position(Number($('annotation'+side).value));
   $('sheet'+side+'Bar').value=p.bar;$('sheet'+side+'Beat').value=Number(p.beat.toFixed(3));
  }
 }
 function moveTo(start) {
  const old=Number($('annotationStart').value),delta=start-old,end=Number($('annotationEnd').value)+delta;
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<-EPS||end>state.duration+EPS||end<=start){error.textContent=uiText('Ce déplacement dépasse les limites du morceau.');refreshPosition();return;}
  const round=n=>Number(n.toFixed(3));
  $('annotationStart').value=round(Math.max(0,start));$('annotationEnd').value=round(Math.min(state.duration,end));
  for(const input of $('wordRows').querySelectorAll('[data-word=start],[data-word=end]'))input.value=round(Number(input.value)+delta);
  error.textContent=uiText('Position modifiée. Enregistre pour l’appliquer.');refreshPosition();
 }
 const baseAnnotation=openAnnotation;openAnnotation=function(item){
  baseAnnotation(item);replace.checked=true;replaceLabel.hidden=annotationEdit.kind!=='chords';error.textContent='';refreshPosition();
  $('annotationForm').querySelector('button[type=submit]').disabled=!!state.busy;
  $('annotationForm').querySelector('button[type=submit]').textContent=annotationEdit.kind==='lyrics'?uiText('Enregistrer le calage'):uiText('Enregistrer');
 };
 for(const side of ['Start','End']) {
  for(const part of ['Bar','Beat']) $('sheet'+side+part).onchange=()=>{
   const g=editorGrid(),bar=Number($('sheet'+side+'Bar').value),beat=Number($('sheet'+side+'Beat').value);
   if(!Number.isInteger(bar)||!Number.isFinite(beat)||beat<1||beat>=g.meter+1){error.textContent=uiText('Saisis une mesure entière et un temps compris entre 1 et ')+g.meter+'.';refreshPosition();return;}
   const t=g.at((bar-1)*g.meter+beat-1);
   if(side==='Start')moveTo(t);
   else if(t>Number($('annotationStart').value)&&t<=state.duration+EPS){$('annotationEnd').value=Number(Math.min(t,state.duration).toFixed(3));error.textContent='';refreshPosition();}
   else{error.textContent=uiText('La fin doit suivre le début et rester dans le morceau.');refreshPosition();}
  };
  $('annotation'+side).addEventListener('change',refreshPosition);
 }
 const baseSubmit=$('annotationForm').onsubmit;
 $('annotationForm').onsubmit=e=>{
  if(state.busy){e.preventDefault();error.textContent=uiText('Attends la fin du traitement pour enregistrer.');return;}
  // The native command splits overlapping chords atomically, with a single undo step.
  if(annotationEdit.kind==='chords')annotationEdit.replaceRange=replace.checked;
  const start=Number($('annotationStart').value),end=Number($('annotationEnd').value);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>state.duration||end<=start){e.preventDefault();error.textContent=uiText('Vérifie le début et la fin de cette entrée.');return;}
  baseSubmit(e);
 };
})();
