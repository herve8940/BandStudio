'use strict';
// A common navigation language. Controls are moved, never duplicated: existing
// handlers, saved settings, undo and native commands remain the source of truth.
(() => {
 const rail=document.querySelector('.rail');
 $('sidebarCollapse').hidden=true;
 const groups=[['BIBLIOTHÈQUE',['library','queue']],['TON MORCEAU',['studio','sheet','prompter','prepare']],['EXPORTER',['delivery','tools']]];
 const labels={library:['Mes morceaux','Retrouver et ouvrir un morceau'],queue:['Préparer une série','Importer plusieurs fichiers'],studio:['Éditeur du morceau','Modifier les pistes, sections, paroles, accords et le métronome'],sheet:['Fiche morceau','Paroles et accords sur la grille'],prompter:['Prompteur','Suivre le chant pendant la lecture'],guides:['Click & repères','Régler le départ et les annonces'],prepare:['Préparation détaillée','Relancer une analyse si nécessaire'],delivery:['Projet REAPER','Valider et transmettre le morceau'],tools:['Audio & documents','Pistes, paroles et fiche PDF'],settings:['Réglages','Audio, moteurs et mises à jour']};
 const paths={library:'M4 5h16v15H4z M8 2v6 M12 2v6 M16 2v6 M8 12h8 M8 16h5',queue:'M4 6h12 M4 12h12 M4 18h7 M18 15v6 M15 18h6',studio:'M4 5h16 M4 12h16 M4 19h16 M8 2v6 M16 9v6 M11 16v6',sheet:'M6 3h9l4 4v14H6z M14 3v5h5 M9 12h7 M9 16h5',prompter:'M5 4h14v14H9l-4 3z M8 8h8 M8 12h6',guides:'M12 3L4 21h16z M12 13l6-8 M9 18h6',prepare:'M4 7h16 M4 17h16 M8 4v6 M16 14v6',delivery:'M4 5h8 M4 5v15h16v-8 M13 3h8v8 M11 13L21 3',tools:'M12 3v12 M8 11l4 4 4-4 M4 16v5h16v-5',settings:'M5 6h14 M5 12h14 M5 18h14 M9 3v6 M15 9v6 M9 15v6'};
 function decorate(b,key){
  const [label,hint]=labels[key]||[b.textContent,''];
  const icon=node('span','nav-icon');icon.setAttribute('aria-hidden','true');
  if(paths[key])icon.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="'+paths[key]+'"/></svg>';
  const text=node('span','nav-copy',label);b.replaceChildren(icon,text);b.title=hint;b.setAttribute('aria-label',label);
 }
 rail.querySelectorAll('.nav-label,.nav-divider').forEach(e=>e.remove());
 const anchor=rail.querySelector('.spacer');
 for(const [title,keys] of groups){
  const group=node('nav','nav-group');group.setAttribute('aria-label',title);group.append(node('span','nav-label',title));
  for(const key of keys){const b=rail.querySelector('[data-view="'+key+'"]');if(b){decorate(b,key);group.append(b);}}
  rail.insertBefore(group,anchor);
 }
 const guidesNavigation=rail.querySelector('[data-view=guides]');if(guidesNavigation)guidesNavigation.remove();
 const settings=rail.querySelector('[data-view=settings]');if(settings)decorate(settings,'settings');
 const context=node('span','app-location');context.id='appLocation';
 const eyebrow=document.querySelector('header .eyebrow');eyebrow.replaceChildren(context);
 const settingsView=$('view-settings'),settingsHeading=settingsView.querySelector('.page-heading');if(settingsHeading)settingsView.prepend(settingsHeading);
 // Import/correction belongs with the lyrics. Export keeps just its formats.
 const lyricsCard=$('importLyrics').closest('article'),lyricsTools=node('details','lyrics-tools');lyricsTools.id='lyricsTools';
 lyricsTools.append(node('summary','','Corriger ou importer les paroles'));
 const content=node('div','lyrics-tools-content');
 for(const id of ['lyricsFile','replaceLyrics','importLyrics','correctLyrics','manualLyrics','lyricsReferenceStatus','lyricsImportStatus']){
  const e=$(id);content.append(id==='replaceLyrics'?e.closest('label'):e);
 }
 lyricsTools.append(content);$('editorAnnotations').prepend(lyricsTools);
 lyricsCard.querySelector('h3').textContent='Exporter les paroles';lyricsCard.querySelector('p').textContent='Enregistre les paroles synchronisées au format LRC ou SRT.';
 function showLyricsTools(){openStudioEditor('lyrics');lyricsTools.open=true;lyricsTools.scrollIntoView({block:'nearest'});}
 $('sheetCorrectLyrics').onclick=()=>{showLyricsTools();$('correctLyrics').click();};
 $('sheetImportLyrics').onclick=()=>{showLyricsTools();$('importLyrics').click();};
 // One prominent starting point; detailed analyses remain available on demand.
 // Import is the start of the preparation, at the existing quality settings.
 const importChoice=node('label','checkbox import-preparation');
 const autoImport=node('input');autoImport.type='checkbox';autoImport.id='autoPrepareImport';autoImport.checked=true;
 try{autoImport.checked=localStorage.getItem('bandstudio.autoPrepareImport')!=='false';}catch{}
 autoImport.onchange=()=>{try{localStorage.setItem('bandstudio.autoPrepareImport',String(autoImport.checked));}catch{}};
 importChoice.append(autoImport,node('span','','Préparer automatiquement après l’import'));
 $('view-library').querySelector('.page-heading').append(importChoice);
 document.querySelectorAll('[data-action=import]').forEach(b=>{b.onclick=()=>send('import',{prepare:autoImport.checked});});
 const validationDetails=node('details','listening-checklist');
 validationDetails.append(node('summary','','Ma vérification à l’écoute (facultative)'));
 $('validationForm').before(validationDetails);validationDetails.append($('validationForm'));
 $('validateProject').textContent='Enregistrer ma vérification';
 $('sendReaper').textContent='Vérifier et ouvrir dans REAPER ↗';
 $('saveReaper').textContent='Vérifier et exporter le projet';
 $('view-delivery').querySelector('.page-heading h2').textContent='Ton projet REAPER';
 $('view-delivery').querySelector('.page-heading p').textContent='Retrouve tes pistes, tes repères et tes guides dans REAPER, avec les réglages de ton écoute.';
 $('validationForm').closest('article').querySelector('h3').textContent='Vérification et export';
 const deliveryNote=$('saveReaper').parentElement.querySelector(':scope > small:last-child');
 if(deliveryNote)deliveryNote.textContent='Chaque export crée un nouveau dossier et vérifie les médias. Les passages signalés restent à écouter.';
 const workflow=node('nav','song-workflow');workflow.id='songWorkflow';workflow.setAttribute('aria-label','Parcours du morceau');
 const prepareStep=$('prepareAllStructure');
 const editStep=button('2 · Écouter et corriger',openReview);editStep.id='workflowReview';
 const exportStep=button('3 · Exporter vers REAPER',()=>view('delivery'));exportStep.id='workflowExport';
 workflow.append(prepareStep,editStep,exportStep);
 $('workspace').before(workflow);
 let reviewOpenedFor='',finishedFor='';
 function openReview(){
  reviewOpenedFor=state.project.id;
  openStudioEditor(state.project.sections.length?'structure':'tracks');
  updateWorkflow();
  const target=$('songReview');
  (target&&!target.hidden?target:$('workspace')).scrollIntoView({block:'nearest'});
 }
 function updateWorkflow(){
  const {audio,prepared,preparing,reviewable}=songPreparationState();
  const reviewing=!preparing&&audio&&(reviewable||reviewOpenedFor===state.project.id);
  workflow.hidden=!state.loaded;
  prepareStep.textContent=preparing?'1 · Préparation en cours':prepared?'1 · Préparé':'1 · Préparer';
  for(const [step,active] of [[prepareStep,!reviewing],[editStep,reviewing]]){
   step.classList.toggle('primary',active);
   if(active)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');
  }
  exportStep.disabled=editStep.disabled=!audio||!!state.busy;
 }
 const receiveBeforeWorkflow=window.studioReceive;
 window.studioReceive=function(data){
  if(data.type==='state'&&data.project.id!==state.project.id){reviewOpenedFor='';finishedFor='';}
  receiveBeforeWorkflow(data);
  if(data.type==='preparationFinished'&&data.projectID===state.project.id)finishedFor=data.projectID;
  if(data.type!=='state'&&data.type!=='preparationFinished')return;
  updateWorkflow();
  if(finishedFor&&finishedFor===state.project.id&&!state.busy){
   finishedFor='';
   if(state.loaded&&['studio','prepare','library'].some(name=>!$('view-'+name).hidden)&&!document.querySelector('dialog[open]'))openReview();
  }
 };
 updateWorkflow();
 $('structureTable').before($('structureReview'));
 const duplicateExport=document.querySelector('#workspace [data-view=delivery]');if(duplicateExport)duplicateExport.hidden=true;
 document.querySelectorAll('#workspace .toolbar [data-action=export]').forEach(b=>b.hidden=true);
 const oldView=view;
 function location(name){
  context.textContent=labels[name]?.[0]||({support:'Aide & Discord',takes:'Enregistrer',creative:'Création',phone:'Télécommande'}[name]||'Ton atelier');
  rail.querySelectorAll('[data-view]').forEach(b=>{if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  document.dispatchEvent(new CustomEvent('studio:view-changed',{detail:name}));
 }
 view=function(name){oldView(name);location(name==='guides'?'studio':name);};
 location([...document.querySelectorAll('.view')].find(v=>!v.hidden)?.id.replace('view-','')||'studio');
})();
