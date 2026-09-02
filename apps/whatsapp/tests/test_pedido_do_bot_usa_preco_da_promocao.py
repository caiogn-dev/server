"""O bot também tem que cobrar a promoção do dia.

Mesma raiz do pedido pelo painel (02/09): `preco_vigente()` é a fonte única de
preço desde 12/08, mas os caminhos que COBRAM continuavam lendo `product.price`
direto. No WhatsApp isso aparecia duas vezes na mesma conversa:

  • o resumo do pedido de catálogo (`_linha_de_item_do_catalogo`);
  • o `unit_price` que segue para o pedido de verdade.

Resultado na quarta da Almôndega: vitrine e cardápio a R$ 30,75, bot cobrando
R$ 44,90.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreProduct
from apps.whatsapp.services.webhook_service import WebhookService

User = get_user_model()

QUARTA, QUINTA = 2, 3


def _quarta():
    return timezone.make_aware(timezone.datetime(2026, 8, 12, 13, 0))


def _quinta():
    return timezone.make_aware(timezone.datetime(2026, 8, 13, 13, 0))


class PrecoDaPromocaoNoBotTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-promo-bot', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-promo-bot', owner=owner,
        )
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium', slug='almondega-promo-bot',
            price=Decimal('44.90'), is_active=True,
            promo_price=Decimal('30.75'), promo_weekday=QUARTA,
        )

    def test_resumo_do_catalogo_usa_o_preco_da_promocao(self):
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            linha, subtotal = WebhookService._linha_de_item_do_catalogo(
                self.produto, quantidade=2, preco_da_meta=44.90,
            )

        self.assertEqual(subtotal, Decimal('61.50'))
        self.assertIn('61,50', linha)

    def test_fora_do_dia_o_bot_cobra_cheio(self):
        with patch('django.utils.timezone.localtime', return_value=_quinta()):
            _, subtotal = WebhookService._linha_de_item_do_catalogo(
                self.produto, quantidade=1, preco_da_meta=None,
            )

        self.assertEqual(subtotal, Decimal('44.90'))
