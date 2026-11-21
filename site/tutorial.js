'use strict';
(() => {
 const steps=[...document.querySelectorAll('[data-step]')],links=[...document.querySelectorAll('[data-step-link]')];
 const previous=document.getElementById('tutorialPrevious'),next=document.getElementById('tutorialNext'),status=document.getElementById('tutorialStatus');
 if(!steps.length)return;
 let current=0;
 function show(index,remember=true){
  if(!Number.isInteger(index)||index<0||index>=steps.length)return;
  current=index;steps.forEach((s,i)=>s.hidden=i!==current);
  links.forEach((link,i)=>{if(i===current)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});
  previous.disabled=current===0;next.disabled=current===steps.length-1;
  status.textContent=(document.documentElement.lang==='fr'?'Étape ':'Step ')+(current+1)+' / '+steps.length;
  if(remember)history.replaceState(null,'','#step-'+(current+1));
 }
 links.forEach((link,i)=>link.addEventListener('click',e=>{e.preventDefault();show(i);}));
 previous.addEventListener('click',()=>show(current-1));next.addEventListener('click',()=>show(current+1));
 document.querySelector('.tutorial-controls').hidden=false;
 const fromHash=()=>{const match=location.hash.match(/^#step-(\d+)$/);show(match?Number(match[1])-1:0,false);};
 window.addEventListener('hashchange',fromHash);fromHash();
})();
