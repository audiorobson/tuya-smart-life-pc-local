'use strict';
const adjustmentTimers=new Map();
let activeDragBox=null;
function communicationState(d){
  if(!connected)return 'stale';
  return ({online:'ok',configuracao_pendente:'config',nao_consultado:'waiting',aguardando_evento:'waiting',verificar_chave_ou_protocolo:'auth'})[d.state]||'noresp';
}
function switchControl(d,c,disabled){
  const last=data.last_command,match=last?.id===d.id&&last.control===c.index;
  const status=!connected||!c.enabled?'unavailable':match?last.status:'confirmed';
  const checked=status==='pending'?last.target==='Ligar':c.value===true;
  const label=status==='pending'?'Enviando':status==='unconfirmed'?'Não confirmado':c.value===null?'Sem leitura':c.value?'Ligado':'Desligado';
  return `<div class="channel au-row"><div class="channel-title"><span>${escapeHTML(c.name)}</span><strong>${label}${!connected?' · última leitura':''}</strong></div><button class="au-switch" role="switch" aria-checked="${checked}" data-status="${status}" aria-label="${escapeHTML(d.name)} · ${escapeHTML(c.name)}: ${label}" data-id="${escapeHTML(d.id)}" data-control="${c.index}" data-action="${c.value?'Desligar':'Ligar'}" ${disabled||!c.enabled?'disabled':''}></button></div>`;
}
function adjustment(d,s,disabled){
  const value=s.value??s.limits.min;
  const pct=Math.round(value/s.limits.max*100);
  return `<div class="adjustment" data-adjustment="${escapeHTML(s.dp)}" data-device="${escapeHTML(d.id)}"><div class="adjustment-heading"><span class="au-label">${escapeHTML(s.name)}</span><output>${s.value===null?'—':pct+'%'}</output></div><div class="au-knob" role="slider" tabindex="${disabled||!s.enabled?-1:0}" aria-label="${escapeHTML(s.name)} de ${escapeHTML(d.name)}" aria-valuemin="${s.limits.min}" aria-valuemax="${s.limits.max}" aria-valuenow="${value}" aria-valuetext="${pct}%" aria-disabled="${disabled||!s.enabled}" data-step="${s.limits.step}"><div class="knob-ring"></div><div class="au-knob__face"></div><div class="au-knob__pointer"></div><span class="knob-value" aria-hidden="true">${s.value===null?'—':pct+'%'}</span></div><input class="adjustment-range" aria-label="${escapeHTML(s.name)} deslizante de ${escapeHTML(d.name)}" type="range" min="${s.limits.min}" max="${s.limits.max}" step="${s.limits.step}" value="${value}" ${disabled||!s.enabled?'disabled':''}><small>Arraste ou use as setas para ajustar.</small><span class="adjustment-result au-meta" role="status"></span></div>`;
}
function clampAdjustment(value,min,max,step){return Math.max(min,Math.min(max,min+Math.round((value-min)/step)*step));}
function paintAdjustment(box,value){
  const knob=box.querySelector('.au-knob'),range=box.querySelector('input');
  const pct=Math.round(value/Number(range.max)*100);
  knob.setAttribute('aria-valuenow',value);knob.setAttribute('aria-valuetext',pct+'%');
  knob.style.setProperty('--au-angle',(-135+270*(value-Number(range.min))/(Number(range.max)-Number(range.min)))+'deg');
  box.querySelector('output').textContent=pct+'%';box.querySelector('.knob-value').textContent=pct+'%';range.value=value;
}
function paintAdjustments(){document.querySelectorAll('.adjustment').forEach(box=>{const range=box.querySelector('input');paintAdjustment(box,Number(range.value));});}
function enforceControlAvailability(unavailable){
  document.querySelectorAll('#devices [data-action]').forEach(b=>{const d=data.devices.find(d=>d.id===b.dataset.id),c=d?.controls.find(c=>c.index===Number(b.dataset.control));b.disabled=unavailable||!c?.enabled;});
  document.querySelectorAll('.adjustment').forEach(box=>{
    const s=data.devices.find(d=>d.id===box.dataset.device)?.settings.find(s=>s.dp===box.dataset.adjustment);
    const blocked=unavailable||!s?.enabled,knob=box.querySelector('.au-knob');
    knob.setAttribute('aria-disabled',String(blocked));knob.tabIndex=blocked?-1:0;box.querySelector('input').disabled=blocked;
    const command=data.last_command;
    box.querySelector('.adjustment-result').textContent=command?.id===box.dataset.device&&command.dp===box.dataset.adjustment?({pending:'Enviando…',confirmed:'Valor confirmado',unconfirmed:'Resultado não confirmado'})[command.status]:!s?.enabled?'Aguardando leitura válida':'';
    if(!unavailable&&!adjustmentTimers.has(box)&&box!==activeDragBox&&s?.value!==null&&s?.value!==undefined)paintAdjustment(box,s.value);
    if(s?.value===null){box.querySelector('output').textContent='—';box.querySelector('.knob-value').textContent='—';knob.setAttribute('aria-valuetext','Sem leitura');}
  });
  document.querySelectorAll('.setting-form').forEach(form=>{const s=data.devices.find(d=>d.id===form.dataset.device)?.settings.find(s=>s.dp===form.dataset.dp);form.querySelector('fieldset').disabled=unavailable||!s?.enabled;});
  document.querySelectorAll('#devices [data-read],#devices [data-favorite],#devices [data-pair]').forEach(b=>{b.disabled=unavailable||Boolean(b.dataset.pair&&!data.cloud_available);});
  if(unavailable){adjustmentTimers.forEach(clearTimeout);adjustmentTimers.clear();}
}
async function sendAdjustment(box){
  const knob=box.querySelector('.au-knob');if(knob.getAttribute('aria-disabled')==='true')return;
  await post('/api/setting',{id:box.dataset.device,dp:box.dataset.adjustment,value:Number(knob.getAttribute('aria-valuenow'))});
}
document.addEventListener('DOMContentLoaded',()=>{
  const root=document.body,sidebar=document.querySelector('.sidebar');
  let prefs={};try{prefs=JSON.parse(localStorage.getItem('ativ-appearance')||'{}');}catch{}
  if(['auto','light','dark'].includes(prefs.theme))root.dataset.auTheme=prefs.theme;
  if(['ciano','verde','ambar','violeta','azul'].includes(prefs.accent))root.dataset.auAccent=prefs.accent;
  $('theme-select').value=root.dataset.auTheme;$('accent-select').value=root.dataset.auAccent;
  function appearance(){root.dataset.auTheme=$('theme-select').value;root.dataset.auAccent=$('accent-select').value;try{localStorage.setItem('ativ-appearance',JSON.stringify({theme:root.dataset.auTheme,accent:root.dataset.auAccent}));}catch{}}
  $('theme-select').onchange=appearance;$('accent-select').onchange=appearance;
  $('device-editor').addEventListener('close',()=>{
    const card=[...document.querySelectorAll('[data-device-card]')].find(c=>c.dataset.deviceCard===selectedDevice);
    card?.querySelector('[data-details]')?.focus();
  });
  $('scene-editor').addEventListener('close',()=>$('new-scene').focus());
  function collapse(value){sidebar.dataset.collapsed=String(value);$('menu-toggle').setAttribute('aria-expanded',String(!value));$('menu-toggle').setAttribute('aria-label',value?'Expandir menu':'Recolher menu');}
  collapse(matchMedia('(max-width:720px)').matches);
  $('menu-toggle').onclick=()=>collapse(sidebar.dataset.collapsed!=='true');
  document.querySelectorAll('[data-filter]').forEach(b=>{b.setAttribute('aria-label',b.textContent.trim());b.title=b.textContent.trim();b.setAttribute('aria-current',String(b.classList.contains('active')));b.onclick=()=>{if(matchMedia('(max-width:720px)').matches)collapse(true);};});
  const devices=$('devices');let drag=null;
  devices.addEventListener('pointerdown',event=>{
    const knob=event.target.closest('.au-knob');if(!knob||knob.getAttribute('aria-disabled')==='true'||event.button!==0)return;
    event.preventDefault();knob.focus();knob.setPointerCapture(event.pointerId);
    drag={knob,box:knob.closest('.adjustment'),x:event.clientX,y:event.clientY,value:Number(knob.getAttribute('aria-valuenow')),pointer:event.pointerId};
    activeDragBox=drag.box;
    const timer=adjustmentTimers.get(drag.box);if(timer)clearTimeout(timer);adjustmentTimers.delete(drag.box);
  });
  devices.addEventListener('pointermove',event=>{
    if(!drag||drag.pointer!==event.pointerId)return;
    const {knob,box}=drag;if(knob.getAttribute('aria-disabled')==='true')return;
    const min=Number(knob.getAttribute('aria-valuemin')),max=Number(knob.getAttribute('aria-valuemax'));
    paintAdjustment(box,clampAdjustment(drag.value+(event.clientX-drag.x+drag.y-event.clientY)*(max-min)/220,min,max,Number(knob.dataset.step)));
  });
  devices.addEventListener('pointerup',event=>{if(!drag||event.pointerId!==drag.pointer)return;const previous=drag;drag=null;activeDragBox=null;if(Number(previous.knob.getAttribute('aria-valuenow'))!==previous.value)sendAdjustment(previous.box);});
  devices.addEventListener('pointercancel',()=>{if(drag)paintAdjustment(drag.box,drag.value);drag=null;activeDragBox=null;});
  devices.addEventListener('keydown',event=>{
    const knob=event.target.closest('.au-knob');if(!knob||knob.getAttribute('aria-disabled')==='true')return;
    const min=Number(knob.getAttribute('aria-valuemin')),max=Number(knob.getAttribute('aria-valuemax')),step=Number(knob.dataset.step),value=Number(knob.getAttribute('aria-valuenow'));
    const values={ArrowUp:value+step,ArrowRight:value+step,ArrowDown:value-step,ArrowLeft:value-step,PageUp:value+(max-min)/10,PageDown:value-(max-min)/10,Home:min,End:max};
    if(!(event.key in values))return;event.preventDefault();const box=knob.closest('.adjustment');paintAdjustment(box,clampAdjustment(values[event.key],min,max,step));schedule(box);
  });
  function schedule(box){clearTimeout(adjustmentTimers.get(box));adjustmentTimers.set(box,setTimeout(()=>{adjustmentTimers.delete(box);sendAdjustment(box);},600));}
  devices.addEventListener('keydown',e=>{if(e.target.matches('.adjustment-range'))e.target.dataset.keyboard='true';});
  devices.addEventListener('pointerdown',e=>{if(e.target.matches('.adjustment-range')){delete e.target.dataset.keyboard;activeDragBox=e.target.closest('.adjustment');}});
  devices.addEventListener('input',e=>{if(e.target.matches('.adjustment-range'))paintAdjustment(e.target.closest('.adjustment'),Number(e.target.value));});
  devices.addEventListener('change',e=>{if(e.target.matches('.adjustment-range')){const box=e.target.closest('.adjustment');activeDragBox=null;if(e.target.dataset.keyboard)schedule(box);else sendAdjustment(box);}});
});
