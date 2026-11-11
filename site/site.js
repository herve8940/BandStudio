'use strict';
const labels=document.documentElement.lang==='en'?['Vocals','Guitar','Bass','Drums']:['Chant','Guitare','Basse','Batterie'];
const stems=[['vocals',labels[0],'#dcb18d'],['guitar',labels[1],'#879ff0'],['bass',labels[2],'#62cabe'],['drums',labels[3],'#b58ce9']];
for(const [role,label,color] of stems){
 const row=document.createElement('div');row.className='stem';row.dataset.role=role;row.style.setProperty('--stem',color);
 const name=document.createElement('span');name.className='stem-label';const mark=document.createElement('i');name.append(mark,document.createTextNode(label));
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 400 48');svg.setAttribute('aria-hidden','true');svg.setAttribute('preserveAspectRatio','none');
 const path=document.createElementNS(svg.namespaceURI,'path');let d='';const seed=stems.findIndex(x=>x[0]===role)+1;
 for(let x=0;x<400;x+=3){const a=2+Math.abs(Math.sin(x*.19+seed)*Math.cos(x*.039+seed*.6))*(10+9*Math.abs(Math.sin(x*.012)));d+=`M${x} ${24-a}v${a*2} `;}
 path.setAttribute('d',d);svg.append(path);row.append(name,svg);document.getElementById('demoStems').append(row);
}
document.querySelectorAll('[data-mix]').forEach(button=>button.addEventListener('click',()=>{
 document.querySelectorAll('[data-mix]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});
 document.querySelectorAll('.stem').forEach(row=>row.classList.toggle('dimmed',button.dataset.mix==='minus'?row.dataset.role==='guitar':button.dataset.mix==='solo'?row.dataset.role!=='guitar':false));
}));
