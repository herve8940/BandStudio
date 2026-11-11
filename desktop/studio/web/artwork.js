'use strict';
// One background lookup at a time. New imports join the queue; already imported
// projects are discovered on the first state, without blocking audio controls.
const artworkSeen=new Set(),artworkQueue=[];
let artworkActive=null,artworkProject=null,artworkPaused=false;
const artworkDialog=node('dialog');artworkDialog.id='artworkDialog';
artworkDialog.innerHTML='<form id="artworkForm"><div class="eyebrow">POCHETTE DU MORCEAU</div><h2 id="artworkName"></h2><p>Recherche du titre et de l’artiste uniquement. L’audio reste local.</p><label>Titre<input id="artworkTitle" maxlength="200" required></label><label>Artiste<input id="artworkArtist" maxlength="200" placeholder="Nom du groupe ou de l’artiste"></label><div class="dialog-actions"><button type="button" id="artworkFile">Choisir une image…</button><button class="primary" type="submit">Rechercher sur Internet</button></div></form><p id="artworkMessage" role="status"></p><div id="artworkChoices"></div><small>Catalogue : MusicBrainz · Images : Cover Art Archive</small><div class="dialog-actions"><button id="artworkClose">Fermer</button></div>';
document.body.append(artworkDialog);
const artworkBar=node('div','artwork-bar');
artworkBar.append(button('Rechercher les pochettes manquantes',()=>{artworkPaused=false;for(const p of state.library||[])if(!p.artwork)queueArtwork({path:p.path,action:'sync',force:true});pumpArtwork();}),button('Suspendre',()=>{artworkPaused=!artworkPaused;pumpArtwork();},'artwork-pause'),node('small','',''));
artworkBar.lastChild.id='artworkProgress';artworkBar.lastChild.setAttribute('role','status');
$('library').before(artworkBar);

function queueArtwork(task,priority=false){
 if(task.action==='sync'&&(artworkActive?.path===task.path||artworkQueue.some(t=>t.path===task.path)))return;
 if(priority){for(let i=artworkQueue.length-1;i>=0;i--)if(artworkQueue[i].path===task.path)artworkQueue.splice(i,1);artworkQueue.unshift(task);}
 else artworkQueue.push(task);
}
function pumpArtwork(){
 artworkBar.querySelector('.artwork-pause').textContent=artworkPaused?'Reprendre':'Suspendre';
 artworkBar.querySelector('.artwork-pause').disabled=!artworkActive&&!artworkQueue.length;
 if(!artworkActive){
  const index=artworkQueue.findIndex(t=>t.action!=='sync'||!artworkPaused);
  if(index>=0){
   artworkActive=artworkQueue.splice(index,1)[0];
   if((state.library||[]).some(p=>p.path===artworkActive.path))send('artwork',artworkActive);
   else{artworkActive=null;pumpArtwork();return;}
  }
 }
 const current=(state.library||[]).find(p=>p.path===artworkActive?.path);
 $('artworkProgress').textContent=current?'Recherche : '+current.name+(artworkQueue.length?' · '+artworkQueue.length+' en attente':''):artworkPaused&&artworkQueue.length?'Recherche suspendue.':'Les pochettes sont conservées pour une utilisation hors ligne.';
 $('artworkForm').querySelector('button[type=submit]').disabled=artworkActive?.path===artworkProject?.path;
 $('artworkFile').disabled=artworkActive?.path===artworkProject?.path||!!state.busy;
}
function scanArtwork(){
 for(const p of state.library||[])if(!p.artwork&&!artworkSeen.has(p.path)){artworkSeen.add(p.path);queueArtwork({path:p.path,action:'sync'});}
 pumpArtwork();
}
function openArtwork(p){
 artworkProject=p;$('artworkName').textContent=p.name;
 const name=p.name.replace(/_/g,' ').replace(/^FULL\s+/i,'').split(/\s+[-–—]\s+/);
 $('artworkTitle').value=p.title||name[name.length>1?1:0];$('artworkArtist').value=p.artist||(name.length>1?name[0]:'');
 $('artworkMessage').textContent=p.artworkMessage||'Précise le titre et l’artiste pour trouver le bon album.';$('artworkChoices').replaceChildren();
 artworkDialog.showModal();pumpArtwork();
}
$('artworkClose').onclick=()=>artworkDialog.close();
$('artworkFile').onclick=()=>{send('projectArtwork',{path:artworkProject.path});artworkDialog.close();};
$('artworkForm').onsubmit=e=>{
 e.preventDefault();$('artworkMessage').textContent='Recherche dans le catalogue…';$('artworkChoices').replaceChildren();
 queueArtwork({path:artworkProject.path,action:'search',title:$('artworkTitle').value.trim(),artist:$('artworkArtist').value.trim()},true);pumpArtwork();
};
const artworkReceive=window.studioReceive;
window.studioReceive=data=>{
 if(data.type==='artworkResult'){
  if(data.path!==artworkActive?.path)return;
  if(data.entry){state.library=(state.library||[]).map(p=>p.path===data.path?data.entry:p);renderLibrary();}
  if(artworkProject?.path===data.path&&artworkDialog.open){
   $('artworkMessage').textContent=data.message||'';
   if(data.entry){artworkProject=data.entry;if(artworkActive.action==='sync'){$('artworkTitle').value=data.entry.title||$('artworkTitle').value;$('artworkArtist').value=data.entry.artist||$('artworkArtist').value;}}
   $('artworkChoices').replaceChildren(...(data.candidates||[]).map(c=>{
    const row=node('div','artwork-choice'),label=node('div');label.append(node('strong','',c.album),node('small','',c.artist+' · '+c.title+(c.date?' · '+c.date.slice(0,4):'')));
    row.append(label,button('Utiliser cet album',()=>{$('artworkChoices').replaceChildren();$('artworkMessage').textContent='Téléchargement de la pochette…';queueArtwork({path:data.path,action:'apply',id:c.id},true);pumpArtwork();}));return row;
   }));
  }
  if(artworkActive.action==='sync'&&data.entry?.artworkStatus==='offline')artworkPaused=true;
  artworkActive=null;pumpArtwork();return;
 }
 artworkReceive(data);
 if(data.type==='state')scanArtwork();
};
scanArtwork();
