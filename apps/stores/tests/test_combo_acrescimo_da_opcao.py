"""Acréscimo por opção em combo de PREÇO FECHADO (03/11).

O dono: "combo fechado é 59,99, mas se escolher a Tilápia em vez da Queridinha
seria +3,00". Até aqui o combo fixo devolvia `price` e ignorava as escolhas —
o `price_override` da opção só vale no combo de montagem (dynamic_pricing),
onde ele é o preço do item, não um acréscimo. Campo próprio (`acrescimo`)
para não começar a cobrar em combo fixo que já tinha `price_override` salvo.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.api.serializers import PublicComboSerializer, StoreComboSerializer
from apps.stores.models import Store, StoreCombo, StoreProduct, StoreProductVariant

User = get_user_model()


class AcrescimoDaOpcaoTests(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-acr', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-acr', owner=dono, status='active')
        self.queridinha = StoreProduct.objects.create(
            store=self.store, name='Queridinha', slug='queridinha', price=Decimal('39.90'), status='active', track_stock=False)
        self.tilapia = StoreProduct.objects.create(
            store=self.store, name='Tilápia', slug='tilapia', price=Decimal('44.90'), status='active', track_stock=False)
        self.suco = StoreProduct.objects.create(
            store=self.store, name='Suco', slug='suco', price=Decimal('12.00'), status='active', track_stock=False)
        self.laranja = StoreProductVariant.objects.create(
            product=self.suco, name='Laranja', price=Decimal('12.00'))
        self.detox = StoreProductVariant.objects.create(
            product=self.suco, name='Detox', price=Decimal('14.00'))

    def _combo(self, dynamic=False, opcoes=None, variantes=None, price='59.99'):
        payload = {
            'store': str(self.store.id), 'name': 'Salada + Suco + Sobremesa', 'slug': 'sss',
            'price': price, 'is_active': True, 'dynamic_pricing': dynamic,
            'groups': [
                {'title': 'Salada', 'min_selections': 1, 'max_selections': 1, 'position': 0,
                 'product_options': opcoes if opcoes is not None else [
                     {'product_id': str(self.queridinha.id), 'max_selections': 1},
                     {'product_id': str(self.tilapia.id), 'max_selections': 1, 'acrescimo': '3.00'},
                 ]},
                {'product': str(self.suco.id), 'min_selections': 1, 'max_selections': 1, 'position': 1,
                 'variant_limits': variantes if variantes is not None else [
                     {'variant_id': str(self.laranja.id), 'max_selections': 1},
                     {'variant_id': str(self.detox.id), 'max_selections': 1, 'acrescimo': '2.50'},
                 ]},
            ],
        }
        s = StoreComboSerializer(data=payload)
        self.assertTrue(s.is_valid(), s.errors)
        combo = s.save()
        grupos = sorted(combo.groups.all(), key=lambda g: g.position)
        return combo, str(grupos[0].id), str(grupos[1].id)

    def test_escolha_sem_acrescimo_fica_no_preco_fechado(self):
        combo, salada, suco = self._combo()
        self.assertEqual(
            combo.compute_unit_price({salada: [str(self.queridinha.id)], suco: [str(self.laranja.id)]}),
            Decimal('59.99'))

    def test_tilapia_soma_tres_reais(self):
        combo, salada, suco = self._combo()
        self.assertEqual(
            combo.compute_unit_price({salada: [str(self.tilapia.id)], suco: [str(self.laranja.id)]}),
            Decimal('62.99'))

    def test_acrescimo_de_variante_tambem_soma(self):
        combo, salada, suco = self._combo()
        self.assertEqual(
            combo.compute_unit_price({salada: [str(self.tilapia.id)], suco: [str(self.detox.id)]}),
            Decimal('65.49'))

    def test_combo_fixo_com_price_override_antigo_nao_passa_a_cobrar(self):
        combo, salada, suco = self._combo(opcoes=[
            {'product_id': str(self.tilapia.id), 'max_selections': 1, 'price_override': '18.00'},
        ])
        self.assertEqual(combo.compute_unit_price({salada: [str(self.tilapia.id)]}), Decimal('59.99'))

    def test_selecao_de_outro_combo_ou_id_inventado_nao_soma(self):
        combo, salada, _ = self._combo()
        self.assertEqual(combo.compute_unit_price({salada: ['nao-existe'], 'grupo-falso': [str(self.tilapia.id)]}),
                         Decimal('59.99'))

    def test_acrescimo_negativo_e_recusado(self):
        payload_opcoes = [{'product_id': str(self.tilapia.id), 'max_selections': 1, 'acrescimo': '-5'}]
        payload = {
            'store': str(self.store.id), 'name': 'X', 'slug': 'x', 'price': '10', 'is_active': True,
            'groups': [{'title': 'S', 'min_selections': 1, 'max_selections': 1, 'product_options': payload_opcoes}],
        }
        s = StoreComboSerializer(data=payload)
        if s.is_valid():
            combo = s.save()
            grupo = combo.groups.first()
            self.assertEqual(combo.compute_unit_price({str(grupo.id): [str(self.tilapia.id)]}), Decimal('10.00'))
        else:
            self.assertIn('groups', s.errors)

    def test_painel_e_vitrine_leem_o_acrescimo(self):
        combo, _, _ = self._combo()
        combo = StoreCombo.objects.get(pk=combo.pk)
        for dados in (StoreComboSerializer(combo).data, PublicComboSerializer(combo).data):
            grupos = sorted(dados['groups'], key=lambda g: g.get('position', 0))
            opcoes = {o['product_id']: o for o in grupos[0]['product_options']}
            self.assertEqual(opcoes[str(self.tilapia.id)]['acrescimo'], 3.0)
            self.assertEqual(opcoes[str(self.queridinha.id)]['acrescimo'], 0.0)
            variantes = {v['variant_id']: v for v in grupos[1]['variant_limits']}
            self.assertEqual(variantes[str(self.detox.id)]['acrescimo'], 2.5)

    def test_combo_de_montagem_continua_igual(self):
        combo, salada, _ = self._combo(dynamic=True, price='0', opcoes=[
            {'product_id': str(self.queridinha.id), 'max_selections': 1, 'price_override': '20.00'},
            {'product_id': str(self.tilapia.id), 'max_selections': 1},
        ], variantes=[])
        self.assertEqual(combo.compute_unit_price({salada: [str(self.queridinha.id)]}), Decimal('20.00'))
        self.assertEqual(combo.compute_unit_price({salada: [str(self.tilapia.id)]}), Decimal('44.90'))
