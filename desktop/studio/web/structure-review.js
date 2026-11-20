'use strict';
// An optional addition to the existing workspace, never a replacement workflow.
(() => {
 const panel=node('section','structure-review');panel.id='structureReview';panel.setAttribute('aria-label','Compléter la structure et les accords');
 const header=node('div','structure-review-heading'),intro=node('div');
 intro.append(node('strong','','Compléter la structure et les accords'),node('small','','Une proposition sur tes repères, à valider ensemble.'));
 const start=button('Vérifier et compléter',()=>{
  stopAudition();
  send('reviewStructure',{model:$('model').value,quality:$('separationQuality').value,language:$('lyricsLanguage').value});
 });start.id='reviewStructure';
 header.append(intro,start);panel.append(header);
 const result=node('div','structure-review-result');result.hidden=true;
 const summary=node('p');summary.id='structureReviewSummary';summary.setAttribute('role','status');
 const reviewStatus=node('small','structure-review-source');reviewStatus.id='structureReviewListening';
 const warnings=node('ul','structure-review-warnings');warnings.id='structureReviewWarnings';
 const details=node('details'),detailTitle=node('summary','','Voir les changements'),list=node('div','structure-review-changes');
 list.id='structureReviewChanges';details.append(detailTitle,list);
 const source=node('small','structure-review-source');source.id='structureReviewSourceSummary';
 const sourceDetails=node('details'),sourceTitle=node('summary','','Sources consultées'),sourceList=node('div','structure-review-changes');
 sourceDetails.id='structureReviewSources';sourceDetails.append(sourceTitle,sourceList);
 const actions=node('div','structure-review-actions');
 const listen=button('Écouter les passages',()=>audition ? stopAudition() : beginAudition());listen.id='listenStructure';
 const dismiss=button('Garder le parcours actuel',()=>{stopAudition();send('dismissStructure',{proposalID:state.project.structureProposal.id});});dismiss.id='dismissStructure';
 const approve=button('Valider et exporter vers REAPER',()=>{
  const proposal=state.project.structureProposal;if(!proposal||approve.disabled)return;
  stopAudition();send('exportStructure',{proposalID:proposal.id,reviewed:true});
 },'primary');approve.id='exportStructure';
 actions.append(listen,dismiss,approve);result.append(summary,reviewStatus,warnings,details,source,sourceDetails,actions);panel.append(result);
 const draft=node('small','structure-review-draft');draft.id='structureReviewDraft';panel.append(draft);
 const exportLink=button('Afficher l’export REAPER',()=>send('showExport'));exportLink.id='structureReviewExport';panel.append(exportLink);
 document.querySelector('.workspace-heading').after(panel);
 let lastProposal='',audition=null;
 const stamp=t=>`${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0').replace('.',',')}`;
 function dirty(){return !!guideDirty||$('notes').value!==(state.project.notes||'');}
 function clipsFor(proposal){
  if(!proposal)return [];
  if(Array.isArray(proposal.reviewPassages))return proposal.reviewPassages.map(p=>({start:p.start,end:p.end}));
  const clips=[];
  for(const c of proposal.changes||[]){
   const clip={start:Math.max(0,c.time-3),end:Math.min(state.duration,c.time+4)};
   if(clips.length&&clip.start<=clips.at(-1).end)clips.at(-1).end=Math.max(clips.at(-1).end,clip.end);else clips.push(clip);
  }
  return clips;
 }
 function render(){
  const p=state.project,proposal=p.structureProposal,blocked=!state.loaded||state.busy||dirty();
  start.disabled=blocked||!p.tracks.some(t=>t.role==='source');
  approve.disabled=dismiss.disabled=blocked||!proposal;
  listen.disabled=blocked||!clipsFor(proposal).length;
  result.hidden=!proposal;exportLink.hidden=!state.lastExport;exportLink.disabled=!!state.busy;
  draft.textContent=dirty()?'Enregistre tes notes et applique tes réglages en cours avant la vérification.':'';
  if(audition&&(audition.project!==p.id||audition.proposal!==proposal?.id)){stopAudition(false);}
  if(!proposal){lastProposal='';return;}
  const key=p.id+':'+proposal.id;if(key===lastProposal)return;lastProposal=key;
  const changed=proposal.changes.length||proposal.chordUpdate||proposal.memory||proposal.restoredGrid;
  approve.textContent=changed?'Valider et exporter vers REAPER':'Exporter la préparation actuelle vers REAPER';
  const added=proposal.changes.filter(c=>c.kind==='insert').length,renamed=proposal.changes.filter(c=>c.kind==='rename').length;
  const parts=[];
  if(added)parts.push(`${added} section${added>1?'s':''} à ajouter`);
  const adjusted=proposal.changes.filter(c=>c.kind==='adjust').length;
  if(adjusted)parts.push(`${adjusted} début${adjusted>1?'s':''} de section à recaler`);
  if(renamed)parts.push(`${renamed} nom${renamed>1?'s':''} à préciser`);
  if(proposal.chordUpdate)parts.push('accords recalés proposés');
  summary.textContent=proposal.memory ? `Préparation retrouvée · ${proposal.memory.sections} sections · ${proposal.memory.chords} accords. Même enregistrement que « ${proposal.memory.name} ».` : parts.length ? parts.join(' · ')+'.' : changed?proposal.message:'Aucune amélioration proposée — préparation actuelle conservée.';
  const queue=clipsFor(proposal),groups=proposal.repeatedGroups||0,transfers=proposal.transferredPhrases||0;
  const seconds=Math.ceil(queue.reduce((total,c)=>total+c.end-c.start,0)),duration=`${Math.floor(seconds/60)} min ${String(seconds%60).padStart(2,'0')} s`;
  reviewStatus.textContent=proposal.memory ? 'Tes décisions enregistrées sont proposées à nouveau. Le mix et les pistes actuels sont conservés.' : `${queue.length} passage${queue.length===1?'':'s'} à écouter${queue.length?` · ${duration}`:''}${groups?` · ${groups} groupe${groups===1?'':'s'} de répétitions comparé${groups===1?'':'s'}`:''}${transfers?` · ${transfers} phrase${transfers===1?'':'s'} corrigée${transfers===1?'':'s'} adaptée${transfers===1?'':'s'}`:''}.`;
  warnings.replaceChildren(...proposal.warnings.map(text=>node('li','',text.startsWith('Aucune structure Internet exploitable trouvée')?'Repères minutés non récupérés auprès de DRUMY.':text)));warnings.hidden=!proposal.warnings.length;
  list.replaceChildren(...proposal.changes.map(change=>{
   const row=node('div','structure-review-change');
   row.append(node('span','structure-review-time',stamp(change.time)),node('span','',`${change.kind==='insert'?'Ajouter':'Préciser'} : ${change.after}`));
   const note=node('small','',`${change.before} → ${change.after} · ${change.reason}`);row.append(note);return row;
  }));
  details.hidden=!proposal.changes.length;
  const confirmed=proposal.confirmedSections||0;
  const charts=(proposal.chordReference?.sources||[]).length;
  const timed=proposal.sources.filter(s=>!s.format||s.format==='timed').length;
  const ordered=proposal.sources.filter(s=>s.format==='order').length;
  const examples=proposal.sources.filter(s=>s.format==='types').length;
  const found=[];
  if(charts)found.push(`${charts} grille${charts>1?'s':''} d’accords trouvée${charts>1?'s':''}`);
  if(timed)found.push(`${timed} source${timed>1?'s':''} avec minutage`,`${proposal.anchors} repère${proposal.anchors===1?'':'s'} concordant${proposal.anchors===1?'':'s'}`);
  if(ordered)found.push(`${ordered} source${ordered>1?'s':''} avec ordre des sections, sans minutage`);
  if(examples)found.push(`${examples} source${examples>1?'s':''} avec exemples de passages`);
  if(confirmed)found.push(`${confirmed} repère${confirmed===1?'':'s'} confirmé${confirmed===1?'':'s'} conservé${confirmed===1?'':'s'}`);
  source.textContent=found.length?found.join(' · ')+'.':'Aucune référence exploitable récupérée auprès des sources consultées.';
  const shapes={timed:'repères minutés',order:'ordre des sections, sans horaires',types:'exemples de passages, sans ordre complet'};
  const statuses={found:'Disponible',cached:'Référence enregistrée',no_sections:'Pas de sections explicites',not_found:'Morceau non trouvé',unavailable:'Référence non récupérée',identity_missing:'Titre ou artiste incomplet'};
  sourceList.replaceChildren(...(proposal.sourceChecks||[]).map(check=>{
   const row=node('div','structure-review-change');
   row.append(node('strong','',check.publisher),node('span','',`${statuses[check.status]||'Indisponible'} · ${shapes[check.format]||'référence'}`));
   const ref=proposal.sources.find(s=>s.publisher===check.publisher);
   if(ref?.sectionNames?.length)row.append(node('small','',ref.sectionNames.join(ref.format==='types'?' · ':' → ')));
   return row;
  }));
  sourceDetails.hidden=!(proposal.sourceChecks||[]).length;
 }
 function beginAudition(){
  const p=state.project,proposal=p.structureProposal,clips=clipsFor(proposal);if(!clips.length||state.busy)return;
  audition={project:p.id,proposal:proposal.id,clips,index:0,armed:false,last:null,
   loop:{on:!!transport.loop,start:transport.loopStart||0,end:transport.loopEnd||state.duration}};
  nextClip();
 }
 function nextClip(){
  if(!audition)return;
  const clip=audition.clips[audition.index];
  if(!clip){stopAudition();return;}
  audition.armed=false;audition.last=null;
  listen.textContent=`Arrêter l’écoute · ${audition.index+1}/${audition.clips.length}`;
  send('audition',clip);
 }
 function stopAudition(stop=true){
  if(!audition)return;
  const previous=audition;audition=null;listen.textContent='Écouter les passages';
  if(stop&&previous.project===state.project.id){send('stop');send('loop',previous.loop);}
 }
 const beforeTransport=renderTransport;
 renderTransport=function(){
  beforeTransport();if(!audition)return;
  const clip=audition.clips[audition.index],at=transport.position||0;
  if(transport.playing&&at>=clip.start-.1&&at<=clip.end+.1){
   const wrapped=audition.armed&&audition.last!==null&&at<audition.last-.5;
   audition.armed=true;audition.last=at;
   if(at>=clip.end-.16||wrapped){audition.index++;nextClip();}
  }else if(audition.armed&&!state.busy){stopAudition(false);}
 };
 const beforePreparation=renderPreparation;
 renderPreparation=function(){beforePreparation();render();};
 $('notes').addEventListener('input',render);
 $('guideForm').addEventListener('input',()=>queueMicrotask(render));
 render();
})();
