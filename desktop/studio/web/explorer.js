'use strict';

(() => {
 const overview=$('workspaceOverview'), container=overview.closest('.workspace-overview');
 const rail=node('div','explore-rail'), frame=node('div','explore-frame'), head=node('i','explore-head');
 function grips(box){
  for(const side of ['start','end']){
   const grip=node('i','explore-grip');grip.dataset.edge=side;box.append(grip);
  }
 }
 grips(frame);rail.append(frame,head);container.append(rail);
 rail.title=uiText('Déplacer ce cadre pour parcourir le morceau');rail.tabIndex=0;rail.setAttribute('role','slider');rail.setAttribute('aria-label',uiText('Parcourir le morceau'));
 const controls=node('div','explore-nav');
 controls.innerHTML=uiMarkup('<button id="exBack">Vue précédente</button><button id="exFollow">Revenir à la lecture</button><output id="exPosition"></output>');
 const panel=node('details','explore-panel');panel.id='explorer';
 panel.innerHTML=uiMarkup(`<summary>Explorer le morceau</summary>
 <div class="explore-row"><label>Aller à <input id="exQuery" type="search" placeholder="1:42, M37 ou refrain"></label><button id="exGo">Chercher</button></div><div class="explore-row explore-results" id="exResults" aria-live="polite"></div>
 <div class="explore-row"><label>Déplacer la vue <select id="exStep"><option value="beat">1 temps</option><option value="bar" selected>1 mesure</option><option value="page">1 écran</option></select></label><button id="exPrev" aria-label="Vue vers la gauche">←</button><button id="exNext" aria-label="Vue vers la droite">→</button>
 <label>Cadrage <select id="exSize"><option value="1">1 mesure</option><option value="4" selected>4 mesures</option><option value="8">8 mesures</option></select></label><button id="exFitBars">Cadrer</button></div>
 <fieldset><legend>Passage A–B</legend><div class="explore-row"><label>A (s) <input type="number" id="exA" step="0.001" min="0"></label><label>B (s) <input type="number" id="exB" step="0.001" min="0"></label><button id="exSection">Prendre la section</button><button id="exFit">Cadrer A–B</button></div>
 <div class="explore-row"><label>Élan <select id="exLead"><option value="0">Aucun</option><option value="1">1 mesure</option><option value="2">2 mesures</option></select></label><button id="exListen">Écouter une fois</button><button id="exReplay">Rejouer</button><button id="exLoop">Boucler A–B</button></div></fieldset>
 <div class="explore-row"><label>Signet <select id="exBookmark"><option>1</option><option>2</option></select></label><button id="exMark">Mémoriser la vue</button><button id="exRecall">Rappeler le signet</button></div>
 <fieldset id="exAdapt" hidden><legend>Adapter le passage</legend><div class="explore-row"><label>Mesures entre A et B <input type="number" id="exBars" min="1" max="256" value="1"></label><label>Temps par mesure <input type="number" id="exMeter" min="1" max="12" value="4"></label><button id="exGrid">Recaler la grille A–B</button></div>
 <div class="explore-row"><label>Variante <select id="exEdit"><option value="cut">Couper A–B</option><option value="repeat">Répéter A–B</option></select></label><button id="exJoin">Écouter la jonction</button><button id="exVariant">Créer une variante du morceau</button></div></fieldset>
 <small id="exStatus" role="status"></small>`);
 container.after(controls,panel);
 const rangeRow=node('div','timeline-head'), range=node('div','explore-range'), highlight=node('div','explore-highlight');
 rangeRow.append(node('div','track-label',uiText('Passage A–B')),range);range.id='exRange';range.title=uiText('Glisser pour sélectionner un passage');grips(highlight);range.append(highlight);
 $('ruler').closest('.timeline-head').after(rangeRow);
 const openExplorer=button(uiText('Explorer'),()=>{
  window.openStudioEditor('tracks');panel.open=true;panel.scrollIntoView({block:'center'});
 });
 openExplorer.id='openExplorer';$('play').after(openExplorer);
 $('ruler').title=uiText('Un clic place la tête de lecture');
 const follow=$('zoomFollow'), status=$('exStatus');
 let owner=null,passage=null,replay=null,history=[],bookmarks=[],drag=null,paint=0,wheelTime=-Infinity;
 let grid=null,gridProject=null;
 function clock(){if(gridProject!==state.project){gridProject=state.project;grid=musicalGrid(gridProject);}return grid;}
 function enabled(){return state.loaded&&!state.busy&&state.duration>0;}
 const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
 function remember(v=viewport()){
  const previous=history.at(-1);
  if(!previous||Math.abs(previous.start-v.start)>.001||Math.abs(previous.span-v.span)>.001){
   history.push({start:v.start,span:v.span});if(history.length>40)history.shift();
  }
 }
 function change(start,span,record=true){
  if(!enabled())return;
  if(record)remember();follow.checked=false;
  zoomSpan=clamp(span,Math.min(.05,state.duration),state.duration);
  zoomStart=clamp(start,0,state.duration-zoomSpan);
  if(!paint)paint=requestAnimationFrame(()=>{paint=0;redrawTimeline();});
  draw();
 }
 function locate(t){
  const v=viewport();change(t-v.span/2,v.span);
 }
 function step(direction){
  const v=viewport(),g=clock(),unit=$('exStep').value,beats=unit==='bar'?g.meterAt(v.start):1;
  change(unit==='page'?v.start+direction*v.span:g.at(g.coordinate(v.start)+direction*beats),v.span);
 }
 function returnToPlay(){
  if(!enabled())return;
  const v=viewport();change((transport.position||0)-v.span*.25,v.span);follow.checked=true;draw();
 }
 function setRange(start,end){
  if(!Number.isFinite(start)||!Number.isFinite(end)||end-start<.05||start<0||end>state.duration)return false;
  passage={start,end};status.textContent='';
  $('exA').value=start.toFixed(3);$('exB').value=end.toFixed(3);draw();return true;
 }
 function draw(full=true){
  const loaded=enabled();openExplorer.disabled=!loaded;controls.hidden=panel.hidden=rangeRow.hidden=rail.hidden=!state.loaded;
  if(!state.loaded)return;
  const v=viewport(),duration=Math.max(.001,state.duration),position=transport.position||0;
  frame.style.left=v.start/duration*100+'%';frame.style.width=v.span/duration*100+'%';head.style.left=clamp(position/duration*100,0,99.9)+'%';
  rail.setAttribute('aria-valuemin','0');rail.setAttribute('aria-valuemax',String(duration-v.span));rail.setAttribute('aria-valuenow',String(v.start));rail.setAttribute('aria-valuetext',time(v.start)+' – '+time(v.end));
  const cropped=passage&&passage.end>v.start&&passage.start<v.end;
  highlight.hidden=!cropped;
  if(cropped){const a=clamp((passage.start-v.start)/v.span,0,1),b=clamp((passage.end-v.start)/v.span,0,1);highlight.style.left=a*100+'%';highlight.style.width=(b-a)*100+'%';highlight.firstChild.hidden=passage.start<v.start;highlight.lastChild.hidden=passage.end>v.end;}
  $('exBack').disabled=!loaded||!history.length;$('exFollow').disabled=!loaded;
  $('exFollow').textContent=(position<v.start?'← ':position>v.end?'→ ':'')+uiText('Revenir à la lecture');
  $('exPosition').textContent=time(position)+' · '+clock().label(position);
  const looping=!!passage&&transport.loop&&Math.abs(transport.loopStart-passage.start)<.001&&Math.abs(transport.loopEnd-passage.end)<.001;
  $('exLoop').setAttribute('aria-pressed',String(!!looping));$('exLoop').classList.toggle('active',!!looping);
  if(!full)return;
  for(const e of panel.querySelectorAll('input,select,button'))e.disabled=!loaded;
  for(const id of ['exListen','exLoop','exFit','exVariant','exJoin','exGrid'])$(id).disabled=!loaded||!passage;
  $('exRecall').disabled=!loaded||!bookmarks[Number($('exBookmark').value)];
  $('exReplay').disabled=!loaded||!replay;
  $('exSection').disabled=!loaded||!state.project.sections.some(s=>s.id===selected||s.start<=position&&position<s.end);
  $('exAdapt').hidden=!state.exploreAdaptation;
  if(transport.recording||guideDirty||$('notes').value!==(state.project.notes||'')){
   for(const id of ['exGrid','exVariant','exJoin','exListen','exLoop','exReplay'])$(id).disabled=true;
  }
 }
 function fraction(e,el){const box=el.getBoundingClientRect();return clamp((e.clientX-box.left)/Math.max(1,box.width),0,1);}
 function begin(e,el,kind){
  if(!enabled()||e.button!==0||drag)return;
  if(el===overview&&!e.target.closest('.overview-window'))return;
  const v=viewport(),ratio=fraction(e,el),edge=e.target.dataset.edge;
  let mode=edge||(kind==='range'?(e.target.closest('.explore-highlight')?'move':'new'):(el===overview||e.target.closest('.explore-frame')?'move':'jump'));
  drag={el,kind,mode,v,ratio,initial:passage&&{...passage},x:e.clientX,id:e.pointerId};
  el.setPointerCapture(e.pointerId);e.preventDefault();
  if(kind==='view'&&el!==overview){remember();if(mode==='jump'){locateAtPointer(e);drag.mode='move';drag.v=viewport();}else follow.checked=false;}
 }
 function locateAtPointer(e){const v=drag.v;change(fraction(e,drag.el)*state.duration-v.span/2,v.span,false);}
 function snap(t){const mode=$('markerSnap').value,g=clock();return clamp(mode==='free'?t:mode==='bar'?g.nearestBar(t):g.snap(t,1),0,state.duration);}
 function motion(e){
  if(!drag||drag.id!==e.pointerId)return;
  const {el,kind,mode,v,ratio,initial}=drag,r=fraction(e,el);
  if(kind==='view'){
   if(el===overview&&!drag.moved){
    if(Math.abs(e.clientX-drag.x)<4)return;
    remember();drag.moved=true;
   }
   const delta=(r-ratio)*state.duration,min=Math.min(.05,state.duration);
   if(mode==='start'){const a=clamp(v.start+delta,0,v.end-min);change(a,v.end-a,false);}
   else if(mode==='end')change(v.start,clamp(v.end+delta,v.start+min,state.duration)-v.start,false);
   else change(v.start+delta,v.span,false);
  }else{
   const t=snap(v.start+r*v.span);
   if(mode==='move'){const a=clamp(snap(initial.start+(r-ratio)*v.span),0,state.duration-(initial.end-initial.start));setRange(a,a+(initial.end-initial.start));}
   else if(mode==='start')setRange(t,initial.end);
   else if(mode==='end')setRange(initial.start,t);
   else{const anchor=snap(v.start+ratio*v.span);setRange(Math.min(t,anchor),Math.max(t,anchor));}
  }
 }
 function finish(e){
  if(!drag||drag.id!==e.pointerId)return;
  if(e.type==='pointerup'&&Math.abs(e.clientX-drag.x)>1)motion(e);
  if(drag.el===overview&&!drag.moved&&e.type==='pointerup'){
   document.elementsFromPoint(e.clientX,e.clientY).find(el=>el.classList.contains('overview-section'))?.click();
  }
  if(drag.kind==='range'&&e.type==='pointerup')panel.open=true;
  drag=null;draw();
 }
 for(const [el,kind] of [[overview,'view'],[rail,'view'],[range,'range']]){
  el.addEventListener('pointerdown',e=>begin(e,el,kind));
  el.addEventListener('pointermove',motion);el.addEventListener('pointerup',finish);el.addEventListener('lostpointercapture',finish);
 }
 rail.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();step(e.key==='ArrowLeft'?-1:1);}};
 const wheelTarget=document.querySelector('.arrangement');
 wheelTarget.addEventListener('wheel',e=>{
  if(!enabled()||!e.target.closest('.track-wave,.timeline,.explore-rail,.explore-range')||document.querySelector('dialog[open]'))return;
  const zoom=e.ctrlKey||e.metaKey,delta=e.shiftKey?(e.deltaX||e.deltaY):Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:0;
  if(!zoom&&!delta)return;
  const v=viewport();if(!zoom&&v.span>=state.duration)return;
  if(performance.now()-wheelTime>350)remember();wheelTime=performance.now();
  if(zoom)return;
  e.preventDefault();
  const pixels=delta*(e.deltaMode===1?16:e.deltaMode===2?range.clientWidth:1);
  change(v.start+pixels*v.span/Math.max(1,range.clientWidth),v.span,false);
 },{passive:false,capture:true});
 $('ruler').addEventListener('click',e=>{if(enabled()){const v=viewport();seekInTimeline(v.start+fraction(e,$('ruler'))*v.span);}});
 for(const id of ['zoomAll','zoomIn','zoomOut','zoomSelection'])$(id).addEventListener('click',()=>{if(enabled()){remember();follow.checked=false;}},true);
 $('zoomPosition').addEventListener('pointerdown',()=>remember());
 $('exBack').onclick=()=>{const last=history.pop();if(last)change(last.start,last.span,false);};
 $('exFollow').onclick=returnToPlay;follow.addEventListener('change',()=>{if(follow.checked)returnToPlay();});
 $('exPrev').onclick=()=>step(-1);$('exNext').onclick=()=>step(1);
 $('exFitBars').onclick=()=>{const g=clock(),v=viewport(),t=follow.checked?transport.position||0:v.start+v.span/2,bar=g.barNumber(t),a=g.barAt(bar),b=g.barAt(bar+Number($('exSize').value));change(a,b-a);};
 function search(){
  const out=$('exResults'),q=$('exQuery').value.trim().toLocaleLowerCase(),g=clock();out.replaceChildren();if(!q)return;
  const bar=/^(?:m(?:esure)?|bar)\s*(\d+)(?:[.,](\d+))?$/i.exec(q),stamp=/^(?:(\d+):([0-5]\d)|([0-9]+))(?:[.,](\d+))?$/.exec(q);
  let t;
  if(bar&&Number(bar[1])>=1){const a=g.barAt(Number(bar[1])-1),beat=Number(bar[2]||1);if(beat>=1&&beat<=g.meterAt(a))t=g.at(g.coordinate(a)+beat-1);}
  else if(stamp)t=Number(stamp[1]||0)*60+Number(stamp[2]||stamp[3])+Number('0.'+(stamp[4]||0));
  if(Number.isFinite(t)&&t>=0&&t<=state.duration){locate(t);out.textContent=time(t,true)+' · '+g.label(t);return;}
  const markers=reviewMarkers().filter(m=>m.item.name.toLocaleLowerCase().includes(q));
  for(const m of markers)out.append(button(m.item.name+' · '+time(m.time),()=>locate(m.time)));
  if(!markers.length)out.textContent=uiText('Aucun passage trouvé.');
 }
 $('exGo').onclick=search;$('exQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search();}};
 $('exSection').onclick=()=>{const s=state.project.sections.find(s=>s.id===selected)||state.project.sections.find(s=>s.start<=transport.position&&transport.position<s.end);if(s)setRange(s.start,s.end);};
 for(const id of ['exA','exB'])$(id).onchange=()=>{
  if(!setRange($('exA').valueAsNumber,$('exB').valueAsNumber)){
   passage=null;status.textContent=uiText('Place A avant B, à au moins 50 ms, dans le morceau.');draw();
  }
 };
 $('exFit').onclick=()=>change(passage.start,passage.end-passage.start);
 function listenOnce(clip){
  if(state.exploreAdaptation){studioAudition.stop();send('auditionOnce',clip);}
  else studioAudition.play(clip);
 }
 $('exListen').onclick=()=>{const g=clock(),a=passage.start;replay={start:Math.max(0,g.barOffset(a,-Number($('exLead').value))),end:passage.end};listenOnce(replay);draw();};
 $('exReplay').onclick=()=>{if(replay)listenOnce(replay);};
 $('exLoop').onclick=()=>{
  studioAudition.stop();
  if(transport.loop&&Math.abs(transport.loopStart-passage.start)<.001&&Math.abs(transport.loopEnd-passage.end)<.001)
   send('loop',{on:false,...passage});
  else send('audition',{...passage});
 };
 $('exMark').onclick=()=>{const v=viewport();bookmarks[Number($('exBookmark').value)]={...v,passage:passage&&{...passage}};status.textContent=uiText('Vue mémorisée.');draw();};
 $('exBookmark').onchange=draw;
 $('exRecall').onclick=()=>{const b=bookmarks[Number($('exBookmark').value)];if(!b)return;change(b.start,b.span);if(b.passage)setRange(b.passage.start,b.passage.end);else{passage=null;$('exA').value=$('exB').value='';draw();}};
 $('exGrid').onclick=()=>{if($('exBars').reportValidity()&&$('exMeter').reportValidity())send('alignPassage',{...passage,bars:$('exBars').valueAsNumber,meter:$('exMeter').valueAsNumber});};
 $('exJoin').onclick=()=>{studioAudition.stop();send('previewJoin',{...passage,edit:$('exEdit').value});};
 $('exVariant').onclick=()=>send('passageVariant',{...passage,edit:$('exEdit').value});
 const transportRender=renderTransport;
 renderTransport=function(){transportRender();draw(false);};
 $('guideForm').addEventListener('input',()=>queueMicrotask(draw));$('notes').addEventListener('input',()=>draw());
 const previousReceive=window.studioReceive;
 window.studioReceive=function(data){
  if(data.type==='state'&&data.project.id!==owner){
   owner=data.project.id;history=[];bookmarks=[];passage=null;replay=null;drag=null;wheelTime=-Infinity;
   $('exA').value=$('exB').value=$('exQuery').value='';$('exResults').replaceChildren();status.textContent='';follow.checked=true;
  }
  previousReceive(data);
  if(data.type==='state'){if(!passage)$('exMeter').value=clock().meter;draw();}
 };
 draw();
})();
