'use strict';

// One coordinate system for the ruler, snapping, zoom and the listening window.
function musicalGrid(project) {
 const s={...guideDefaults,...project.settings},meter=s.beatsPerBar;
 const beats=(project.beats||[]).filter(Number.isFinite);
 const detected=s.gridMode==='detected'&&beats.length>1&&beats.every((t,i)=>!i||t>beats[i-1]);
 const period=60/pulseTempo(project);
 const nearest=detected?beats.reduce((best,t,i)=>Math.abs(t-s.firstBeat)<Math.abs(beats[best]-s.firstBeat)?i:best,0):0;
 const anchor=nearest%meter;
 function at(value) {
  if(!detected)return s.firstBeat+value*period;
  const index=value+anchor,i=Math.max(0,Math.min(beats.length-2,Math.floor(index)));
  return beats[i]+(index-i)*(beats[i+1]-beats[i]);
 }
 function coordinate(t) {
  if(!detected)return (t-s.firstBeat)/period;
  let lo=0,hi=beats.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(beats[mid]<=t)lo=mid+1;else hi=mid;}
  const i=Math.max(0,Math.min(beats.length-2,lo-1));
  return i-anchor+(t-beats[i])/(beats[i+1]-beats[i]);
 }
 const label=t=>{const c=coordinate(t),b=Math.floor((c+1e-7)/meter);return c<-.0001?'Levée':'Mesure '+(b+1)+' · temps '+(c-b*meter+1).toFixed(2).replace(/\.00$/,'');};
 return {meter,at,coordinate,label,snap:(t,unit)=>at(Math.round(coordinate(t)/unit)*unit)};
}

let editorSong='',editorFocus=null,editorPending=null,zoomStart=0,zoomSpan=0;
const zoomBar=node('div','editor-zoom');
zoomBar.title='Ctrl + molette (ou Cmd + molette) sur une piste : zoom autour du pointeur';
zoomBar.innerHTML='<strong>ÉCOUTER & AJUSTER</strong><button id="zoomAll">Tout</button><button id="zoomOut" aria-label="Dézoomer">−</button><button id="zoomIn" aria-label="Zoomer">＋</button><span id="zoomLabel"></span><label class="editor-follow"><input id="zoomFollow" type="checkbox" checked>Suivre la lecture</label><label>Calage <select id="markerSnap"><option value="bar">Mesure</option><option value="beat">Temps</option></select></label><input id="zoomPosition" type="range" min="0" max="1000" value="0" aria-label="Parcourir le morceau">';
document.querySelector('.workspace-grid').before(zoomBar);
zoomBar.append(node('small','','Ctrl / Cmd + molette sur les pistes pour zoomer'));
const gridSummary=node('p','grid-calibration');
gridSummary.id='gridCalibration';zoomBar.after(gridSummary);
const mixer=node('div','editor-mixer');
const mixerDefs=[['clickGain','Métronome','clickEnabled'],['callsGain','Appels','callsEnabled'],['cuesGain','Cues','speakCues'],['countGain','Décompte','regionCountEnabled']];
const previousGains={};
for(const [key,title] of mixerDefs){
 const group=node('div','editor-mix-channel'),label=node('label','',title),input=node('input'),output=node('output');
 input.type='range';input.min=0;input.max=1.5;input.step=.01;input.id='mix-'+key;input.setAttribute('aria-label','Volume '+title);output.id='mix-value-'+key;
 input.oninput=()=>{output.textContent=Math.round(input.value*100)+' %';};
 input.onchange=()=>send('guideMix',{key,value:Number(input.value)});
 const mute=button('Muet',()=>{const gain=Number(input.value);if(gain>0)previousGains[key]=gain;send('guideMix',{key,value:gain>0?0:previousGains[key]||.8});});
 mute.id='mute-'+key;mute.setAttribute('aria-label','Couper ou rétablir '+title);
 label.append(input);group.append(label,output,mute);mixer.append(group);
}
zoomBar.before(mixer);
const review=node('div','marker-review');
review.innerHTML='<div class="eyebrow">UN REPÈRE À LA FOIS</div><div class="marker-navigation"><button id="markerPrevious" aria-label="Repère précédent">←</button><select id="markerChoice" aria-label="Repère à vérifier"></select><button id="markerNext" aria-label="Repère suivant">→</button></div><button id="markerName" class="marker-name">Choisir un repère</button><p id="markerPosition"></p><span id="markerStatus" class="marker-status"></span><div class="marker-nudges"><button data-marker-step="-1" data-unit="bar">−1 mesure</button><button data-marker-step="1" data-unit="bar">+1 mesure</button><button data-marker-step="-1" data-unit="beat">−1 temps</button><button data-marker-step="1" data-unit="beat">+1 temps</button></div><button id="markerListen" class="wide">▶ Écouter autour</button><button id="markerValidate" class="primary wide">✓ Valider et suivant</button><p id="markerFeedback" role="status"></p><small id="markerProgress"></small><div class="divider"></div>';
document.querySelector('.inspector').prepend(review);

function reviewMarkers(){return [...state.project.sections.map(item=>({kind:'section',item,time:item.start})),...state.project.cues.map(item=>({kind:'cue',item,time:item.time}))].sort((a,b)=>a.time-b.time||a.kind.localeCompare(b.kind));}
function focusMarker(){return reviewMarkers().find(m=>m.item.id===editorFocus?.id&&m.kind===editorFocus?.kind);}
function chooseMarker(kind,id,seek=true){
 editorFocus={kind,id};const marker=focusMarker();if(!marker)return;
 if(kind==='section')displaySection(marker.item);
 if(zoomSpan<state.duration&&(marker.time<zoomStart||marker.time>zoomStart+zoomSpan))zoomStart=Math.max(0,Math.min(state.duration-zoomSpan,marker.time-zoomSpan/3));
 $('markerFeedback').textContent='';renderManualEditor();renderSections();drawWaves();
 if(seek)send('seek',{time:marker.time});
}
function moveMarker(marker,t){
 if(!marker||state.busy||editorPending)return;
 const previous=marker.kind==='section'?state.project.sections.filter(s=>s.start<marker.item.start).at(-1):null;
 if(!Number.isFinite(t)||t<0||t>state.duration||(marker.kind==='section'&&(t>=marker.item.end-.01||(previous&&t<=previous.start+.01)))){
  $('markerFeedback').textContent='Cette position dépasse les limites du passage.';return;
 }
 editorPending={kind:marker.kind,id:marker.item.id,time:t};
 send('moveMarker',{kind:marker.kind,id:marker.item.id,time:t});renderManualEditor();
}
function navigateMarker(delta){const rows=reviewMarkers(),i=rows.findIndex(m=>m.kind===editorFocus?.kind&&m.item.id===editorFocus?.id),m=rows[Math.max(0,Math.min(rows.length-1,i+delta))];if(m)chooseMarker(m.kind,m.item.id);}
$('markerPrevious').onclick=()=>navigateMarker(-1);$('markerNext').onclick=()=>navigateMarker(1);
$('markerChoice').onchange=()=>{const marker=reviewMarkers()[Number($('markerChoice').value)];if(marker)chooseMarker(marker.kind,marker.item.id);};
$('markerName').onclick=()=>{const marker=focusMarker();if(marker)openEditor(marker.kind,marker.item);};
document.querySelectorAll('[data-marker-step]').forEach(b=>b.onclick=()=>{const m=focusMarker(),g=musicalGrid(state.project),unit=b.dataset.unit==='bar'?g.meter:1;if(m)moveMarker(m,g.at((Math.round(g.coordinate(m.time)/unit)+Number(b.dataset.markerStep))*unit));});
$('markerListen').onclick=()=>{
 const m=focusMarker();if(!m)return;const g=musicalGrid(state.project),c=g.coordinate(m.time),s={...guideDefaults,...state.project.settings};
 const start=Math.max(0,g.at(c-Math.max(2*g.meter,s.leadBeats+g.meter))),end=Math.min(state.duration,g.at(c+g.meter));
 if(end-start>.05)send('audition',{start,end});
};
$('markerValidate').onclick=()=>{const m=focusMarker();if(!m||editorPending)return;editorPending={kind:m.kind,id:m.item.id,review:true};send('reviewMarker',{kind:m.kind,id:m.item.id});renderManualEditor();};

function viewport(){const total=Math.max(.001,state.duration);if(!zoomSpan)zoomSpan=total;zoomSpan=Math.min(total,zoomSpan);zoomStart=Math.max(0,Math.min(total-zoomSpan,zoomStart));return {start:zoomStart,end:zoomStart+zoomSpan,span:zoomSpan};}
let zoomFrame=0;
function setZoom(factor,anchor=null){
 const v=viewport(),center=anchor?.time??Math.max(v.start,Math.min(v.end,focusMarker()?.time??transport.position??v.start)),span=Math.max(Math.min(2,state.duration),Math.min(state.duration,v.span*factor));
 zoomStart=center-span*(anchor?.ratio??.5);zoomSpan=span;viewport();
 if(anchor){if(!zoomFrame)zoomFrame=requestAnimationFrame(()=>{zoomFrame=0;redrawTimeline();});}
 else redrawTimeline();
}
document.querySelector('.arrangement').addEventListener('wheel',e=>{
 if(!(e.ctrlKey||e.metaKey)||!state.loaded||state.busy||state.duration<=0||document.querySelector('dialog[open]'))return;
 const lane=e.target.closest('.track-wave,.timeline');if(!lane)return;
 const box=lane.getBoundingClientRect();if(box.width<=0)return;
 const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?box.height:1);
 if(!Number.isFinite(delta)||delta===0)return;
 e.preventDefault();
 const v=viewport(),ratio=Math.max(0,Math.min(1,(e.clientX-box.left)/box.width));
 $('zoomFollow').checked=false;
 setZoom(Math.exp(Math.max(-1,Math.min(1,delta*.003))),{time:v.start+ratio*v.span,ratio});
},{passive:false});
$('zoomAll').onclick=()=>{zoomStart=0;zoomSpan=state.duration;redrawTimeline();};
$('zoomIn').onclick=()=>setZoom(.5);$('zoomOut').onclick=()=>setZoom(2);
$('zoomPosition').oninput=()=>{zoomStart=Number($('zoomPosition').value)/1000*Math.max(0,state.duration-zoomSpan);redrawTimeline();};
function redrawTimeline(){viewport();renderSections();drawWaves();renderTransport();renderManualEditor();}

function renderManualEditor(){
 gridSummary.textContent=state.project.gridLocked?'Calage manuel protégé':state.project.analysisNote||'';
 gridSummary.classList.toggle('needs-review',!state.project.gridLocked&&/à vérifier|incertain|non confirmées/i.test(gridSummary.textContent));
 gridSummary.hidden=!state.loaded||!gridSummary.textContent;
 if(editorSong!==state.project.id){editorSong=state.project.id;editorFocus=null;editorPending=null;zoomStart=0;zoomSpan=state.duration;}
 const markers=reviewMarkers();if(!focusMarker()&&markers.length)editorFocus={kind:markers[0].kind,id:markers[0].item.id};
 const current=focusMarker(),index=markers.findIndex(m=>m===undefined?false:m.kind===editorFocus?.kind&&m.item.id===editorFocus?.id),g=musicalGrid(state.project);
 const choices=markers.map((m,i)=>{const o=node('option','',(i+1)+'. '+m.item.name);o.value=i;return o;});$('markerChoice').replaceChildren(...choices);$('markerChoice').value=index;
 $('markerName').textContent=current?.item.name||'Ajoute une section ou un cue';
 $('markerPosition').textContent=current?g.label(current.time)+' · '+time(current.time,true):'';
 $('markerStatus').textContent=current?.item.reviewed?'✓ Validé':'À vérifier';$('markerStatus').classList.toggle('validated',!!current?.item.reviewed);
 $('markerProgress').textContent=markers.filter(m=>m.item.reviewed).length+' / '+markers.length+' repères validés';
 review.querySelectorAll('button,select').forEach(b=>b.disabled=!current||state.busy||!!editorPending);
 const s={...guideDefaults,...state.project.settings};
 for(const [key,,enabled] of mixerDefs){const input=$('mix-'+key),gain=s[key]??s.callsGain;if(document.activeElement!==input)input.value=gain;$('mix-value-'+key).textContent=s[enabled]===false?'Désactivé':Math.round(gain*100)+' %';input.disabled=!state.loaded||state.busy;$('mute-'+key).disabled=input.disabled;$('mute-'+key).setAttribute('aria-pressed',String(gain===0));}
 const v=viewport();$('zoomLabel').textContent=time(v.start)+' – '+time(v.end);$('zoomPosition').value=state.duration>v.span?1000*v.start/(state.duration-v.span):0;
 zoomBar.querySelectorAll('button,input,select').forEach(b=>b.disabled=!state.loaded||state.busy);
 $('zoomPosition').disabled=!state.loaded||v.span>=state.duration||state.busy;
}

function attachMarkerDrag(button,marker){
 button.onpointerdown=e=>{
  if(e.button!==0||state.busy||editorPending)return;
  const rect=button.parentElement.getBoundingClientRect(),v=viewport(),down=e.clientX,original=marker.time;
  let moved=false,target=original;button.setPointerCapture(e.pointerId);
  button.onpointermove=ev=>{if(Math.abs(ev.clientX-down)<4&&!moved)return;moved=true;const g=musicalGrid(state.project),unit=$('markerSnap').value==='bar'?g.meter:1;target=g.snap(original+(ev.clientX-down)/rect.width*v.span,unit);button.style.left=((target-v.start)/v.span*100)+'%';$('markerFeedback').textContent=g.label(target);};
  button.onpointerup=ev=>{button.onpointermove=null;button.onpointerup=null;button.releasePointerCapture(ev.pointerId);if(moved){button.onclick=ev=>ev.preventDefault();editorFocus={kind:marker.kind,id:marker.item.id};moveMarker(marker,target);renderSections();}};
  button.onpointercancel=()=>{button.onpointermove=null;button.onpointerup=null;renderSections();};
 };
}

renderSections=function(){
 const v=viewport(),g=musicalGrid(state.project);$('sections').replaceChildren();$('cues').replaceChildren();$('cueList').replaceChildren();$('ruler').replaceChildren();
 for(const m of reviewMarkers()){
  const item=m.item;if(m.kind==='section'&&item.end>v.start&&item.start<v.end){
   const b=button((item.reviewed?'✓ ':'')+item.name,()=>{selectSection(item);chooseMarker('section',item.id,false);},'section'+(editorFocus?.id===item.id?' selected':''));b.dataset.id=item.id;
   b.style.left=((Math.max(v.start,item.start)-v.start)/v.span*100)+'%';b.style.width=((Math.min(v.end,item.end)-Math.max(v.start,item.start))/v.span*100)+'%';b.title=item.name+' · '+g.label(item.start)+' · glisser pour déplacer le début';b.ondblclick=()=>openEditor('section',item);attachMarkerDrag(b,m);$('sections').append(b);
  }else if(m.kind==='cue'){
   if(item.time>=v.start&&item.time<=v.end){const pin=button((item.reviewed?'✓ ':'')+item.name,()=>chooseMarker('cue',item.id),'cue-pin');pin.dataset.id=item.id;pin.style.left=((item.time-v.start)/v.span*100)+'%';pin.title=g.label(item.time);pin.ondblclick=()=>openEditor('cue',item);attachMarkerDrag(pin,m);$('cues').append(pin);}
   const row=node('div','cue-row');row.append(button((item.reviewed?'✓ ':'')+item.name,()=>chooseMarker('cue',item.id)),button('✎',()=>openEditor('cue',item)));$('cueList').append(row);
  }
 }
 if(!state.project.cues.length)$('cueList').append(node('small','','Ajoute un fill, un arrêt ou une reprise.'));
 const startBar=Math.ceil(g.coordinate(v.start)/g.meter),endBar=Math.floor(g.coordinate(v.end)/g.meter),step=Math.max(1,Math.ceil((endBar-startBar)/10));
 for(let b=startBar;b<=endBar;b+=step){const mark=node('span','ruler-mark',b<0?'Levée':'M'+(b+1));mark.style.left=((g.at(b*g.meter)-v.start)/v.span*100)+'%';$('ruler').append(mark);}
};
drawWaves=function(){
 const v=viewport(),g=musicalGrid(state.project);
 document.querySelectorAll('canvas[data-track]').forEach(canvas=>{
  const t=state.project.tracks.find(t=>t.id===canvas.dataset.track);if(!t)return;
  const width=canvas.clientWidth,height=100,scale=window.devicePixelRatio||1;canvas.width=width*scale;canvas.height=height*scale;
  const ctx=canvas.getContext('2d');ctx.scale(scale,scale);ctx.clearRect(0,0,width,height);
  const first=Math.ceil(g.coordinate(v.start)),last=Math.floor(g.coordinate(v.end)),stride=Math.max(1,Math.ceil((last-first)/400));
  for(let beat=first;beat<=last;beat+=stride){const bar=beat%g.meter===0;if(!bar&&(last-first)>80)continue;const x=(g.at(beat)-v.start)/v.span*width;ctx.strokeStyle=bar?'#64718c66':'#64718c22';ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}
  const samples=t.peaks||[];ctx.strokeStyle=colors[t.role]||colors.other;ctx.globalAlpha=.82;ctx.beginPath();
  for(let x=0;x<width;x+=2){const a=Math.floor((v.start+x/width*v.span-t.offset)/t.duration*samples.length),b=Math.ceil((v.start+(x+2)/width*v.span-t.offset)/t.duration*samples.length);let peak=0;for(let i=Math.max(0,a);i<Math.min(samples.length,b);i++)peak=Math.max(peak,samples[i]);const amp=Math.min(1,peak)*39;ctx.moveTo(x,50-amp);ctx.lineTo(x,50+amp);}ctx.stroke();
  canvas.parentElement.onclick=e=>{const r=canvas.parentElement.getBoundingClientRect();send('seek',{time:Math.max(0,Math.min(state.duration,v.start+(e.clientX-r.left)/r.width*v.span))});};
 });
};
const editorTransport=renderTransport;
renderTransport=function(){
 editorTransport();let v=viewport();
 if(transport.playing&&$('zoomFollow').checked&&v.span<state.duration&&(transport.position>v.end||transport.position<v.start)){
  zoomStart=transport.position-v.span*.2;v=viewport();renderSections();drawWaves();renderManualEditor();
 }
 document.querySelectorAll('.playhead').forEach(e=>{e.style.left=((transport.position-v.start)/v.span*100)+'%';e.hidden=transport.position<v.start||transport.position>v.end;});
 document.querySelectorAll('.loop-shade').forEach(e=>{const a=Math.max(v.start,transport.loopStart||0),b=Math.min(v.end,transport.loopEnd||0);e.hidden=!transport.loop||b<=a;e.style.left=((a-v.start)/v.span*100)+'%';e.style.width=(Math.max(0,b-a)/v.span*100)+'%';});
};
const editorReceive=window.studioReceive;
window.studioReceive=function(data){
 if(data.type==='state'&&data.project.id!==editorSong){zoomSpan=data.duration;zoomStart=0;}
 editorReceive(data);
 if(data.type==='state'){
  const pending=editorPending;editorPending=null;renderManualEditor();
  if(pending?.review&&data.project.id===editorSong){const markers=reviewMarkers(),done=markers.find(m=>m.kind===pending.kind&&m.item.id===pending.id);if(done?.item.reviewed){const index=markers.indexOf(done),next=[...markers.slice(index+1),...markers.slice(0,index)].find(m=>!m.item.reviewed);if(next)chooseMarker(next.kind,next.item.id);else $('markerFeedback').textContent='Tous les repères sont validés.';}}
 }
};
renderManualEditor();
