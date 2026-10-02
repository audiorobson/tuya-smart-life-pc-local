'use strict';
let data = null;
let filter = 'all';
let connected = false;
let sending = false;
let lastMarkup = '';
let errorMessage = '';
const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {online:'Respondendo', configuracao_pendente:'Pendente', nao_consultado:'Aguardando leitura', aguardando_evento:'Sem resposta recente', sem_resposta:'Sem resposta', falha_conexao:'Falha de conexão', inacessivel:'Não acessível', verificar_chave_ou_protocolo:'Verificar acesso', erro_protocolo:'Erro de comunicação', nao_suportado:'Não suportado'};
const titles = {favorites:'Favoritos',all:'Todos os dispositivos',control:'Iluminação e relés',gateway:'Gateways e painéis',sensor:'Sensores',pending:'Equipamentos pendentes'};
function isGateway(d){return ['gateway','panel'].includes(d.kind);}
function isSensor(d){return ['wsdcg','pir','mcs','sj','wxkg'].includes(d.category);}
function timeLabel(value){return value ? new Date(value).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit',second:'2-digit'}) : 'Ainda sem leitura';}
function render(){
  if(!data)return;
  renderInventory();
  const devices=data.devices;
  $('total').textContent=devices.length;
  $('online').textContent=devices.filter(d=>d.state==='online').length;
  $('controllable').textContent=devices.filter(d=>d.controls.some(c=>c.enabled)).length;
  $('gateways').textContent=devices.filter(isGateway).length;
  const unavailable=!connected||data.busy||sending;
  $('refresh').disabled=unavailable;
  if(connected){$('notice').classList.toggle('error',Boolean(errorMessage));$('notice-text').textContent=errorMessage||(data.busy?data.operation:'Serviço local conectado. Consultas automáticas a cada minuto; acionamentos somente por você.');}
  const query=$('search').value.trim().toLocaleLowerCase();
  const filtered=devices.filter(d=>{
    const matches=filter==='all'||(filter==='favorites'&&d.favorite)||(filter==='control'&&d.controls.length)||(filter==='gateway'&&isGateway(d))||(filter==='sensor'&&isSensor(d))||(filter==='pending'&&d.state!=='online');
    const room=$('room-filter').value;
    const matchesRoom=!room||(room==='__unassigned'?!d.room:d.room===room);
    return matches&&matchesRoom&&`${d.name} ${d.parent_name} ${d.room} ${d.id} ${d.category} ${names[d.state]||d.state}`.toLocaleLowerCase().includes(query);
  }).sort((a,b)=>Number(b.favorite)-Number(a.favorite)||(a.state==='online'?0:1)-(b.state==='online'?0:1)||a.name.localeCompare(b.name,'pt-BR'));
  $('section-title').textContent=titles[filter];
  $('results-count').textContent=`${filtered.length} equipamento${filtered.length===1?'':'s'}`;
  const markup=filtered.map(d=>{
    const badge=d.state==='online'?'online':d.state==='configuracao_pendente'?'warning':'';
    const connection=d.parent_name?`Via ${d.parent_name}`:d.kind==='zigbee'?'Gateway não associado':'Conexão direta · rede local';
    const icon=isGateway(d)?'⌘':isSensor(d)?'◇':'◉';
    const controls=d.controls.map(c=>switchControl(d,c,unavailable)).join('');
    const readings=d.readings.map(r=>`<div class="reading au-inset ${r.stale||!connected?'au-inset--stale':''}"><small>${escapeHTML(r.name)}${(r.stale||!connected)&&r.available?' · última leitura':''}</small><strong>${escapeHTML(r.value)}</strong><em>${escapeHTML(r.unit)}</em></div>`).join('');
    const hint=d.detail||(isGateway(d)?`${d.children} dispositivos vinculados · ${d.kind==='panel'?'Painel inteligente':'Gateway'}`:!controls&&!readings?'Somente leitura nesta versão.':'');
    return `<article class="card au-card" aria-label="${escapeHTML(d.name)}" data-device-card="${escapeHTML(d.id)}"><div class="card-top"><div class="device-icon" aria-hidden="true">${icon}</div><button class="au-btn au-icon-btn favorite-button" data-favorite="${escapeHTML(d.id)}" aria-label="${d.favorite?'Remover dos':'Adicionar aos'} favoritos: ${escapeHTML(d.name)}" aria-pressed="${d.favorite}" ${unavailable?'disabled':''}>${d.favorite?'★':'☆'}</button><span class="au-chip" data-state="${communicationState(d)}"><span class="au-dot"></span>${escapeHTML(!connected?'Último estado conhecido':names[d.state]||d.state)}</span></div><h3>${escapeHTML(d.name)}</h3><p class="connection">${escapeHTML(connection)}${d.room?` · ${escapeHTML(d.room)}`:''}</p>${readings?`<div class="readings">${readings}</div>`:''}${hint?`<p class="hint">${escapeHTML(hint)}</p>`:''}<div class="controls">${controls}</div>${deviceFeatures(d,unavailable)}<div class="card-bottom"><button class="au-btn au-btn--link au-btn--sm read-button" data-details="${escapeHTML(d.id)}">Detalhes / organizar</button><span class="last-seen">${d.last_seen?'Leitura às ':''}${escapeHTML(timeLabel(d.last_seen))}</span><button class="au-btn au-btn--link au-btn--sm read-button" data-read="${escapeHTML(d.id)}" ${unavailable?'disabled':''}>↻ Consultar</button></div></article>`;
  }).join('')||'<p class="empty">Nenhum dispositivo encontrado neste filtro.</p>';
  // Evita recriar botões e perder foco quando o snapshot não mudou.
  const editing=$('devices').contains(document.activeElement)&&document.activeElement.matches('input,select,[role=slider]');
  if(markup!==lastMarkup&&(!editing||!connected)){
    const openDetails=[...$('devices').querySelectorAll('details[open]')].map(d=>({id:d.closest('[data-device-card]').dataset.deviceCard,index:[...d.parentElement.querySelectorAll('details')].indexOf(d)}));
    $('devices').innerHTML=markup;lastMarkup=markup;
    openDetails.forEach(info=>{const card=[...$('devices').children].find(c=>c.dataset.deviceCard===info.id);const el=card?.querySelectorAll('details')[info.index];if(el)el.open=true;});
    paintAdjustments();
  }
  enforceControlAvailability(unavailable);
  renderFeatures(unavailable);
  $('activity').innerHTML=data.activity.slice(0,6).map(a=>`<li class="${a.level==='error'?'error':''}"><time>${escapeHTML(timeLabel(a.time))}</time>${escapeHTML(a.text)}</li>`).join('')||'<li>Aguardando a primeira consulta.</li>';
}
async function poll(){
  try{
    data=await PanelAPI.state();connected=true;render();
  }catch(error){connected=false;render();$('notice').classList.add('error');$('notice-text').textContent='Serviço desconectado. Os controles estão desabilitados; tentando reconectar…';}
  setTimeout(poll,2000);
}
async function post(path,payload){
  if(!connected||sending||data.busy){
    errorMessage='Aguarde o serviço ficar disponível e tente novamente. Nenhum novo comando foi enviado.';
    render();return;
  }
  if(path==='/api/command')data.last_command={id:payload.id,control:payload.control,status:'pending',target:payload.action};
  if(path==='/api/setting')data.last_command={id:payload.id,dp:payload.dp,status:'pending',target:payload.value};
  sending=true;errorMessage='';render();
  let accepted=false;
  try{
    await PanelAPI.send(path,payload);
    data.busy=true;data.operation='Operação recebida. Aguardando o equipamento…';
    accepted=true;
  }catch(error){errorMessage=error.name==='TimeoutError'?'O serviço demorou a responder. Consulte o estado antes de repetir um comando.':error.message;}
  finally{sending=false;if(!accepted&&data.last_command?.status==='pending')data.last_command.status='unconfirmed';render();}
  return accepted;
}
$('refresh').addEventListener('click',()=>post('/api/refresh',{}));
$('search').addEventListener('input',render);
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
  filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>(b.classList.toggle('active',b===button),b.setAttribute('aria-current',String(b===button))));render();
}));
$('devices').addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button||button.disabled)return;
  if(button.dataset.read){post('/api/status',{id:button.dataset.read});return;}
  if(button.dataset.action)post('/api/command',{id:button.dataset.id,control:Number(button.dataset.control),action:button.dataset.action});
});
poll();
