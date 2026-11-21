'use strict';

// The sheet edits the project's existing annotations; it has no separate saved copy.
(() => {
 const EPS = 1e-7;
 function musicalGrid(project, duration) {
  const settings = {...guideDefaults, ...project.settings};
  const meter = settings.beatsPerBar;
  const bpm = pulseTempo(project);
  const beats = [...new Set((project.beats || []).filter(t => Number.isFinite(t) && t >= 0 && t <= duration))].sort((a,b) => a-b);
  const detected = settings.gridMode !== 'fixed' && beats.length > 1;
  let anchor = 0;
  if (detected) beats.forEach((t,i) => {if (Math.abs(t-settings.firstBeat) < Math.abs(beats[anchor]-settings.firstBeat)) anchor=i;});
  if (detected) anchor %= meter; // Same measure numbering as the structure editor and metronome.
  const origin = detected ? beats[anchor] : settings.firstBeat;
  function at(coordinate) {
   if (!detected) return origin + coordinate * 60 / bpm;
   const index = coordinate + anchor, lower = Math.max(0, Math.min(beats.length-2, Math.floor(index)));
   return beats[lower] + (index-lower) * (beats[lower+1]-beats[lower]);
  }
  function coordinate(t) {
   if (!detected) return (t-origin) * bpm / 60;
   let lo=0, hi=beats.length-1;
   while (hi-lo>1) {const mid=(lo+hi)>>1;if(beats[mid]<=t)lo=mid;else hi=mid;}
   return lo-anchor+(t-beats[lo])/(beats[lo+1]-beats[lo]);
  }
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
 window.bandStudioSheetGrid = musicalGrid;

 const nav=button('',()=>view('sheet'),'nav');nav.dataset.view='sheet';
 nav.append(node('b','','▦'),document.createTextNode('Fiche morceau'));
 document.querySelector('.rail [data-view=prompter]').before(nav);
 const sheet=node('section','view');sheet.id='view-sheet';sheet.hidden=true;
 const heading=node('div','sheet-hero');
 const identity=node('div','sheet-identity');
 const artist=node('p','sheet-artist');artist.id='sheetArtist';
 const songTitle=node('h2','sheet-title');songTitle.id='sheetTitle';
 const album=node('p','sheet-album');album.id='sheetAlbum';
 const cover=button('',()=>{const entry=libraryEntry();if(entry&&typeof openArtwork==='function')openArtwork(entry);},'sheet-cover');cover.id='sheetCover';
 identity.append(node('div','sheet-kicker','BANDSTUDIO / FICHE MORCEAU'),artist,songTitle,album);
 heading.append(identity,cover);
 const meta=node('p','sheet-meta');meta.id='sheetMeta';
 const stats=node('div','sheet-stats');stats.id='sheetStats';
 const toolbar=node('div','sheet-toolbar');
 const sections=node('select');sections.id='sheetSection';sections.setAttribute('aria-label','Passage de la fiche');
 const exportButton=button('Exporter la fiche PDF',()=>$('exportSheet').click(),'primary');exportButton.id='sheetExport';
 const undo=button('↶ Annuler',()=>send('undo'));undo.id='sheetUndo';
 const redo=button('↷ Rétablir',()=>send('redo'));redo.id='sheetRedo';
 const importButton=button('Importer des paroles',()=>{view('tools');$('importLyrics').click();});importButton.id='sheetImportLyrics';
 const details=button('Détails',()=>{const on=sheet.classList.toggle('sheet-details');details.setAttribute('aria-pressed',String(on));});details.id='sheetDetails';details.setAttribute('aria-pressed','false');
 toolbar.append(sections,details,undo,redo,importButton,exportButton);
 const hint=node('p','sheet-hint');hint.id='sheetHint';
 const calibration=button('Vérifier le calage',()=>view('guides'),'sheet-calibration');
 const sheetHelp=node('div','sheet-help');sheetHelp.append(hint,calibration);
 const references=node('div','sheet-toolbar');
 const searches=[];
 for(const [kind,label] of [['chords','Accords sur Internet ↗'],['lyrics','Paroles sur Internet ↗']]) {
  const search=button(label,()=>{
   const source=selectedChordSource(state.project);
   if(kind==='chords'&&source)send('chordSourceOpen',{url:source.url});
   else send('referenceSearch',{kind,query:[artist.textContent,songTitle.textContent].filter(Boolean).join(' ')});
  });
  search.id='sheetSearch-'+kind;search.title='Ouvrir une recherche dans ton navigateur pour comparer les propositions';
  searches.push(search);references.append(search);
 }
 references.append(node('small','','Compare la version et la tonalité, puis corrige la fiche.'));
 references.append(button('Comparer les sources d’accords',()=>{view('prompter');$('chordReferencePrompter').scrollIntoView({block:'start'});}));
 const correctLyrics=button('Corriger les paroles et recaler',()=>{view('tools');$('correctLyrics').click();});correctLyrics.id='sheetCorrectLyrics';references.append(correctLyrics);
 const manualLyrics=button('Recaler à la main',()=>$('manualLyrics').click());manualLyrics.id='sheetManualLyrics';references.append(manualLyrics);
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
  const clean=String(p.name||'Ton morceau').replace(/\s*[\[(](?:official (?:music )?(?:video|audio)|lyrics?|hd|hq)[\])]/gi,'').trim();
  const parts=clean.split(/\s+[-–—]\s+/);
  artist.textContent=entry?.artist||(parts.length>1?parts[0]:'');
  songTitle.textContent=entry?.title&&entry.title!==p.name?entry.title:parts.slice(parts.length>1?1:0).join(' - ');
  album.textContent=entry?.album||'Ta grille de répétition';
  cover.replaceChildren();
  if(entry?.artwork?.startsWith('data:image/jpeg;base64,')) {
   const img=node('img');img.src=entry.artwork;img.alt='Pochette'+(entry.album?' de '+entry.album:' du morceau');cover.append(img);
  } else cover.append(node('span','sheet-record','♪'));
  cover.disabled=!entry||!!state.busy;
  cover.title=entry?.artwork?'Changer la pochette':'Choisir une pochette';
  cover.setAttribute('aria-label',cover.title);
 }
 function chordLabel(text) {
  text=String(text).trim();
  if(/^(N|NC|N\.C\.|NO_CHORD)$/i.test(text))return 'N.C.';
  return text.replace(/:min(?=$|[^a-z])/g,'m').replace(/:maj(?=$|\/|\s)/g,'').replace(/:maj(?=\d)/g,'maj').replace(/:(dim|aug|sus|add|\d)/g,'$1');
 }

 function positionLabel(grid,t) {
  const p=grid.position(t);
  return (p.bar<1?'Levée':'mes. '+p.bar)+' · temps '+Number(p.beat.toFixed(2));
 }
 function editEntry(kind,item,start,end) {
  if(state.busy)return;
  $('annotationKind').value=kind;
  openAnnotation(item || {start,end,text:''});
 }
 function entryButton(kind,item,start,end,grid) {
  const continuation=item.start<start-EPS;
  let label=item.text;
  if(kind==='chords')label=transposeChord(chordLabel(label),(transport.pitch||0)-(state.project.capo||0));
  else if(item.words?.length)label=item.words.filter(w=>w.start>=start-EPS&&w.start<end-EPS).map(w=>w.text).join(' ');
  else if(continuation)return null;
  if(!label)return null;
  const uncertain=kind==='chords'&&!item.manual&&item.sourceURL&&item.confidence<.5;
  const b=button('',()=>editEntry(kind,item),'sheet-entry sheet-'+kind+(item.manual?' manual':'')+(uncertain?' uncertain':''));
  b.dataset.annotation=item.id;b.dataset.kind=kind;b.disabled=!!state.busy;
  b.append(node('span','sheet-entry-text',label+(uncertain?' ?':'')));
  const pos=positionLabel(grid,Math.max(start,item.start));
  b.append(node('small','',pos+' · '+(item.manual?'corrigé':item.sourceURL?'Internet · '+(uncertain?'calage incertain':'proposé'):'auto')));
  b.title='Modifier '+(kind==='chords'?'l’accord':'la ligne')+' : '+item.text+' ('+positionLabel(grid,item.start)+')';
  if(item.sourceURL&&!item.manual)b.title+=' · '+(uncertain?'Calage incertain, à vérifier':'Calage proposé depuis une grille Internet');
  return b;
 }
 function groups(project,duration) {
  const result=[];let end=0;
  for(const s of [...(project.sections||[])].sort((a,b)=>a.start-b.start)) {
   const a=Math.max(end,s.start,0), b=Math.min(duration,s.end);
   if(a>end+EPS)result.push({name:'Sans section',start:end,end:a,id:'gap-'+end});
   if(b>a+EPS){result.push({...s,start:a,end:b});end=b;}
  }
  if(end<duration-EPS)result.push({name:result.length?'Sans section':'Le morceau',start:end,end:duration,id:'gap-'+end});
  return result;
 }
 function renderSheet() {
  const p=state.project, duration=state.duration||0, opened=state.loaded&&duration>0;
  const chordSource=typeof selectedChordSource==='function'?selectedChordSource(p):p.chordReference?.sources?.[0];
  chordLegend.textContent=chordSource?'Accords : '+chordSource.publisher+' · calage proposé sur ta grille. ? = accord ou placement à vérifier.':'';
  const disabled=!opened||!!state.busy;
  exportButton.disabled=importButton.disabled=sections.disabled=calibration.disabled=details.disabled=disabled;
  searches.forEach(b=>b.disabled=!opened);
  undo.disabled=disabled||!state.undo;redo.disabled=disabled||!state.redo;
  if(sheet.hidden)return;
  renderIdentity();
  content.replaceChildren();highlighted=null;
  if(!opened){meta.textContent='';hint.textContent='Ouvre un morceau pour afficher sa fiche.';sections.replaceChildren();return;}
  const grid=musicalGrid(p,duration);
  stats.replaceChildren();
  for(const [label,value] of [['TEMPO',Number(grid.bpm.toFixed(1))+' BPM'],['TONALITÉ',p.key?transposeChord(chordLabel(p.key),transport.pitch||0):'À préciser'],['MESURE',grid.timeSignature],['DURÉE',time(duration)]]) {
   const stat=node('div','sheet-stat');stat.append(node('small','',label),node('strong','',value));stats.append(stat);
  }
  const all=groups(p,duration), chosen=p.id===sheetProject?sections.value:'';
  sheetProject=p.id;sections.replaceChildren();
  const option=node('option','','Tout le morceau');option.value='';sections.append(option);
  for(const group of all){const o=node('option','',group.name);o.value=group.id;sections.append(o);}
  sections.value=all.some(s=>s.id===chosen)?chosen:'';
  const shift=(transport.pitch||0)-(p.capo||0);currentPitch=transport.pitch||0;
  meta.textContent=[p.name,Number(grid.bpm.toFixed(1))+' BPM',grid.timeSignature,p.key?'Tonalité : '+transposeChord(p.key,transport.pitch||0):'',p.capo?'Capo '+p.capo:''].filter(Boolean).join(' · ');
  hint.textContent='Clique sur un accord ou des paroles pour les corriger. Les numéros repèrent les mesures.'+(shift?' Accords transposés ; l’éditeur montre les accords source.':'')+(!(p.lyrics||[]).length?' Aucune parole : utilise + Paroles ou importe un fichier LRC/SRT.':'');
  for(const group of all.filter(s=>!sections.value||s.id===sections.value)) {
   const article=node('article','sheet-section');article.dataset.section=group.id;
   const head=node('div','sheet-section-heading');
   const title=button(group.name,()=>send('seek',{time:group.start}),'sheet-section-title');
   title.title='Aller au début de '+group.name;
   const groupBars=grid.bars.filter(b=>b.start<group.end-EPS&&b.end>group.start+EPS);
   const range=groupBars.length?(groupBars[0].number===0?'Levée':'M. '+groupBars[0].number)+' – '+groupBars.at(-1).number:'';
   head.append(node('span','sheet-section-number',String(all.indexOf(group)+1).padStart(2,'0')),title,node('small','',range));
   head.title=positionLabel(grid,group.start)+' → '+time(group.end,true);
   const originalSection=(p.sections||[]).find(s=>s.id===group.id);
   if(originalSection) {const edit=button('Modifier la section',()=>openEditor('section',originalSection));edit.disabled=!!state.busy;head.append(edit);}
   const row=node('div','sheet-bars');
   for(const bar of groupBars) {
    const start=Math.max(bar.start,group.start),end=Math.min(bar.end,group.end);
    const cell=node('div','sheet-bar');cell.dataset.start=start;cell.dataset.end=end;cell.dataset.bar=bar.number;
    const partial=start>bar.start+EPS||end<bar.end-EPS;
    const top=node('div','sheet-bar-heading');const seek=button(bar.number?'M. '+bar.number:'Levée',()=>send('seek',{time:start}));
    seek.setAttribute('aria-label',bar.number?'Écouter la mesure '+bar.number:'Écouter la levée');
    seek.title='Écouter à partir de '+time(start,true);top.append(seek);
    if(partial)top.append(node('span','sheet-partial',start>bar.start+EPS?'suite':'début'));
    top.append(node('small','',time(start,true)));cell.append(top);
    for(const kind of ['chords','lyrics']) {
     const lane=node('div','sheet-lane sheet-lane-'+kind);lane.setAttribute('aria-label',kind==='chords'?'Accords':'Paroles');
     for(const item of (p[kind]||[]).filter(e=>e.start<end-EPS&&e.end>start+EPS).sort((a,b)=>a.start-b.start)) {
      const b=entryButton(kind,item,start,end,grid);if(b)lane.append(b);
     }
     const add=button(kind==='chords'?'+ Accord':'+ Paroles',()=>editEntry(kind,null,start,end),'sheet-add');
     add.dataset.add=kind;add.disabled=!!state.busy;
     lane.classList.toggle('has-entries',!!lane.children.length);lane.append(add);cell.append(lane);
    }
    row.append(cell);
   }
   article.append(head,row);content.append(article);
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
 placement.append(node('legend','','Placement dans le morceau'));
 const fields=node('div','sheet-position-fields');
 for(const [id,label] of [['sheetStartBar','Mesure de début'],['sheetStartBeat','Temps'],['sheetEndBar','Mesure de fin'],['sheetEndBeat','Temps']]) {
  const l=node('label','',label), input=node('input');input.id=id;input.type='number';input.step=id.endsWith('Beat')?'0.001':'1';l.append(input);fields.append(l);
 }
 const move=node('div','sheet-move');
 for(const [label,beats] of [['← 1 mesure','bar-'],['← 1 temps',-1],['1 temps →',1],['1 mesure →','bar+']]) {
  const b=button(label,()=>{const g=editorGrid(),amount=beats==='bar-'?-g.meter:beats==='bar+'?g.meter:beats;moveTo(g.at(g.coordinate(Number($('annotationStart').value))+amount));});
  b.dataset.shift=beats;move.append(b);
 }
 for(const [label,delta] of [['← 100 ms',-.1],['100 ms →',.1]]) {
  const control=button(label,()=>moveTo(Number($('annotationStart').value)+delta));control.dataset.shiftSeconds=delta;move.append(control);
 }
 move.append(button('Placer au curseur',()=>moveTo(transport.position||0)),button('Écouter cette ligne',()=>{
  const start=Math.max(0,Number($('annotationStart').value)-.5),end=Math.min(state.duration,Number($('annotationEnd').value)+.5);
  if(Number.isFinite(start)&&Number.isFinite(end)&&end>start)send('audition',{start,end});
 }),button('Pause',()=>{if(transport.playing)send('play');}));
 const help=node('small','','Les flèches déplacent toute la ligne avec ses mots. Enregistrer sauvegarde tes horaires dans le morceau et les protège des analyses automatiques. Mesure 0 : levée avant la mesure 1.');
 const error=node('p','sheet-error');error.id='sheetPositionError';error.setAttribute('role','status');
 const replaceLabel=node('label','checkbox'), replace=node('input');replace.id='sheetReplaceChords';replace.type='checkbox';replace.checked=true;
 replaceLabel.id='sheetReplaceLabel';replaceLabel.append(replace,document.createTextNode('Remplacer les accords présents sur cette plage'));
 placement.append(fields,move,help,replaceLabel,error);
 $('annotationText').parentElement.after(placement);
 function editorGrid(){return musicalGrid(state.project,state.duration);}
 function refreshPosition() {
  const g=editorGrid();
  for(const side of ['Start','End']) {
   const p=g.position(Number($('annotation'+side).value));
   $('sheet'+side+'Bar').value=p.bar;$('sheet'+side+'Beat').value=Number(p.beat.toFixed(3));
  }
 }
 function moveTo(start) {
  const old=Number($('annotationStart').value),delta=start-old,end=Number($('annotationEnd').value)+delta;
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<-EPS||end>state.duration+EPS||end<=start){error.textContent='Ce déplacement dépasse les limites du morceau.';refreshPosition();return;}
  const round=n=>Number(n.toFixed(3));
  $('annotationStart').value=round(Math.max(0,start));$('annotationEnd').value=round(Math.min(state.duration,end));
  for(const input of $('wordRows').querySelectorAll('[data-word=start],[data-word=end]'))input.value=round(Number(input.value)+delta);
  error.textContent='Position modifiée. Enregistre pour l’appliquer.';refreshPosition();
 }
 const baseAnnotation=openAnnotation;openAnnotation=function(item){
  baseAnnotation(item);replace.checked=true;replaceLabel.hidden=annotationEdit.kind!=='chords';error.textContent='';refreshPosition();
  $('annotationForm').querySelector('button[type=submit]').disabled=!!state.busy;
  $('annotationForm').querySelector('button[type=submit]').textContent=annotationEdit.kind==='lyrics'?'Enregistrer le calage':'Enregistrer';
 };
 for(const side of ['Start','End']) {
  for(const part of ['Bar','Beat']) $('sheet'+side+part).onchange=()=>{
   const g=editorGrid(),bar=Number($('sheet'+side+'Bar').value),beat=Number($('sheet'+side+'Beat').value);
   if(!Number.isInteger(bar)||!Number.isFinite(beat)||beat<1||beat>=g.meter+1){error.textContent='Saisis une mesure entière et un temps compris entre 1 et '+g.meter+'.';refreshPosition();return;}
   const t=g.at((bar-1)*g.meter+beat-1);
   if(side==='Start')moveTo(t);
   else if(t>Number($('annotationStart').value)&&t<=state.duration+EPS){$('annotationEnd').value=Number(Math.min(t,state.duration).toFixed(3));error.textContent='';refreshPosition();}
   else{error.textContent='La fin doit suivre le début et rester dans le morceau.';refreshPosition();}
  };
  $('annotation'+side).addEventListener('change',refreshPosition);
 }
 const baseSubmit=$('annotationForm').onsubmit;
 $('annotationForm').onsubmit=e=>{
  if(state.busy){e.preventDefault();error.textContent='Attends la fin du traitement pour enregistrer.';return;}
  // The native command splits overlapping chords atomically, with a single undo step.
  if(annotationEdit.kind==='chords')annotationEdit.replaceRange=replace.checked;
  const start=Number($('annotationStart').value),end=Number($('annotationEnd').value);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>state.duration||end<=start){e.preventDefault();error.textContent='Vérifie le début et la fin de cette entrée.';return;}
  baseSubmit(e);
 };
})();
