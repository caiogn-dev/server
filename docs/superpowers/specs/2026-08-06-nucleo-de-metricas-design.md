# Núcleo de métricas — fonte de verdade única

**Data:** 06/08/2026
**Escopo:** SSOT de faturamento + camada de agregação. Observabilidade, estatística/previsão e quebra dos arquivos-monstro são ciclos seguintes.

## Problema

Seis arquivos calculam faturamento por conta própria:

| Arquivo | Linhas | O que faz |
|---|---|---|
| `stores/api/analytics_views.py` | 1.094 | 20 views de relatório, cada uma agrega do seu jeito |
| `stores/api/views/order_views.py` | 891 | `/orders/stats/` — fonte do card da home |
| `core/dashboard_views.py` | 840 | overview + charts |
| `stores/api/export_views.py` | 806 | exports |
| `core/services/dashboard_stats.py` | 136 | agregador do KPI |
| `stores/services/revenue.py` | 129 | **o SSOT que já existia e era subusado** |

Consequências observadas em produção (06/ago/2026):

1. **Card "Receita hoje" zerava às 21h.** `timezone.now().replace(hour=0)` devolve 00:00 UTC = 21:00 de Brasília do dia anterior. Estava replicado em 7 lugares.
2. **Eixos de data divergentes.** `/orders/stats/` agrupava por `created_at`; as outras por `paid_at`. Pedido feito 23h40 e pago 00h05 caía em dias diferentes conforme a tela.
3. **Correções aplicadas em um lugar e não nos outros.** O fix de "pedido cancelado não é receita" (05/ago) foi commitado mas nunca deployado em 7 arquivos — produção rodou o dia inteiro com código velho.

A correção de hoje igualou os *resultados* mas não a *origem*: continuam 4 endpoints com 4 contas. Enquanto forem 4, divergem de novo na próxima mudança.

## Decisões tomadas

- **Eixo único:** `Coalesce(paid_at, created_at)` — data do pagamento, com fallback para a criação quando não houve gateway (dinheiro na entrega, baixa manual). Concilia com extrato do Mercado Pago e fechamento de caixa. Consequência aceita: a série histórica de `/orders/stats/` muda, porque ela usava `created_at`.
- **Sem cache, sem rollup, sem injeção de dependência.** A query direta responde em ~150ms. Rollup materializado vira necessário lá na frente; o desenho mantém a porta aberta via assinatura estável, mas não constrói agora.

## Arquitetura

```
apps/stores/metrics/
  __init__.py     API pública — o resto do código só importa daqui
  definicoes.py   o que é receita, o eixo de data, pedido de teste
  janelas.py      hoje/ontem/semana/mês no fuso da loja
  series.py       agregação por dia/semana/mês, totais, top-N
```

### `definicoes.py`
Migra `revenue.py` inteiro. Responde "o que conta como dinheiro":

- `NON_REVENUE_STATUSES` — cancelado, estornado, falho
- `eixo_de_receita()` → `Coalesce('paid_at', 'created_at')`
- `pedidos_de_receita(loja, inicio, fim)` → queryset filtrado
- `itens_de_receita(...)` → `StoreOrderItem` dos pedidos de receita
- `apenas_receita(queryset)` → aplica a regra a um queryset já montado
- `eh_pedido_de_teste(pedido)` / `marcar_como_teste(pedido)`

Regra invariável: **pago E não cancelado/estornado/falho E não é teste**.

### `janelas.py`
Responde "que intervalo é esse", sempre no fuso da loja. Mata `core/utils.start_of_today` (que eu criei hoje no lugar errado — é conceito de métrica, não utilitário genérico).

- `Janela` — dataclass com `inicio`, `fim`, `rotulo`
- `hoje()`, `ontem()`, `ultimos_dias(n)`, `mes_corrente()`
- `janela_anterior(janela)` — mesmo tamanho, deslocada para trás (comparativos)

Invariável: nenhuma janela nasce de `timezone.now()` cru. `timezone.localtime()` primeiro, sempre. O bug das 21h fica impossível de reintroduzir por construção.

### `series.py`
Responde "como isso se distribui":

- `serie_temporal(loja, janela, granularidade)` → lista de pontos com receita, contagem, ticket médio
- `totais(loja, janela)` → agregado do período
- `top_produtos(loja, janela, limite)`

Invariável: **contagem operacional ≠ receita**. A cozinha precisa ver o cancelado; o faturamento não. São funções distintas e nomeadas — `totais()` fala de dinheiro, `contagem_operacional()` fala de volume. Ninguém mais confunde por acidente.

### O que sai das views
As 4 superfícies param de calcular e passam a só montar resposta. Nenhum `Sum('total')`, nenhum `payment_status='paid'`, nenhum `replace(hour=0)` fora de `metrics/`.

## Teste de equivalência — a garantia anti-fragmentação

Um teste que consulta as 4 superfícies e exige o mesmo número:

```
receita_hoje(home) == receita_hoje(kpi) == receita_hoje(overview) == receita_hoje(relatorios)
```

Se alguém reintroduzir matemática própria em qualquer view, ele quebra. É o que impede a fragmentação de voltar, e é a semente da observabilidade do próximo ciclo (o mesmo comparador vira endpoint de sanidade + alerta no GlitchTip).

Segundo teste, estrutural: varre `apps/` e falha se `Sum('total')` ou `payment_status='paid'` aparecer fora de `metrics/`. Impede reincidência sem depender de code review.

## Migração

15 call sites importam `services/revenue.py` — poucos o bastante para migrar de uma vez, sem camada de compatibilidade. `revenue.py` é **deletado**, não deixado como atalho: um segundo nome para a mesma coisa é exatamente a fragmentação que estamos removendo.

Ordem: criar `metrics/` com testes → migrar as 4 superfícies → deletar `revenue.py` e `start_of_today` → testes de equivalência e estrutural.

## Riscos

- **Números históricos da home mudam** ao trocar `created_at` por eixo de pagamento. Decidido e aceito.
- **Regressão silenciosa em relatório pouco usado.** Mitigação: antes de migrar, capturar a saída atual dos 20 relatórios num snapshot e comparar depois. Diferença que não seja explicada pela troca de eixo é bug.
- **Deploy parcial.** Foi o que aconteceu em 05/ago. Mitigação: conferir hash de cada arquivo dentro do container após o deploy, não confiar no `docker cp`.

## Fora de escopo (ciclos seguintes)

1. Observabilidade — endpoint de sanidade, métricas estruturadas, alerta de divergência
2. Estatística/previsão — tendência, sazonalidade por dia da semana, intervalo de confiança, anomalia
3. Quebra dos arquivos-monstro — `analytics_views.py` 1.094 linhas → um módulo por relatório
