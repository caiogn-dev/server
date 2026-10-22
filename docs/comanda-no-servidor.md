# Comanda montada no servidor — contrato (22/10/2026)

Aprovado pelo dono em 22/10. Motivo: o desenho da comanda morava no print agent
(Node, `pastita-print-agent/src/escpos.js`); toda mudança exigia atualizar o PC
de cada loja à mão ("paia"). Agora o servidor monta os bytes ESC/POS a partir do
layout salvo no painel; o agente só imprime. Referência visual aprovada:
https://claude.ai/artifact/XyFgyUpma5zCXnTUu2F57w (estilo 99Food, tracejado,
COBRAR no topo, nº curto grande, "3º pedido", SEM invertido, cupom com código).

## 1. Layout (server2)

Guardado em `Store.metadata['comanda']` (sem migração). Ausente = padrão abaixo.

```json
{
  "versao": 1,
  "blocos": [
    {"id": "cabecalho",   "ligado": true},
    {"id": "numero",      "ligado": true},
    {"id": "pagamento",   "ligado": true},
    {"id": "cliente",     "ligado": true},
    {"id": "endereco",    "ligado": true},
    {"id": "avisos",      "ligado": true},
    {"id": "itens",       "ligado": true},
    {"id": "totais",      "ligado": true},
    {"id": "observacao",  "ligado": true},
    {"id": "mensagem",    "ligado": false},
    {"id": "codigo_barras","ligado": true}
  ],
  "separador": "tracejado",      // tracejado | linha | espaco
  "colunas": 48,                 // 48 (80 mm) | 32 (58 mm)
  "vias": 1,                     // 1 | 2
  "itens_grandes": false,        // nome do item em altura dupla
  "precos_nos_itens": true,
  "mensagem": ""                 // texto livre do bloco "mensagem", até 200 chars
}
```

Ordem de `blocos` = ordem no papel. Bloco desconhecido é ignorado; bloco
faltando entra no fim desligado (layout velho continua válido).
`avisos` = endereço divergente + "atenção da loja" + agendamento (sempre que
existirem). Na comanda de PREPARO (`template=prep_ticket`) o bloco `itens`
inclui as linhas `prep` como hoje.

## 2. Linhas intermediárias (fonte única do papel E da prévia)

`apps/stores/services/comanda_linhas.py`:
`linhas_da_comanda(payload: dict, layout: dict) -> list[dict]` — recebe o MESMO
payload de `print_service.build_order_print_payload` (com `customer.pedidos`,
`totals.descontos`, etc.). Cada linha:

```json
{"texto": "COBRAR          R$ 73,44", "alinhar": "esquerda|centro|direita",
 "negrito": true, "altura_dupla": false, "largura_dupla": false, "invertido": true,
 "tipo": "texto|separador|codigo_barras|corte|espaco"}
```

Texto já quebrado na largura (`colunas`, metade quando `largura_dupla`).
Duas colunas (rótulo ... valor) já vêm montadas no `texto`.

`apps/stores/services/comanda_escpos.py`:
`bytes_da_comanda(linhas, colunas) -> bytes` — ESC @, codepage PC850
(ESC t 2, texto `encode('cp850', errors='replace')`), ESC E, GS ! (altura/largura),
GS B (invertido), ESC a (alinhamento), código de barras CODE128 (GS k), corte
(GS V 66 0). Mesmos comandos que `pastita-print-agent/src/escpos.js` usa hoje.

## 3. Payload do job

`build_order_print_payload` ganha `escpos_b64` (base64 dos bytes, já com as
`vias` repetidas) em jobs `kitchen_ticket`/`prep_ticket`. O resto do payload
continua igual: **agente velho ignora `escpos_b64` e monta como sempre** —
nenhuma loja fica sem comanda durante a troca.

## 4. API (server2, autenticada, dono/staff da loja)

- `GET  /api/v1/stores/{slug}/comanda/layout/` → layout efetivo (padrão preenchido).
- `PUT  /api/v1/stores/{slug}/comanda/layout/` → valida e salva; devolve o salvo.
- `POST /api/v1/stores/{slug}/comanda/previa/` body `{layout?, pedido_id?, template?}`
  → `{"linhas": [...], "colunas": 48, "pedido": "CE-..."}`. Sem `pedido_id` usa o
  último pedido da loja; sem pedido nenhum, um pedido de exemplo.
- `POST /api/v1/stores/{slug}/comanda/imprimir-teste/` body `{layout?}` → enfileira
  job de teste com o último pedido (dedupe desligado) e devolve o job.

## 5. Agente (pastita-print-agent 0.6.0)

- `#printJob`: se `job.payload.escpos_b64` existe → `Buffer.from(b64,'base64')`
  direto para `printRawWindows`; senão, o builder antigo.
- Heartbeat manda `version`; servidor responde `versao_atual` e `atualizacao`
  `{versao, url_zip, sha256}`; agente baixa, confere sha256, troca os arquivos
  e reinicia o serviço (auto-update).
- Instalador Windows `.exe` (NSIS, gerado no Linux com `makensis`): Node
  embutido, assistente pede a chave do agente/loja, registra serviço, abre o
  teste de impressão. Sem `git pull` / `npm install` nos PCs.

## 6. Painel (pastita-dash)

Impressoras → aba/tela **Layout da comanda** (`storeHref('printing/comanda')`):
blocos com liga/desliga e reordenação (subir/descer), separador, papel, vias,
itens grandes, preços, mensagem; prévia à direita desenhada a partir de
`linhas` (monoespaçada, invertido = fundo preto); botões Salvar e Imprimir teste.
