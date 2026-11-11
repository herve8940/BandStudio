/* Real REAPER state only. No demo tracks, generated waveforms or simulated audio. */
'use strict';
const $ = id => document.getElementById(id);
const all = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = seconds => {const s = Math.max(0, Math.floor(seconds || 0)); return `${Math.floor(s/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`;};
const colors = ['#a778fa','#35d3e9','#6aceaf','#eeae69','#e78cbf','#7f9eff'];
let state = null, connected = false, status = {}, selected = null, editing = null;
let song = {}, peaks = null, library = [], page = 'practice', tab = 'work', polling = false;
let regionSignature = '', trackSignature = '', takesSignature = '', inputSignature = '', waveKey = '', publicationAt = 0;
const viewNames = {library:'Mes morceaux',prepare:'Préparer un morceau',practice:'Travailler un morceau',takes:'Mes prises',group:'Répéter en groupe',concert:'Préparer le concert',lighting:'Lumière & timecode',bandpilot:'Le son avec BandPilot',settings:'Réglages'};

function message(text, success = false) {
  $('message').hidden = !text;
  $('message').classList.toggle('success', success);
  $('message').replaceChildren(document.createTextNode(text || ''));
  const close = document.createElement('button'); close.textContent = '×'; close.setAttribute('aria-label','Fermer le message');
  close.onclick = () => {$('message').hidden = true;}; $('message').append(close);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache:'no-store'} : {
    method:'POST', headers:{'Content-Type':'application/json','X-ReaCue-Desktop':'1'}, body:JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Erreur ${response.status}`);
  return data;
}
async function control(command, args = {}) {
  if (!connected || !state) throw new Error('Le pont Desktop doit être connecté à REAPER.');
  const result = await api('/api/control', {command,args,project_id:state.project_id});
  await poll(); return result;
}
async function task(command) {
  await api('/api/task', {command,project_id:state?.project_id});
  publicationAt = 0; message('Traitement lancé. Suis son avancement dans Préparer → Traitements.',true);
  await poll();
}
function guarded(fn) { return async event => {try {await fn(event);} catch(error) {message(error.message || String(error));}}; }
function focusRegion() {return state?.regions?.find(r => r.id === selected) || null;}
function loopBounds() {
  const r=focusRegion(),first=+$('loop-first').value,last=+$('loop-last').value;
  return r && first===r.first && last===r.last ? {start:r.start,finish:r.finish} : {first,last};
}
function native(tabName, action) {return control('native',{tab:tabName, ...(action ? {action} : {})});}
function mountFrame(id, mode, prompter = false) {
  const frame = $(id);
  if (connected && !frame.getAttribute('src')) frame.src = prompter ? '/legacy/prompteur.html?role=drums' : `/legacy/studio.html?mode=${mode}`;
}
function navigate(name) {
  page = name;
  all('[data-view]').forEach(el => {el.hidden = el.dataset.view !== name;});
  all('[data-page]').forEach(el => el.classList.toggle('active',el.dataset.page === name));
  $('page-title').textContent = viewNames[name];
  $('song-header').hidden = ['library','settings'].includes(name);
  if (name === 'group') mountFrame('group-frame','groupe');
  if (name === 'concert') mountFrame('concert-frame','concert');
  if (name === 'lighting') mountFrame('lighting-frame','lumiere');
  if (name === 'library') loadLibrary().catch(e=>message(e.message));
  if (name === 'practice') setTab(tab);
}
function setTab(name) {
  tab = name;
  all('[data-panel]').forEach(el => {el.hidden = el.dataset.panel !== name;});
  all('#practice-tabs [data-tab]').forEach(el=>el.classList.toggle('active',el.dataset.tab===name));
  if (name === 'studio') mountFrame('studio-frame','travail');
  if (name === 'drummer') mountFrame('drummer-frame','',true);
  if (name === 'work') requestAnimationFrame(drawWave);
}
async function chooseSection(id, seek = true) {
  selected = id;
  const r = focusRegion(); if (!r) return;
  $('loop-first').value = r.first; $('loop-last').value = r.last;
  renderRegions(true); renderFocus();
  if (seek) {
    // When looping, selecting another passage also moves the real loop.
    if (state.repeat_on) await control('loop',{start:r.start,finish:r.finish});
    await control('seek',{position:r.start});
  }
}
function renderRegions(force = false) {
  const regions = state?.regions || [];
  const signature = JSON.stringify([regions, selected]);
  if (!force && signature === regionSignature) return;
  regionSignature = signature;
  $('no-sections').hidden = regions.length > 0;
  $('sections').innerHTML = regions.map((r,i)=>`<button class="section ${r.id===selected?'active':''}" data-section="${r.id}" style="--color:${colors[i%colors.length]};--length:${Math.max(1,r.last-r.first+1)}" aria-pressed="${r.id===selected}"><b>${esc(r.name || 'Section')}</b><small>${r.first}–${r.last} · ${r.last-r.first+1} m.</small></button>`).join('');
  $('structure-list').innerHTML = regions.length ? regions.map((r,i)=>`<div class="structure-row ${r.id===selected?'active':''}" style="--color:${colors[i%colors.length]}"><button class="name" data-section="${r.id}"><i></i>${esc(r.name)}</button><span>m. ${r.first}–${r.last}</span><span class="muted">${clock(r.finish-r.start)}</span><div class="structure-actions"><button class="button" data-edit="${r.id}">Modifier</button><button class="button" data-region-op="split" data-id="${r.id}" ${r.last<=r.first?'disabled':''}>Couper</button><button class="button" data-region-op="merge" data-id="${r.id}" ${i===regions.length-1?'disabled':''}>Fusionner</button><button class="button" data-region-op="delete" data-id="${r.id}" ${regions.length<2?'disabled':''} aria-label="Supprimer ${esc(r.name)}">×</button></div></div>`).join('') : '<p class="empty">Aucune section dans ce projet. Prépare le morceau pour commencer.</p>';
}
function renderFocus() {
  const r = focusRegion(), index = state?.regions.findIndex(x=>x.id===selected) ?? -1;
  $('focus-name').textContent = r?.name || 'Choisis une section';
  $('focus-bars').textContent = r ? `Mesures REAPER ${r.first} à ${r.last} · ${r.last-r.first+1} mesures` : '—';
  $('loop-status').textContent = state?.repeat_on ? `Boucle active · ${clock(state.loop_start)} → ${clock(state.loop_end)}` : 'Boucle désactivée';
  $('loop-toggle').classList.toggle('active',!!state?.repeat_on);
  $('loop-toggle').setAttribute('aria-pressed',String(!!state?.repeat_on));
  $('loop-toggle').textContent = state?.repeat_on ? '↻ Désactiver' : '↻ Activer';
  $('next-section').textContent = state?.regions[index+1] ? `Puis : ${state.regions[index+1].name} →` : r ? 'Fin du morceau' : '';
  $('focus-position').textContent = r ? `Passage ${index+1} / ${state.regions.length} · ${clock(r.start)} → ${clock(r.finish)}` : '';
  $('band-passage').textContent = r ? `${r.name} · mesures ${r.first}–${r.last}` : 'Choisis un passage dans Travailler.';
  const key = `${state?.project_id}|${r?.id}|${r?.first}|${r?.last}`;
  if ($('bar-buttons').dataset.key !== key) {
    $('bar-buttons').dataset.key = key;
    const count = r ? r.last-r.first+1 : 0;
    const step = Math.max(1,Math.ceil(count/16));
    const bars = Array.from({length:Math.ceil(count/step)},(_,i)=>r.first+i*step);
    $('bar-buttons').style.setProperty('--bars',Math.max(1,bars.length));
    $('bar-buttons').innerHTML = bars.map(b=>`<button data-bar="${b}" title="Aller à la mesure ${b}">${b}</button>`).join('');
    drawWave();
  }
  all('[data-bar]').forEach(el=>el.classList.toggle('active',+el.dataset.bar===state?.measure));
  const fraction = r ? (state.position-r.start)/(r.finish-r.start) : -1;
  $('playhead').hidden = fraction < 0 || fraction > 1;
  $('playhead').style.left = `${Math.max(0,Math.min(1,fraction))*100}%`;
}
function drawWave() {
  const canvas = $('wave-canvas'), r=focusRegion();
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width*ratio; canvas.height = height*ratio;
  const ctx=canvas.getContext('2d'); ctx.scale(ratio,ratio); ctx.clearRect(0,0,width,height);
  ctx.strokeStyle='#2c3550'; ctx.beginPath();ctx.moveTo(0,height/2);ctx.lineTo(width,height/2);ctx.stroke();
  const track = peaks?.tracks?.find(t=>/drum|batter/i.test(t.name)) || peaks?.tracks?.find(t=>t.data);
  const bytes=track?._bytes;
  $('wave-message').hidden = !!(bytes?.length && r);
  if (!bytes?.length || !r) return;
  const hop=peaks.hop || .04, scale=height*.44;
  const gradient=ctx.createLinearGradient(0,0,width,0);gradient.addColorStop(0,'#7c68cc');gradient.addColorStop(.6,'#bca0ff');gradient.addColorStop(1,'#7b91e3');ctx.fillStyle=gradient;
  for(let x=0;x<width;x+=3){
    const start=Math.max(0,Math.floor((r.start+(x/width)*(r.finish-r.start))/hop));
    const end=Math.min(bytes.length/2,Math.max(start+1,Math.ceil((r.start+((x+3)/width)*(r.finish-r.start))/hop)));
    let lo=127,hi=127;for(let n=start;n<end;n++){lo=Math.min(lo,bytes[n*2]);hi=Math.max(hi,bytes[n*2+1]);}
    ctx.fillRect(x,height/2-(hi-127)/127*scale,2,Math.max(1,(hi-lo)/127*scale));
  }
}
function renderTracks() {
  const tracks=state?.tracks || [], music=tracks.filter(t=>!t.generated && !t.record_track);
  const signature=JSON.stringify(music.map(({peak,...rest})=>rest));
  // Polling must not replace a slider being edited.
  if (signature!==trackSignature && !$('stem-mixer').contains(document.activeElement)) {
    trackSignature=signature;
    $('stem-mixer').innerHTML=music.length ? music.map((t,i)=>`<div class="stem" style="--color:${colors[i%colors.length]}"><label for="vol-${i}" title="${esc(t.name)}">${esc(t.name || 'Piste '+t.id)}</label><input id="vol-${i}" aria-label="Volume ${esc(t.name)}" type="range" min="0" max="150" value="${Math.round(t.volume*100)}" data-volume="${esc(t.guid)}"><output>${t.volume>0?(20*Math.log10(t.volume)).toFixed(1)+' dB':'−∞ dB'}</output><button class="${t.mute?'active':''}" data-track="${esc(t.guid)}" data-field="mute" data-value="${!t.mute}" aria-pressed="${t.mute}" aria-label="Couper ${esc(t.name)}">M</button><button class="solo ${t.solo?'active':''}" data-track="${esc(t.guid)}" data-field="solo" data-value="${!t.solo}" aria-pressed="${t.solo}" aria-label="Solo ${esc(t.name)}">S</button></div>`).join('') : '<p class="empty">Les pistes du projet apparaîtront ici.</p>';
  }
  $('stem-count').textContent=`${music.length} pistes`;
  all('[data-listen]').forEach(el=>el.classList.toggle('active',el.dataset.listen===(state?.listen_mode || 'original')));
  const click=tracks.find(t=>t.name==='CLICK'), cues=tracks.filter(t=>['CUES','VOICE','VOIX'].includes(t.name));
  $('click-toggle').disabled=!connected || !click; $('click-toggle').classList.toggle('active',!!click && !click.mute);
  $('cue-toggle').disabled=!connected || !cues.length; $('cue-toggle').classList.toggle('active',cues.some(t=>!t.mute));
}
function renderRecording() {
  const inputs=state?.inputs || [], signature=JSON.stringify(inputs);
  if (signature!==inputSignature) {
    inputSignature=signature; const previous=$('record-input').value;
    $('record-input').innerHTML=inputs.length ? inputs.map(x=>`<option value="${x.id}">${x.id+1} · ${esc(x.name)}</option>`).join('') : '<option value="">Aucune entrée audio configurée</option>';
    if(inputs.some(i=>String(i.id)===previous)) $('record-input').value=previous;
  }
  const tracks=(state?.tracks || []).filter(t=>!t.generated), takes=state?.takes || [];
  const key=JSON.stringify([tracks.map(t=>[t.guid,t.name,t.record,t.input]),takes]);
  if (key===takesSignature) return; takesSignature=key;
  $('record-tracks').innerHTML=tracks.map(t=>`<div class="record-track"><span>${esc(t.name)} <small class="muted">· ${esc(inputs.find(i=>i.id===t.input)?.name || 'Entrée à régler dans REAPER')}</small></span><label><input type="checkbox" data-arm="${esc(t.guid)}" ${t.record?'checked':''}> Armée</label></div>`).join('');
  $('takes-list').innerHTML=takes.length ? takes.map((t,i)=>`<div class="take"><span>◉</span><div><h3>${esc(t.name || 'Prise '+(i+1))}</h3><p>${esc(t.track)} · ${clock(t.duration)} · ${t.active?'Prise active':'Autre prise'}</p></div><button class="button" data-take="${t.start}">Repérer ↗</button></div>`).join('') : '<p class="empty">Aucune prise sur les pistes armées ou nommées « PRISE … ». Choisis une entrée, ajoute une piste puis lance l’enregistrement.</p>';
}
async function loadLibrary() {const data=await api('/api/library');library=data.songs || [];renderLibrary();}
function renderLibrary() {
  const query=$('library-search').value.toLocaleLowerCase('fr');
  const songs=library.filter(s=>(s.title || '').toLocaleLowerCase('fr').includes(query));
  $('library-list').innerHTML=songs.length ? songs.map(s=>`<button class="library-song" data-project="${esc(s.path || s.project || '')}" ${connected?'':'disabled'}><span>♫</span><div><strong>${esc(s.title || 'Sans titre')}</strong><small>${esc(s.path || '')}</small></div><div class="meta">${Math.round(s.bpm || 0) || '—'} BPM<br><small>${clock(s.duration_s)} · Ouvrir ↗</small></div></button>`).join('') : '<p class="empty">Aucun morceau dans la bibliothèque publiée. Clique sur Actualiser ou prépare ton premier morceau.</p>';
}
async function loadPublication(project) {
  publicationAt=Date.now();
  try {
    const [s,p]=await Promise.all([api('/api/published/reacue_song.json'),api('/api/published/reacue_peaks.json')]);
    if(state?.project_id!==project) return;
    song=s.stale ? {} : s;
    const key=JSON.stringify([p.song_id,p.fingerprint,p.duration,p.tracks?.map(t=>t.data)]);
    if(key!==waveKey){waveKey=key;peaks=p.stale?null:p;
      for(const t of peaks?.tracks || []) {const raw=atob(t.data || '');t._bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));}
      drawWave();
    }
    $('wave-message').textContent=p.message || 'Publie le morceau pour afficher sa forme d’onde.';
  } catch(error) { $('wave-message').textContent=error.message; }
}
function diagnostics() {
  const rows=[['Version',status.version || '—'],['Connexion',connected?'REAPER connecté':'Pont à lancer dans REAPER'],['Projet',state?.project || 'Non enregistré'],['Source GitHub',(status.revision || '').slice(0,12)],['Moteurs',status.source || '—'],['Ressources REAPER',status.resource || '—']];
  $('diagnostics').innerHTML=rows.map(([key,value])=>`<div><b>${esc(key)}</b><span>${esc(value)}</span></div>`).join('');
}
function render() {
  $('connection').textContent=connected?(state.recording?'● Enregistrement':state.playing?'● Lecture · REAPER':'● REAPER connecté'):status.waiting?'● REAPER en attente':'● REAPER déconnecté';
  $('connection').classList.toggle('off',!connected);
  $('connect-panel').hidden=connected || status.waiting;
  $('waiting-panel').hidden=!status.waiting;
  $('bridge-path').textContent=status.bridge_script || '';
  all('.require').forEach(el=>{el.disabled=!connected;});
  if(!connected){diagnostics();return;}
  $('song-title').textContent=state.title;
  $('song-meta').textContent=`${state.tracks.length} pistes · ${state.regions.length} sections${state.dirty?' · Modifications non enregistrées':''}`;
  $('song-bpm').textContent=Math.round(state.bpm*10)/10;
  $('song-signature').textContent=`${state.numerator || 4}/${state.denominator || 4}`;
  $('song-bars').textContent=song.n_bars || (state.regions.length?Math.max(...state.regions.map(r=>r.last)):'—');
  $('song-duration').textContent=clock(state.length);
  $('project-path').textContent=state.project || 'Projet REAPER non enregistré';
  $('band-project').textContent=state.project || 'Enregistre le projet dans REAPER pour le retrouver dans BandPilot.';
  $('position').innerHTML=`${state.measure}<small> . ${state.beat}</small>`;
  $('transport-time').textContent=`${clock(state.position)} / ${clock(state.length)}`;
  const playingRegion=state.regions.find(r=>state.position>=r.start && state.position<r.finish);
  $('transport-section').textContent=playingRegion?.name || (state.recording?'Enregistrement':state.playing?'Lecture':'À l’arrêt');
  $('play').textContent=state.playing?'Ⅱ':'▶';
  for (const id of ['record','record-main']) {$(id).textContent=state.recording?'■ Arrêter la prise':'● Enregistrer';$(id).classList.toggle('active',state.recording);}
  if(document.activeElement!==$('speed')) $('speed').value=Math.round(state.rate*100);
  $('speed-value').textContent=`${Math.round(state.rate*100)} %`;
  $('work-bpm').textContent=Math.round(state.bpm*state.rate);
  renderRegions();renderFocus();renderTracks();renderRecording();diagnostics();
  const job=status.task, engine=status.job;
  $('job-status').textContent=job?.state==='running' ? `Traitement ${job.command} en cours…\n${engine?.message || engine?.stage || ''}` : job?.state==='error' ? 'Le traitement a échoué. Ouvre Historique pour consulter le diagnostic et reprendre.' : job?.state==='done' ? 'Traitement terminé.' : engine?.state==='running' ? `Traitement ReaCue en cours : ${engine.message || engine.stage || ''}` : 'Aucun traitement Desktop en cours.';
}
async function poll() {
  if(polling)return;polling=true;
  try {
    const next=await api('/api/status'); status=next; connected=!!next.connected;
    if(connected){
      const changed=state?.project_id!==next.reaper.project_id; state=next.reaper;
      if(changed){
        selected=null;song={};peaks=null;regionSignature=trackSignature=takesSignature=waveKey='';publicationAt=0;
        $('section-dialog').close();editing=null;
        all('iframe').forEach(f=>f.removeAttribute('src'));navigate(page);
      }
      if(!state.regions.some(r=>r.id===selected)) {selected=state.regions[0]?.id ?? null;const r=focusRegion();if(r){$('loop-first').value=r.first;$('loop-last').value=r.last;}}
      if(Date.now()-publicationAt>12000) void loadPublication(state.project_id);
    }
    render();
  } catch(error){connected=false;status.error=error.message;render();$('connection').textContent='● Service local indisponible';}
  finally{polling=false;}
}

document.addEventListener('click',guarded(async event=>{
  const el=event.target.closest('button');if(!el || el.disabled)return;
  const d=el.dataset;
  if(d.page) navigate(d.page);
  else if(d.tab) setTab(d.tab);
  else if(d.open) await api('/api/open',{target:d.open});
  else if(d.native){await native(d.native,d.action);message('Les outils ReaCue sont ouverts dans REAPER.',true);}
  else if(d.task) await task(d.task);
  else if(d.section) await chooseSection(+d.section);
  else if(d.bar) await control('seek',{bar:+d.bar});
  else if(d.listen) await control('listen',{mode:d.listen});
  else if(d.track) await control('track',{guid:d.track,field:d.field,value:d.value==='true'});
  else if(d.edit){const r=state.regions.find(r=>r.id===+d.edit);editing={id:r.id,project:state.project_id};$('section-name').value=r.name;$('section-first').value=r.first;$('section-last').value=r.last;$('section-dialog').showModal();}
  else if(d.regionOp){await control('region',{id:+d.id,operation:d.regionOp});publicationAt=0;message('Structure modifiée dans REAPER. Synchronise les prompteurs lorsque tes corrections sont terminées.',true);}
  else if(d.close) $(d.close).close();
  else if(d.project){await control('open_project',{path:d.project});navigate('practice');}
  else if(d.take) await control('seek',{position:+d.take});
}));
document.addEventListener('change',guarded(async event=>{
  const el=event.target;
  if(el.dataset.volume) {await control('track',{guid:el.dataset.volume,field:'volume',value:+el.value/100});el.blur();trackSignature='';}
  if(el.dataset.arm) await control('track',{guid:el.dataset.arm,field:'record',value:el.checked});
}));
document.addEventListener('input',event=>{if(event.target.dataset.volume){const value=+event.target.value/100;event.target.nextElementSibling.textContent=value>0?(20*Math.log10(value)).toFixed(1)+' dB':'−∞ dB';}});
$('speed').oninput=()=>{$('work-bpm').textContent=Math.round((state?.bpm || 0)*+$('speed').value/100);$('speed-value').textContent=$('speed').value+' %';};
$('speed').onchange=guarded(()=>control('rate',{rate:+$('speed').value/100}));
$('original-speed').onclick=guarded(()=>control('rate',{rate:1}));
$('loop-form').onsubmit=guarded(async event=>{event.preventDefault();await control('loop',loopBounds());});
$('loop-toggle').onclick=guarded(()=>control('loop',state.repeat_on?{enabled:false}:loopBounds()));
$('section-form').onsubmit=guarded(async event=>{event.preventDefault();if(editing?.project!==state.project_id)throw new Error('Le projet a changé.');await control('region',{id:editing.id,operation:'update',name:$('section-name').value.trim(),first:+$('section-first').value,last:+$('section-last').value});$('section-dialog').close();publicationAt=0;});
$('play').onclick=guarded(()=>control('transport',state.playing?{action:'pause'}:state.paused?{action:'play'}:{action:'play',start:state.position,count_in:+$('countin').value}));
$('stop').onclick=guarded(()=>control('transport',{action:'stop'}));
$('home').onclick=guarded(()=>control('seek',{position:focusRegion()?.start || 0}));
for(const id of ['record','record-main']) $(id).onclick=guarded(()=>control('transport',{action:state.recording?'stop':'record'}));
$('record-form').onsubmit=guarded(async event=>{event.preventDefault();if($('record-input').value==='')throw new Error('Configure le périphérique et ses entrées dans REAPER.');await control('record_track',{name:$('record-name').value.trim() || 'Batterie',input:+$('record-input').value});});
$('click-toggle').onclick=guarded(()=>{const t=state.tracks.find(t=>t.name==='CLICK');return control('track',{guid:t.guid,field:'mute',value:!t.mute});});
$('cue-toggle').onclick=guarded(async()=>{const tracks=state.tracks.filter(t=>['CUES','VOICE','VOIX'].includes(t.name));const mute=tracks.some(t=>!t.mute);for(const t of tracks)await control('track',{guid:t.guid,field:'mute',value:mute});});
$('pitch-down').onclick=guarded(()=>control('transpose',{delta:-1}));
$('pitch-up').onclick=guarded(()=>control('transpose',{delta:1}));
$('undo').onclick=guarded(()=>control('undo'));
$('redo').onclick=guarded(()=>control('redo'));
$('band-locate').onclick=guarded(()=>control('seek',{position:focusRegion()?.start || 0}));
$('library-search').oninput=renderLibrary;
$('library-full').onclick=()=>{$('library-frame').hidden=false;mountFrame('library-frame','biblio');};
$('wave-canvas').onclick=guarded(event=>{const r=focusRegion();if(!r)return;const rect=event.target.getBoundingClientRect();return control('seek',{position:r.start+(event.clientX-rect.left)/rect.width*(r.finish-r.start)});});
window.addEventListener('resize',drawWave);
document.addEventListener('keydown',event=>{if(page==='practice' && tab==='work' && event.code==='Space' && !event.repeat && !['INPUT','SELECT','TEXTAREA','BUTTON'].includes(event.target.tagName) && !$('section-dialog').open){event.preventDefault();if(connected)$('play').click();}});
const features=[
  ['Préparation & import','Fichier, stems, lien, tempo, grille, décompte, sections et reprise.','song'],
  ['Stems & modèles','Séparation, modèles installés, caches, récupération des traitements.','song'],
  ['Paroles & prompteurs','Paroles automatiques, calage mot par mot, rôles, PIN et QR.','stage'],
  ['Batterie & accords','Analyse, MIDI batterie, accords, grille et PDF.','song'],
  ['Répétition avancée','Boucles progressives, instruments joués, transposition et profils.','stage'],
  ['Concerts & setlists','Composition, préparation en lot, portabilité, sauvegarde et restauration.','concert'],
  ['Lumière & timecode','grandMA3, LTC/MTC, patch, séquences et exports.','lighting'],
  ['Réglages & diagnostic','Tous les réglages, options des modèles et vérification de l’installation.','settings']
];
$('feature-list').innerHTML=features.map(([name,description,target])=>`<div class="feature"><div><h3>${name}</h3><p>${description}</p></div><button class="button require" data-native="${target}">Ouvrir ↗</button></div>`).join('');
void poll(); setInterval(poll,750);
