'use strict';
let selectedDevice=null;
function renderInventory(){
  const rooms=$('room-filter');
  const previous=rooms.value;
  const options='<option value="">Todos os ambientes</option><option value="__unassigned">Sem ambiente</option>'+data.rooms.map(r=>`<option value="${escapeHTML(r)}">${escapeHTML(r)}</option>`).join('');
  if(rooms.innerHTML!==options){rooms.innerHTML=options;rooms.value=previous;if(rooms.selectedIndex<0)rooms.value='';}
  document.querySelector('.scene-section').hidden=!data.features.scenes_ui;
  if($('device-editor').open)renderCloudSnapshot();
}
function showDevice(id){
  const d=data.devices.find(d=>d.id===id);if(!d)return;
  selectedDevice=id;
  $('device-title').textContent=d.name;
  $('device-name').value=d.name;$('device-room').value=d.room;
  $('device-favorite').checked=d.favorite;
  $('device-message').textContent='';
  const childDevices=data.devices.filter(c=>c.parent===id);
  const fields=[['Estado',names[d.state]||d.state],['Identificador',d.id],['Categoria',d.category||'Não identificada'],['Endereço local',d.ip||'Não encontrado'],['Conexão',d.parent_name?'Via '+d.parent_name:'Direta pela rede local'],['Última resposta',timeLabel(d.last_seen)],['Controles disponíveis',d.controls.filter(c=>c.enabled).length+' de '+d.controls.length],['Configurações disponíveis',d.settings.filter(s=>s.enabled).length+' de '+d.settings.length],['Pendência',d.detail||d.integration.blocker||'Nenhuma pendência de controle identificada']];
  $('device-diagnostics').innerHTML=fields.map(([name,value])=>`<dt>${escapeHTML(name)}</dt><dd>${escapeHTML(value)}</dd>`).join('');
  $('device-children').innerHTML=childDevices.length?'<h3>Dispositivos vinculados</h3><ul>'+childDevices.map(c=>`<li>${escapeHTML(c.name)} — ${escapeHTML(names[c.state]||c.state)}</li>`).join('')+'</ul>':'';
  $('device-resources').innerHTML='<h3>Recursos identificados</h3><ul>'+[...d.readings.map(r=>`${r.name}: ${r.value}${r.unit?' '+r.unit:''}${r.stale&&r.available?' (última leitura)':''}`),...d.settings.map(s=>`${s.name}: ${s.enabled?'disponível':'aguardando leitura'}`)].map(t=>`<li>${escapeHTML(t)}</li>`).join('')+'</ul>';
  $('cloud-read-device').disabled=!data.cloud_available||data.busy||!connected;
  renderCloudSnapshot();
  $('device-editor').showModal();
}
function renderCloudSnapshot(){
  const d=data.devices.find(d=>d.id===selectedDevice);if(!d)return;
  const snapshot=d.cloud_snapshot;
  $('cloud-read-device').disabled=!data.cloud_available||data.busy||!connected||sending;
  $('device-cloud-readings').innerHTML=snapshot?`<p class="muted">Consulta às ${escapeHTML(timeLabel(snapshot.queried_at))}. Últimos valores conhecidos pela Tuya; horário de medição não informado.</p>`+snapshot.readings.map(r=>`<p>${escapeHTML(r.name)}: ${escapeHTML(r.value)} ${escapeHTML(r.unit)}</p>`).join(''):'<p class="muted">Nenhuma consulta nesta sessão. A leitura da nuvem não confirma resposta local.</p>';
}
document.addEventListener('DOMContentLoaded',()=>{
  $('room-filter').onchange=render;
  $('close-device').onclick=()=>$('device-editor').close();
  $('cloud-read-device').onclick=()=>post('/api/cloud-status',{id:selectedDevice});
  $('device-form').onsubmit=async event=>{
    event.preventDefault();
    const ok=await post('/api/metadata',{id:selectedDevice,name:$('device-name').value,room:$('device-room').value,favorite:$('device-favorite').checked});
    if(ok)$('device-editor').close();else $('device-message').textContent=errorMessage;
  };
  $('devices').addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.details)showDevice(b.dataset.details);
    if(b.dataset.favorite){const d=data.devices.find(d=>d.id===b.dataset.favorite);post('/api/metadata',{id:d.id,favorite:!d.favorite});}
  });
  $('export-inventory').onclick=()=>{
    if(!data)return;
    const report={api_version:data.api_version,exported_at:new Date().toISOString(),devices:data.devices};
    const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download='inventario-painel.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
});
