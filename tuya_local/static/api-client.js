'use strict';
// Transporte independente da interface. Nenhum comando é repetido automaticamente.
const PanelAPI = (()=>{
  let token='';
  async function request(path,options={}){
    const response=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(5000),...options});
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'Serviço indisponível.');
    return body;
  }
  return Object.freeze({
    async state(){const state=await request('/api/state');token=state.token;return state;},
    send(path,payload){return request(path,{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(payload)});}
  });
})();
