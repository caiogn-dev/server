"""Regressão de segurança (tampering cross-tenant): is_staff podia ESCREVER
em lojas alheias via combos e product-types.

`_assert_store_access` (StoreComboViewSet e StoreProductTypeViewSet) liberava
`user.is_staff or user.is_superuser`. is_staff dá acesso ao /admin do Django,
NÃO acesso cross-tenant (invariante do commit 0d62a19): um usuário is_staff
sem vínculo com a loja conseguia CRIAR/EDITAR/DELETAR combos e tipos de
produto de qualquer tenant. Mesma família: StoreProductVariantViewSet
vazava a LEITURA de variantes de produtos alheios para is_staff.

Cenários:
  1-3. attacker is_staff NÃO cria/edita/deleta combo na loja vítima (403).
  4-6. idem para product-types.
  7.   attacker is_staff NÃO lista variantes de produto alheio.
  8-9. Regressão: owner e superuser continuam operando normalmente.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store, StoreCategory, StoreCombo, StoreProduct, StoreProductType,
    StoreProductVariant,
)

User = get_user_model()

COMBOS_URL = '/api/v1/stores/combos/'
TYPES_URL = '/api/v1/stores/product-types/'


class ProductWriteIsStaffTamperingTest(APITestCase):
    def setUp(self):
        self.victim = User.objects.create_user(
            username='tam-victim', email='tam-v@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja Vítima', slug='tam-loja-vitima', owner=self.victim, status='active')
        self.combo = StoreCombo.objects.create(
            store=self.store, name='Combo Secreto', slug='tam-combo',
            price=Decimal('30.00'))
        self.ptype = StoreProductType.objects.create(
            store=self.store, name='Molho', slug='tam-molho')
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='tam-cat')
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Prod', slug='tam-prod',
            price=Decimal('10.00'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False)
        self.variant = StoreProductVariant.objects.create(
            product=self.product, name='Grande', price=Decimal('12.00'),
            stock_quantity=5)

        # is_staff (acesso /admin) SEM vínculo com a loja vítima.
        self.attacker = User.objects.create_user(
            username='tam-staff', email='tam-s@t.com', password='x', is_staff=True)
        self.superuser = User.objects.create_superuser(
            username='tam-super', email='tam-su@t.com', password='x')

    # --- Combos -----------------------------------------------------------

    def test_isstaff_nao_cria_combo_em_loja_alheia(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(COMBOS_URL, {
            'store': str(self.store.id), 'name': 'Injetado',
            'slug': 'tam-injetado', 'price': '1.00',
        }, format='json')
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(StoreCombo.objects.filter(slug='tam-injetado').exists())

    def test_isstaff_nao_edita_combo_de_loja_alheia(self):
        # 404 (escondido pelo get_queryset) ou 403 são negações válidas.
        self.client.force_authenticate(self.attacker)
        resp = self.client.patch(
            f'{COMBOS_URL}{self.combo.id}/', {'name': 'HACKED'}, format='json')
        self.assertIn(resp.status_code, (403, 404), resp.content)
        self.combo.refresh_from_db()
        self.assertEqual(self.combo.name, 'Combo Secreto')

    def test_isstaff_nao_deleta_combo_de_loja_alheia(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.delete(f'{COMBOS_URL}{self.combo.id}/')
        self.assertIn(resp.status_code, (403, 404), resp.content)
        self.assertTrue(StoreCombo.objects.filter(pk=self.combo.pk).exists())

    # --- Product types ----------------------------------------------------

    def test_isstaff_nao_cria_product_type_em_loja_alheia(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(TYPES_URL, {
            'store': str(self.store.id), 'name': 'Injetado', 'slug': 'tam-tipo-inj',
        }, format='json')
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(StoreProductType.objects.filter(slug='tam-tipo-inj').exists())

    def test_isstaff_nao_edita_product_type_de_loja_alheia(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.patch(
            f'{TYPES_URL}{self.ptype.id}/', {'name': 'HACKED'}, format='json')
        self.assertIn(resp.status_code, (403, 404), resp.content)
        self.ptype.refresh_from_db()
        self.assertEqual(self.ptype.name, 'Molho')

    def test_isstaff_nao_deleta_product_type_de_loja_alheia(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.delete(f'{TYPES_URL}{self.ptype.id}/')
        self.assertIn(resp.status_code, (403, 404), resp.content)
        self.assertTrue(StoreProductType.objects.filter(pk=self.ptype.pk).exists())

    # --- Variantes (leitura) ----------------------------------------------

    def test_isstaff_nao_lista_variantes_de_produto_alheio(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(
            f'/api/v1/stores/products/{self.product.id}/variants/')
        # is_staff sem vínculo não pode enxergar as variantes do tenant.
        if resp.status_code == 200:
            data = resp.data.get('results', resp.data)
            self.assertEqual(len(data), 0, data)
        else:
            self.assertIn(resp.status_code, (403, 404), resp.content)

    # --- Regressão: owner e superuser seguem funcionando -------------------

    def test_owner_continua_editando_o_proprio_combo(self):
        self.client.force_authenticate(self.victim)
        resp = self.client.patch(
            f'{COMBOS_URL}{self.combo.id}/', {'name': 'Novo Nome'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.combo.refresh_from_db()
        self.assertEqual(self.combo.name, 'Novo Nome')

    def test_superuser_continua_editando_qualquer_combo(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.patch(
            f'{COMBOS_URL}{self.combo.id}/', {'name': 'Via Super'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.combo.refresh_from_db()
        self.assertEqual(self.combo.name, 'Via Super')
