"""Promoção por dia da semana precisa SALVAR pelo painel.

O painel tem os campos, o formulário envia os dois, e o backend descartava em
silêncio: `StoreProductCreateSerializer` — usado em create/update/partial_update
— não listava `promo_price` nem `promo_weekday` em `fields`, e o DRF ignora
campo fora da lista SEM erro.

Resultado: o lojista preenchia, via "Produto atualizado!", o modal fechava e
nada era gravado. Em 20/08 só 1 dos 42 produtos da Cê Saladas tinha promoção —
e essa única tinha sido escrita direto no banco, não pelo painel.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct


class PromoSalvaPeloPainelTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username='dono_promo', email='d@promo.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Promo', slug='loja-promo', owner=self.owner, status='active',
        )
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Especial Filé de Frango',
            price=Decimal('39.99'), status='active',
        )
        self.client.force_authenticate(user=self.owner)

    def _url(self):
        return f'/api/v1/stores/products/{self.produto.id}/'

    def test_patch_grava_a_promocao(self):
        resp = self.client.patch(
            self._url(), {'promo_price': '32.99', 'promo_weekday': 3}, format='json',
        )
        self.assertIn(resp.status_code, (200, 202), resp.content[:300])
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.promo_price, Decimal('32.99'))
        self.assertEqual(self.produto.promo_weekday, 3)

    def test_promocao_pode_ser_removida(self):
        """Tirar a promoção precisa funcionar tanto quanto pôr."""
        self.produto.promo_price = Decimal('32.99')
        self.produto.promo_weekday = 3
        self.produto.save()
        self.client.patch(
            self._url(), {'promo_price': None, 'promo_weekday': None}, format='json',
        )
        self.produto.refresh_from_db()
        self.assertIsNone(self.produto.promo_price)
        self.assertIsNone(self.produto.promo_weekday)

    def test_preco_de_cadastro_nao_e_tocado(self):
        """`price` é o valor cheio e NUNCA muda — quem decide é preco_vigente()."""
        self.client.patch(
            self._url(), {'promo_price': '32.99', 'promo_weekday': 3}, format='json',
        )
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.price, Decimal('39.99'))
