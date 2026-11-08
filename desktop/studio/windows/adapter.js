'use strict';
// Preserve the shared Mac UI's message contract without exposing a network service.
const pendingWindowsMessages=[];
function windowsPost(message){if(window.pywebview?.api?.command)window.pywebview.api.command(message);else pendingWindowsMessages.push(message);}
window.webkit={messageHandlers:{studio:{postMessage:windowsPost}}};
window.addEventListener('pywebviewready',()=>{for(const message of pendingWindowsMessages.splice(0))windowsPost(message);});
window.addEventListener('DOMContentLoaded',()=>{
 document.querySelector('.version').textContent='DEV · Win';
 const openRPP=document.createElement('button');openRPP.textContent='Importer REAPER';openRPP.onclick=()=>send('openRPP');document.querySelector('.header-actions').prepend(openRPP);
 const settings=document.querySelector('#view-settings');
 const heading=document.createElement('div');heading.className='page-heading';heading.innerHTML='<div class="eyebrow">COMPOSANTS FACULTATIFS</div><h2>Analyses locales</h2><p>Installe seulement les moteurs dont tu as besoin. Internet est nécessaire au premier téléchargement. Les installations s’ouvrent dans une fenêtre séparée.</p>';
 const cards=document.createElement('div');cards.className='cards';
 for(const [id,label,description] of [['stems','Séparer les stems','Demucs · 4 ou 6 pistes, modèles téléchargés au premier usage.'],['structure','Structure automatique','SongFormer · plusieurs gigaoctets, licences affichées avant installation.'],['words','Paroles synchronisées','Whisper · transcription et mots synchronisés.'],['chords','Accords','Reconnaissance harmonique locale.'],['drums','Transcription batterie','ADTOF · licence non commerciale présentée avant installation.']]){
  const card=document.createElement('article'),title=document.createElement('h3'),text=document.createElement('p'),button=document.createElement('button');title.textContent=label;text.textContent=description;button.textContent='Installer / vérifier';button.onclick=()=>send('installComponent',{component:id});card.append(title,text,button);cards.append(card);
 }
 settings.prepend(heading,cards);
 for(const p of document.querySelectorAll('#view-settings p,#view-takes p,#view-prepare p,#view-prepare small'))p.textContent=p.textContent.replaceAll('du Mac','de Windows').replaceAll('macOS','Windows').replaceAll('ce Mac','ce PC');
 const modelsNote=[...document.querySelectorAll('#view-prepare small')].find(x=>x.textContent.includes('modèles sont déjà'));if(modelsNote)modelsNote.textContent='Installe le moteur dans Réglages → Analyses locales avant le premier essai. La qualité et la durée du calcul dépendent du morceau et du PC.';
 const voice=document.querySelector('#setting-voice');if(voice){voice.value='Système';voice.parentElement.firstChild.textContent='Voix Windows installée (ou Système)';}
 const hint=[...document.querySelectorAll('#guideFields small')].find(x=>x.textContent.includes('Thomas'));if(hint)hint.textContent='Système choisit une voix Windows disponible, de préférence dans la langue du décompte. Tu peux saisir le nom exact d’une voix SAPI installée.';
 const note=document.createElement('div');note.className='callout';note.innerHTML='<strong>Préversion Windows 11 · test local</strong><p>La vitesse et la tonalité sont préparées dans des fichiers temporaires : le changement peut prendre un instant. Les voix et le décompte gardent leur hauteur. Les entrées/sorties audio utilisent les périphériques par défaut de Windows. Aucun compte n’est nécessaire.</p>';
 document.querySelector('#view-settings').append(note);
});
