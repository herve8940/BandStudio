'use strict';
// Everything stays local until the user copies the reviewed message and posts in Discord.
let supportInfo=null, supportCopying=false, supportTimer=null, supportRequest=0;
const supportPreview=$('supportPreview'), supportStatus=$('supportStatus');
function cleanSupportText(value){
 return String(value||'').trim()
  .replace(/https?:\/\/[^\s<>"']+/gi,'<lien masqué>')
  .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,'<e-mail masqué>')
  .replace(/(?:[A-Z]:[\\/]|\/(?:Users|home|Volumes|private|tmp)\/)[^\r\n<>]+/gi,'<chemin masqué>')
  .replace(/(authorization\s*[:=]\s*)(?:bearer\s+)?[^\r\n,;]+/gi,'$1<masqué>')
  .replace(/((?:token|password|secret|api[_-]?key)["'\s]*[:=]\s*)[^\r\n,;]+/gi,'$1<masqué>')
  .replace(/@/g,'@\u200b').replace(/`/g,'ˋ');
}
function renderSupport(){
 const summary=cleanSupportText($('supportSummary').value), steps=cleanSupportText($('supportSteps').value), expected=cleanSupportText($('supportExpected').value);
 const environment=supportInfo?.environment||'BandStudio · informations système indisponibles';
 const lines=['Incident BandStudio — '+summary,environment,steps?'Pour reproduire :\n'+steps:'',expected?'Résultat attendu :\n'+expected:''];
 if($('supportIncludeDebug').checked&&supportInfo?.debug)lines.push('Diagnostic compact :\n'+supportInfo.debug);
 supportPreview.value=lines.filter(Boolean).join('\n\n');
 const length=supportPreview.value.length;
 $('supportCount').textContent=length+' / 2 000 caractères';
 $('supportTooLong').hidden=length<=2000;
 $('supportCopy').disabled=!summary||length>2000||supportCopying||!supportInfo;
}
function openSupport(){view('support');supportStatus.textContent='';send('supportInfo');renderSupport();}
document.querySelectorAll('[data-support]').forEach(b=>b.onclick=openSupport);
document.querySelectorAll('[data-community]').forEach(b=>b.onclick=()=>send('openCommunity',{destination:b.dataset.community}));
for(const id of ['supportSummary','supportSteps','supportExpected','supportIncludeDebug'])$(id).addEventListener('input',()=>{supportStatus.textContent='';renderSupport();});
$('supportRefresh').onclick=()=>send('supportInfo');
$('supportCopy').onclick=()=>{
 renderSupport();if($('supportCopy').disabled)return;
 supportCopying=true;renderSupport();const request=++supportRequest;
 supportStatus.textContent='Copie du rapport…';
 send('copyDiscordReport',{text:supportPreview.value,request});
 supportTimer=setTimeout(()=>{supportCopying=false;supportStatus.textContent='Pas de confirmation de copie. Sélectionne le rapport, copie-le, puis ouvre le salon des bugs.';supportPreview.focus();supportPreview.select();renderSupport();},8000);
};
const supportReceive=window.studioReceive;
window.studioReceive=data=>{
 if(data.type==='supportInfo'){supportInfo=data;renderSupport();return;}
 if(data.type==='supportCopied'){
  if(data.request!==supportRequest)return;
  clearTimeout(supportTimer);supportCopying=false;
  supportStatus.textContent=data.message;
  if(!data.ok){supportPreview.focus();supportPreview.select();}
  renderSupport();return;
 }
 supportReceive(data);
};
renderSupport();
