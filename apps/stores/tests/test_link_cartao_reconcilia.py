"""O pagamento por REDIRECT (link de cartão) precisa achar o pedido de volta.

31/08, pedido CE-2608318490 da Dênia: ela pagou R$ 35,99 no cartão pelo link
que o bot mandou no WhatsApp. O Mercado Pago aprovou, notificou QUATRO vezes, e
o sistema devolveu 200 nas quatro sem fazer nada:

    WARNING  Order/charge not found for payment 176516131214

Dinheiro na conta, pedido `pending` no painel, venda fora do faturamento.

A causa é um beco sem saída. O branch de cartão com `allow_redirect` (o que o
bot do WhatsApp usa) é o ÚNICO caminho de pagamento que:

  - não cria StorePayment  (o branch 'link' cria, o PIX cria);
  - manda notification_url SEM o slug da loja  (o branch 'link' manda com);
  - nunca grava order.payment_id.

Resultado: o webhook chega só com o id do pagamento. Para buscar o pagamento no
MP é preciso a credencial da loja; para saber a loja é preciso o
`external_reference`; e o `external_reference` só existe DENTRO do pagamento que
ainda não pôde ser buscado. O handler desiste antes de começar.

O que este arquivo trava:
  1. a reconciliação casa o pedido pelo `external_reference` = id do pedido,
     que é exatamente o que esse branch escreve na preference;
  2. o branch de redirect passa a registrar a cobrança e a assinar a
     notificação com o slug — como o link já fazia.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService


def _loja_e_pedido(slug='loja-lc'):
    User = get_user_model()
    dono = User.objects.create_user(username=f'dono_{slug}', email=f'{slug}@t.com', password='x')
    loja = Store.objects.create(name='Loja LC', slug=slug, owner=dono)
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='DENIA OLIVEIRA',
        customer_email='denia@t.com', customer_phone='556384122444',
        subtotal=Decimal('35.99'), total=Decimal('35.99'),
        payment_method='credit_card',
    )
    return loja, pedido


class ReconciliaPorExternalReferenceTests(TestCase):
    """O webhook casa o pedido pelo id do pedido no external_reference."""

    def test_pedido_sem_cobranca_e_sem_payment_id_ainda_e_reconciliado(self):
        # Exatamente o estado do CE-2608318490: preference criada pelo branch de
        # redirect, portanto nenhuma StorePayment e payment_id vazio.
        _, pedido = _loja_e_pedido('loja-lc1')
        self.assertEqual(pedido.payments.count(), 0)
        self.assertEqual(pedido.payment_id, '')

        devolvido = CheckoutService.process_payment_webhook(
            '176516131214', 'approved', external_reference=str(pedido.id),
        )

        pedido.refresh_from_db()
        self.assertIsNotNone(devolvido, 'webhook devolveu None — pagamento perdido')
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(pedido.paid_at)

    def test_grava_o_payment_id_para_o_reenvio_casar_direto(self):
        _, pedido = _loja_e_pedido('loja-lc2')

        CheckoutService.process_payment_webhook(
            '176516131214', 'approved', external_reference=str(pedido.id),
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.payment_id, '176516131214')

    def test_external_reference_que_nao_e_uuid_nao_estoura(self):
        # `subpix:<uuid>:2026-08` e `splink:<hex>` passam pelo mesmo caminho.
        # Um filter(id=...) cru levanta ValidationError e derruba o webhook.
        _loja_e_pedido('loja-lc3')
        try:
            CheckoutService.process_payment_webhook(
                '999', 'approved', external_reference='subpix:nao-e-uuid:2026-08',
            )
        except Exception as e:                                    # pragma: no cover
            self.fail(f'external_reference não-UUID derrubou o webhook: {e!r}')


@override_settings(BASE_URL='https://api.exemplo.com')
class RedirectDeCartaoRegistraCobrancaTests(TestCase):
    """O link de cartão precisa deixar rastro igual ao link de pagamento."""

    def setUp(self):
        self.loja, self.pedido = _loja_e_pedido('loja-lc4')

    def _criar_com_redirect(self):
        preference = {'id': '235180147-23105bd9', 'init_point': 'https://mp/x'}
        sdk = mock.MagicMock()
        sdk.preference.return_value.create.return_value = {'status': 201, 'response': preference}
        with mock.patch('mercadopago.SDK', return_value=sdk), \
             mock.patch.object(
                 CheckoutService, 'get_payment_credentials',
                 return_value={'provider': 'mercadopago', 'access_token': 'TOKEN', 'sandbox': False},
             ):
            resultado = CheckoutService.create_payment(
                order=self.pedido, payment_method='credit_card',
                payment_data={'allow_redirect': True},
            )
        enviado = sdk.preference.return_value.create.call_args[0][0]
        return resultado, enviado

    def test_cria_a_cobranca_do_pedido(self):
        resultado, _ = self._criar_com_redirect()
        self.assertTrue(resultado['success'])
        cobrancas = self.pedido.payments.all()
        self.assertEqual(cobrancas.count(), 1, 'redirect de cartão não registrou cobrança')
        cobranca = cobrancas.first()
        self.assertEqual(cobranca.external_id, '235180147-23105bd9')
        self.assertEqual(cobranca.external_reference, str(self.pedido.id))
        self.assertEqual(cobranca.amount, Decimal('35.99'))
        self.assertEqual(cobranca.status, StorePayment.PaymentStatus.PENDING)

    def test_notification_url_leva_o_slug_da_loja(self):
        # Sem o slug o handler não tem como resolver a credencial antes de
        # buscar o pagamento — foi o que fez o aviso da Dênia ser descartado.
        _, enviado = self._criar_com_redirect()
        self.assertTrue(
            enviado['notification_url'].endswith(f'/{self.loja.slug}/'),
            f"notification_url sem slug: {enviado['notification_url']}",
        )
