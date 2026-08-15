# Relatórios: contrato de números

**Data:** 14/08/2026
**Origem:** "relatórios estão errados... analise tudo! e refine os relatórios!"
**Escopo:** server2 (métricas, status de pedido) + pastita-dash (cartões)

---

## 1. O que está errado, medido

Tudo abaixo foi medido em produção em 14/08, não inferido.

### 1.1 O cartão do painel mistura duas regras e dois eixos

`GET /stores/reports/dashboard/` devolve, para a Cê Saladas:

```
month -> {'orders': 49, 'revenue': 2807.64}
```

Os dois números vêm de conjuntos diferentes:

| número | regra | eixo | resultado |
|---|---|---|---|
| `revenue` = 2807.64 | só pagos, sem cancelado, sem teste | data do **pagamento** | 40 pedidos |
| `orders` = 49 | **todos**, inclusive cancelado e não pago | data de **criação** | 49 pedidos |

Medição que confirma:

```
últimos 30d, canônico :  40 pedidos  R$ 2807.64   <- virou o 'revenue'
últimos 30d, TODOS    :  49 pedidos  R$ 3581.63   <- virou o 'orders'
```

Consequência: quem divide um pelo outro lê ticket médio de **R$ 57,30**; o
ticket real dos pedidos que geraram aquela receita é **R$ 70,19**. O cartão não
mente em nenhum campo isolado — mente na leitura que ele convida a fazer.

A mistura é deliberada e está comentada em `apps/stores/api/export_views.py`
("a operação precisa ver o pedido cancelado, o faturamento não"). A decisão é
razoável; a apresentação é que não avisa.

Além disso o rótulo diz **"month"** e a janela é `today - 30 dias`, não o mês do
calendário. Para o dono, "esse mês" tem primeiro dia.

### 1.2 Existem DUAS implementações de "mudar status do pedido"

`StoreOrder.update_status()` (model, `apps/stores/models/order.py:402`) contém a
regra que faz a venda em dinheiro virar receita:

```python
OFFLINE_PAYMENT_METHODS = {'cash'}
if new_status in {DELIVERED, COMPLETED} and self.payment_method in OFFLINE_PAYMENT_METHODS:
    self.payment_status = PaymentStatus.PAID
```

`OrderService.update_status()` (`apps/stores/services/order_service.py:98`) — o
caminho que **o painel** usa — reescreve toda a lógica de timestamps, chama
`order.save()` e **nunca chama o método do model**. Ele trata `cancelled` como
caso especial e não trata `delivered` + dinheiro.

Resultado medido: **28 pedidos em dinheiro entregues, 26 pagos, 2 não.**

| pedido | loja | data | cliente | valor |
|---|---|---|---|---|
| `CE-2607316642` | Cê Saladas | 31/07 | gabriela ribeiro guimarães | R$ 95,00 |
| `KER2608076764` | Kero Kero | 07/08 | — | R$ 211,00 |

**R$ 306,00 entregues, recebidos em mãos, fora do faturamento.**

⚠️ O comando `/entregue` do WhatsApp (`apps/whatsapp/services/comandos.py`,
escrito em 14/08) tem o mesmo defeito: seta `pedido.status` e salva. Entra na
correção.

### 1.3 Os métodos de pagamento são um conjunto aberto

`payment_method` é `CharField(max_length=50, blank=True)` sem `choices`. Em
produção (fotografia de 14/08 18h — a loja segue vendendo, os totais mudam):

```
pix 74 · cash 37 · '' 5 · other 3 · credit_card 3 · card 3
```

`card` e `credit_card` são a mesma coisa escrita de dois jeitos. Nenhum
relatório consegue cortar por método de pagamento com isso, e é pré-requisito
do próximo plano ("pagar na entrega").

### 1.4 O caixa tem o método chumbado

`StoreCashSession.expected_amount` (`apps/stores/models/cash.py:76`) filtra
`payment_method='cash'`. Quando existir "pagar na entrega no cartão", esse
dinheiro **não entra na gaveta** (correto) mas também **não aparece em lugar
nenhum** como recebido na entrega (errado).

### 1.5 O que está CERTO e não deve ser tocado

- `apps/stores/metrics/` já é a definição única de receita e está correta.
- `GET /stores/reports/revenue/` bate exatamente com ela: R$ 2.921,53 / 42
  pedidos no período 01/07–14/08. Este endpoint é a referência.

---

## 2. Princípio

> Todo número exibido declara sua **regra** e seu **eixo**. Dois números só
> aparecem lado a lado se compartilharem os dois.

Regra: `receita` (pago, não cancelado, não teste) ou `operacao` (tudo).
Eixo: `pagamento` (`paid_at`) ou `criacao` (`created_at`).

A divergência entre telas não nasce de contas erradas — nasce de cada tela
poder escolher a sua regra em silêncio. O contrato tira essa liberdade.

---

## 3. Desenho

### 3.1 Uma implementação de mudança de status

`OrderService.update_status()` passa a **delegar** ao model:

```python
order.update_status(new_status, notify=False)   # regra do dinheiro mora aqui
```

Mantém o que é dele (validação de transição, `notes`, webhook, liquidação do
cancelado) e para de reescrever timestamps. O `/entregue` do WhatsApp idem.

**Teste:** para cada caminho que muda status (painel, bot, comando "/"), um
pedido em dinheiro marcado como entregue precisa terminar `payment_status=paid`
com `paid_at` preenchido.

### 3.2 O contrato, em código

`apps/stores/metrics/contrato.py`:

```python
@dataclass(frozen=True)
class Numero:
    valor: Decimal | int
    regra: Literal['receita', 'operacao']
    eixo: Literal['pagamento', 'criacao']
    rotulo: str
```

Os endpoints de resumo passam a montar `Numero`, e o serializer emite
`{valor, regra, eixo, rotulo}`. O painel usa `regra`/`eixo` para decidir se
pode dividir dois números — e para mostrar a legenda.

YAGNI: não vira framework. É um dataclass e uma função de serialização.

### 3.3 O cartão

Antes: `49 pedidos · R$ 2.807,64` (incompatíveis).
Depois: **`40 pedidos pagos · R$ 2.807,64 · ticket R$ 70,19`** — mesma regra,
mesmo eixo, divisão correta.

Cancelados e pendentes saem do cartão de faturamento e viram um bloco de
operação ao lado ("9 pedidos não faturados: 7 cancelados, 2 aguardando
pagamento"), que é onde a operação quer vê-los.

Rótulo: `month` vira **mês do calendário** (primeiro dia até hoje), e a janela
de 30 dias, quando usada, é rotulada "últimos 30 dias". O que o texto diz e o
que a query faz passam a ser a mesma coisa.

### 3.4 Blindagem: o teste de coerência

Um teste que, para o mesmo período e a mesma loja, pede o número a **todas** as
superfícies e exige o mesmo valor:

- `metrics.totais()` (referência)
- `GET /stores/reports/revenue/`
- `GET /stores/reports/dashboard/`
- `GET /stores/reports/orders/export/`
- `StoreCashSession.expected_amount` (recorte: só dinheiro)
- `ai_insights`

Falha com a diferença impressa por superfície. É este teste que impede a
próxima tela de inventar a regra dela — sem ele, o resto desta spec envelhece
em duas semanas.

### 3.5 Recuperar os R$ 306

Comando `python manage.py liquidar_entregas_em_dinheiro [--dry-run] [--loja]`:
marca `paid` os pedidos entregues em método offline que nunca liquidaram, usando
`delivered_at` como `paid_at` (e não `now()`, senão a venda de 31/07 aparece no
faturamento de hoje). Idempotente.

### 3.6 Normalizar os métodos

`payment_method` ganha `choices` com um conjunto fechado, e uma migração de
dados mapeia o legado:

```
credit_card, card  -> card
other              -> other        (mantido: é o link de pagamento avulso)
''                 -> unknown
```

Os vazios: a maioria é `failed`/`cancelled` (irrelevantes) e um é uma venda
entregue e paga de R$ 40,49 (`CE-2606169495`) — vira `unknown`, sem inventar
método. Adivinhar "provavelmente foi dinheiro" colocaria R$ 40,49 na gaveta de
um caixa que nunca os viu.

### 3.7 Cortes novos

No relatório de vendas: faturamento **por método de pagamento** e **por canal**
(site / WhatsApp / PDV). O canal sai de `metadata.source`, que já é gravado.

---

## 4. Ordem de execução

1. Delegação do status (3.1) — é a causa da perda de dinheiro.
2. Comando de recuperação (3.5) — só depois de 1, senão o furo continua.
3. Teste de coerência (3.4) — vermelho aqui é o mapa do que falta.
4. Cartão + rótulos (3.3).
5. Contrato em código (3.2).
6. Normalização de métodos (3.6) — pré-requisito do próximo plano.
7. Cortes novos (3.7).

---

## 5. O que NÃO está neste plano

- "Pagar na entrega" — é o plano seguinte, e depende de 3.6.
- Checkout do cliente recorrente — terceiro plano.
- Reescrever `apps/stores/metrics/` — está correto.
- Frete/cupom/gorjeta dentro ou fora do faturamento: `reports/revenue` já
  devolve `total_delivery_fees` e `total_discounts` separados. Se depois da
  correção o número ainda não bater com o caixa do dono, isso vira investigação
  própria — mudar a definição de receita sem evidência seria trocar um número
  arbitrário por outro.

---

## 6. Critério de pronto

- Pedido em dinheiro entregue por **qualquer** caminho termina pago.
- Os R$ 306,00 aparecem no faturamento, na data em que foram entregues.
- O teste de coerência passa com todas as superfícies.
- O cartão do painel mostra dois números divisíveis entre si.
- Nenhum `payment_method` fora do conjunto fechado.
- Suítes verdes: `apps/stores`, `apps/whatsapp`, painel.
