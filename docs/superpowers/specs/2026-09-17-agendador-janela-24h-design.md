# Agendador de campanha ciente da janela de 24h — design

**Data:** 17/09/2026 · **Repos:** server2 (backend) + pastita-dash (painel)
**Decisões do dono:** tomadas em 16–17/set, registradas em cada seção.

## 1. Problema

A regra da Meta: até 24h depois da **última mensagem do cliente**, a loja manda texto
livre de graça. Fora disso, só template pago.

Produção já tem quase tudo para campanha grátis:

- `apps/campaigns/services/janela.py` — `chaves_com_janela_aberta(em=)`,
  `resumo_da_janela(em=)`, `recortar_para_a_janela(campaign)`;
- `start_campaign` chama o recorte no início do envio;
- endpoint `/campaigns/audiencia/janela/?em=` e prévia no modal de agendamento.

Dois buracos:

1. **Pronto e desligado.** O recorte só roda se a campanha tiver
   `audience_filters.somente_janela_aberta`, e **nenhuma tela liga essa marca** —
   0 de 8 campanhas em produção. Campanha de texto livre sai para quem está fora da
   janela e falha com `131047`, uma por destinatário.
2. **Quem fecha antes do horário é descartado.** Campanha às 20h: quem falou com a
   loja ontem às 12h tem a janela fechando hoje às 12h — está dentro da janela agora e
   é perdido às 20h, mesmo podendo receber de graça mais cedo.

## 2. Decisões

| # | Decisão | Origem |
|---|---|---|
| D1 | Campanha **sem template** (texto livre) é sempre "só janela aberta" — marca automática. Não é opção de tela: a Meta recusa texto livre fora da janela. | design |
| D2 | Quem teria a janela fechada no horário da campanha é **antecipado**, não descartado. | dono, 16/set |
| D3 | Antecipação sai **1 hora antes** da janela fechar. | dono, 16/set |
| D4 | **Silêncio:** nada é enviado entre **21h e 8h**, no fuso da loja. | dono, 16/set |
| D5 | Antecipação **só no mesmo dia** do horário da campanha. | dono, 17/set |
| D6 | O horário de cada pessoa é **calculado ao vivo**, a cada rodada, nunca gravado. | abordagem A, dono 17/set |
| D7 | Campanha **com template** não muda. | design |
| D8 | UI: **linha do tempo do dia (A) + agenda em faixas (C)**, nos dois momentos (agendar e rodando). | dono, 17/set |
| D9 | Consequência do D4: o modal **não deixa agendar texto livre fora de 08:00–21:00**. Sem isso, uma campanha às 22h puxaria todo mundo para as 21h pela regra do silêncio. | **a confirmar pelo dono** |

## 3. A regra do horário de cada destinatário

Função pura, sem banco: `horario_alvo(fecha_em, horario_campanha, fuso) -> datetime | None`.

```
se fecha_em é None                          → None   (nunca falou; fica de fora)
alvo = min(horario_campanha, fecha_em − 1h)
se alvo está fora de [08:00, 21:00] no fuso → alvo = o 21:00 mais recente ANTES do alvo
                                               (22:30 → 21:00 do mesmo dia;
                                                05:00 → 21:00 da véspera)
se data_local(alvo) ≠ data_local(horario_campanha) → None   (D5: só no mesmo dia)
se alvo ≥ fecha_em                          → None   (não cabe na janela)
devolve alvo
```

`fecha_em = last_customer_message_at + 24h`, lido **na hora** de cada rodada.
`data_local` e a faixa [08:00, 21:00] são sempre no **fuso da loja** (`Store.timezone`),
nunca no do servidor. 21:00 em ponto ainda é permitido.

**Casos (todos viram teste de tabela):**

| Última msg do cliente | Campanha | Alvo | Por quê |
|---|---|---|---|
| ontem 12:00 | hoje 20:00 | **hoje 11:00** | fecha 12:00 → 1h antes (exemplo do dono) |
| hoje 09:00 | hoje 20:00 | **hoje 20:00** | fecha amanhã 09:00, depois das 20h |
| ontem 06:00 | hoje 20:00 | **ontem 21:00 → None** | alvo 05:00 é silêncio; recua para a véspera; D5 descarta |
| ontem 12:00, e de novo hoje 10:00 | hoje 20:00 | **hoje 20:00** | janela renovou até amanhã 10:00 |
| nunca falou | hoje 20:00 | **None** | sem janela |
| ontem 20:30 | hoje 20:00 | **hoje 19:30** | fecha 20:30 → 1h antes |
| há 3 dias | hoje 20:00 | **None** | janela já fechada |
| ontem 12:00 | **daqui a 2 dias** 20:00 | **None** | D5 — senão antecipa a lista inteira |

## 4. Componentes

### Backend (server2)

1. **`janela.py` — `horario_alvo()`** (seção 3) e **`fechamentos_por_chave(account_ids)`**
   → `{chave_do_telefone: fecha_em}`, na mesma chave canônica que o recorte já usa.

2. **Marca automática (D1)** — no create/update de campanha: sem `template` →
   `audience_filters['somente_janela_aberta'] = True`. Com template → não toca.

3. **Ciclo de vida da campanha marcada.**
   - `check_scheduled_campaigns` (Beat, a cada 60s) passa a considerar campanhas
     marcadas `SCHEDULED` cujo `scheduled_at` é **hoje** (fuso da loja), não só
     `scheduled_at ≤ agora`.
   - Nova rodada `processar_rodada_da_janela(campaign)`:
     1. para cada `PENDING`: calcula `alvo`;
     2. `alvo is None` e já passou a chance → `SKIPPED` (`error_code='fora_da_janela'`);
     3. `alvo ≤ agora` e janela aberta agora → **reserva** e envia;
     4. respeita `messages_per_minute`.
   - Campanha vira `RUNNING` na primeira reserva; `COMPLETED` quando passou do
     `scheduled_at` e não resta `PENDING`/`SENDING`.
   - **Para campanhas marcadas, `recortar_para_a_janela` sai do `start_campaign`**: a
     decisão agora é por pessoa, na hora dela. Campanha de template segue igual.

4. **Reserva sem lock longo.** Novo status `SENDING`.
   `UPDATE ... SET status='sending' WHERE id=? AND status='pending'` — só envia quem
   afetou 1 linha. Lock de campanha no Redis (`acquire_lock`, já existe) evita duas
   rodadas simultâneas. **Recuperação:** `SENDING` há mais de 10 min volta a `PENDING`
   (worker morreu no meio).

5. **Prévia** — `resumo_da_janela(em=)` passa a devolver:
   `no_horario`, `antecipados`, `de_fora`, `primeiro_antecipado_em` e
   `faixas: [{hora, quantidade}]`. **Mesmo código da rodada**, para a prévia nunca
   divergir do envio.

6. **Detalhe ao vivo** — endpoint da campanha devolve as faixas com
   `enviadas / aguardando`, a próxima faixa e as pessoas que **mudaram de horário**
   desde o agendamento (o alvo de agora ≠ o alvo previsto; o previsto fica em
   `CampaignRecipient.variables['alvo_previsto']` só para exibir).

### Painel (pastita-dash)

7. **Modal "Agendar campanha"** (texto livre): linha do tempo do dia 8h–21h (faixas de
   silêncio hachuradas, bolinhas douradas = antecipados, barra verde = horário
   escolhido) + agenda em faixas + rodapé "X de Y recebem sem pagar template".
8. **Página da campanha rodando:** mesma linha do tempo com marcador "agora" e trecho
   verde até ele; faixas passadas "✓ N enviadas"; próxima faixa em destaque com
   contagem regressiva; aviso de quem mudou de horário ("Juliana falou com a loja às
   15:10 — agora recebe às 20h"); rodapé "R$ 0,00 em template até agora"; botão pausar.
9. **Clique** numa bolinha ou faixa abre quem está nela e quando a janela fecha.

Mockups: `pastita-dash/.superpowers/brainstorm/*/content/agendamento-combinado-v2.html`.

## 5. Fluxo

```
agenda 20:00 ──► marca automática (texto livre) ──► SCHEDULED
                                                        │
             Beat a cada 60s, no dia da campanha ◄──────┘
                         │
     para cada PENDING: alvo = horario_alvo(fecha_em lido agora, 20:00, fuso)
                         │
   alvo ≤ agora ─► reserva (pending→sending) ─► envia ─► SENT / SKIPPED(131047)
   sem chance   ─► SKIPPED(fora_da_janela)
                         │
   passou das 20:00 e não há PENDING/SENDING ─► COMPLETED
```

## 6. Erros

| Situação | Comportamento |
|---|---|
| Duas rodadas pegam a mesma pessoa | Lock de campanha + reserva condicional: só uma envia. |
| Meta responde `131047` | `SKIPPED` com esse código — não é `FAILED`. |
| Worker fora do ar por 1h | Na volta, quem perdeu o alvo é reavaliado: janela aberta → envia agora (se não for silêncio); fechada → `SKIPPED`. Nada sai depois das 21h para "compensar". |
| Worker morre com `SENDING` | Volta a `PENDING` após 10 min. |
| Loja sem fuso | `settings.TIME_ZONE` (`America/Sao_Paulo`). |
| Dono pausa | Nenhuma rodada envia; ao retomar a conta é refeita. |
| Dono muda o horário | Nada a recalcular — a conta é sempre ao vivo. |
| Campanha com template | Fluxo atual, intocado. |

## 7. Testes

- **Regra pura:** a tabela da seção 3, mais fuso da loja ≠ fuso do servidor (o
  container roda em UTC — mesma armadilha do bot de horário de 16/set).
- **Ciclo:** relógio congelado andando o dia inteiro (8h → 21h); confere quem sai em
  cada hora, ninguém duas vezes, `COMPLETED` no fim.
- **Concorrência:** duas rodadas simultâneas → cada destinatário enviado uma vez.
- **Recuperação:** `SENDING` antigo volta a `PENDING`.
- **Marca automática:** texto livre ganha; template não.
- **Prévia = envio:** para o mesmo instante, os números da prévia batem com o que a
  rodada faria.
- **Template intocado:** campanha com template segue o `start_campaign` atual.
- **Painel:** modal com as três contagens e faixas; página rodando com "agora", faixas
  enviadas, próxima em destaque e aviso de mudança; clique abre a lista.

## 8. Fora do escopo

- **Evolution API / número não oficial** — só depois de medir o resíduo fora da janela.
- **Instagram e Messenger** — mesma regra de 24h existe, mas não entra aqui.
- **Mensagens agendadas avulsas** (`ScheduledMessage`) — continuam sem noção de janela.
- **Fallback para template pago** de quem ficou de fora — decidido contra (C na
  pergunta de 16/set): volta a gastar.
