"""Link de pagamento pago tem que virar VENDA.

Relatado pelo dono em 14/ago: "o link de pagamento que geramos pelo próprio
painel não conta como venda no final".

Investigado com dado real, e a queixa procede — mas não pelo motivo que parecia.
A reconciliação FUNCIONA: o `external_reference` `splink:<token>` casa o webhook
com a cobrança, e um link de 07/08 chegou a receber o id do MP e virar `failed`
corretamente. Os 8 pendentes eram links que ninguém pagou (confirmado na API do
Mercado Pago: nenhum pagamento existe para aqueles `external_reference`).

O buraco é o passo seguinte, e estava escrito no docstring do próprio código:

    "Avulso (order=None) só marca a cobrança."

Ou seja: o cliente paga, a cobrança vira `completed`, e morre ali. Nunca nasce
um `StoreOrder` — e faturamento se conta por pedido. Dinheiro que entrou e não
apareceu como venda.

Medido: **2 cobranças completed sem pedido, R$ 249,01**.

Contrato: link pago sem pedido cria uma venda avulsa. Link amarrado a um pedido
continua reconciliando nele, sem duplicar.
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _cobranca(loja, valor='142.00', order=None, ref='splink:abc123'):
    return StorePayment.objects.create(
        store=loja, order=order, amount=Decimal(valor),
        status=StorePayment.PaymentStatus.PENDING,
        payment_method='other', external_reference=ref,
    )


@pytest.mark.django_db
class TestLinkPagoViraVenda:
    def test_link_avulso_pago_cria_o_pedido(self, loja):
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order is not None, 'link pago continuou sem venda'
        assert cobranca.order.total == Decimal('142.00')

    def test_a_venda_nasce_paga(self, loja):
        """Nascer pendente faria o dono cobrar de novo quem já pagou."""
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.payment_status == 'paid'

    def test_a_venda_diz_de_onde_veio(self, loja):
        """Sem marca, ela vira um pedido fantasma que ninguém sabe explicar."""
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.metadata.get('origem') == 'link_de_pagamento'

    def test_a_venda_tem_uma_linha_de_item(self, loja):
        """Pedido sem item nenhum é a queixa de 15/ago: "só sai o valor".

        O pedido do link nascia com total e mais nada — a página de pedidos
        mostrava um valor solto e a comanda saía sem uma linha sequer. Não há
        produto de catálogo aqui (a cobrança é de valor arbitrário), mas há o
        que foi cobrado: a descrição, o valor e a quantidade 1. `product` é
        nulo de propósito — não inventamos um item do cardápio.
        """
        cobranca = _cobranca(loja)
        cobranca.metadata = {'description': 'Encomenda de sexta'}
        cobranca.save(update_fields=['metadata'])

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        item = cobranca.order.items.get()
        assert item.product_id is None
        assert item.product_name == 'Encomenda de sexta'
        assert item.quantity == 1
        assert item.unit_price == Decimal('142.00')
        assert item.subtotal == Decimal('142.00')

    def test_sem_descricao_a_linha_ainda_se_explica(self, loja):
        """Descrição vazia não pode virar linha em branco na comanda."""
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.items.get().product_name == 'Cobrança por link de pagamento'

    def test_a_venda_carrega_o_nome_de_quem_pagou(self, loja):
        """Pedido sem cliente na lista é indistinguível de pedido corrompido."""
        cobranca = _cobranca(loja)
        cobranca.payer_name = 'Sillas Rodrigues'
        cobranca.payer_email = 'sillas@exemplo.com'
        cobranca.save(update_fields=['payer_name', 'payer_email'])

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.customer_name == 'Sillas Rodrigues'
        assert cobranca.order.customer_email == 'sillas@exemplo.com'

    def test_o_canal_e_o_link_e_nao_o_site(self, loja):
        """`source` caía em 'web' e o relatório por canal creditava o site.

        A coluna `source` é o que o BI lê; `metadata['origem']` ninguém
        agrupa. Enquanto os dois discordavam, a tela de canais mentia.
        """
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.source == 'payment_link'

    def test_nao_promete_entrega_que_ninguem_vai_fazer(self, loja):
        """`delivery_method` caía no default 'delivery' — sem endereço nenhum.

        A comanda então imprimia "*** ENTREGA ***" para uma cobrança que não
        tem para onde ir.
        """
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        cobranca.refresh_from_db()
        assert cobranca.order.delivery_method == 'digital'

    def test_webhook_repetido_nao_cria_dois_pedidos(self, loja):
        """O Mercado Pago reentrega notificação — é a regra, não a exceção."""
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        assert StoreOrder.objects.filter(store=loja).count() == 1


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_link_amarrado_a_pedido_nao_cria_outro(self, loja):
        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('100.00'), subtotal=Decimal('100.00'),
            status='pending', payment_status='pending', payment_method='pix',
        )
        cobranca = _cobranca(loja, '100.00', order=pedido)

        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

        assert StoreOrder.objects.filter(store=loja).count() == 1
        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'

    def test_link_nao_pago_nao_vira_venda(self, loja):
        """Cobrança gerada e não paga é orçamento, não faturamento.

        8 dos pendentes em produção eram exatamente isto — e contá-los seria
        inflar o faturamento com dinheiro que nunca entrou.
        """
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'pending')

        cobranca.refresh_from_db()
        assert cobranca.order is None
        assert StoreOrder.objects.filter(store=loja).count() == 0

    def test_link_recusado_nao_vira_venda(self, loja):
        cobranca = _cobranca(loja)

        CheckoutService._handle_storepayment_webhook(cobranca, 'rejected')

        cobranca.refresh_from_db()
        assert cobranca.order is None
