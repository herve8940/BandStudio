'use strict';
let captureDirty=false,captureProject='';
const control=(action,args={})=>send('studioControl',{action,...args});
function captureInputs(settings){
 const device=state.capture?.devices?.find(d=>d.uid===$('captureDevice').value);$('captureChannels').replaceChildren();
 for(let input=1;input<=Math.min(32,device?.channels||0);input++){
  const saved=settings.channels?.find(c=>c.input===input),row=node('label','capture-channel'),check=node('input'),name=node('input');
  check.type='checkbox';check.checked=!!saved;check.dataset.input=input;check.setAttribute('aria-label','Armer entrée '+input);
  name.value=saved?.name||'Entrée '+input;name.maxLength=120;name.setAttribute('aria-label','Nom entrée '+input);
  row.append(check,node('span','','USB '+input),name);$('captureChannels').append(row);
 }
}
function captureRender(){
 const available=!!state.capture;$('captureForm').hidden=!available;
 $('enableBridge').disabled=!available;$('createSession').disabled=!available||state.busy||transport.recording;
 if(!available){$('captureSummary').textContent='Le nouvel enregistreur nécessite BandStudio 0.5.';return;}
 const s=state.capture.settings||{};
 if(captureProject!==state.project.id){captureProject=state.project.id;captureDirty=false;}
 if(!captureDirty){
  $('captureDevice').replaceChildren();for(const d of state.capture.devices){const o=node('option','',d.name+' · '+d.channels+' entrées · '+Math.round(d.rate)+' Hz');o.value=d.uid;$('captureDevice').append(o);}
  if(s.deviceUID)$('captureDevice').value=s.deviceUID;
  captureInputs(s);$('captureMode').value=s.mode||'overdub';$('captureLatency').value=s.latencyMS||0;$('punchStart').value=s.punchStart||0;$('punchEnd').value=s.punchEnd||0;$('capturePreRoll').value=s.preRoll??2;
 }
 $('enableBridge').checked=!!state.bridgeEnabled;$('bridgeStatus').textContent=state.bridgeEnabled?'Connexion active · BandPilot → Enregistrement → BandStudio':'Connexion désactivée';
 $('captureSummary').textContent=(s.channels||[]).length+' entrées armées · '+({live:'répétition entière',overdub:'prise sur le morceau',punch:'prise limitée à une plage'}[s.mode]||'');
 $('generateForm').querySelector('button').disabled=!state.loaded||state.busy;$('splitVocals').disabled=!state.loaded||state.busy||!state.project.tracks.some(t=>t.role==='vocals');
 captureTransport();
}
function captureTransport(){
 $('captureElapsed').textContent=time(transport.captureElapsed||0,true);
 $('captureStart').disabled=!state.loaded||!state.capture||state.busy||captureDirty||transport.recording||state.capture?.pending||!(state.capture?.settings.channels||[]).length;
 $('captureStop').disabled=!transport.recording&&!state.capture?.pending&&!state.busy;$('captureMarker').disabled=!state.loaded||state.busy;
 $('captureForm').querySelectorAll('input,select,button').forEach(e=>e.disabled=!!transport.recording||!!state.capture?.pending);
 $('captureMeters').replaceChildren();(state.capture?.settings.channels||[]).forEach((c,i)=>{const row=node('div','capture-meter'),meter=node('meter');meter.min=0;meter.max=1;meter.high=.9;meter.optimum=.3;meter.value=transport.meters?.[i]||0;row.append(node('span','',c.name),meter);$('captureMeters').append(row);});
}
$('captureForm').oninput=()=>{captureDirty=true;captureTransport();};
$('captureDevice').onchange=()=>{captureDirty=true;captureInputs({channels:[]});};
$('captureForm').onsubmit=e=>{e.preventDefault();const channels=[...$('captureChannels').children].filter(row=>row.querySelector('[type=checkbox]').checked).map(row=>({input:Number(row.querySelector('[data-input]').dataset.input),name:row.querySelector('input:not([type=checkbox])').value.trim()}));captureDirty=false;send('captureSettings',{deviceUID:$('captureDevice').value,channels,mode:$('captureMode').value,latencyMS:Number($('captureLatency').value),punchStart:Number($('punchStart').value),punchEnd:Number($('punchEnd').value),preRoll:Number($('capturePreRoll').value)});};
$('refreshDevices').onclick=()=>{captureDirty=false;send('ready');};
$('punchSelection').onclick=()=>{$('punchStart').value=$('loopStart').value;$('punchEnd').value=$('loopEnd').value;$('captureMode').value='punch';captureDirty=true;};
$('createSession').onclick=()=>send('newSession',{name:$('sessionName').value});
$('enableBridge').onchange=()=>send('bridge',{on:$('enableBridge').checked});
$('captureStart').onclick=()=>control('record');$('captureStop').onclick=()=>control('stop');$('captureMarker').onclick=()=>control('marker');
const captureFeatures=renderFeatures;renderFeatures=function(){captureFeatures();captureRender();};
const captureTransportBefore=renderTransport;renderTransport=function(){captureTransportBefore();captureTransport();};
const nav=node('div','navigation-tools');
for(const [action,label] of [['start','|◀ Début'],['previous','◀ Repère'],['back','−1 mesure'],['forward','+1 mesure'],['next','Repère ▶'],['end','Fin ▶|']])nav.append(button(label,()=>control(action)));
const seek=node('input');seek.type='number';seek.min=0;seek.step=.001;seek.placeholder='Secondes';seek.setAttribute('aria-label','Aller à la position en secondes');nav.append(seek,button('Aller à',()=>control('seek',{time:Number(seek.value)})));
$('workspace').prepend(nav);
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey||e.altKey)return;
 const action={Home:'start',End:'end',ArrowLeft:e.shiftKey?'previous':'back',ArrowRight:e.shiftKey?'next':'forward',KeyM:'marker'}[e.code];if(action){e.preventDefault();control(action);}
});
