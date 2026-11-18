'use strict';

// Workspace navigation only: every edit continues through the existing project
// commands, undo stack and protected-marker workflow.
(() => {
 const workspace=$('workspace'),arrangement=document.querySelector('.arrangement');
 let mode='tracks',filter='all',query='',compact=false,lastProject='';
 const heading=node('div','workspace-heading');
 heading.innerHTML='<div><div class="eyebrow">ATELIER DU MORCEAU</div><h2>Pistes & structure</h2></div><div id="workspaceMetrics" class="workspace-metrics"></div>';
 workspace.prepend(heading);
 const navigation=document.querySelector('.navigation-tools');
 heading.querySelector('h2').after($('prepareAllStructure'));
 const navigationMenu=node('details','workspace-navigation');
 navigationMenu.append(node('summary','','Navigation & repères'),navigation);
 heading.append(navigationMenu);
 const controls=node('div','workspace-controls');
 const tabs=node('div','segmented workspace-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','Vue de travail');
 for(const [key,label] of [['tracks','Pistes'],['structure','Structure']]){
  const b=button(label,()=>{mode=key;renderWorkspace();requestAnimationFrame(drawWaves);});b.dataset.workspaceMode=key;tabs.append(b);
 }
 const search=node('input');search.type='search';search.id='workspaceSearch';search.placeholder='Rechercher une piste…';search.setAttribute('aria-label','Rechercher dans la vue de travail');
 search.oninput=()=>{query=search.value.toLocaleLowerCase('fr');renderWorkspaceContent();};
 const role=node('select');role.id='workspaceFilter';role.setAttribute('aria-label','Afficher les pistes');
 for(const [key,label] of [['all','Toutes les pistes'],['instruments','Instruments'],['source','Original'],['guides','Guides']]){const o=node('option','',label);o.value=key;role.append(o);}
 role.onchange=()=>{filter=role.value;renderWorkspaceContent();};
 const density=button('Compact',()=>{compact=!compact;renderWorkspace();requestAnimationFrame(drawWaves);});density.id='workspaceCompact';density.title='Réduire la hauteur des pistes';
 const focus=button('Masquer l’inspecteur',()=>{const hidden=workspace.classList.toggle('inspector-hidden');focus.textContent=hidden?'Afficher l’inspecteur':'Masquer l’inspecteur';focus.setAttribute('aria-pressed',String(hidden));requestAnimationFrame(drawWaves);});focus.id='workspaceFocus';focus.setAttribute('aria-pressed','false');
 controls.append(tabs,search,role,density,focus);
 arrangement.querySelector('.arrangement-top').after(controls);

 const overview=node('div','workspace-overview');
 const overviewLane=node('div','overview-lane');overviewLane.id='workspaceOverview';overviewLane.setAttribute('aria-label','Vue d’ensemble du morceau');
 const overviewWindow=node('div','overview-window');overviewWindow.setAttribute('aria-hidden','true');
 overview.append(node('span','overview-caption','VUE D’ENSEMBLE'),overviewLane);
 controls.after(overview);
 const table=node('div','structure-table');table.id='structureTable';table.hidden=true;
 table.setAttribute('role','table');table.setAttribute('aria-label','Sections du morceau');
 $('tracks').after(table);
 const noTracks=node('p','workspace-empty');noTracks.textContent='Aucune piste ne correspond à ce filtre.';noTracks.hidden=true;$('tracks').after(noTracks);

 const selectionZoom=button('Sélection',()=>{
  const s=state.project.sections.find(s=>s.id===selected)||focusMarker()?.item;
  if(!s||!Number.isFinite(s.end))return;
  zoomSpan=Math.min(state.duration,Math.max(2,s.end-s.start)*1.15);zoomStart=s.start-(zoomSpan-(s.end-s.start))/2;
  $('zoomFollow').checked=false;redrawTimeline();
 });selectionZoom.id='zoomSelection';selectionZoom.title='Cadrer la section sélectionnée · F';$('zoomAll').after(selectionZoom);
 const mixToggle=button('Mix des guides',()=>{const show=document.querySelector('.editor-mixer').hidden;document.querySelector('.editor-mixer').hidden=!show;mixToggle.setAttribute('aria-expanded',String(show));});
 mixToggle.id='workspaceMix';mixToggle.setAttribute('aria-expanded','false');mixToggle.setAttribute('aria-controls','workspaceGuideMixer');
 const mixer=document.querySelector('.editor-mixer');mixer.id='workspaceGuideMixer';mixer.hidden=true;
 $('zoomPosition').before(mixToggle);
 const shortcuts=node('small','workspace-shortcuts','Espace · lecture    Alt + ← / → · repères    F · cadrer la section    L · boucle');
 arrangement.after(shortcuts);
 // Keep the help inside the arrangement column, outside the inspector grid flow.
 arrangement.append(shortcuts);

 function color(name){
  const value=name.toLocaleLowerCase('fr');
  return /refrain|chorus/.test(value)?'#56cbbf':/couplet|verse/.test(value)?'#a894e5':/pont|bridge/.test(value)?'#e9b96b':/solo|instrument/.test(value)?'#7aa8ee':/break|arrêt/.test(value)?'#ee94a5':'#8b9eb7';
 }
 function length(section,g){
  const pulses=Math.max(0,g.coordinate(section.end)-g.coordinate(section.start)),bars=pulses/g.meter;
  return Math.abs(bars-Math.round(bars))<.04?Math.round(bars)+' mesures':bars.toLocaleString('fr',{maximumFractionDigits:1})+' mesures';
 }
 function rowFor(section,index,g){
  const row=node('div','structure-row');row.dataset.id=section.id;row.setAttribute('role','row');row.classList.toggle('selected',selected===section.id);row.style.setProperty('--section-color',color(section.name));
  const identity=node('div','structure-identity');identity.setAttribute('role','cell');
  const select=button(section.name,()=>{selectSection(section);chooseMarker('section',section.id,false);},'structure-name');
  select.title='Sélectionner et écouter '+section.name;identity.append(node('span','structure-number',String(index+1).padStart(2,'0')),select);
  const pos=node('div','structure-position');pos.setAttribute('role','cell');pos.append(node('strong','',g.label(section.start)),node('small','',time(section.start,true)+' → '+time(section.end,true)));
  const span=node('div','structure-length',length(section,g));span.setAttribute('role','cell');
  const status=node('div','structure-status');status.setAttribute('role','cell');status.append(node('span',section.reviewed?'reviewed':'',section.reviewed?'✓ Validée':'À vérifier'));if(section.locked)status.append(node('small','','Protégée'));
  const actions=node('div','structure-actions');actions.setAttribute('role','cell');
  const loop=button('↻',()=>{selectSection(section);chooseMarker('section',section.id,false);if(!transport.loop)send('loop',{on:true,start:section.start,end:section.end});});loop.title='Boucler '+section.name;loop.setAttribute('aria-label',loop.title);
  const edit=button('Modifier',()=>openEditor('section',section));edit.disabled=!!state.busy;loop.disabled=!!state.busy;actions.append(loop,edit);
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
  for(const name of ['SECTION','DÉPART / FIN','LONGUEUR','VÉRIFICATION','ACTIONS']){const cell=node('span','',name);cell.setAttribute('role','columnheader');header.append(cell);}
  const rows=state.project.sections.map((s,i)=>({s,i})).filter(({s})=>s.name.toLocaleLowerCase('fr').includes(query));
  table.replaceChildren(header,...rows.map(({s,i})=>rowFor(s,i,g)));
  if(!rows.length)table.append(node('p','workspace-empty',state.project.sections.length?'Aucune section ne correspond à la recherche.':'Ajoute une section avec le bouton + de la ligne Structure.'));
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
  $('workspaceMetrics').replaceChildren(...[[tempo.bpm>0?tempo.bpm.toLocaleString('fr',{maximumFractionDigits:1}):'—','BPM'],[signature,'MESURE'],[time(state.duration),'DURÉE'],[p.sections.filter(s=>s.reviewed).length+'/'+p.sections.length,'VALIDÉES']].map(([value,label])=>{const item=node('div');item.append(node('strong','',value),node('small','',label));return item;}));
  workspace.classList.toggle('compact-tracks',compact);density.setAttribute('aria-pressed',String(compact));
  tabs.querySelectorAll('button').forEach(b=>{const active=b.dataset.workspaceMode===mode;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  $('tracks').hidden=mode!=='tracks';table.hidden=mode!=='structure';role.hidden=density.hidden=mode!=='tracks';search.placeholder=mode==='tracks'?'Rechercher une piste…':'Rechercher une section…';
  selectionZoom.disabled=!!state.busy||!p.sections.some(s=>s.id===selected);
  renderWorkspaceContent();renderOverview();
 }
 const originalSections=renderSections;
 renderSections=function(){originalSections();selectionZoom.disabled=!!state.busy||!state.project.sections.some(s=>s.id===selected);renderOverview();if(mode==='structure')renderWorkspaceContent();};
 const originalReceive=window.studioReceive;
 window.studioReceive=function(data){
  if(data.type==='state'&&data.project.id!==lastProject){lastProject=data.project.id;query='';search.value='';}
  originalReceive(data);
  if(data.type==='state'){document.body.classList.toggle('workspace-open',state.loaded&&!$('view-studio').hidden);renderWorkspace();}
 };
 const originalView=view;
 view=function(name){originalView(name);document.body.classList.toggle('workspace-open',name==='studio'&&state.loaded);};
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
