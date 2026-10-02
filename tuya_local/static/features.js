'use strict';
let editingScene=null;
function valueInput(s, id, value=s.value){
  const attr=`id="${escapeHTML(id)}" aria-label="${escapeHTML(s.name)}"`;
  if(s.type==='Boolean')return `<select ${attr}><option value="true" ${value===true?'selected':''}>Ligado</option><option value="false" ${value!==true?'selected':''}>Desligado</option></select>`;
  if(s.type==='Enum')return `<select ${attr}>${s.limits.range.map(v=>`<option ${v===value?'selected':''} value="${escapeHTML(v)}">${escapeHTML(v)}</option>`).join('')}</select>`;
  return `<input ${attr} type="number" min="${s.limits.min}" max="${s.limits.max}" step="${s.limits.step}" value="${value??s.limits.min}" required>`;
}
function typedValue(s,element){return s.type==='Boolean'?element.value==='true':s.type==='Integer'?Number(element.value):element.value;}
function deviceFeatures(d,disabled){
  const continuous=d.settings.filter(s=>['bright_value_1','voice_vol'].includes(s.code));
  let html=continuous.map(s=>adjustment(d,s,disabled)).join('');
  const settings=d.settings.filter(s=>!continuous.includes(s));
  if(settings.length)html+=`<details><summary>Configurações (${settings.length})</summary>${settings.map(s=>`<form class="setting-form" data-device="${escapeHTML(d.id)}" data-dp="${s.dp}"><label>${escapeHTML(s.name)}${s.limits.unit?' ('+escapeHTML(s.limits.unit)+')':''}</label><fieldset ${disabled||!s.enabled?'disabled':''}>${valueInput(s,`setting-${d.id}-${s.dp}`)}<button class="au-btn secondary" type="submit">Aplicar</button></fieldset><small>${!s.enabled?'Aguardando leitura local deste recurso.':escapeHTML(s.code)}</small></form>`).join('')}</details>`;
  if(isGateway(d))html+=`<details><summary>Adicionar dispositivos Zigbee</summary><p class="muted">Solicita à nuvem Tuya uma janela de pareamento. Requer permissão da API e suporte do gateway. Coloque o acessório em modo de pareamento conforme o fabricante.</p><p class="muted">${d.pairing_until*1000>Date.now()?'Solicitação aceita; janela de busca em andamento.':'Compatibilidade de pareamento ainda depende da resposta do equipamento.'}</p><div class="switch-actions"><button data-pair="${escapeHTML(d.id)}" data-duration="60" ${disabled||!data.cloud_available?'disabled':''}>Buscar por 60s</button><button data-pair="${escapeHTML(d.id)}" data-duration="0" ${disabled||!data.cloud_available?'disabled':''}>Parar busca</button></div><p class="muted">Após vincular, clique em Sincronizar cadastro Tuya para importar o novo acessório.</p></details>`;
  return html;
}
function renderFeatures(disabled){
  $('new-scene').disabled=disabled;
  $('discover').disabled=disabled;
  $('sync').disabled=disabled||!data.cloud_available;
  $('cloud-scenes').disabled=disabled||!data.cloud_available;
  $('cloud-message').textContent=data.cloud_message;
  $('scenes').innerHTML=data.scenes.map(s=>`<article class="card"><h3>${escapeHTML(s.name)}</h3><p class="muted">${s.steps.length} ações · execução local</p><div class="switch-actions"><button data-scene-run="${s.scene_id}" ${disabled?'disabled':''}>Executar</button><button data-scene-edit="${s.scene_id}" ${disabled?'disabled':''}>Editar</button><button data-scene-delete="${s.scene_id}" ${disabled?'disabled':''}>Excluir</button></div></article>`).join('')||'<p class="muted">Nenhuma cena local criada.</p>';
  $('cloud-scene-list').innerHTML=data.cloud_scenes.map(s=>`<article class="card"><h3>${escapeHTML(s.name)}</h3><button class="au-btn secondary" data-cloud-run="${escapeHTML(s.scene_id)}" data-home="${escapeHTML(s.home_id)}" ${disabled?'disabled':''}>Executar pela Tuya</button></article>`).join('');
}
function stepOptions(d){return [...d.controls.map(c=>({key:'c'+c.index,name:c.name,type:'Boolean',limits:{},control:c.index})),...d.settings.map(s=>({...s,key:'s'+s.dp}))];}
function fillStep(row,step){
  const d=data.devices.find(d=>d.id===row.querySelector('.step-device').value);
  const options=stepOptions(d), select=row.querySelector('.step-function');
  select.innerHTML=options.map(s=>`<option value="${s.key}">${escapeHTML(s.name)}</option>`).join('');
  if(step)select.value='dp'in step?'s'+step.dp:'c'+step.control;
  fillValue(row,step);
}
function fillValue(row,step){
  const d=data.devices.find(d=>d.id===row.querySelector('.step-device').value);
  const s=stepOptions(d).find(s=>s.key===row.querySelector('.step-function').value);
  row.querySelector('.step-value').innerHTML=valueInput(s,'scene-value-'+row.dataset.row,step?('dp'in step?step.value:step.action==='Ligar'):undefined);
}
let rowCounter=0;
function addStep(step){
  const eligible=data.devices.filter(d=>d.controls.length||d.settings.length);
  if(!eligible.length){$('scene-error').textContent='Nenhum equipamento com perfil de controle disponível.';return;}
  const row=document.createElement('div');row.className='scene-step';row.dataset.row=++rowCounter;
  row.innerHTML=`<label>Dispositivo<select class="step-device">${eligible.map(d=>`<option value="${escapeHTML(d.id)}">${escapeHTML(d.name)}</option>`).join('')}</select></label><label>Função<select class="step-function"></select></label><div class="step-value"></div><button type="button" class="secondary remove-step">Remover ação</button>`;
  $('scene-steps').append(row);
  if(step)row.querySelector('.step-device').value=step.id;
  fillStep(row,step);
  row.querySelector('.step-device').onchange=()=>fillStep(row);
  row.querySelector('.step-function').onchange=()=>fillValue(row);
  row.querySelector('.remove-step').onclick=()=>row.remove();
}
function editScene(scene){
  editingScene=scene?.scene_id||null;$('scene-name').value=scene?.name||'';$('scene-steps').innerHTML='';$('scene-error').textContent='';
  $('scene-title').textContent=scene?'Editar cena local':'Criar cena local';
  if(scene)scene.steps.forEach(addStep);else addStep();
  $('scene-editor').showModal();
}
document.addEventListener('DOMContentLoaded',()=>{
  $('new-scene').onclick=()=>editScene(null);
  $('add-step').onclick=()=>addStep();
  $('close-editor').onclick=()=>$('scene-editor').close();
  $('cloud-scenes').onclick=()=>post('/api/cloud-scenes',{});
  $('discover').onclick=()=>post('/api/discover',{});
  $('sync').onclick=()=>post('/api/sync',{});
  $('scene-form').onsubmit=async event=>{
    event.preventDefault();
    const steps=[...$('scene-steps').children].map(row=>{
      const id=row.querySelector('.step-device').value,d=data.devices.find(d=>d.id===id);
      const s=stepOptions(d).find(s=>s.key===row.querySelector('.step-function').value);
      const value=typedValue(s,row.querySelector('.step-value input,.step-value select'));
      return s.dp?{id,dp:s.dp,value}:{id,control:s.control,action:value?'Ligar':'Desligar'};
    });
    if(!steps.length){$('scene-error').textContent='Adicione pelo menos uma ação.';return;}
    if(await post('/api/scene-save',{scene_id:editingScene,name:$('scene-name').value,steps}))$('scene-editor').close();
    else $('scene-error').textContent=errorMessage;
  };
  document.addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.sceneEdit)editScene(data.scenes.find(s=>s.scene_id===b.dataset.sceneEdit));
    if(b.dataset.sceneRun)post('/api/scene-run',{scene_id:b.dataset.sceneRun});
    if(b.dataset.sceneDelete)post('/api/scene-delete',{scene_id:b.dataset.sceneDelete});
    if(b.dataset.cloudRun)post('/api/cloud-run',{scene_id:b.dataset.cloudRun,home_id:b.dataset.home});
    if(b.dataset.pair)post('/api/pair',{id:b.dataset.pair,duration:Number(b.dataset.duration)});
  });
  $('devices').addEventListener('submit',event=>{
    const f=event.target.closest('.setting-form');if(!f)return;event.preventDefault();
    const d=data.devices.find(d=>d.id===f.dataset.device),s=d.settings.find(s=>s.dp===f.dataset.dp);
    post('/api/setting',{id:d.id,dp:s.dp,value:typedValue(s,f.querySelector('input,select'))});
  });
});
