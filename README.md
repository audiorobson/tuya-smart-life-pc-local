
# Tuya Smart-life PC Local

## Painel web local

### Etapa atual: dispositivos e preparação da interface

### Interface aplicada a partir de `design`

O painel utiliza o `automacao-ui.css` da pasta
`design/Suite de elementos web reutilizáveis/automacao-ui-kit`, seguindo o README
e o Guia de Componentes. O `support.js` e os dados simulados do protótipo não são
carregados no painel real. Figtree e JetBrains Mono são fontes variáveis servidas
localmente, com suas licenças OFL ao lado dos arquivos em `tuya_local/static`.

Tema claro, escuro ou sistema e cinco acentos ficam nos seletores do cabeçalho;
a preferência visual é salva no navegador. O menu pode ser recolhido e começa
recolhido em telas estreitas. Cards usam estados com texto e forma, favoritos,
chaves de canal, leituras em relevo e detalhes técnicos na ficha do dispositivo.

`controls.js` integra os componentes visuais ao contrato existente. Knobs de
brilho e volume aceitam arraste, setas, Home/End e PageUp/PageDown; enviam ao
soltar ou após 600 ms sem novas teclas. O slider oferece uma alternativa ao knob.
`last_command` em `/api/state` informa alvo e estado `pending`, `confirmed` ou
`unconfirmed`; aceitação HTTP não é exibida como confirmação do equipamento.
Na perda da conexão os comandos ficam bloqueados e os valores passam a ser
identificados como último estado conhecido. Ajustes de tema não enviam comandos.

A instrução anterior do usuário de enviar comandos individuais sem confirmação
permanece aplicada. Cenas continuam ocultas e não foram ampliadas nesta etapa.
O visual usa `automacao-ui.css` (kit), `style.css` (layout e integração) e
`theme.css` (ajustes locais). Tokens `--au-*` substituem os antigos `--panel-*`.

A evolução de cenas foi adiada. O módulo existente e seus arquivos continuam
preservados, mas a seção está oculta por `features.scenes_ui=false` na resposta
do serviço. Nenhuma assinatura ou alteração de cenas é necessária para esta etapa.

O painel permite favoritar equipamentos, definir nome local e ambiente, filtrar
por ambiente, consultar detalhes e visualizar filhos de gateways. Essas preferências
são persistidas em `config.local.json` e não renomeiam dispositivos no Smart Life.
O inventário pode ser exportado em JSON sem chaves, token do serviço ou credenciais.
Na ficha, **Consultar leituras Tuya** faz uma consulta manual à nuvem e mostra apenas
as leituras permitidas. São os últimos valores conhecidos pelo serviço, com horário
da consulta, não da medição. Esse retorno não marca o dispositivo como disponível
na LAN nem habilita controles locais; a consulta depende das permissões do projeto.

As leituras incluem temperatura, umidade, bateria, contato de porta, movimento,
água, carga, modo do alarme e eventos de botão, conforme o mapeamento de cada
equipamento. Recursos sem resposta mostram **Sem leitura**; valores anteriores
são identificados como última leitura. Contatos booleanos são apresentados como
Ativo/Inativo, sem presumir a polaridade física de cada modelo. As leituras não
habilitam novos comandos de alarme, fechadura ou controle infravermelho.

### Contrato para a próxima interface gráfica

- `tuya_local/presentation.py`: transforma dados do equipamento em leituras e
  capacidades públicas, sem depender de HTML ou estilos.
- `tuya_local/static/api-client.js`: centraliza `GET /api/state` e POSTs com token,
  timeout e erros. Escritas não são repetidas automaticamente.
- `tuya_local/static/inventory.js`: organização, favoritos, ficha e exportação.
- `tuya_local/static/features.js`: componentes de configurações e pareamento;
  contém o módulo de cenas preservado para uma etapa futura.
- `tuya_local/static/app.js`: filtros, renderização dos cards e ciclo de atualização.
- `tuya_local/static/automacao-ui.css`: tokens e componentes do kit fornecido.
  `style.css` integra o layout e `theme.css` contém os ajustes locais de tema.

`GET /api/state` retorna `api_version: 1`, `features`, `rooms`, `busy`, `operation`,
`activity`, `devices` e o token antifalsificação. Em cada dispositivo:

| Campo | Uso na interface |
| --- | --- |
| `id`, `name`, `room`, `favorite` | Identidade e organização |
| `state`, `detail`, `last_seen` | Disponibilidade e diagnóstico |
| `parent`, `parent_name`, `children` | Relações entre gateway e acessórios |
| `controls[]` | Canal, índice, ações, valor e disponibilidade |
| `settings[]` | DP autorizado, tipo, limites, valor e disponibilidade |
| `readings[]` | Código, nome, valor, unidade, `available`, `stale` e `widget` |
| `integration` | Transporte, contagem de recursos, bloqueio e pareamento |

`widget` sugere `metric` ou `status`; a nova interface pode trocar o componente.
Knobs e sliders devem respeitar min/max/step do servidor e enviar somente ao
concluir a interação. O retorno HTTP 202 significa operação aceita na fila,
não execução confirmada. A conclusão aparece em `activity` e nas novas leituras.
Bloquear novos envios enquanto `busy`, desconectado ou `enabled=false`.

POSTs usam JSON e cabeçalho `X-Local-Token`:

| Endpoint | Corpo |
| --- | --- |
| `/api/metadata` | `{id, name?, room?, favorite?}`; somente organização local |
| `/api/status` | `{id}` |
| `/api/cloud-status` | `{id}`; leitura opcional da nuvem, separada em `cloud_snapshot` |
| `/api/command` | `{id, control, action}`; ações fornecidas no snapshot |
| `/api/setting` | `{id, dp, value}`; apenas DP autorizado e valor válido |
| `/api/refresh`, `/api/discover`, `/api/sync` | `{}` |
| `/api/pair` | `{id, duration}`; 60 inicia e 0 solicita parar |

Respostas: 202 aceita, 409 ocupado, 400 inválido, 403 origem/token rejeitado.
Preservar a política de mesma origem e o servidor loopback na atualização visual.
Exportar somente os campos públicos do inventário, nunca o snapshot inteiro com
token. O contrato permite substituir o frontend sem alterar chaves e transporte;
uma nova aplicação frontend ainda precisará implementar seus próprios componentes.

### Execução

Com as dependências instaladas e os cadastros `config.local.json` e `devices.json`
importados, execute na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe web_panel.py
```

Abra **http://127.0.0.1:8770** neste computador. O painel oferece busca, filtros,
estado dos equipamentos, gateways e filhos Zigbee, leituras de sensores e botões
de ligar/desligar. Os canais são derivados dos mapeamentos já importados, somente
para interruptores, relés, dimmers e relés de painéis identificados. O clique envia
diretamente o comando, sem caixa de confirmação. O serviço exige uma leitura válida
do canal antes de escrever e consulta novamente para verificar o resultado.

- Brilho dos dimmers: ajuste pelo controle deslizante, com envio ao soltar.
- Configurações: temporizadores, brilho mínimo, tipo de lâmpada, comportamento dos
  relés e volume do painel, quando presentes no perfil e na leitura local.
  Os valores enumerados seguem o mapeamento do fabricante; os limites são validados.
- Cenas locais: criar, editar, excluir e executar até 30 ações em sequência.
  São persistidas em `scenes.local.json`; uma falha interrompe a sequência sem
  desfazer as ações anteriores. O serviço precisa estar aberto para executá-las.
- Cenas Tuya: consultar e chamar cenas existentes, condicionado à autorização da
  API. Na conta testada, a Tuya retornou `28841101` (API não assinada). Criação de
  cenas na nuvem ainda não está implementada; use o editor de cenas locais.
- Pareamento: solicitar busca Zigbee de 60 segundos e parar busca nos hubs/painéis
  pela API Tuya. Depende do modelo e das permissões; aceitação da API não comprova
  que um acessório foi vinculado. Nenhum pareamento físico foi executado na validação.
- Após parear, use **Sincronizar cadastro Tuya**, **Buscar IPs na rede** se necessário,
  e **Atualizar estados**. A sincronização importa chaves, funções e vínculos dos
  filhos; a descoberta LAN encontra anúncios dos equipamentos Wi-Fi/gateways.

`capabilities.local.json` guarda as funções de escrita consultadas na Tuya e as
casas da conta. Configurações adicionais só aparecem quando esse perfil confirma
a função. A sincronização atualiza as funções. `tinytuya.json` habilita as operações
de nuvem; controles LAN e cenas locais não precisam de uma chamada à nuvem.

Os estados são consultados ao iniciar e a cada minuto, com eventos dos gateways
entre consultas. O navegador acompanha o progresso sem bloquear. Durante uma
operação os controles ficam desabilitados. Sensores usam a escala/unidade do
mapeamento importado; valores anteriores são sinalizados quando não há resposta
recente. A sincronização pelo painel recarrega o cadastro; edições manuais dos
arquivos ainda exigem reiniciar o serviço. Alarmes, reset de fábrica e DPs arbitrários
não são expostos por esta interface.

O serviço escuta apenas em `127.0.0.1`: não está publicado na internet e não é
acessível pelo celular nesta versão. As APIs retornam somente os campos necessários
à interface, sem credenciais, e verificam origem e token para as operações. Não é
um servidor para exposição pública. Encerre com `Ctrl+C`; não mantenha a interface
Tkinter consultando os mesmos equipamentos ao mesmo tempo.

Para outra porta: `web_panel.py --port 8766`. Os testes usam dispositivos simulados
e não acionam equipamentos reais:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Novo gerenciador local: Wi-Fi, gateways, Zigbee e painéis

A nova entrada é `hub.py`. Os programas antigos continuam disponíveis, mas usam o
cadastro e as funções específicas da instalação original. O novo gerenciador não
importa automaticamente `meus_dispositivos.json` e começa com cadastro vazio.

### Executar no Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe hub.py
```

Na interface:

1. Clique em **Descobrir na rede**. A descoberta atualiza IPs pela identidade do
   equipamento, preservando nomes, chaves e dispositivos ausentes.
2. Importe o `devices.json` gerado pelo assistente TinyTuya. Para obtê-lo, execute
   `.\.venv\Scripts\python.exe -m tinytuya wizard` e siga o
   [guia oficial](https://github.com/jasonacox/tinytuya#setup-wizard---getting-local-keys).
   O assistente requer sua conta/projeto Tuya; a operação local posterior usa as
   chaves importadas. Execute-o na pasta do projeto para manter os arquivos gerados
   nos caminhos ignorados pelo Git.
3. Em **Editar**, informe nome, ambiente, tipo e protocolo. A descoberta sozinha
   não identifica se o equipamento é um painel ou gateway: o tipo inicial é
   `unknown` (não identificado).
4. Para filhos Zigbee, configure o ID do gateway/painel pai e o `node_id`/`cid`.
   O filho usa a conexão e a chave do gateway. Associações ausentes não são
   adivinhadas: permanecem pendentes para edição manual.
5. Use **Consultar selecionado** para validar a leitura. Ative **Escutar gateways**
   para receber eventos dos filhos. Sensores silenciosos mantêm a última leitura
   com data; ausência de resposta não prova que um sensor a pilha está offline.
6. Cadastre controles apenas após confirmar os DPs do modelo. Todos os acionamentos
   pedem confirmação e exigem uma leitura atual do canal. Exemplo de controles:

```json
[{"name": "Luz", "dp": "1", "values": {"Ligar": true, "Desligar": false}}]
```

O exemplo não é um mapeamento universal: sem controles cadastrados, o equipamento
fica somente para leitura. Painéis que expõem canais locais podem usar esses
controles; telas, cenas e modelos específicos ainda precisam de validação. Um
painel também pode ser pai de dispositivos Zigbee. Comandos de dispositivos que
não oferecem leitura do canal não são habilitados nesta versão.

### Cadastro e diagnóstico

`config.local.json` é salvo junto de `hub.py`, independentemente da pasta de onde
o programa foi iniciado. Ele contém credenciais e está no `.gitignore`, assim
como os arquivos usuais do wizard. Isso não criptografa os arquivos nem remove
dados já versionados no repositório. `config.example.json` documenta o formato
sem chaves reais. Não publique seu cadastro nem use `git add -f` nesses arquivos.

```powershell
.\.venv\Scripts\python.exe hub.py discover --seconds 20
.\.venv\Scripts\python.exe hub.py import devices.json
.\.venv\Scripts\python.exe hub.py list
.\.venv\Scripts\python.exe hub.py status ID_DO_DISPOSITIVO
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`list` não imprime chaves. `status` consulta somente leitura. Não existe comando
de acionamento na CLI. Para usar outro cadastro, passe `--config CAMINHO` antes
do subcomando; mantenha qualquer arquivo com credenciais fora do versionamento.

Esta primeira implementação inclui conexão compartilhada por gateway, recepção de
eventos, reconexão e controles explícitos. Leituras são mantidas em memória durante
a sessão; histórico persistente, perfis específicos de painéis, escalas/unidades
de sensores e pareamento Zigbee pela aplicação ficam para etapas posteriores.
O pareamento e a mudança de rede Wi-Fi continuam sendo feitos no aplicativo do
fabricante. A compatibilidade real exige testar os modelos da instalação.

---

<strong>Versão 2.0:</strong><br>
  Implementei, os termostatos que utilizam pilha e se conectam de modo diferente a rede, separei os comandos do ar condicionado em um novo arquivo para o codigo ficar menor e mais legivel. Retirei a parte de scaneamento de IPs pois mais atrapalhava que ajudava.

Este projeto é uma solução local (offline) em Python com interface gráfica para controle de dispositivos inteligentes Tuya usando a biblioteca [TinyTuya](https://github.com/jasonacox/tinytuya). Ele permite o controle completo de dispositivos via rede LAN, sem depender da nuvem Tuya diretamente do seu computador com Windows sem a necessidade de uso de emuladores ou qualquer tipo de virtualização.

![Interface](offline.jpg)

## ⚙️ Funcionalidades

- Controle local (LAN) de dispositivos Tuya, sem uso da internet
- Suporte a dispositivos:
  - Comuns (ligar/desligar)
  - Cortinas (abrir/fechar)
  - Portões automáticos
  - Alarmes
  - Ar-condicionado IR com ajuste de temperatura, modo e intensidade
- Leitura de sensores de temperatura e umidade
- Detecção de IPs incorretos e opção de correção automática
- Armazenamento de status dos dispositivos
- Aprendizado de botões IR com extração de head/key (arquivo separado)

## 📦 Arquivos

- `tuya_lan.py`: Interface principal com controle dos dispositivos via LAN.
- `meus_dispositivos.json`: Lista com os dispositivos configurados (IDs, IPs, keys, tipo e versão).
- `ir_scan.py`: Ferramenta para aprender botões infravermelho, capturando `head` e `key` dos comandos.
- `offline.jpg`: Imagem ilustrativa da interface gráfica.

## 🛠️ Requisitos

- Python 3.9 ou superior
- Dispositivos compatíveis com controle via LAN (protocolo Tuya 3.3 ou 3.4)
- Biblioteca necessária:
  ```bash
  pip install tinytuya
  ```

## 🚀 Como usar

1. Clone o repositório:
   ```bash
   git clone https://github.com/seuusuario/tuya-smartlife-pc-local.git
   cd tuya-smartlife-pc-local
   ```

2. Edite o arquivo `meus_dispositivos.json` com as configurações dos seus dispositivos:
   ```json
   {
     "name": "Luz Quarto",
     "id": "xxxxxxxxxxxxxxxx",
     "ip": "192.168.x.x",
     "key": "xxxxxxxxxxxxxxxx",
     "version": 3.3,
     "dps": 1
   }
   ```

3. Execute a interface gráfica:
   ```bash
   python tuya_lan.py
   ```

4. (Opcional) Para aprender comandos IR, execute:
   ```bash
   python ir_scan.py
   ```

## 🔄 Atualização de IPs

Se algum dispositivo mudar de IP, o programa detecta automaticamente e oferece uma opção para atualizar com um clique (requer `tinytuya scan`).

## 💡 Observações

- O controle de ar-condicionado funciona com IR Blaster Tuya. Os comandos devem ser previamente aprendidos e salvos como `head/key`.
- O sistema armazena o último status de uso localmente.
- O botão "Desligar TV + PC" pode ser personalizado para desligar qualquer dispositivo + o próprio computador.


## 👨‍💻 Desenvolvido por

[MHPS](https://www.mhps.com.br) – Soluções em automação e sistemas inteligentes.
