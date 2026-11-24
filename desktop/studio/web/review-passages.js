'use strict';
// A read-only index of the current analysis warnings. Listening never validates
// music; corrections use the existing editor, host commands and undo history.
(() => {
 const panel=node('section','song-review');panel.id='songReview';panel.hidden=true;
 panel.setAttribute('aria-label',uiText('Écoute ciblée des passages à vérifier'));
 const heading=node('div','song-review-heading');
 heading.append(node('strong','',uiText('Écoute ciblée')));
 const total=node('span');total.id='songReviewCount';heading.append(total);
 const controls=node('div','song-review-controls'),label=node('label','',uiText('Passage à vérifier'));
 const choice=node('select');choice.id='songReviewChoice';label.htmlFor=choice.id;label.append(choice);
 const listen=button(uiText('Écouter ce passage'),()=>{
  const clip=current();if(!clip)return;
  if(playing())studioAudition.stop();else{if(blocked())return;focus(clip);studioAudition.play({start:clip.start,end:clip.end});}
  playback();
 },'primary');listen.id='songReviewListen';
 const edit=button(uiText('Modifier dans l’éditeur'),()=>{
  const clip=current();if(!clip||blocked())return;
  studioAudition.stop();focus(clip);
  if(clip.kind==='rhythm'){$('editorRhythm').scrollIntoView({block:'nearest'});return;}
  const item=(state.project[clip.kind==='structure'?'sections':clip.kind]||[]).find(row=>row.id===clip.target);
  if(item){if(clip.kind==='structure')openEditor('section',item);else openAnnotation(item);}
 });edit.id='songReviewEdit';
 const next=button(uiText('Passage suivant →'),()=>{
  if(blocked()||!queue.length)return;
  studioAudition.stop();index=(index+1)%queue.length;choice.value=queue[index].id;
  focus(queue[index],true);playback();
 });next.id='songReviewNext';
 controls.append(label,listen,edit,next);
 const note=node('small');note.id='songReviewNote';note.setAttribute('role','status');
 panel.append(heading,controls,note);$('songWorkflow').after(panel);
 let queue=[],index=0,owner='';
 const current=()=>queue[index];
 const blocked=()=>!state.loaded||!!state.busy||guideDirty||$('notes').value!==(state.project.notes||'');
 function playing(){const clip=current(),active=window.studioAudition?.current();return !!clip&&!!active&&active.start===clip.start&&active.end===clip.end;}
 function focus(clip,seek=false){
  openStudioEditor(clip.kind);
  zoomSpan=Math.min(state.duration,Math.max(8,clip.end-clip.start+2));
  zoomStart=Math.max(0,Math.min(state.duration-zoomSpan,clip.start-1));
  $('zoomFollow').checked=false;
  if(clip.kind==='structure'&&clip.target)chooseMarker('section',clip.target,false);
  redrawTimeline();if(seek)send('seek',{time:clip.start});
 }
 choice.onchange=()=>{
  studioAudition.stop();index=Math.max(0,queue.findIndex(c=>c.id===choice.value));
  if(current())focus(current(),true);playback();
 };
 function passages(p){
  const rows=[],seen=new Set(),length=state.duration;
  const add=(kind,target,start,end,reason)=>{
   if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start||start>=length||end<=0)return;
   const id=kind+':'+target;if(seen.has(id))return;seen.add(id);
   rows.push({id,kind,target,start:Math.max(0,start),end:Math.min(length,end),reason});
  };
  if(!p.gridLocked&&p.settings?.gridMode!=='fixed'&&p.beats?.length&&/à vérifier|non confirm|incertain|check by ear|unconfirmed|uncertain/i.test(p.analysisNote||'')){
   const start=Number(p.settings.firstBeat)||0;
   add('rhythm','grid',Math.max(0,start-2),start+8,uiText('Premier temps et mesures'));
  }
  if(p.structureProposal?.status==='prepared'){
   for(const change of p.structureProposal.changes||[]){
    const time=change.time;if(!Number.isFinite(time))continue;
    const section=p.sections.reduce((best,s)=>!best||Math.abs(s.start-time)<Math.abs(best.start-time)?s:best,null);
    if(!section||section.reviewed||section.locked||section.origin==='manual')continue;
    add('structure',section.id,time-3,time+4,section.name+uiText(' · section ajustée'));
   }
  }
  for(const row of p.lyrics||[]){
   if(!annotationNeedsReview(row))continue;
   const words=(row.words||[]).filter(w=>w.timingReview&&w.start>=row.start&&w.end>w.start&&w.end<=row.end+.1);
   const start=words.length?words[0].start:row.start,end=words.length?words.at(-1).end:row.end;
   add('lyrics',row.id,start-1.5,end+1.5,uiText('Paroles · ')+row.text);
  }
  for(const row of p.chords||[]){
   if(annotationNeedsReview(row)){
    const section=p.sections.find(s=>s.start<=row.start&&row.start<s.end);
    add('chords',row.id,row.start-1.5,row.end+1.5,uiText('Accord ')+row.text+(section?' · '+section.name:''));
   }
  }
  return rows.sort((a,b)=>a.start-b.start||a.kind.localeCompare(b.kind));
 }
 function playback(){
  const active=playing();listen.textContent=active?uiText('Arrêter l’extrait'):uiText('Écouter ce passage');
  listen.setAttribute('aria-pressed',String(active));
  const disabled=blocked()||!queue.length;
  choice.disabled=edit.disabled=disabled;listen.disabled=disabled&&!active;next.disabled=disabled||queue.length<2;
  note.textContent=guideDirty||$('notes').value!==(state.project.notes||'')?uiText('Enregistre tes notes et applique tes réglages avant l’écoute ciblée.'):
   current()?uiFormat`${time(current().start,true)} → ${time(current().end,true)} · L’écoute ne valide pas automatiquement le passage.`:'';
 }
 function render(){
  const previous=current(),project=state.project;queue=passages(project);
  index=project.id===owner?Math.max(0,queue.findIndex(c=>c.id===previous?.id)):0;owner=project.id;
  const selected=current();
  // Do not finish listening to a superseded line after a correction or undo.
  if(previous&&(!selected||previous.id!==selected.id||previous.start!==selected.start||previous.end!==selected.end))studioAudition.stop();
  panel.hidden=!state.loaded||!queue.length;
  total.textContent=uiFormat`${queue.length} passage${queue.length===1?'':'s'} signalé${queue.length===1?'':'s'}`;
  choice.replaceChildren(...queue.map((clip,i)=>{const option=node('option','',`${i+1}. ${time(clip.start)} · ${clip.reason}`);option.value=clip.id;return option;}));
  if(selected)choice.value=selected.id;playback();
 }
 const receive=window.studioReceive;
 window.studioReceive=function(data){receive(data);if(data.type==='state')render();};
 const beforeTransport=renderTransport;
 renderTransport=function(){beforeTransport();playback();};
 const beforePreparation=renderPreparation;
 renderPreparation=function(){beforePreparation();playback();};
 render();
})();
