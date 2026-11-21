'use strict';
// A common navigation language. Controls are moved, never duplicated: existing
// handlers, saved settings, undo and native commands remain the source of truth.
(() => {
 const rail=document.querySelector('.rail');
 $('sidebarCollapse').hidden=true;
 const groups=[['BIBLIOTHÈQUE',['library','queue']],['TON MORCEAU',['studio','sheet','prompter','guides','prepare']],['EXPORTER',['delivery','tools']]];
 const labels={library:['Mes morceaux','Retrouver et ouvrir un morceau'],queue:['Préparer une série','Importer plusieurs fichiers'],studio:['Pistes & structure','Écouter, comparer et jouer'],sheet:['Fiche morceau','Paroles et accords sur la grille'],prompter:['Paroles & accords','Suivre le chant et corriger le texte'],guides:['Click & repères','Régler le départ et les annonces'],prepare:['Préparation détaillée','Relancer une analyse si nécessaire'],delivery:['Projet REAPER','Valider et transmettre le morceau'],tools:['Audio & documents','Pistes, paroles et fiche PDF'],settings:['Réglages','Audio, moteurs et mises à jour']};
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
 lyricsTools.append(content);$('view-prompter').querySelector('.page-heading').after(lyricsTools);
 lyricsCard.querySelector('h3').textContent='Exporter les paroles';lyricsCard.querySelector('p').textContent='Enregistre les paroles synchronisées au format LRC ou SRT.';
 function showLyricsTools(){view('prompter');lyricsTools.open=true;lyricsTools.scrollIntoView({block:'nearest'});}
 $('sheetCorrectLyrics').onclick=()=>{showLyricsTools();$('correctLyrics').click();};
 $('sheetImportLyrics').onclick=()=>{showLyricsTools();$('importLyrics').click();};
 // One prominent starting point; detailed analyses remain available on demand.
 const heading=document.querySelector('.workspace-heading'),prepare=$('prepareAllStructure');
 const quick=node('div','workspace-quick-prepare');quick.append(prepare,node('small','','Un clic pour préparer le morceau complet.'));heading.append(quick);
 const oldView=view;
 function location(name){
  context.textContent=labels[name]?.[0]||({support:'Aide & Discord',takes:'Enregistrer',creative:'Création',phone:'Télécommande'}[name]||'Ton atelier');
  rail.querySelectorAll('[data-view]').forEach(b=>{if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  document.dispatchEvent(new CustomEvent('studio:view-changed',{detail:name}));
 }
 view=function(name){oldView(name);location(name);};
 location([...document.querySelectorAll('.view')].find(v=>!v.hidden)?.id.replace('view-','')||'studio');
})();
