'use strict';

// Workspace navigation only: every edit continues through the existing project
// commands, undo stack and protected-marker workflow.
(() => {
 // The toggle stays in the header so navigation can always be restored.
 const rail=document.querySelector('.rail'),header=document.querySelector('.app > header');
 rail.id='mainSidebar';
 const headerStart=node('div','header-start'),title=header.firstElementChild;
 header.prepend(headerStart);
 const menu=button('',()=>setSidebar(!rail.hidden,true),'sidebar-toggle');menu.id='sidebarToggle';
 menu.innerHTML='<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><rect x="2" y="3" width="16" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 3v14" stroke="currentColor" stroke-width="1.5"/></svg><span>Menu</span>';
 menu.setAttribute('aria-controls',rail.id);headerStart.append(menu,title);
 const collapseMenu=button(uiText('‹ Réduire le menu'),()=>{setSidebar(true,true);menu.focus();},'sidebar-collapse');collapseMenu.id='sidebarCollapse';
 collapseMenu.setAttribute('aria-controls',rail.id);collapseMenu.setAttribute('aria-label',uiText('Réduire le menu'));rail.prepend(collapseMenu);
 function setSidebar(hidden,save=false){
  rail.hidden=hidden;document.body.classList.toggle('sidebar-collapsed',hidden);
  menu.setAttribute('aria-expanded',String(!hidden));menu.title=hidden?uiText('Afficher le menu'):uiText('Réduire le menu');menu.setAttribute('aria-label',menu.title);menu.querySelector('span').textContent=menu.title;
  collapseMenu.setAttribute('aria-expanded',String(!hidden));
  if(save){try{localStorage.setItem('bandstudio.sidebarCollapsed',String(hidden));}catch{}}
  requestAnimationFrame(redrawTimeline);
 }
 let sidebarHidden=false;
 try{sidebarHidden=localStorage.getItem('bandstudio.sidebarCollapsed')==='true';}catch{}
 setSidebar(sidebarHidden);
 const workspace=$('workspace'),arrangement=document.querySelector('.arrangement');
 let mode='tracks',filter='all',query='',compact=false,lastProject='';
 const heading=node('div','workspace-heading');
 heading.innerHTML=uiMarkup('<div><div class="eyebrow">ATELIER DU MORCEAU</div><h2>Éditeur du morceau</h2></div><div id="workspaceMetrics" class="workspace-metrics"></div>');
 workspace.prepend(heading);
 const navigation=document.querySelector('.navigation-tools');
 heading.querySelector('h2').after($('prepareAllStructure'));
 const navigationMenu=node('details','workspace-navigation');
 navigationMenu.append(node('summary','',uiText('Navigation & repères')),navigation);
 heading.append(navigationMenu);
 const controls=node('div','workspace-controls');
 const tabs=node('div','segmented workspace-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label',uiText('Vue de travail'));
 for(const [key,label] of [['tracks',uiText('Pistes')],['structure','Sections'],['lyrics',uiText('Paroles')],['chords',uiText('Accords')],['rhythm',uiText('Métronome')]]){
  const b=button(label,()=>{mode=key;renderWorkspace();requestAnimationFrame(drawWaves);});b.dataset.workspaceMode=key;tabs.append(b);
 }
 const search=node('input');search.type='search';search.id='workspaceSearch';search.placeholder=uiText('Rechercher une piste…');search.setAttribute('aria-label',uiText('Rechercher dans la vue de travail'));
 search.oninput=()=>{query=search.value.toLocaleLowerCase('fr');renderWorkspaceContent();};
 const role=node('select');role.id='workspaceFilter';role.setAttribute('aria-label',uiText('Afficher les pistes'));
 for(const [key,label] of [['all',uiText('Toutes les pistes')],['instruments','Instruments'],['source','Original'],['guides','Guides']]){const o=node('option','',label);o.value=key;role.append(o);}
 role.onchange=()=>{filter=role.value;renderWorkspaceContent();};
 const density=button('Compact',()=>{compact=!compact;renderWorkspace();requestAnimationFrame(drawWaves);});density.id='workspaceCompact';density.title=uiText('Réduire la hauteur des pistes');
 const focus=button(uiText('Masquer l’inspecteur'),()=>{const hidden=workspace.classList.toggle('inspector-hidden');focus.textContent=hidden?uiText('Afficher l’inspecteur'):uiText('Masquer l’inspecteur');focus.setAttribute('aria-pressed',String(hidden));requestAnimationFrame(drawWaves);});focus.id='workspaceFocus';focus.setAttribute('aria-pressed','false');
 controls.append(tabs,search,role,density,focus);
 arrangement.querySelector('.arrangement-top').after(controls);

 const overview=node('div','workspace-overview');
 const overviewLane=node('div','overview-lane');overviewLane.id='workspaceOverview';overviewLane.setAttribute('aria-label',uiText('Vue d’ensemble du morceau'));
 const overviewWindow=node('div','overview-window');overviewWindow.setAttribute('aria-hidden','true');
 overview.append(node('span','overview-caption',uiText('VUE D’ENSEMBLE')),overviewLane);
 controls.after(overview);
 const table=node('div','structure-table');table.id='structureTable';table.hidden=true;
 table.setAttribute('role','table');table.setAttribute('aria-label',uiText('Sections du morceau'));
 $('tracks').after(table);
 const noTracks=node('p','workspace-empty');noTracks.textContent=uiText('Aucune piste ne correspond à ce filtre.');noTracks.hidden=true;$('tracks').after(noTracks);

 // Move the existing controls into one workshop. There is no second form,
 // document copy, or independent save path in the sheet and prompter.
 const textEditor=node('section','workspace-editor-panel');textEditor.id='editorAnnotations';textEditor.hidden=true;
 const annotationTools=$('addAnnotation').closest('.annotation-toolbar');
 textEditor.append($('songKey').closest('.annotation-toolbar'),$('chordReferencePrompter'),annotationTools,$('annotations'));
 table.after(textEditor);
 $('annotationKind').hidden=true;
 annotationTools.querySelectorAll('[data-action]').forEach(b=>$('view-tools').querySelector('.page-heading').append(b));
 const drumEditor=node('details','workspace-editor-panel');drumEditor.id='editorDrums';
 drumEditor.append(node('summary','',uiText('Batterie · mesure à la tête de lecture')),$('drumGrid'));
 $('tracks').after(drumEditor);
 const rhythmEditor=node('section','workspace-editor-panel');rhythmEditor.id='editorRhythm';rhythmEditor.hidden=true;
 rhythmEditor.append($('view-guides').querySelector('.callout'),$('guideForm'));textEditor.after(rhythmEditor);
 const keyTools=$('songKey').closest('.annotation-toolbar');keyTools.id='editorHarmonySettings';
 const prompterHeading=$('view-prompter').querySelector('.page-heading');
 prompterHeading.querySelector('h2').textContent=uiText('Prompteur');
 prompterHeading.append(node('p','',uiText('Les paroles et les accords suivent les corrections enregistrées dans l’éditeur.')),button(uiText('Modifier dans l’éditeur'),()=>window.openStudioEditor('lyrics')));
 window.openStudioEditor=function(kind='tracks'){
  mode=['tracks','structure','lyrics','chords','rhythm'].includes(kind)?kind:'tracks';
  view('studio');renderWorkspace();requestAnimationFrame(redrawTimeline);
 };
 const annotationsChanged=$('annotationKind').onchange;
 $('annotationKind').onchange=()=>{mode=$('annotationKind').value;annotationsChanged();renderWorkspace();};

 const selectionZoom=button(uiText('Sélection'),()=>{
  const s=state.project.sections.find(s=>s.id===selected)||focusMarker()?.item;
  if(!s||!Number.isFinite(s.end))return;
  zoomSpan=Math.min(state.duration,Math.max(2,s.end-s.start)*1.15);zoomStart=s.start-(zoomSpan-(s.end-s.start))/2;
  $('zoomFollow').checked=false;redrawTimeline();
 });selectionZoom.id='zoomSelection';selectionZoom.title=uiText('Cadrer la section sélectionnée · F');$('zoomAll').after(selectionZoom);
 const mixToggle=button(uiText('Mix des guides'),()=>{const show=document.querySelector('.editor-mixer').hidden;document.querySelector('.editor-mixer').hidden=!show;mixToggle.setAttribute('aria-expanded',String(show));});
 mixToggle.id='workspaceMix';mixToggle.setAttribute('aria-expanded','false');mixToggle.setAttribute('aria-controls','workspaceGuideMixer');
 const mixer=document.querySelector('.editor-mixer');mixer.id='workspaceGuideMixer';mixer.hidden=true;
 $('zoomPosition').before(mixToggle);
 const shortcuts=node('small','workspace-shortcuts',uiText('Espace · lecture    Alt + ← / → · repères    F · cadrer la section    L · boucle'));
 arrangement.after(shortcuts);
 // Keep the help inside the arrangement column, outside the inspector grid flow.
 arrangement.append(shortcuts);

 function color(name){
  return sectionStyle(name).color;
 }
 function length(section,g){
  const pulses=Math.max(0,g.coordinate(section.end)-g.coordinate(section.start)),bars=pulses/g.meter;
  return Math.abs(bars-Math.round(bars))<.04?Math.round(bars)+uiText(' mesures'):bars.toLocaleString('fr',{maximumFractionDigits:1})+uiText(' mesures');
 }
 function rowFor(section,index,g){
  const row=node('div','structure-row');row.dataset.id=section.id;row.setAttribute('role','row');row.classList.toggle('selected',selected===section.id);row.style.setProperty('--section-color',color(section.name));
  const identity=node('div','structure-identity');identity.setAttribute('role','cell');
  const select=button(section.name,()=>{selectSection(section);chooseMarker('section',section.id,false);},'structure-name');
  select.title=uiText('Sélectionner et écouter ')+section.name;identity.append(node('span','structure-number',String(index+1).padStart(2,'0')),select);
  const pos=node('div','structure-position');pos.setAttribute('role','cell');pos.append(node('strong','',g.label(section.start)),node('small','',time(section.start,true)+' → '+time(section.end,true)));
  const span=node('div','structure-length',length(section,g));span.setAttribute('role','cell');
  const status=node('div','structure-status');status.setAttribute('role','cell');status.append(node('span',section.reviewed?'reviewed':'',section.reviewed?uiText('✓ Validée'):uiText('À vérifier')));if(section.locked)status.append(node('small','',uiText('Protégée')));
  const actions=node('div','structure-actions');actions.setAttribute('role','cell');
  const loop=button('↻',()=>{selectSection(section);chooseMarker('section',section.id,false);if(!transport.loop)send('loop',{on:true,start:section.start,end:section.end});});loop.title=uiText('Boucler ')+section.name;loop.setAttribute('aria-label',loop.title);
  const edit=button(uiText('Modifier'),()=>openEditor('section',section));edit.disabled=!!state.busy;loop.disabled=!!state.busy;actions.append(loop,edit);
  row.append(identity,pos,span,status,actions);return row;
 }
 function renderWorkspaceContent(){
  const g=musicalGrid(state.project);
  let visible=0;
  document.querySelectorAll('#tracks .track').forEach(row=>{
   const t=state.project.tracks.find(t=>t.id===row.dataset.id);if(!t)return;
   const matches=filter==='all'||filter==='guides'&&t.role.startsWith('guide_')||filter==='source'&&t.role==='source'||filter==='instruments'&&t.role!=='source'&&!t.role.startsWith('guide_');
   row.hidden=!matches||![t.name,roles[t.role]].join(' ').toLocaleLowerCase('fr').includes(query);if(!row.hidden)visible++;
   row.querySelectorAll('.track-buttons button').forEach(b=>{if(b.textContent==='M'||b.textContent==='S'){b.setAttribute('aria-label',b.title);b.setAttribute('aria-pressed',String(b.textContent==='M'?!!t.muted:!!t.solo));}});
  });
  noTracks.hidden=mode!=='tracks'||visible>0;
  const header=node('div','structure-row structure-header');header.setAttribute('role','row');
  for(const name of ['SECTION',uiText('DÉPART / FIN'),uiText('LONGUEUR'),uiText('VÉRIFICATION'),'ACTIONS']){const cell=node('span','',name);cell.setAttribute('role','columnheader');header.append(cell);}
  const rows=state.project.sections.map((s,i)=>({s,i})).filter(({s})=>s.name.toLocaleLowerCase('fr').includes(query));
  table.replaceChildren(header,...rows.map(({s,i})=>rowFor(s,i,g)));
  if(!rows.length)table.append(node('p','workspace-empty',state.project.sections.length?uiText('Aucune section ne correspond à la recherche.'):uiText('Ajoute une section avec le bouton + de la ligne Structure.')));
  requestAnimationFrame(drawWaves);
 }
 function renderOverview(){
  overviewLane.replaceChildren();
  const duration=Math.max(.001,state.duration),g=musicalGrid(state.project);
  for(const s of state.project.sections){
   const b=button(s.name,()=>{selectSection(s);chooseMarker('section',s.id,false);},'overview-section');
   b.style.left=Math.max(0,s.start)/duration*100+'%';b.style.width=Math.max(0,Math.min(duration,s.end)-Math.max(0,s.start))/duration*100+'%';b.style.setProperty('--section-color',color(s.name));b.title=s.name+' · '+length(s,g);b.setAttribute('aria-label',b.title);overviewLane.append(b);
  }
  overviewLane.append(overviewWindow);
  const v=viewport();overviewWindow.style.left=v.start/duration*100+'%';overviewWindow.style.width=v.span/duration*100+'%';overviewWindow.hidden=v.span>=duration;
  document.querySelectorAll('#sections .section').forEach(b=>{const s=state.project.sections.find(s=>s.id===b.dataset.id);if(s){b.style.setProperty('--section-color',color(s.name));b.setAttribute('aria-label',s.name+' · '+g.label(s.start)+' · '+length(s,g));}});
 }
 function renderWorkspace(){
  const p=state.project,s={...guideDefaults,...p.settings},tempo=tempoSummary(p);
  const signature=pulseScale(p)===1.5?s.beatsPerBar*3+'/8':s.beatsPerBar+'/4';
  $('workspaceMetrics').replaceChildren(...[[tempo.bpm>0?tempo.bpm.toLocaleString('fr',{maximumFractionDigits:1}):'—','BPM'],[signature,uiText('MESURE')],[time(state.duration),uiText('DURÉE')],[p.sections.filter(s=>s.reviewed).length+'/'+p.sections.length,uiText('VALIDÉES')]].map(([value,label])=>{const item=node('div');item.append(node('strong','',value),node('small','',label));return item;}));
  workspace.classList.toggle('compact-tracks',compact);density.setAttribute('aria-pressed',String(compact));
  tabs.querySelectorAll('button').forEach(b=>{const active=b.dataset.workspaceMode===mode;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  $('tracks').hidden=mode!=='tracks';table.hidden=mode!=='structure';role.hidden=density.hidden=mode!=='tracks';search.placeholder=mode==='tracks'?uiText('Rechercher une piste…'):uiText('Rechercher une section…');
  drumEditor.hidden=mode!=='tracks'||!(p.drumHits||[]).length;
  const textMode=mode==='lyrics'||mode==='chords';textEditor.hidden=!textMode;rhythmEditor.hidden=mode!=='rhythm';
  search.hidden=mode!=='tracks'&&mode!=='structure';
  if(textMode){$('annotationKind').value=mode;$('addAnnotation').textContent=mode==='lyrics'?uiText('＋ Ajouter une ligne'):uiText('＋ Ajouter un accord');renderAnnotations();}
  focus.hidden=mode!=='tracks'&&mode!=='structure';
  workspace.classList.toggle('contextual-editor',mode!=='tracks'&&mode!=='structure');
  keyTools.hidden=mode!=='chords';$('chordReferencePrompter').hidden=mode!=='chords';
  if($('lyricsTools'))$('lyricsTools').hidden=mode!=='lyrics';
  workspace.dataset.editor=mode;
  arrangement.querySelector('.arrangement-top>span').textContent=({tracks:uiText('Pistes audio'),structure:uiText('Sections et repères'),lyrics:uiText('Paroles synchronisées'),chords:uiText('Accords du morceau'),rhythm:uiText('Métronome et décomptes')})[mode];
  selectionZoom.disabled=!!state.busy||!p.sections.some(s=>s.id===selected);
  renderWorkspaceContent();renderOverview();
 }
 const originalSections=renderSections;
 renderSections=function(){originalSections();selectionZoom.disabled=!!state.busy||!state.project.sections.some(s=>s.id===selected);renderOverview();if(mode==='structure')renderWorkspaceContent();};
 const originalReceive=window.studioReceive;
 window.studioReceive=function(data){
  if(data.type==='state'&&data.project.id!==lastProject){lastProject=data.project.id;query='';search.value='';mode='tracks';}
  originalReceive(data);
  if(data.type==='state'){document.body.classList.toggle('workspace-open',state.loaded&&!$('view-studio').hidden);renderWorkspace();}
 };
 const originalView=view;
 view=function(name){
  if(name==='guides'){mode='rhythm';name='studio';}
  originalView(name);document.body.classList.toggle('workspace-open',name==='studio'&&state.loaded);
  if(name==='studio')renderWorkspace();
 };
 const originalSelect=selectSection;
 selectSection=function(section){originalSelect(section);selectionZoom.disabled=!!state.busy;document.querySelectorAll('.structure-row[data-id]').forEach(row=>row.classList.toggle('selected',row.dataset.id===section.id));};
 document.addEventListener('keydown',e=>{
  if(e.defaultPrevented||!state.loaded||state.busy||$('view-studio').hidden||e.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey)return;
  if(e.altKey&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();navigateMarker(e.key==='ArrowLeft'?-1:1);}
  else if(!e.altKey&&!e.shiftKey&&e.key.toLowerCase()==='f'){e.preventDefault();selectionZoom.click();}
  else if(!e.altKey&&!e.shiftKey&&e.key.toLowerCase()==='l'){e.preventDefault();$('loopToggle').click();}
 });
 renderWorkspace();
})();
