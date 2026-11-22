'use strict';
// Percentages describe completed work; the full preparation counts equally weighted steps.
const analysisLabels={prepareReview:"Vérification finale des sections et accords",structureReview:"Comparaison de la structure",structureExport:"Validation et export REAPER",separate:'Séparation des instruments',drumsep:'Éléments de batterie',grid:'Tempo',smartgrid:'Temps et mesures',structure:'Structure',key:'Tonalité',lyrics:'Paroles',lyricscorrect:'Correction et recalage des paroles',chords:'Grille Internet',drums:'Transcription batterie',guides:'Click et annonces',vocalsplit:'Chant et chœurs',generate:'Création musicale',stemsexport:'Export des pistes',report:'Niveaux audio',sheet:'Fiche PDF',master:'Normalisation',portable:'Projet portable',reaper:'Projet REAPER',validate:'Vérification',decode:'Import audio'};
let analysisProject='',analysisJob='',analysisCurrent=null,analysisHistory={},analysisPlan=[],analysisPlanIndex=0;
const analysisMeters=new Map();
function progressMeter(label){
 const box=node('div','analysis-progress'),text=node('small','analysis-progress-label',label),bar=node('progress');
 bar.max=100;bar.value=0;bar.setAttribute('aria-label',label);box.append(text,bar);return box;
}
function updateMeter(box,percent,label,waiting=false){
 const value=typeof percent==='number'&&Number.isFinite(percent)?Math.max(0,Math.min(100,percent)):null;
 box.querySelector('small').textContent=label;
 const bar=box.querySelector('progress');
 if(value===null)bar.removeAttribute('value');else bar.value=value;
 bar.setAttribute('aria-valuetext',label);box.classList.toggle('waiting',waiting);
}
const currentMeter=progressMeter('Progression de l’analyse');currentMeter.id='jobProgressBar';$('jobDetail').after(currentMeter);
const overallMeter=progressMeter('Préparation complète');overallMeter.id='overallProgress';overallMeter.hidden=true;currentMeter.after(overallMeter);
const planPanel=node('div','analysis-plan');planPanel.id='preparationProgress';
$('analysisPlan').after(planPanel);
function addAnalysisMeter(button,task){
 if(!button||!task||button.closest('#job'))return;
 const meter=progressMeter(analysisLabels[task]||'Traitement');meter.dataset.task=task;
 button.after(meter);if(!analysisMeters.has(task))analysisMeters.set(task,[]);analysisMeters.get(task).push(meter);
}
document.querySelectorAll('[data-analysis],[data-studio-task]').forEach(b=>addAnalysisMeter(b,b.dataset.analysis||b.dataset.studioTask));
for(const [selector,task] of [['#splitVocals','vocalsplit'],['[data-action="guides"]','guides'],['#exportSheet','sheet']])addAnalysisMeter(document.querySelector(selector),task);
function analysisDone(task){
 const project=state.project,completed=project.analysesCompleted||[];
 if(task==='chords')return !!project.preparation?.fingerprint||(project.chords||[]).some(c=>c.manual||(c.sourceURL&&project.chordReference?.sources?.length));
 if(completed.includes(task))return true;
 if(task==='separate')return project.tracks.some(t=>['drums','bass','vocals','other','guitar','piano'].includes(t.role));
 if(task==='guides')return !!state.guidesReady;
 return false;
}
function taskProgress(task){
 const data=analysisHistory[task];
 if(task==='chords'&&!state.busy&&!analysisDone(task)){
  const status=state.project.chordReference?.status;
  if(status==='unavailable'||status==='not_found')return {value:0,text:status==='unavailable'?'Sources indisponibles':'Aucune grille trouvée'};
 }
 if(data?.failed)return {value:data.progress||0,text:'Interrompu · '+Math.floor(data.progress||0)+' %'};
 if(data?.finished||(!data&&analysisDone(task)))return {value:100,text:'Terminé · 100 %'};
 if(data){
  const value=typeof data.progress==='number'&&Number.isFinite(data.progress)?data.progress:null;
  return {value,text:(value===null?'En cours':Math.floor(value)+' %'+(data.progressBasis==='steps'?' des étapes':''))+' · '+(data.progressLabel||'Calcul en cours…'),waiting:!!data.indeterminate};
 }
 return {value:0,text:'En attente · 0 %'};
}
function renderAnalysisProgress(){
 for(const [task,meters] of analysisMeters){const p=taskProgress(task);for(const meter of meters){updateMeter(meter,p.value,p.text,p.waiting);meter.classList.toggle('idle',!analysisHistory[task]&&!analysisDone(task));}}
 const data=analysisCurrent||{},p=taskProgress(data.task);
 updateMeter(currentMeter,p.value,p.text,p.waiting);
 overallMeter.hidden=analysisPlan.length<2;
 if(analysisPlan.length){
  const fraction=typeof data.progress==='number'?Math.min(100,data.progress)/100:0;
  const value=100*(analysisPlanIndex+fraction)/analysisPlan.length;
  updateMeter(overallMeter,value,'Préparation · '+Math.floor(value)+' % des étapes');
 }
 const plan=analysisPlan.length?analysisPlan:(state.analysisPlan||[]);
 planPanel.replaceChildren();
 for(const [index,task] of plan.entries()){
  const meter=progressMeter(analysisLabels[task]||task),p=taskProgress(task);
  if(analysisPlan.length&&index<analysisPlanIndex){p.value=100;p.text='Terminé · 100 %';}
  updateMeter(meter,p.value,(analysisLabels[task]||task)+' · '+p.text,p.waiting);planPanel.append(meter);
 }
}
const receiveBeforeProgress=window.studioReceive;
window.studioReceive=function(data){
 if(data.type==='state'){
  if(data.project.id!==analysisProject){analysisProject=data.project.id;analysisHistory={};analysisCurrent=null;analysisPlan=[];analysisJob='';}
  if(data.busy&&data.jobID&&data.jobID!==analysisJob){
   analysisJob=data.jobID;analysisCurrent={task:data.jobTask,jobID:data.jobID,progress:0,indeterminate:true,progressLabel:'Préparation…'};
   if(data.jobTask)analysisHistory[data.jobTask]=analysisCurrent;
  }
  if(data.busy){analysisPlan=data.jobPlan||[];analysisPlanIndex=data.jobPlanIndex||0;}
  if(!data.busy&&analysisCurrent&&!analysisCurrent.finished&&!analysisCurrent.failed){
   analysisCurrent={...analysisCurrent,failed:true};analysisHistory[analysisCurrent.task]=analysisCurrent;
  }
 }
 if(data.type==='job'&&data.task){
  const previous=analysisHistory[data.task];
  const same=previous?.jobID===data.jobID;
  const merged={...(same?previous:{}),...data};
  if(same&&typeof previous.progress==='number')merged.progress=Math.max(previous.progress,Number.isFinite(data.progress)?data.progress:0);
  if(merged.finished)merged.progressLabel='Terminé';
  if(merged.failed)merged.progressLabel='Interrompu';
  analysisHistory[data.task]=merged;
  if(data.jobID&&data.jobID!==analysisJob){renderAnalysisProgress();return;}
  data=merged;
  if(!data.jobID||data.jobID===analysisJob){analysisCurrent=merged;if(data.plan){analysisPlan=data.plan;analysisPlanIndex=data.planIndex||0;}}
 }
 receiveBeforeProgress(data);
 if(data.type==='state'||data.type==='job')renderAnalysisProgress();
};
renderAnalysisProgress();
