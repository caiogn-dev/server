"""Preço zero só com marca de brinde; pausa automática ao zerar estoque."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct, StoreCombo
from apps.stores.services.pausa_por_estoque import pausar_se_zerou, retomar_se_repos

User = get_user_model()


class Base(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='pz-owner', password='pw')
        self.store = Store.objects.create(name='Loja PZ', slug='pz-loja', owner=self.owner)
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')


class PrecoZeroProdutoTests(Base):
    URL = '/api/v1/stores/products/'

    def payload(self, **kw):
        base = {'store': str(self.store.id), 'name': 'Item', 'slug': 'item', 'price': '0.00', 'status': 'active'}
        base.update(kw)
        return base

    def test_ativo_a_zero_sem_brinde_e_barrado(self):
        r = self.client.post(self.URL, self.payload(), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('price', str(r.data))

    def test_ativo_a_zero_como_brinde_passa(self):
        r = self.client.post(self.URL, self.payload(is_brinde=True), format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_rascunho_a_zero_passa(self):
        r = self.client.post(self.URL, self.payload(status='draft'), format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_preco_positivo_passa(self):
        r = self.client.post(self.URL, self.payload(price='12.50'), format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_ativar_rascunho_a_zero_e_barrado(self):
        p = StoreProduct.objects.create(store=self.store, name='R', slug='r', price=Decimal('0'), status='draft')
        r = self.client.patch(f'{self.URL}{p.id}/', {'status': 'active'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_editar_outro_campo_de_legado_a_zero_nao_quebra(self):
        p = StoreProduct.objects.create(store=self.store, name='L', slug='l', price=Decimal('0'), status='active')
        r = self.client.patch(f'{self.URL}{p.id}/', {'stock_quantity': 5}, format='json')
        self.assertEqual(r.status_code, 200, r.data)


class PrecoZeroComboTests(Base):
    URL = '/api/v1/stores/combos/'

    def payload(self, **kw):
        base = {'store': str(self.store.id), 'name': 'Combo', 'slug': 'combo', 'price': '0.00', 'is_active': True}
        base.update(kw)
        return base

    def test_ativo_a_zero_sem_brinde_e_barrado(self):
        r = self.client.post(self.URL, self.payload(), format='json')
        self.assertEqual(r.status_code, 400, getattr(r, 'data', None))

    def test_brinde_passa(self):
        r = self.client.post(self.URL, self.payload(is_brinde=True), format='json')
        self.assertIn(r.status_code, (200, 201), r.data)

    def test_inativo_a_zero_passa(self):
        r = self.client.post(self.URL, self.payload(is_active=False), format='json')
        self.assertIn(r.status_code, (200, 201), r.data)

    def test_preco_dinamico_aceita_base_zero(self):
        r = self.client.post(self.URL, self.payload(dynamic_pricing=True), format='json')
        self.assertIn(r.status_code, (200, 201), r.data)


class PausaPorEstoqueTests(Base):
    def prod(self, **kw):
        d = dict(store=self.store, name='P', slug='p', price=Decimal('10'), track_stock=True, stock_quantity=1, status='active')
        d.update(kw)
        return StoreProduct.objects.create(**d)

    def test_flag_desligada_nao_pausa(self):
        p = self.prod()
        StoreProduct.objects.filter(id=p.id).update(stock_quantity=0)
        pausar_se_zerou([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_flag_ligada_pausa_ao_zerar(self):
        p = self.prod(pausar_ao_zerar=True)
        StoreProduct.objects.filter(id=p.id).update(stock_quantity=0)
        pausar_se_zerou([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'out_of_stock')

    def test_com_estoque_nao_pausa(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=3)
        pausar_se_zerou([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_aceita_encomenda_nao_pausa(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=0, allow_backorder=True)
        pausar_se_zerou([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_repor_estoque_devolve_ao_cardapio(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=0, status='out_of_stock')
        StoreProduct.objects.filter(id=p.id).update(stock_quantity=4)
        retomar_se_repos([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_inativo_pelo_dono_nao_volta_sozinho(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=4, status='inactive')
        retomar_se_repos([p.id])
        p.refresh_from_db()
        self.assertEqual(p.status, 'inactive')

    def test_salvar_pelo_painel_com_estoque_zero_pausa_e_repor_devolve(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=2)
        p.stock_quantity = 0
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.status, 'out_of_stock')
        p.stock_quantity = 6
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.status, 'active')

    def test_decrement_stock_pausa(self):
        p = self.prod(pausar_ao_zerar=True, stock_quantity=1)
        p.decrement_stock(1)
        p.refresh_from_db()
        self.assertEqual(p.status, 'out_of_stock')
