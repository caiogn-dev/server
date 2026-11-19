# Homologação iFood — Cardapidex (CNPJ 25.142.396/0001-32)

Chamado de suporte: #36595833. Módulos: **Order + Events** (automático, app "Cardapidex"),
**Shipping + Merchant** (por chamado, depois dos obrigatórios).

Apps no Portal do Desenvolvedor:
- **Cardapidex** — ba5e470c-d0ca-4741-8e89-67607ddce6f9 (Order/Events; credenciais só após homologar)
- **Cardapidex Entregas** — f5ce2c72-85b0-400a-9c78-1c2561d41c3f (Shipping; token devolve 403 até vincular loja)
- Loja de teste: 00f0d5a7-6142-4120-b34d-1b1d36cdecec ("Teste - L. DE SOUZA SANTOS LTDA")

Código: `server2/apps/stores/services/` — `ifood_oauth.py`, `pedidos_do_ifood.py` (Order/Events),
`entrega_ifood.py` (Shipping), `loja_no_ifood.py` (Merchant). Testes: `apps/stores/tests/test_*ifood*.py`.

## Order — critérios × implementação

| Critério | Onde |
|---|---|
| Polling ≥ 30 s, `x-polling-merchants` | beat `buscar-eventos-ifood` 30 s; `processar_eventos_da_loja` |
| ACK de todos os eventos | idem; evento que falhou fica sem ACK e volta |
| Deduplicação | `ifood_oauth.evento_ja_visto/lembrar_evento` (eventId, 24 h); pedido novo idempotente pelo orderId |
| Confirmar em ≤ 8 min | confirmação automática ao receber (`confirmar_depois`) |
| `cancellationReasons` exibidos ao usuário | painel: modal Cancelar lista os motivos do iFood (`orders/<id>/ifood/motivos-cancelamento/`) |
| Cancelamento do cliente/plataforma | eventos CAN/CAR/CARF aplicados ao pedido |
| Bandeira do cartão, troco | comanda: "Crédito VISA (pago online) R$ …", "troco de R$ … (para R$ …)" |
| Cupom e quem paga | comanda: "Cupom R$ 10,00 (iFood R$ 6,00 · loja R$ 4,00)" |
| Observações, código de coleta | notas do item + `delivery_notes` ("Código de coleta: …") |
| CPF/CNPJ da nota | comanda: "CPF/CNPJ na nota: …" |
| Sincronização de status externo | CFM/CON/CAN do Gestor de Pedidos atualizam o painel |
| Plataforma de Negociação (HSD/HSS) | faixa no pedido: aceitar / recusar / contraproposta (REFUND, BENEFIT, ADDITIONAL_TIME) |
| `readyToPickup` (retirada e entrega própria) | status "Pronto"; na entrega própria é enviado antes do `dispatch` |
| `dispatch` só na entrega própria | entregador do iFood → loja não manda dispatch |
| Token só renovado ao expirar | cache = expiresIn; 401 → renova e repete 1x |
| Rate limit | 429 respeita Retry-After; 5xx backoff 0,5 s/1 s, máx. 3 tentativas |

## Events
- Polling a cada 30 s com `x-polling-merchants` (até 100 lojas por chamada).
- App de logística: `excludeHeartbeat=true` (não abre a loja no app do iFood).
- ACK imediatamente após processar; dedup por eventId.

## Merchant
| Endpoint | Uso |
|---|---|
| GET /merchants | `manage.py ifood_lojas` (uso interno: lista lojas que aprovaram o app) |
| GET /merchants/{id} | conferir a loja ao salvar o ID no painel |
| GET /status | selo Aberta/Fechada no painel (Integrações → iFood → Loja no iFood) |
| GET/POST/DELETE /interruptions | pausas 15 min/30 min/1 h/2 h e "Retomar"; 409 InterruptionOverlap vira mensagem |
| GET/PUT /opening-hours | tabela de turnos por dia, vários turnos, "Salvar horários"; turno inválido recusado |
| Erros 400/401/403/409/429/5xx | mensagem legível no painel; 401/403 → "Aprove o app no Portal do Parceiro" |

## Shipping (entrega iFood para pedidos fora da plataforma)
| Critério | Onde |
|---|---|
| Cotação (deliveryAvailabilities) | frete no checkout (`frete_para_o_cliente`) com acréscimo da loja |
| Pedir entregador | botão "Chamar entregador iFood" ou automático (ao confirmar / ao ficar pronto) |
| Eventos REQUEST_DRIVER_*, ASSIGN_DRIVER, DROP_CODE, IN_TRANSIT, CONCLUDED, CANCELLED | bloco "Entregador iFood" do pedido; pedido anda sozinho |
| Código de entrega | mostrado em destaque no pedido |
| Cancelamento com motivos dinâmicos | lista dos `cancellationReasons` para o lojista escolher |
| Mudança de endereço | DELIVERY_ADDRESS_CHANGE_*: faixa "Cliente pediu outro endereço" com prazo; Aceitar/Recusar |
| Dedup, ACK, retry com backoff, logs com eventId/orderId | igual a Order/Events |

## Pendências conhecidas (para mencionar ao analista)
- Shipping recomenda renovar o token 5 min antes; Order exige renovar só ao expirar. Seguimos o de Order (obrigatório) + renovação automática no 401.
- `idempotency-key`: as operações de mudança são idempotentes do nosso lado (trava por pedido + estado); o header não é enviado.
- Turno de horário que passa da meia-noite: dividir em dois turnos.

## Roteiro de gravação (checklist do suporte)
1. Integrações → iFood: ID da loja de teste salvo, selo "Conectado".
2. Loja no iFood: status, pausar 15 min, Retomar, editar e salvar horários.
3. Pedido de teste entra sozinho, imprime comanda, confirma; mostrar bandeira/cupom/CPF na comanda.
4. Pronto → Saiu para entrega (entrega própria) → Entregue.
5. Cancelar escolhendo o motivo do iFood.
6. Negociação: aceitar/recusar/contrapropor.
7. Entrega iFood: cotação no checkout, chamar entregador, status, código, cancelar com motivo, mudança de endereço.
