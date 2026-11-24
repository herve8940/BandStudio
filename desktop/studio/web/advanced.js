'use strict';
// Local tools share the existing project-bound native message channel.
const studioTask=(kind,options={})=>send('studioTask',{kind,options});
document.querySelectorAll('[data-studio-task]').forEach(b=>b.onclick=()=>studioTask(b.dataset.studioTask,['smartgrid','key'].includes(b.dataset.studioTask)?{reanalyze:true}:{}));
const musicKeys=[['',uiText('Non renseignée')]];
for(const [name,label] of [['C',uiText('Do')],['C#','Do♯'],['D',uiText('Ré')],['Eb','Mi♭'],['E',uiText('Mi')],['F',uiText('Fa')],['F#','Fa♯'],['G',uiText('Sol')],['Ab','La♭'],['A',uiText('La')],['Bb','Si♭'],['B',uiText('Si')]]){
 const note = interfaceLanguage==='en' ? name.replace('#','♯').replace('b','♭') : label;
 musicKeys.push([name,note+uiText(' majeur')],[name+'m',note+uiText(' mineur')]);
}
for(const [value,label] of musicKeys){const o=node('option','',label);o.value=value;$('songKey').append(o);}
$('songKey').onchange=()=>send('musicSettings',{key:$('songKey').value});
$('capo').onchange=()=>send('musicSettings',{capo:Number($('capo').value)});
$('lockGrid').onchange=()=>send('musicSettings',{gridLocked:$('lockGrid').checked});
$('unlockTempo').onclick=()=>send('musicSettings',{gridLocked:false});
$('editTempo').onclick=()=>{view('guides');$('setting-referenceBPM').focus();};
$('markDownbeat').onclick=()=>{
 const s={...guideDefaults,...state.project.settings,firstBeat:transport.position||0};
 dirtyGuideSettings.delete('firstBeat');guideDirty=dirtyGuideSettings.size>0;send('settings',{value:s});
};
let taps=[];
$('tapTempo').onclick=()=>{
 const now=performance.now();if(taps.length&&now-taps.at(-1)>3000)taps=[];
 taps.push(now);taps=taps.slice(-9);
 if(taps.length<3){$('tapResult').textContent=uiText('Continue à taper sur les temps…');return;}
 const deltas=taps.slice(1).map((v,i)=>v-taps[i]).sort((a,b)=>a-b);
 const bpm=60000/deltas[Math.floor(deltas.length/2)];
 if(bpm<20||bpm>400)return;
 $('setting-manualBPM').value=(bpm*($('setting-pulseUnit').value==='dottedQuarter'?1.5:1)).toFixed(1);$('setting-gridMode').value='fixed';markGuideSetting('manualBPM');markGuideSetting('gridMode');
 $('tapResult').textContent=$('setting-manualBPM').value+uiText(' BPM à la noire · Appliquer au morceau pour enregistrer ce tempo fixe');
};
$('exportStems').onclick=()=>studioTask('stemsexport',{format:$('stemFormat').value});
$('exportLyrics').onclick=()=>studioTask('lyricsexport',{format:$('lyricFormat').value});
$('manualLyrics').onclick=()=>{
 if(!state.loaded||state.busy)return;
 window.openStudioEditor?.('lyrics');$('annotationKind').value='lyrics';renderAnnotations();
 const lines=state.project.lyrics||[],at=transport.position||0;
 const line=lines.find(x=>x.start<=at&&at<x.end)||lines.find(x=>x.start>=at)||lines.at(-1);
 openAnnotation(line);$('wordEditor').open=!!line?.words?.length;
};
$('correctLyrics').onclick=()=>send('analyze',{kind:'lyricscorrect',model:'htdemucs',language:'auto',reanalyze:true});
$('importLyrics').onclick=()=>$('lyricsFile').click();
$('lyricsFile').onchange=async()=>{
 const f=$('lyricsFile').files?.[0];if(!f)return;
 if(f.size>2000000){$('lyricsImportStatus').textContent=uiText('Le fichier doit faire moins de 2 Mo.');return;}
 try{studioTask('lyricsimport',{text:await f.text(),replace:$('replaceLyrics').checked});}
 catch{$('lyricsImportStatus').textContent=uiText('Impossible de lire ce fichier.');}
 $('lyricsFile').value='';
};
const oldFeatures=renderFeatures;
renderFeatures=function(){oldFeatures();
 const p=state.project;
 $('lyricsReferenceStatus').textContent=p.lyricsReference ? uiText(p.lyricsReference.message)+uiText(' Sources : ')+(p.lyricsReference.sources||[]).join(', ') : uiText('Recherche gratuite sans compte. Seuls le titre et l’artiste sont envoyés ; le recalage du chant reste local.');
 if(document.activeElement!==$('songKey'))$('songKey').value=p.key||'';
 if(document.activeElement!==$('capo'))$('capo').value=p.capo||0;
 $('lockGrid').checked=!!p.gridLocked;
 $('unlockTempo').hidden=!p.gridLocked;
 $('unlockTempo').disabled=$('editTempo').disabled=!state.loaded||state.busy;
 $('tempoStatus').textContent=p.gridLocked?uiText('Calage protégé : tu peux le modifier ou le déverrouiller ici.'):uiText(p.analysisNote)||uiText('Détection modifiable : tu peux la recalculer ou corriger le tempo.');
 const {fixed,bpm,measured,reference}=tempoSummary(p);
 $('bpmValue').textContent=bpm?Number(bpm).toFixed(1):'—';
 $('bpmKind').textContent=uiText('BPM · noire · ')+(fixed?'fixe':reference?uiText('référence'):uiText('estimé'));
 const pulse=p.settings?.pulseUnit==='dottedQuarter'?uiText('noires pointées'):'noires';
 const detail=(reference?uiText('Référence renseignée ; grille mesurée ≈ ')+measured.toFixed(1)+uiText(' BPM à la noire. '):fixed?uiText('Tempo fixe. '):uiText('Tempo mesuré à la noire. '))+(p.bpm||fixed?uiText('Clic : ')+pulseTempo(p).toFixed(1)+uiText(' pulsations/min · ')+pulse+'.':'');
 $('tempoDetail').textContent=detail;$('guideTempoDetail').textContent=detail;

 $('rhythmStatus').textContent=p.gridLocked?uiText('Calage protégé · décoche la protection pour relancer la détection'):uiText(p.analysisNote)||uiText('Calage modifiable');
 document.querySelectorAll('[data-studio-task],#exportStems,#exportLyrics,#importLyrics,#correctLyrics,#manualLyrics,#masterForm button,#markDownbeat,#tapTempo,#songKey,#capo,#lockGrid,#exportSheet,#startPhone').forEach(b=>b.disabled=!state.loaded||state.busy);
};
const originalStage=renderStage;
renderStage=function(){originalStage();
 const p=state.project;
 $('stageKey').textContent=p.key?uiText('Tonalité entendue · ')+transposeChord(chordLabel(p.key),transport.pitch||0):uiText('Tonalité à déterminer');
};
function wordRow(word){
 const row=node('div','word-edit-row');
 for(const [key,label] of [['start',uiText('Début du mot (s)')],['end',uiText('Fin du mot (s)')],['text',uiText('Mot')]]){
  const input=node('input');input.dataset.word=key;input.type=key==='text'?'text':'number';input.value=word[key];input.setAttribute('aria-label',label);
  if(key!=='text'){input.min=0;input.step=.001;}else{
   input.maxLength=120;
   if(word.timingReview){
    input.classList.add('word-timing-review');input.title=uiText('Calage de ce mot à écouter');
    input.setAttribute('aria-label',uiText('Mot dont le calage est à écouter'));
   }
  }
  input.oninput=()=>{const text=[...$('wordRows').querySelectorAll('[data-word=text]')].map(x=>x.value).join(' ');$('annotationText').value=text;};
  row.append(input);
 }
 row.append(button('×',()=>{row.remove();if($('wordRows').children.length)$('annotationText').value=[...$('wordRows').querySelectorAll('[data-word=text]')].map(x=>x.value).join(' ');}));$('wordRows').append(row);
}
const originalAnnotation=openAnnotation;
openAnnotation=function(item){originalAnnotation(item);$('wordEditor').hidden=annotationEdit.kind!=='lyrics';$('wordRows').replaceChildren();$('wordError').textContent='';for(const word of item?.words||[])wordRow(word);};
$('distributeWords').onclick=()=>{
 const words=$('annotationText').value.trim().split(/\s+/).filter(Boolean),a=Number($('annotationStart').value),b=Number($('annotationEnd').value);
 if(!words.length||b<=a)return;$('wordRows').replaceChildren();
 words.forEach((text,i)=>wordRow({text,start:Number((a+(b-a)*i/words.length).toFixed(3)),end:Number((a+(b-a)*(i+1)/words.length).toFixed(3))}));
 $('wordError').textContent=uiText('Répartition régulière approximative : ajuste les horaires en écoutant.');
};
$('clearWords').onclick=()=>$('wordRows').replaceChildren();
$('annotationForm').onsubmit=e=>{
 e.preventDefault();const start=Number($('annotationStart').value),end=Number($('annotationEnd').value),words=[];let previous=start;
 for(const row of $('wordRows').children){
  const word={};row.querySelectorAll('[data-word]').forEach(i=>word[i.dataset.word]=i.dataset.word==='text'?i.value.trim():Number(i.value));
  if(!word.text||!Number.isFinite(word.start)||!Number.isFinite(word.end)||word.start<previous||word.end<=word.start||word.end>end){$('wordError').textContent=uiText('Les mots doivent se suivre dans les limites de la ligne, sans chevauchement.');return;}
  words.push(word);previous=word.end;
 }
 const text=$('annotationText').value.trim();
 if(words.length&&words.map(w=>w.text).join(' ')!==text.replace(/\s+/g,' ')){$('wordError').textContent=uiText('Le texte et les mots diffèrent. Corrige les mots ou retire leurs horaires.');return;}
 send('annotation',{...annotationEdit,text,start,end,...(annotationEdit.kind==='lyrics'?{words}:{})});$('annotationEditor').close();
};

$('exportSheet').onclick=()=>studioTask('sheet',{pitch:transport.pitch||0});
$('splitVocals').onclick=()=>send('creative',{kind:'vocalsplit'});
