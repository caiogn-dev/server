"""`StoreOrder.payment_method` fala UMA língua só.

O painel mostrava "other" no pedido. Não era erro de tela: o campo é texto
livre e três escritores discordavam, cada um gravando de um jeito. Em 31/08 o
banco de produção tinha SEIS dialetos no mesmo campo:

    pix 124 | cash 57 | credit_card 8 | card 5 | '' 9 | 'Outro' 1 | 'other' 1

  - `StorePayment._sync_with_order` gravava o RÓTULO (`get_..._display()`),
    de onde saiu o único 'Outro' com O maiúsculo;
  - `_venda_de_cobranca_avulsa` gravava o slug cru;
  - o link de pagamento nasce 'other' e o método REAL que o cliente escolheu no
    Checkout Pro (cartão, PIX, boleto) nunca era gravado de volta.

Regra: o campo guarda SEMPRE um slug de `StorePayment.PaymentMethod`, nunca um
rótulo, e o método real do gateway sobrescreve o provisório 'other'.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services import mp_orders


def _loja_e_pedido(slug, metodo=''):
    User = get_user_model()
    dono = User.objects.create_user(username=f'd_{slug}', email=f'{slug}@t.com', password='x')
    loja = Store.objects.create(name='L', slug=slug, owner=dono)
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_email='c@t.com',
        customer_phone='63999990000', subtotal=Decimal('50.00'),
        total=Decimal('50.00'), payment_method=metodo,
    )
    return loja, pedido


class SincronizacaoGravaSlugTests(TestCase):
    def test_nunca_grava_o_rotulo_em_portugues(self):
        # `get_payment_method_display()` devolve 'Outro' / 'Cartão de crédito'.
        # Rótulo no banco quebra todo filtro e todo relatório por método.
        loja, pedido = _loja_e_pedido('mv1')
        StorePayment.objects.create(
            order=pedido, store=loja, amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.OTHER,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_id='1',
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.payment_method, 'other')

    def test_metodo_real_sobrescreve_o_provisorio_other(self):
        # O link nasce 'other'; quando o gateway diz que foi cartão, o pedido
        # precisa aprender. Antes o `if not order.payment_method` travava o
        # valor provisório para sempre.
        loja, pedido = _loja_e_pedido('mv2', metodo='other')
        StorePayment.objects.create(
            order=pedido, store=loja, amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.CREDIT_CARD,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_id='2',
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.payment_method, 'credit_card')

    def test_nao_sobrescreve_metodo_ja_conhecido(self):
        # Dinheiro na entrega registrado pelo balcão não vira 'pix' porque uma
        # cobrança PIX cancelada existiu no meio do caminho.
        loja, pedido = _loja_e_pedido('mv3', metodo='cash')
        StorePayment.objects.create(
            order=pedido, store=loja, amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_id='3',
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.payment_method, 'cash')


class MetodoDoGatewayTests(TestCase):
    """Tradução do vocabulário do Mercado Pago para o nosso."""

    def test_traduz_os_tipos_que_o_mp_devolve(self):
        casos = [
            ({'payment_type_id': 'credit_card', 'payment_method_id': 'master'}, 'credit_card'),
            ({'payment_type_id': 'debit_card', 'payment_method_id': 'debvisa'}, 'debit_card'),
            ({'payment_type_id': 'bank_transfer', 'payment_method_id': 'pix'}, 'pix'),
            ({'payment_type_id': 'ticket', 'payment_method_id': 'bolbradesco'}, 'boleto'),
            ({'payment_type_id': 'account_money', 'payment_method_id': 'account_money'}, 'wallet'),
        ]
        for payload, esperado in casos:
            with self.subTest(payload=payload):
                self.assertEqual(mp_orders.metodo_do_pagamento(payload), esperado)

    def test_desconhecido_nao_inventa_metodo(self):
        self.assertIsNone(mp_orders.metodo_do_pagamento({'payment_type_id': 'cripto_novo'}))
        self.assertIsNone(mp_orders.metodo_do_pagamento({}))
        self.assertIsNone(mp_orders.metodo_do_pagamento(None))

    def test_todo_valor_traduzido_existe_no_nosso_vocabulario(self):
        # Tradução que devolve slug fora de PaymentMethod volta a produzir
        # "other" cru na tela — só que agora com outro nome.
        validos = set(StorePayment.PaymentMethod.values)
        for tipo in ['credit_card', 'debit_card', 'bank_transfer', 'ticket', 'account_money']:
            traduzido = mp_orders.metodo_do_pagamento({'payment_type_id': tipo})
            self.assertIn(traduzido, validos)


class WebhookGravaMetodoRealTests(TestCase):
    """O que o cliente escolheu no Checkout Pro volta para o pedido."""

    def test_link_que_nasceu_other_vira_o_metodo_real(self):
        from apps.stores.services.checkout_service import CheckoutService

        loja, pedido = _loja_e_pedido('mv4', metodo='other')
        cobranca = StorePayment.objects.create(
            order=pedido, store=loja, amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.OTHER,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='9001', external_reference=f'splink:{"a" * 32}',
        )

        CheckoutService.process_payment_webhook(
            '9001', 'approved', payment_method='credit_card',
        )

        cobranca.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(cobranca.payment_method, 'credit_card')
        self.assertEqual(pedido.payment_method, 'credit_card')

    def test_sem_traducao_o_metodo_anterior_permanece(self):
        from apps.stores.services.checkout_service import CheckoutService

        loja, pedido = _loja_e_pedido('mv5', metodo='pix')
        cobranca = StorePayment.objects.create(
            order=pedido, store=loja, amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='9002',
        )

        CheckoutService.process_payment_webhook('9002', 'approved', payment_method=None)

        cobranca.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(cobranca.payment_method, 'pix')
        self.assertEqual(pedido.payment_method, 'pix')
