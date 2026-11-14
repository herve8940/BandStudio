'use strict';
// The queue is independent of the song open in the workshop.
let batchState={items:[],enabled:false},batchSignature='',batchPending=null;
const queueView=node('section','view');queueView.id='view-queue';queueView.hidden=true;
queueView.innerHTML=`<div class="page-heading"><div class="eyebrow">AJOUTER · LANCER · RETROUVER</div><h2>File de préparation</h2><p>Ajoute tous tes morceaux, puis lance leur préparation. Rien ne démarre avant ton clic.</p></div>
<div class="cards preparation queue-inputs">
<article><h3>1. Choisir la préparation</h3><label>Instruments<select id="queueModel"><option value="htdemucs">4 pistes · chant, batterie, basse, autres</option><option value="htdemucs_ft">4 pistes · modèle affiné, plus lent</option><option value="htdemucs_6s">6 pistes · avec guitare et piano</option></select></label><label>Calcul<select id="queueQuality"><option value="standard">Équilibré</option><option value="careful">Approfondi · plus long</option><option value="fast">Rapide</option></select></label><label>Langue des paroles<select id="queueLanguage"><option value="auto">Détection automatique</option><option value="fr">Français</option><option value="en">Anglais</option></select></label><small>Ces choix s’appliquent aux prochains ajouts. Séparation, tempo, tonalité et guides ; structure, paroles et accords selon les moteurs installés.</small></article>
<article><h3>2. Ajouter les sources</h3><button id="queueFiles">＋ Fichiers sur mon ordinateur</button><p>Plusieurs fichiers à la fois, un morceau par fichier. Garde les sources disponibles jusqu’à leur import.</p><form id="queueLinksForm"><label>Liens YouTube ou audio · un lien par ligne<textarea id="queueLinks" rows="5" placeholder="https://www.youtube.com/watch?v=…" required></textarea></label><button type="submit" id="queueAddLinks">＋ Ajouter les liens</button></form><small>Un morceau ou une vidéo par lien. Les playlists ne sont pas importées en entier.</small></article>
</div><div class="queue-toolbar"><button id="queueStart" class="primary">▶ Démarrer la file</button><button id="queuePause">Pause</button><button id="queueClear">Retirer les tâches terminées</button><button id="queueRefresh">Actualiser la file</button></div>
<p id="queueStatus" role="status">Prête à recevoir tes morceaux.</p><p id="queueMessage" role="status" hidden></p><p class="queue-help">Laisse BandStudio ouvert. La file attend pendant une lecture ou une autre analyse. Les étapes terminées sont conservées ; après une pause ou une fermeture, seule l’étape interrompue est relancée. Les morceaux préparés restent à écouter et à valider.</p>
<div id="queueItems" class="queue-items"></div>`;
queueView.querySelector('.page-heading').after(queueView.querySelector('.queue-toolbar'),queueView.querySelector('#queueStatus'),queueView.querySelector('#queueMessage'));
$('view-library').after(queueView);
const queueNav=button('',()=>view('queue'),'nav');queueNav.dataset.view='queue';
queueNav.append(node('b','','≡'),node('span','','File de préparation'));
document.querySelector('.rail [data-view=library]').after(queueNav);
const queueHeader=button('＋ Ajouter à la file',()=>view('queue'));
$('view-library').querySelector('.page-heading').append(queueHeader);
function queueOptions(){return {model:$('queueModel').value,quality:$('queueQuality').value,language:$('queueLanguage').value};}
function queueSend(action,extra={}){send('batchQueue',{action,...extra});}
$('queueFiles').onclick=()=>queueSend('files',{options:queueOptions()});
$('queueLinksForm').onsubmit=e=>{
 e.preventDefault();const sources=$('queueLinks').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
 if(!sources.length)return;
 if(sources.length>100||sources.some(s=>{try{const u=new URL(s);return !['http:','https:'].includes(u.protocol)||!!u.username||!!u.password;}catch{return true;}})){
  $('queueMessage').hidden=false;$('queueMessage').textContent='Ajoute jusqu’à 100 liens HTTP ou HTTPS valides, un par ligne.';return;
 }
 batchPending='links-'+Date.now();$('queueAddLinks').disabled=true;
 queueSend('add',{kind:'url',sources,options:queueOptions(),requestID:batchPending});
 // Keep pasted URLs until the service acknowledges the addition.
};
$('queueStart').onclick=()=>queueSend('start');
$('queuePause').onclick=()=>queueSend('pause');
$('queueClear').onclick=()=>queueSend('clearDone');
$('queueRefresh').onclick=()=>queueSend('refresh');
function renderBatch(){
 const items=batchState.items||[],waiting=items.filter(e=>e.status==='pending'||e.status==='running').length,done=items.filter(e=>e.status==='done').length;
 $('queueStart').disabled=batchState.enabled||!waiting;
 $('queueStart').textContent=items.some(e=>e.completed>0&&e.status==='pending')?'▶ Reprendre la file':'▶ Démarrer la file';
 $('queuePause').disabled=!batchState.enabled;
 $('queueClear').disabled=!done;
 $('queueStatus').textContent=(batchState.status||'En pause · démarrage manuel')+' · '+waiting+' en attente · '+done+' terminé(s)';
 $('queueMessage').textContent=batchState.message||'';$('queueMessage').hidden=!batchState.message;
 const signature=JSON.stringify(items);if(signature===batchSignature)return;batchSignature=signature;
 const list=$('queueItems');list.replaceChildren();
 const labels={pending:'En attente',running:'En cours',done:'Prêt à vérifier',error:'À reprendre'};
 items.forEach((item,index)=>{
  const row=node('article','queue-item'),info=node('div','queue-info'),actions=node('div','queue-actions');
  info.append(node('small','queue-state '+item.status,labels[item.status]||item.status),node('h3','',item.title),node('small','queue-source',item.source));
  if(item.total)info.append(node('p','',item.completed+'/'+item.total+' étapes terminées'+(item.stage?' · '+item.stage:'')));
  if(item.error)info.append(node('p','queue-error',item.error));
  if(item.status==='done'&&item.project)actions.append(button('Ouvrir le morceau',()=>{send('library',{path:item.project});view('studio');},'primary'));
  if(item.status==='error')actions.append(button('Réessayer',()=>queueSend('retry',{id:item.id})));
  if(item.status==='pending'&&index>0){const up=button('↑ Monter',()=>queueSend('up',{id:item.id}));up.setAttribute('aria-label','Monter '+item.title);actions.append(up);}
  const remove=button(item.status==='running'?'Annuler cette tâche':'Retirer',()=>queueSend('remove',{id:item.id}));remove.setAttribute('aria-label','Retirer '+item.title);actions.append(remove);
  row.append(info,actions);list.append(row);
 });
 if(!items.length)list.append(node('p','queue-empty','Ta file est vide. Ajoute des fichiers ou colle tes liens ci-dessus.'));
}
const receiveBeforeBatch=window.studioReceive;
window.studioReceive=function(message){
 if(message.type==='batchQueue'){
  batchState=message;
  if(batchPending&&message.ack?.id===batchPending){
   if(message.ack.ok)$('queueLinks').value='';
   batchPending=null;$('queueAddLinks').disabled=false;
  }
  if(message.status==='File arrêtée'||message.status==='File indisponible'){batchPending=null;$('queueAddLinks').disabled=false;}
  renderBatch();return;
 }
 receiveBeforeBatch(message);
};
window.addEventListener('DOMContentLoaded',()=>queueSend('refresh'));
renderBatch();
