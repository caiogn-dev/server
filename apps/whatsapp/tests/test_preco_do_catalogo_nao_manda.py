"""Quem diz o preço é a LOJA, não o catálogo da Meta.

31/08, Dênia × Cê Saladas. Ela pediu pelo catálogo do WhatsApp e o bot
respondeu, em duas mensagens seguidas:

    Recebi seu pedido pelo catalogo:
    • 1x Almôndega Premium - R$ 40.90
    Total dos itens: *R$ 40.90*
                                        ← 15 segundos depois
    📋 *Resumo do seu pedido:*
    • 1x Almôndega Premium — R$ 35,99
    💰 *Total: R$ 35,99*

Dois preços para o mesmo item na mesma conversa. O feed da Meta estava
desatualizado (R$ 40,90) e o preço real da loja era R$ 35,99.

O código já **percebia** a divergência — e usava o preço da Meta assim mesmo:

    product_price = float(product.price)
    unit_price = product_price
    if meta_price_float >= 0:
        unit_price = meta_price_float          # ← sobrescreve o preço real
    if abs(meta_price_float - product_price) >= 0.01:
        logger.warning('Meta catalog price differs from store price')

O pedido de verdade nunca usou esse valor (só `product_id` e `quantity` seguem
adiante) — quem mentia era só a mensagem que o cliente lê. O que é pior do que
parece: se o feed estivesse mais BARATO que a loja, o cliente veria um preço e
pagaria outro, mais caro.

Contrato: o preço exibido vem sempre de `StoreProduct.price`. A divergência
continua virando WARNING, porque é sintoma de feed velho e alguém precisa saber.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreProduct
from apps.whatsapp.services.webhook_service import WebhookService

User = get_user_model()


class PrecoDoCatalogoNaoMandaTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-cat', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-cat', owner=owner,
        )
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium', slug='almondega-premium-cat',
            price=Decimal('35.99'), is_active=True,
        )

    def _resumo(self, preco_da_meta):
        """O resumo que o cliente lê, com o preço que a Meta mandou."""
        return WebhookService._linha_de_item_do_catalogo(
            self.produto, quantidade=1, preco_da_meta=preco_da_meta,
        )

    def test_usa_o_preco_da_loja_e_nao_o_do_catalogo(self):
        linha, subtotal = self._resumo(40.90)

        self.assertIn('35,99', linha)
        self.assertNotIn('40', linha)
        self.assertEqual(subtotal, Decimal('35.99'))

    def test_vale_tambem_quando_o_catalogo_esta_mais_BARATO(self):
        # A direção que machuca o cliente: ele vê barato e paga caro.
        linha, subtotal = self._resumo(19.90)

        self.assertIn('35,99', linha)
        self.assertEqual(subtotal, Decimal('35.99'))

    def test_sem_preco_da_meta_nada_muda(self):
        linha, subtotal = self._resumo(None)

        self.assertIn('35,99', linha)
        self.assertEqual(subtotal, Decimal('35.99'))

    def test_quantidade_multiplica_o_preco_da_LOJA(self):
        linha, subtotal = WebhookService._linha_de_item_do_catalogo(
            self.produto, quantidade=3, preco_da_meta=40.90,
        )

        self.assertEqual(subtotal, Decimal('107.97'))   # 3 × 35,99
        self.assertIn('107,97', linha)
        self.assertIn('3x', linha)

    def test_moeda_em_portugues(self):
        linha, _ = self._resumo(40.90)
        self.assertNotIn('35.99', linha)

    def test_divergencia_continua_virando_aviso(self):
        # Feed velho é problema real; silenciar esconderia a causa.
        with self.assertLogs('apps.whatsapp.services.webhook_service', level='WARNING') as capturado:
            self._resumo(40.90)
        self.assertTrue(
            any('catalog' in linha.lower() for linha in capturado.output),
            capturado.output,
        )

    def test_preco_igual_nao_polui_o_log(self):
        import logging
        with mock.patch.object(logging.getLogger('apps.whatsapp.services.webhook_service'), 'warning') as aviso:
            self._resumo(35.99)
        aviso.assert_not_called()
