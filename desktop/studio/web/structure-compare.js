'use strict';
// This view is read-only. Audition always plays the existing audio, and applying
// a proposal remains an explicit project command in structure-review.js.
function createStructureComparison(onListen){
 const root=node('section','structure-comparison');root.id='structureComparison';root.setAttribute('aria-label',uiText('Comparer la structure actuelle et proposée'));
 const top=node('div','comparison-top'),caption=node('div');
 caption.append(node('span','comparison-kicker',uiText('LA CARTE DES CHANGEMENTS')),node('p','',uiText('Même morceau. Deux découpages.')));
 const controls=node('div','comparison-controls');
 const whole=button(uiText('Tout le morceau'),()=>setRange(0,duration),'comparison-fit');whole.id='comparisonFit';
 const zoom=button(uiText('Cadrer le changement'),()=>focusRange());zoom.id='comparisonZoom';
 controls.append(whole,zoom);top.append(caption,controls);
 const frame=node('div','comparison-frame');
 const lanes={};
 for(const [key,label] of [['current',uiText('ACTUELLE')],['audio','AUDIO'],['proposed',uiText('PROPOSÉE')]]){
  const row=node('div','comparison-row comparison-'+key),identity=node('div','comparison-label');identity.append(node('strong','',label));
  const lane=node('div','comparison-lane');lane.dataset.comparisonLane=key;
  if(key!=='audio')identity.append(node('small'));
  else{const canvas=node('canvas');canvas.setAttribute('aria-label',uiText('Forme d’onde du morceau'));lane.append(canvas);}
  row.append(identity,lane);frame.append(row);lanes[key]={row,identity,lane};
 }
 const ruler=node('div','comparison-row comparison-ruler'),ticks=node('div','comparison-ticks');ruler.append(node('span'),ticks);frame.append(ruler);
 const legend=node('div','comparison-legend');
 for(const [type,text] of [['insert',uiText('＋ Section ajoutée')],['rename',uiText('↔ Nom précisé')],['adjust',uiText('↦ Limite recalée')],['protected',uiText('◇ Section protégée')]])legend.append(node('span','legend-'+type,text));
 const changes=node('div','comparison-chips');changes.id='comparisonChanges';changes.setAttribute('role','group');changes.setAttribute('aria-label',uiText('Parcourir les changements proposés'));
 const detail=node('article','comparison-detail');detail.id='comparisonDetail';
 const info=node('div','comparison-detail-info'),kind=node('span','comparison-kicker'),name=node('h3'),at=node('span','comparison-time');
 const nameLine=node('div','comparison-detail-heading');nameLine.append(name,at);
 const transition=node('div','comparison-transition');
 const reasonDetails=node('details','comparison-reason'),reason=node('p');reasonDetails.append(node('summary','',uiText('Pourquoi cette proposition ?')),reason);
 info.append(kind,nameLine,transition,reasonDetails);
 const actions=node('div','comparison-detail-actions');
 const navigation=node('div','comparison-stepper'),previous=button('←',()=>choose(index-1)),next=button('→',()=>choose(index+1)),position=node('span');
 previous.setAttribute('aria-label',uiText('Changement précédent'));next.setAttribute('aria-label',uiText('Changement suivant'));
 previous.id='comparisonPrevious';next.id='comparisonNext';navigation.append(previous,position,next);
 const listen=button(uiText('▶ Écouter ce passage'),()=>{if(!blocked&&clip)onListen(clip);},'comparison-listen');listen.id='comparisonListen';
 actions.append(navigation,listen,node('small','',uiText('L’audio reste le même. Écoute où la section commence.')));
 detail.append(info,actions);
 const unavailable=node('p','comparison-unavailable');unavailable.hidden=true;
 root.append(top,frame,legend,changes,detail,unavailable);
 let project=null,proposal=null,duration=0,range={start:0,end:0},index=-1,selectedSection=null,blocked=false,clip=null,auditionClip=null,selectionActive=false;
 const stamp=t=>`${Math.floor(Math.max(0,t)/60)}:${(Math.max(0,t)%60).toFixed(2).padStart(5,'0').replace('.',',')}`;
 const valid=rows=>(rows||[]).filter(s=>Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.end>s.start);
 const modifications=()=>proposal?.changes||[];
 const x=t=>(t-range.start)/Math.max(.001,range.end-range.start)*100;
 function setRange(start,end){range={start:Math.max(0,start),end:Math.min(duration,end)};draw();}
 function focusRange(){
  if(!clip)return;
  const at=modifications()[index]?.time??selectedSection?.start??clip.start,span=Math.min(duration,Math.max(12,clip.end-clip.start+6));
  const start=Math.max(0,Math.min(duration-span,at-span*.4));setRange(start,start+span);
 }
 function choose(value){
  if(value<0||value>=modifications().length)return;
  const keepZoom=range.end-range.start<duration-.01;index=value;selectedSection=null;selectionActive=true;detail.hidden=false;showDetail();
  if(keepZoom)focusRange();else draw();
 }
 function select(section){
  const found=modifications().findIndex(c=>Math.abs(c.time-section.start)<.05);
  const inside=found<0?modifications().findIndex(c=>c.time>=section.start&&c.time<section.end):found;
  if(inside>=0){choose(inside);return;}
  selectedSection=section;index=-1;selectionActive=true;detail.hidden=false;showDetail();draw();
 }
 function draw(){
  if(!project||!proposal)return;
  const current=valid(project.sections),proposed=valid(proposal.sections),span=range.end-range.start;
  if(!proposed.length||duration<=0)return;
  for(const [key,rows] of [['current',current],['proposed',proposed]]){
   const {lane,identity}=lanes[key];lane.replaceChildren();identity.querySelector('small').textContent=rows.length+' sections';
   for(const s of rows){
    const left=Math.max(s.start,range.start),right=Math.min(s.end,range.end);if(right<=left)continue;
    const style=sectionStyle(s.name),b=button('',()=>select(s),'comparison-section');b.dataset.sectionId=s.id;b.dataset.start=s.start;b.dataset.end=s.end;
    b.style.left=x(left)+'%';b.style.width=(right-left)/span*100+'%';b.style.setProperty('--section-color',style.color);
    const change=modifications().find(c=>Math.abs(c.time-s.start)<.05&&c.after===s.name);
    if(key==='proposed'&&change){b.classList.add('is-'+change.kind);b.append(node('span','comparison-mark',change.kind==='insert'?'+':change.kind==='adjust'?'↦':'↔'));}
    const locked=key==='current'&&(s.locked||s.reviewed||s.origin==='manual');
    const label=node('span','comparison-section-name',s.name);b.append(label);
    if(locked)b.append(node('span','comparison-lock','◇'));
    b.title=s.name+' · '+stamp(s.start)+' → '+stamp(s.end)+(change&&key==='proposed'?' · '+(change.kind==='insert'?uiText('Section ajoutée'):change.kind==='adjust'?uiText('Limite recalée'):uiText('Nom précisé')):'')+(locked?uiText(' · Protégée'):'');
    b.setAttribute('aria-label',(key==='current'?uiText('Actuelle : '):uiText('Proposée : '))+b.title);
    const at=modifications()[index]?.time??selectedSection?.start;
    b.classList.toggle('is-selected',at!==undefined&&s.start<=at+.01&&s.end>at+.01);
    b.disabled=blocked;lane.append(b);
   }
   lane.append(node('div','comparison-playhead'));
  }
  const audio=lanes.audio.lane;audio.querySelectorAll('button,.comparison-playhead').forEach(n=>n.remove());
  let last=-Infinity;
  modifications().forEach((c,i)=>{
   if(c.time<range.start||c.time>range.end)return;
   const pos=x(c.time);if(pos-last<2&&i!==index)return;last=pos;
   const pin=button(String(i+1).padStart(2,'0'),()=>choose(i),'comparison-pin');pin.classList.toggle('selected',i===index);pin.style.left=pos+'%';
   pin.title=stamp(c.time)+' · '+c.after;pin.setAttribute('aria-label',uiText('Changement ')+(i+1)+' : '+c.after+uiText(' à ')+stamp(c.time));pin.disabled=blocked;audio.append(pin);
  });
  audio.append(node('div','comparison-playhead'));
  ticks.replaceChildren();
  for(let i=0;i<=5;i++){const tick=node('span','',time(range.start+span*i/5));tick.style.left=i*20+'%';ticks.append(tick);}
  whole.classList.toggle('active',span>=duration-.01);whole.setAttribute('aria-pressed',String(span>=duration-.01));
  zoom.classList.toggle('active',span<duration-.01);zoom.setAttribute('aria-pressed',String(span<duration-.01));
  changes.querySelectorAll('button').forEach((b,i)=>{b.classList.toggle('active',i===index);b.setAttribute('aria-pressed',String(i===index));});
  drawAudio();updateTransport();
 }
 function drawAudio(){
  const canvas=lanes.audio.lane.querySelector('canvas'),width=canvas.clientWidth,height=canvas.clientHeight;
  const dpr=Math.min(2,window.devicePixelRatio||1);canvas.width=width*dpr;canvas.height=height*dpr;
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
  const track=project?.tracks?.find(t=>t.role==='source'),peaks=track?.peaks||[];
  if(!peaks.length)return;
  ctx.strokeStyle='#71849f';ctx.globalAlpha=.55;ctx.lineWidth=1;ctx.beginPath();
  for(let px=0;px<width;px+=2){
   const at=range.start+px/width*(range.end-range.start),end=range.start+(px+2)/width*(range.end-range.start);
   let peak=0;const a=Math.max(0,Math.floor((at-track.offset)/track.duration*peaks.length)),b=Math.min(peaks.length,Math.ceil((end-track.offset)/track.duration*peaks.length));
   for(let j=a;j<b;j++)peak=Math.max(peak,Number(peaks[j])||0);
   const amp=Math.min(1,peak)*(height*.42);ctx.moveTo(px,height/2-amp);ctx.lineTo(px,height/2+amp);
  }
  ctx.stroke();
 }
 function showDetail(){
  const change=modifications()[index],atTime=change?.time??selectedSection?.start??0;
  const before=valid(project.sections).find(s=>s.start<=atTime+.01&&s.end>atTime+.01);
  const after=valid(proposal.sections).find(s=>s.start<=atTime+.01&&s.end>atTime+.01);
  kind.textContent=change?({insert:uiText('UNE SECTION RETROUVÉE'),rename:uiText('UN NOM PLUS PRÉCIS'),adjust:uiText('UN DÉPART RECALÉ')}[change.kind]||uiText('CHANGEMENT PROPOSÉ')):uiText('PASSAGE DU MORCEAU');
  name.textContent=change?.after||selectedSection?.name||uiText('Structure conservée');at.textContent=stamp(atTime);
  detail.style.setProperty('--section-color',sectionStyle(name.textContent).color);
  const old=node('div','comparison-before'),fresh=node('div','comparison-after');old.append(node('small','',proposal.status==='prepared'?uiText('AVANT'):uiText('ACTUELLEMENT')),node('strong','',before?.name||change?.before||uiText('Aucune section')));
  const context=change?.kind==='insert'&&before?valid(proposal.sections).filter(s=>s.start<before.end&&s.end>before.start):after?[after]:[];
  fresh.append(node('small','',proposal.status==='prepared'?uiText('APRÈS PRÉPARATION'):uiText('AVEC LA PROPOSITION')));
  const names=node('div','comparison-function-list');
  for(const s of context){const pill=node('span','',s.name);pill.style.setProperty('--section-color',sectionStyle(s.name).color);names.append(pill);}
  if(!context.length)names.append(node('span','',change?.after||uiText('Aucun changement')));
  fresh.append(names);transition.replaceChildren(old,node('span','comparison-arrow','→'),fresh);
  reason.textContent=change?.reason||uiText('Ce passage peut être écouté sans modifier le projet.');reasonDetails.hidden=!change;
  clip={start:Math.max(0,atTime-3),end:Math.min(duration,atTime+6)};
  if(clip.end<=clip.start)clip=null;
  position.textContent=change?`${index+1} / ${modifications().length}`:'Passage';navigation.hidden=!modifications().length;
  previous.disabled=blocked||index<=0;next.disabled=blocked||index>=modifications().length-1;
  setAudition(auditionClip);
 }
 function setBlocked(value){
  blocked=!!value;root.querySelectorAll('button').forEach(b=>b.disabled=blocked);
  zoom.disabled=blocked||!clip;listen.disabled=blocked||!clip;
  previous.disabled=blocked||index<=0;next.disabled=blocked||index>=modifications().length-1;
 }
 function update(p,draft,length){
  const changed=proposal?.id!==draft?.id||project?.id!==p.id;project=draft?.status==='prepared'&&draft.beforeSections?{...p,sections:draft.beforeSections}:p;proposal=draft;duration=Math.max(0,Number(length)||0);
  root.hidden=!draft;
  if(!draft)return;
  const available=valid(draft.sections).length>0&&duration>0;
  [top,frame,legend,changes,detail].forEach(e=>e.hidden=!available);unavailable.hidden=available;
  if(!available){unavailable.textContent=uiText('Cette ancienne proposition ne contient pas de frise. Relance « Vérifier et compléter » pour la comparer visuellement.');clip=null;return;}
  if(changed){range={start:0,end:duration};index=modifications().findIndex(c=>c.kind==='insert');if(index<0&&modifications().length)index=0;selectedSection=null;reasonDetails.open=false;selectionActive=false;}
  detail.hidden=!selectionActive;
  lanes.current.identity.querySelector('strong').textContent=draft.status==='prepared'?uiText('AVANT'):uiText('ACTUELLE');
  lanes.proposed.identity.querySelector('strong').textContent=draft.status==='prepared'?uiText('PRÉPARÉE'):uiText('PROPOSÉE');
  changes.replaceChildren(...modifications().map((c,i)=>{
   const b=button('',()=>choose(i),'comparison-chip');b.append(node('span','comparison-chip-number',String(i+1).padStart(2,'0')),node('span','',c.after),node('small','',stamp(c.time)));b.dataset.changeId=c.id;return b;
  }));
  changes.hidden=!modifications().length;legend.querySelector('.legend-protected').hidden=!p.sections.some(s=>s.locked||s.reviewed||s.origin==='manual');
  showDetail();draw();setBlocked(blocked);
 }
 function updateTransport(){
  const at=transport.position||0,visible=at>=range.start&&at<=range.end;
  root.querySelectorAll('.comparison-playhead').forEach(e=>{e.hidden=!visible;e.style.left=x(at)+'%';});
 }
 function setAudition(value){
  auditionClip=value;const same=clip&&value&&Math.abs(value.start-clip.start)<.01&&Math.abs(value.end-clip.end)<.01;
  listen.textContent=same?uiText('■ Arrêter ce passage'):uiText('▶ Écouter ce passage');listen.setAttribute('aria-pressed',String(!!same));
 }
 const observer=new ResizeObserver(()=>{if(project&&!root.hidden)drawAudio();});observer.observe(lanes.audio.lane);
 return {root,update,setBlocked,updateTransport,setAudition};
}
