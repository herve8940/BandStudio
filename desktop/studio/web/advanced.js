'use strict';
// Local tools share the existing project-bound native message channel.
const studioTask=(kind,options={})=>send('studioTask',{kind,options});
document.querySelectorAll('[data-studio-task]').forEach(b=>b.onclick=()=>studioTask(b.dataset.studioTask));
const musicKeys=[['','Non renseignée']];
for(const [name,label] of [['C','Do'],['C#','Do♯'],['D','Ré'],['Eb','Mi♭'],['E','Mi'],['F','Fa'],['F#','Fa♯'],['G','Sol'],['Ab','La♭'],['A','La'],['Bb','Si♭'],['B','Si']]){
 musicKeys.push([name,label+' majeur'],[name+'m',label+' mineur']);
}
for(const [value,label] of musicKeys){const o=node('option','',label);o.value=value;$('songKey').append(o);}
$('songKey').onchange=()=>send('musicSettings',{key:$('songKey').value});
$('capo').onchange=()=>send('musicSettings',{capo:Number($('capo').value)});
$('lockGrid').onchange=()=>send('musicSettings',{gridLocked:$('lockGrid').checked});
$('markDownbeat').onclick=()=>{
 const s={...guideDefaults,...state.project.settings,firstBeat:transport.position||0};
 guideDirty=false;send('settings',{value:s});
};
let taps=[];
$('tapTempo').onclick=()=>{
 const now=performance.now();if(taps.length&&now-taps.at(-1)>3000)taps=[];
 taps.push(now);taps=taps.slice(-9);
 if(taps.length<3){$('tapResult').textContent='Continue à taper sur les temps…';return;}
 const deltas=taps.slice(1).map((v,i)=>v-taps[i]).sort((a,b)=>a-b);
 const bpm=60000/deltas[Math.floor(deltas.length/2)];
 if(bpm<20||bpm>400)return;
 $('setting-manualBPM').value=bpm.toFixed(1);$('setting-gridMode').value='fixed';guideDirty=true;
 $('tapResult').textContent=bpm.toFixed(1)+' BPM · Appliquer au morceau pour enregistrer ce tempo fixe';
};
$('exportStems').onclick=()=>studioTask('stemsexport',{format:$('stemFormat').value});
$('exportLyrics').onclick=()=>studioTask('lyricsexport',{format:$('lyricFormat').value});
$('importLyrics').onclick=()=>$('lyricsFile').click();
$('lyricsFile').onchange=async()=>{
 const f=$('lyricsFile').files?.[0];if(!f)return;
 if(f.size>2000000){$('lyricsImportStatus').textContent='Le fichier doit faire moins de 2 Mo.';return;}
 try{studioTask('lyricsimport',{text:await f.text(),replace:$('replaceLyrics').checked});}
 catch{$('lyricsImportStatus').textContent='Impossible de lire ce fichier.';}
 $('lyricsFile').value='';
};
const oldFeatures=renderFeatures;
renderFeatures=function(){oldFeatures();
 const p=state.project;
 if(document.activeElement!==$('songKey'))$('songKey').value=p.key||'';
 if(document.activeElement!==$('capo'))$('capo').value=p.capo||0;
 $('lockGrid').checked=!!p.gridLocked;
 $('rhythmStatus').textContent=p.analysisNote||(p.gridLocked?'Calage protégé · tes corrections sont conservées':'Calage modifiable');
 document.querySelectorAll('[data-studio-task],#exportStems,#exportLyrics,#importLyrics,#masterForm button,#markDownbeat,#tapTempo,#songKey,#capo,#lockGrid,#exportSheet,#startPhone').forEach(b=>b.disabled=!state.loaded||state.busy);
};
const originalStage=renderStage;
renderStage=function(){originalStage();
 const p=state.project,steps=transport.pitch||0,capo=p.capo||0;
 $('stageKey').textContent=p.key?'Tonalité entendue : '+transposeChord(p.key,steps):'Tonalité à déterminer';
 const chord=(p.chords||[]).find(c=>c.start<=(transport.position||0)&&c.end>(transport.position||0));
 if(chord)$('stageChord').textContent=transposeChord(chord.text,steps-capo)+(capo?' · capo '+capo:'');
};
function wordRow(word){
 const row=node('div','word-edit-row');
 for(const [key,label] of [['start','Début du mot (s)'],['end','Fin du mot (s)'],['text','Mot']]){
  const input=node('input');input.dataset.word=key;input.type=key==='text'?'text':'number';input.value=word[key];input.setAttribute('aria-label',label);
  if(key!=='text'){input.min=0;input.step=.001;}else input.maxLength=120;
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
 $('wordError').textContent='Répartition régulière approximative : ajuste les horaires en écoutant.';
};
$('clearWords').onclick=()=>$('wordRows').replaceChildren();
$('annotationForm').onsubmit=e=>{
 e.preventDefault();const start=Number($('annotationStart').value),end=Number($('annotationEnd').value),words=[];let previous=start;
 for(const row of $('wordRows').children){
  const word={};row.querySelectorAll('[data-word]').forEach(i=>word[i.dataset.word]=i.dataset.word==='text'?i.value.trim():Number(i.value));
  if(!word.text||!Number.isFinite(word.start)||!Number.isFinite(word.end)||word.start<previous||word.end<=word.start||word.end>end){$('wordError').textContent='Les mots doivent se suivre dans les limites de la ligne, sans chevauchement.';return;}
  words.push(word);previous=word.end;
 }
 const text=$('annotationText').value.trim();
 if(words.length&&words.map(w=>w.text).join(' ')!==text.replace(/\s+/g,' ')){$('wordError').textContent='Le texte et les mots diffèrent. Corrige les mots ou retire leurs horaires.';return;}
 send('annotation',{...annotationEdit,text,start,end,...(annotationEdit.kind==='lyrics'?{words}:{})});$('annotationEditor').close();
};

$('exportSheet').onclick=()=>studioTask('sheet',{pitch:transport.pitch||0});
$('splitVocals').onclick=()=>send('creative',{kind:'vocalsplit'});
