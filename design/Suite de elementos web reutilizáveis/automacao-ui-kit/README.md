# Painel Automação · UI Kit v1.0

Suite de elementos reutilizáveis para um painel corporativo de automação (iluminação, climatização, cortinas, sensores, gateways). Visual em relevo suave, com tema claro, escuro ou automático e cinco cores de acento.

## Conteúdo do pacote

| Arquivo | Função |
|---|---|
| `automacao-ui.css` | Folha de estilo do kit: tokens de cor, temas, acentos e todas as classes `au-*`. **É o único arquivo necessário no projeto original.** |
| `Suite Automacao.dc.html` | Protótipo interativo com todos os elementos (R01–R30), menu lateral e janelas modais, usando dispositivos simulados. |
| `Guia de Componentes.dc.html` | Documentação visual: cada componente com exemplo ao vivo, marcação HTML, estados e notas de acessibilidade. |
| `support.js` | Runtime necessário para abrir os dois arquivos `.dc.html` no navegador. Não é usado no projeto original. |

## Abrir o protótipo e o guia

Os arquivos `.dc.html` carregam `support.js`, `automacao-ui.css` e as fontes do Google Fonts. Sirva a pasta por HTTP para evitar bloqueios do navegador:

```bash
cd automacao-ui-kit
python3 -m http.server 8080
# abra http://localhost:8080/Suite%20Automacao.dc.html
```

## Usar no projeto original

### 1. Incluir fontes e estilo

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="automacao-ui.css">
```

### 2. Definir tema e acento no contêiner raiz

```html
<div class="au-root" data-au-theme="auto" data-au-accent="ciano">
  …
</div>
```

- `data-au-theme`: `light` · `dark` · `auto` (segue o sistema operacional)
- `data-au-accent`: `ciano` · `verde` · `ambar` · `violeta` · `azul`

Trocar em tempo de execução:

```js
const root = document.querySelector('.au-root');
root.dataset.auTheme = 'dark';
root.dataset.auAccent = 'verde';
```

Os tokens são recalculados no elemento com `data-au-theme`, então áreas com temas diferentes podem coexistir na mesma página.

### 3. Estrutura de página com menu lateral

```html
<div class="au-root au-shell" data-au-theme="auto">
  <nav class="au-sidebar" data-collapsed="false" aria-label="Menu principal">
    <div class="au-sidebar__brand">
      <span class="au-sidebar__mark">PA</span>
      <span class="au-sidebar__text">PAINEL AUTOMAÇÃO</span>
    </div>
    <button class="au-sidebar__toggle" aria-expanded="true" aria-controls="nav">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M15 6l-6 6 6 6"/></svg>
      <span class="au-sidebar__text">Recolher menu</span>
    </button>
    <ul class="au-nav" id="nav">
      <li><a class="au-nav__item" href="#" aria-current="true">
        <svg class="au-nav__icon">…</svg><span class="au-nav__label">Dispositivos</span></a></li>
      <li><a class="au-nav__item" href="#" aria-label="Alertas, 3 ativos">
        <svg class="au-nav__icon">…</svg><span class="au-nav__label">Alertas</span>
        <span class="au-nav__badge">3</span></a></li>
    </ul>
    <div class="au-sidebar__footer">…</div>
  </nav>
  <main class="au-shell__main">…</main>
</div>
```

```js
const nav = document.querySelector('.au-sidebar');
const btn = nav.querySelector('.au-sidebar__toggle');
btn.addEventListener('click', () => {
  const collapsed = nav.dataset.collapsed !== 'true';
  nav.dataset.collapsed = collapsed;
  btn.setAttribute('aria-expanded', !collapsed);
});
```

## Componentes

A aparência depende apenas de classes, atributos ARIA e atributos `data-*`. O código da aplicação só altera atributos.

| Componente | Classes | Estado controlado por |
|---|---|---|
| Card / superfície | `au-card`, `au-inset`, `au-inset--stale` | `--stale` = último valor conhecido |
| Botões | `au-btn`, `--primary`, `--danger`, `--sm`, `--link`, `au-icon-btn`, `au-power` | `disabled`, `aria-pressed` (power) |
| Chave liga/desliga | `au-switch`, `au-switch--sm` | `aria-checked`, `data-status="confirmed\|pending\|unconfirmed\|unavailable"` |
| Indicador de estado | `au-chip`, `au-chip--bare`, `au-dot` | `data-state="ok\|noresp\|waiting\|config\|auth\|stale\|confirmed\|pending\|unconfirmed\|sent"` |
| Segmentado / abas / filtros | `au-seg`, `au-seg__item`, `au-seg--pill` | `aria-checked`, `aria-selected` ou `aria-pressed` |
| Slider | `au-slider`, `__fill`, `__thumb` | `style="--au-value:64%"` |
| Fader vertical | `au-fader`, `__fill`, `__thumb` | `style="--au-value:40%"` |
| Knob | `au-knob`, `__face`, `__pointer` | `style="--au-angle:37deg"` (−135deg a 135deg) |
| Entrada numérica | `au-stepper`, `au-stepper__btns`, `au-error` | valor do `input` |
| Campos | `au-field`, `au-input`, `au-select`, `au-checkbox`, `au-radio`, `au-form-label` | `aria-checked` |
| Listas e tabelas | `au-row`, `au-table` | — |
| Modal simples | `au-backdrop`, `au-modal` | — |
| Modal com seções | `au-modal--sectioned`, `__header`, `__icon`, `__heading`, `__close`, `__body`, `__footer` | variantes `au-modal--lg`, `au-modal--alert` |
| Painel lateral | `au-backdrop--drawer`, `au-drawer` | — |
| Menu lateral | `au-sidebar`, `au-nav`, `au-nav__item`, `__icon`, `__label`, `__badge` | `data-collapsed`, `aria-current` |
| Utilitários | `au-label`, `au-tag`, `au-meta`, `au-mono` | — |

### Exemplos rápidos

```html
<!-- Chave com comando em andamento -->
<button class="au-switch" role="switch" aria-checked="true"
        data-status="pending" disabled
        aria-label="Luz principal: ligando, enviando"></button>

<!-- Indicador de comunicação -->
<span class="au-chip" data-state="noresp"><span class="au-dot"></span>Sem resposta</span>

<!-- Slider acessível -->
<div class="au-slider" role="slider" tabindex="0"
     aria-label="Brilho" aria-valuemin="0" aria-valuemax="100"
     aria-valuenow="64" aria-valuetext="64%" style="--au-value:64%">
  <div class="au-slider__fill"></div><div class="au-slider__thumb"></div>
</div>
```

## Tokens principais

| Token | Uso |
|---|---|
| `--au-bg` | Superfície única (o relevo vem das sombras) |
| `--au-text`, `--au-text-strong`, `--au-muted` | Texto, títulos, texto secundário |
| `--au-accent`, `--au-accent-ink`, `--au-on-accent` | Acento, texto de acento, texto sobre acento |
| `--au-ok`, `--au-err`, `--au-warn`, `--au-info`, `--au-stale` (+ `-ink`) | Estados |
| `--au-elev-1`, `--au-elev-2` | Relevo elevado (botões, cards) |
| `--au-inset-sm`, `--au-inset` | Relevo interno (trilhos, campos, leituras) |
| `--au-radius-sm/-/-md/-lg` | 10 · 12 · 16 · 22 px |

**Novo acento:** declare `[data-au-accent="nome"]` com `--au-accent`, `-hi`, `-lo`, `-soft`, `-ring`, `-strong`, `-ink-light`, `-ink-darkmode`, `--au-on-accent` e `--au-accent-wash`.

## Regras de comportamento

1. Habilite um controle somente quando a função e os valores aceitos pelo equipamento estiverem confirmados (leitura validada → escrita liberada).
2. Ao acionar uma chave: `aria-checked` recebe o valor alvo, `data-status="pending"` e `disabled` até o retorno. Sem retorno no tempo limite: `data-status="unconfirmed"`.
3. Knobs e sliders enviam o valor ao soltar (`pointerup`) ou 600 ms após a última tecla, nunca a cada movimento.
4. Valores fora dos limites do equipamento: mostre `.au-error` e não envie nada.
5. Ações sensíveis e comandos em grupo passam por confirmação com equipamento e função explícitos. Grupos e cenas mostram o resultado por equipamento.
6. Comandos infravermelho exibem `data-state="sent"` (enviado, sem retorno de estado).
7. Serviço local desconectado: aplique `disabled` em todos os comandos e mostre os estados como último valor conhecido.
8. Não chame toda falha de "offline": use o estado específico (sem resposta, erro de autenticação, configuração pendente…).

## Acessibilidade

- Teclado: Tab, Espaço/Enter, setas (± passo), PageUp/PageDown (± 10%), Home/End.
- Estado nunca depende só da cor: cada indicador combina forma do ponto e texto.
- Botões só de ícone e itens do menu recolhido precisam de `aria-label`.
- Janelas: `role="dialog"` (ou `alertdialog`), `aria-modal="true"`, `aria-labelledby`. Fechar com Esc; foco inicial no primeiro campo; prender o foco dentro da janela e devolvê-lo ao botão de origem ao fechar.
- Use `aria-live="polite"` nas regiões onde status e resultados mudam.
- `prefers-reduced-motion` desativa transições e animações automaticamente.

## Compatibilidade

Navegadores atuais (Chrome, Edge, Firefox, Safari). O ajuste do fundo da página no tema escuro usa `:has()`; em navegadores sem suporte, aplique o fundo no `body` manualmente.
