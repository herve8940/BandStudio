'use strict';
// The host checks the saved approval against the current project before exporting.
let reviewIdentity='';
function preparationApproved(){
 const p=state.project.preparation;
 return !!(p?.fingerprint&&p?.validatedAt&&Math.abs(p.rate-(transport.rate||1))<.00001&&Math.abs(p.pitch-(transport.pitch||0))<.00001&&p.mode===transport.mode);
}
function songPreparationState(){
 const p=state.project;
 const prepared=p.structureProposal?.status==='prepared'||!!p.preparation?.fingerprint;
 const audio=!!state.loaded&&p.tracks.some(t=>!t.role.startsWith('guide_'));
 const preparing=!!state.busy&&(!!state.jobPlan?.length||state.jobTask==='prepareReview');
 const reviewable=audio&&(prepared||!!(p.sections?.length||p.lyrics?.length||p.chords?.length||p.beats?.length));
 return {audio,prepared,preparing,reviewable};
}
function renderPreparation(){
 const p=state.project,s={...guideDefaults,...p.settings},ready=preparationApproved(),loaded=state.loaded;
 const identity=p.id+':'+state.revision;
 if(identity!==reviewIdentity){reviewIdentity=identity;for(const id of ['reviewAudio','reviewGrid','reviewGuides'])$(id).checked=ready;}
 const phase=songPreparationState();
 $('preparationBadge').textContent=!loaded?uiText('Aucun morceau ouvert'):ready?uiText('✓ Morceau validé'):phase.preparing?uiText('Préparation en cours'):phase.reviewable?uiText('Prêt à écouter'):uiText('À préparer');
 $('preparationBadge').classList.toggle('approved',ready);
 $('deliveryStatus').textContent=ready?uiText('✓ Validé pour REAPER'):loaded?uiText('À vérifier'):uiText('Importe un morceau');
 $('deliveryStatus').classList.toggle('approved',ready);
 $('deliveryName').textContent=loaded?p.name:uiText('Aucun morceau ouvert');
 const rate=transport.rate||1,pitch=transport.pitch||0,tracks=p.tracks.filter(t=>!t.role.startsWith('guide_'));
 const bpm=tempoSummary(p).bpm;
 const metrics=[[uiText('Pistes'),tracks.length],['Sections',p.sections.length],[uiText('Repères'),p.cues.length],['Tempo',bpm?(bpm*rate).toFixed(1)+' BPM':uiText('À caler')],[uiText('Vitesse'),Math.round(rate*100)+' %'],[uiText('Transposition'),(pitch>0?'+':'')+pitch+uiText(' demi-tons')]];
 $('deliveryMetrics').replaceChildren(...metrics.map(([label,value])=>{const e=node('div');e.append(node('small','',label),node('strong','',String(value)));return e;}));
 $('deliveryTracks').replaceChildren(...tracks.map(t=>{const row=node('div','delivery-track');row.append(node('span','track-dot'),node('span','',t.name),node('small','',t.muted?uiText('Muette'):t.solo?'Solo':roles[t.role]||uiText('Piste')));row.firstChild.style.background=colors[t.role]||colors.other;return row;}));
 const modes={original:'Original',mix:uiText('Mix des pistes')};const [kind,target]=listenMode(transport.mode);if(target)modes[transport.mode]=(kind==='minus'?uiText('Sans '):'Solo · ')+instruments[target];
 $('deliveryOptions').textContent=uiText('Écoute : ')+(modes[transport.mode]||uiText('Mix des pistes'))+' · Guides '+(s.exportGuides?'inclus':'exclus')+uiText(' · Décompte initial ')+(s.exportCount?s.countBars+uiText(' mesure(s)'):'exclu');
 $('validateProject').disabled=!loaded||state.busy||ready;
 const unsaved=guideDirty||$('notes').value!==(p.notes||'');
 $('sendReaper').disabled=$('saveReaper').disabled=!loaded||state.busy||unsaved;
 $('validationHint').textContent=ready?uiText('La préparation est enregistrée et validée.'):!loaded?uiText('Importe ou ouvre un morceau pour commencer.'):unsaved?uiText('Enregistre les modifications en cours avant d’exporter.'):uiText('Les médias et le calage seront vérifiés automatiquement avant chaque export.');
 document.querySelectorAll('#validationForm input').forEach(e=>e.disabled=!loaded||state.busy||ready);
 document.querySelectorAll('[data-action=export],[data-action=addTracks],[data-action=save],[data-action=reveal]').forEach(e=>e.disabled=!loaded||state.busy);
 $('splitVocals').disabled=!loaded||state.busy||!p.tracks.some(t=>t.role==='vocals');
 $('rate').disabled=$('pitch').disabled=!loaded||state.busy;
 document.querySelectorAll('#tracks button,#tracks input,#newSection,#newCue,#addCue,#editSection').forEach(e=>e.disabled=!loaded||state.busy);
 $('splitSection').disabled=$('mergeSection').disabled=!!state.busy||!selected;
}
$('validationForm').onsubmit=e=>{
 e.preventDefault();
 if(guideDirty){$('validationHint').textContent=uiText('Applique d’abord les réglages modifiés dans Éditeur du morceau → Métronome.');return;}
 if($('notes').value!==(state.project.notes||'')){$('validationHint').textContent=uiText('Enregistre d’abord tes notes dans Pistes & structure.');return;}
 send('validateProject',{reviewed:true});
};
$('sendReaper').onclick=()=>send('reaper',{open:true,preflight:true});
$('saveReaper').onclick=()=>send('reaper',{open:false,preflight:true});
const previousPreparationFeatures=renderFeatures;
renderFeatures=function(){previousPreparationFeatures();renderPreparation();};
let preparationTransport='';
const previousPreparationTransport=renderTransport;
renderTransport=function(){previousPreparationTransport();const key=[state.project.id,state.revision,transport.mode,transport.rate,transport.pitch,state.busy].join(':');if(key!==preparationTransport){preparationTransport=key;renderPreparation();}};
// Navigation only controls the local preview of the preparation.
const navigation=node('div','navigation-tools');
function navigate(direction){
 const at=transport.position||0,s={...guideDefaults,...state.project.settings};
 const clock=musicalGrid(state.project);
 const marks=[...state.project.sections.map(x=>x.start),...state.project.cues.map(x=>x.time)].sort((a,b)=>a-b);
 const target=direction==='start'?0:direction==='end'?state.duration:direction==='back'?clock.at(clock.coordinate(at)-s.beatsPerBar):direction==='forward'?clock.at(clock.coordinate(at)+s.beatsPerBar):direction==='previous'?[...marks].reverse().find(x=>x<at-.05)??0:marks.find(x=>x>at+.05)??state.duration;
 send('seek',{time:Math.max(0,Math.min(state.duration,target))});
}
for(const [action,label] of [['start',uiText('|◀ Début')],['previous',uiText('◀ Repère')],['back',uiText('−1 mesure')],['forward',uiText('+1 mesure')],['next',uiText('Repère ▶')]])navigation.append(button(label,()=>navigate(action)));
navigation.append(button(uiText('＋ Repère ici'),markAtPlayhead));
$('workspace').prepend(navigation);
document.addEventListener('keydown',e=>{
 if(e.defaultPrevented||e.isComposing||e.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey||e.altKey)return;
 if(e.key.toLowerCase()==='m'){
  if(!state.loaded||state.busy||($('view-studio').hidden && $('view-regie').hidden))return;
  e.preventDefault();if(!e.repeat)markAtPlayhead();return;
 }
 if(e.target.closest('button,summary'))return;
 const direction={Home:'start',End:'end',ArrowLeft:e.shiftKey?'previous':'back',ArrowRight:e.shiftKey?'next':'forward'}[e.code];
 if(direction){e.preventDefault();navigate(direction);}
});
renderPreparation();

$('restoreProject').onclick=()=>send('restoreProject');
const preparePanel=node('article','prepare-all');
preparePanel.append(node('h3','',uiText('Préparer le morceau en un clic')),node('p','',uiText('Instruments, batterie détaillée, chant et chœurs, paroles recalées, accords Internet et sections vérifiées. Un seul parcours, avec les moteurs installés ; les corrections manuelles sont conservées.')));
const planText=node('small');planText.id='analysisPlan';
function prepareAll(){if(guideDirty){openStudioEditor('rhythm');return;}if($('notes').value!==(state.project.notes||'')){openStudioEditor('tracks');$('notes').focus();return;}send('prepareAll',{model:$('model').value,quality:$('separationQuality').value,language:$('lyricsLanguage').value});}
const prepareButton=button(uiText('✧ Tout préparer'),prepareAll,'primary');prepareButton.id='prepareAll';
preparePanel.append(planText,prepareButton,button(uiText('Installer les analyses manquantes'),()=>view('settings')));
$('view-prepare').querySelector('.page-heading').after(preparePanel);
const structurePrepare=button(uiText('✧ Tout préparer'),prepareAll);structurePrepare.id='prepareAllStructure';navigation.prepend(structurePrepare);
const beforeBatchRender=renderPreparation;
renderPreparation=function(){
 beforeBatchRender();
 const labels={separate:uiText('Séparation'),grid:'Tempo',smartgrid:uiText('Temps et mesures'),structure:'Structure',key:uiText('Tonalité'),lyrics:uiText('Paroles'),chords:uiText('Accords'),drumsep:uiText('Batterie détaillée'),vocalsplit:uiText('Chant et chœurs'),lyricscorrect:uiText('Paroles recalées'),prepareReview:uiText('Vérification finale et accords'),guides:uiText('Click et annonces')};
 const plan=state.analysisPlan||[];
 planText.textContent=uiText('Étapes prévues : ')+(plan.map(k=>labels[k]||k).join(' → ')||(state.loaded?uiText('tout est déjà préparé'):uiText('ouvre un morceau pour commencer')));
 const disabled=!state.loaded||state.busy||guideDirty||$('notes').value!==(state.project.notes||'')||!state.project.tracks.some(t=>t.role==='source');
 prepareButton.disabled=structurePrepare.disabled=disabled;
};
renderPreparation();
