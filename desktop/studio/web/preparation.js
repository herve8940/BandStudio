'use strict';
// The host checks the saved approval against the current project before exporting.
let reviewIdentity='';
function preparationApproved(){
 const p=state.project.preparation;
 return !!(p?.fingerprint&&p?.validatedAt&&Math.abs(p.rate-(transport.rate||1))<.00001&&Math.abs(p.pitch-(transport.pitch||0))<.00001&&p.mode===transport.mode);
}
function renderPreparation(){
 const p=state.project,s={...guideDefaults,...p.settings},ready=preparationApproved(),loaded=state.loaded;
 const identity=p.id+':'+state.revision;
 if(identity!==reviewIdentity){reviewIdentity=identity;for(const id of ['reviewAudio','reviewGrid','reviewGuides'])$(id).checked=ready;}
 $('preparationBadge').textContent=!loaded?'Aucun morceau ouvert':ready?'✓ Morceau validé':'Préparation en cours';
 $('preparationBadge').classList.toggle('approved',ready);
 $('deliveryStatus').textContent=ready?'✓ Validé pour REAPER':loaded?'À vérifier':'Importe un morceau';
 $('deliveryStatus').classList.toggle('approved',ready);
 $('deliveryName').textContent=loaded?p.name:'Aucun morceau ouvert';
 const rate=transport.rate||1,pitch=transport.pitch||0,tracks=p.tracks.filter(t=>!t.role.startsWith('guide_'));
 const bpm=s.gridMode==='fixed'?s.manualBPM:p.bpm;
 const metrics=[['Pistes',tracks.length],['Sections',p.sections.length],['Repères',p.cues.length],['Tempo',bpm?(bpm*rate).toFixed(1)+' BPM':'À caler'],['Vitesse',Math.round(rate*100)+' %'],['Transposition',(pitch>0?'+':'')+pitch+' demi-tons']];
 $('deliveryMetrics').replaceChildren(...metrics.map(([label,value])=>{const e=node('div');e.append(node('small','',label),node('strong','',String(value)));return e;}));
 $('deliveryTracks').replaceChildren(...tracks.map(t=>{const row=node('div','delivery-track');row.append(node('span','track-dot'),node('span','',t.name),node('small','',t.muted?'Muette':t.solo?'Solo':roles[t.role]||'Piste'));row.firstChild.style.background=colors[t.role]||colors.other;return row;}));
 const modes={original:'Original',mix:'Mix des pistes'};const [kind,target]=listenMode(transport.mode);if(target)modes[transport.mode]=(kind==='minus'?'Sans ':'Solo · ')+instruments[target];
 $('deliveryOptions').textContent='Écoute : '+(modes[transport.mode]||'Mix des pistes')+' · Guides '+(s.exportGuides?'inclus':'exclus')+' · Départ REAPER à 0:00 (sans décompte ajouté)';
 $('validateProject').disabled=!loaded||state.busy||ready;
 $('sendReaper').disabled=$('saveReaper').disabled=!loaded||state.busy||!ready;
 $('validationHint').textContent=ready?'La préparation est enregistrée et validée.':!loaded?'Importe ou ouvre un morceau pour commencer.':'Toute modification des pistes, du mix ou des repères demande une nouvelle validation.';
 document.querySelectorAll('#validationForm input').forEach(e=>e.disabled=!loaded||state.busy||ready);
 document.querySelectorAll('[data-action=export],[data-action=addTracks],[data-action=save],[data-action=reveal]').forEach(e=>e.disabled=!loaded||state.busy);
 $('splitVocals').disabled=!loaded||state.busy||!p.tracks.some(t=>t.role==='vocals');
 $('rate').disabled=$('pitch').disabled=!loaded||state.busy;
 document.querySelectorAll('#tracks button,#tracks input,#newSection,#newCue,#addCue,#editSection').forEach(e=>e.disabled=!loaded||state.busy);
 $('splitSection').disabled=$('mergeSection').disabled=!!state.busy||!selected;
}
$('validationForm').onsubmit=e=>{
 e.preventDefault();
 if(guideDirty){$('validationHint').textContent='Applique d’abord les réglages modifiés dans Click & cues.';return;}
 if($('notes').value!==(state.project.notes||'')){$('validationHint').textContent='Enregistre d’abord tes notes dans Pistes & structure.';return;}
 send('validateProject',{reviewed:true});
};
$('sendReaper').onclick=()=>send('reaper',{open:true});
$('saveReaper').onclick=()=>send('reaper',{open:false});
const previousPreparationFeatures=renderFeatures;
renderFeatures=function(){previousPreparationFeatures();renderPreparation();};
let preparationTransport='';
const previousPreparationTransport=renderTransport;
renderTransport=function(){previousPreparationTransport();const key=[state.project.id,state.revision,transport.mode,transport.rate,transport.pitch,state.busy].join(':');if(key!==preparationTransport){preparationTransport=key;renderPreparation();}};
// Navigation only controls the local preview of the preparation.
const navigation=node('div','navigation-tools');
function navigate(direction){
 const at=transport.position||0,s={...guideDefaults,...state.project.settings};
 const period=60/(s.gridMode==='fixed'?s.manualBPM:state.project.bpm||s.manualBPM);
 const marks=[...state.project.sections.map(x=>x.start),...state.project.cues.map(x=>x.time)].sort((a,b)=>a-b);
 const target=direction==='start'?0:direction==='end'?state.duration:direction==='back'?at-period*s.beatsPerBar:direction==='forward'?at+period*s.beatsPerBar:direction==='previous'?[...marks].reverse().find(x=>x<at-.05)??0:marks.find(x=>x>at+.05)??state.duration;
 send('seek',{time:Math.max(0,Math.min(state.duration,target))});
}
for(const [action,label] of [['start','|◀ Début'],['previous','◀ Repère'],['back','−1 mesure'],['forward','+1 mesure'],['next','Repère ▶']])navigation.append(button(label,()=>navigate(action)));
navigation.append(button('＋ Repère ici',()=>openEditor('cue')));
$('workspace').prepend(navigation);
document.addEventListener('keydown',e=>{
 if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey||e.altKey)return;
 const direction={Home:'start',End:'end',ArrowLeft:e.shiftKey?'previous':'back',ArrowRight:e.shiftKey?'next':'forward'}[e.code];
 if(direction){e.preventDefault();navigate(direction);}
 if(e.code==='KeyM'){e.preventDefault();openEditor('cue');}
});
renderPreparation();

$('restoreProject').onclick=()=>send('restoreProject');
const preparePanel=node('article','prepare-all');
preparePanel.append(node('h3','','Préparer le morceau en un clic'),node('p','','Enchaîne les analyses installées, puis crée le click et les annonces. Les pistes déjà séparées et le calage protégé sont conservés. Écoute le résultat avant de valider.'));
const planText=node('small');planText.id='analysisPlan';
function prepareAll(){send('prepareAll',{model:$('model').value,quality:$('separationQuality').value,language:$('lyricsLanguage').value});}
const prepareButton=button('✧ Tout préparer',prepareAll,'primary');prepareButton.id='prepareAll';
preparePanel.append(planText,prepareButton,button('Installer les analyses manquantes',()=>view('settings')));
$('view-prepare').querySelector('.page-heading').after(preparePanel);
const structurePrepare=button('✧ Tout préparer',prepareAll);structurePrepare.id='prepareAllStructure';navigation.prepend(structurePrepare);
const beforeBatchRender=renderPreparation;
renderPreparation=function(){
 beforeBatchRender();
 const labels={separate:'Séparation',grid:'Tempo',smartgrid:'Temps et mesures',structure:'Structure',key:'Tonalité',lyrics:'Paroles',chords:'Accords',guides:'Click et annonces'};
 const plan=state.analysisPlan||[];
 planText.textContent='Étapes prévues : '+(plan.map(k=>labels[k]||k).join(' → ')||'ouvre un morceau pour commencer');
 const disabled=!state.loaded||state.busy||!state.project.tracks.some(t=>t.role==='source');
 prepareButton.disabled=structurePrepare.disabled=disabled;
};
renderPreparation();
