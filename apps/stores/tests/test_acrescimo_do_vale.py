"""O cliente que paga com vale paga o custo do vale — e sabe disso antes.

Receber em vale custa caro: a operadora fica com uma fatia que não existe no
PIX. Quem escolhe pagar assim paga esse custo, não a loja e não os outros
clientes pelo preço do prato.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.services.acrescimo_do_vale import (
    acrescimo_do_vale,
    e_pagamento_com_vale,
    percentual_do_vale,
)
from apps.stores.models import Store

User = get_user_model()


class AcrescimoDoValeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-acr', password='x', email='o-acr@real.com')
        self.loja = Store.objects.create(
            name='Loja Acr', slug='loja-acr', owner=self.owner, status='active',
            metadata={'voucher_fee_percent': 10})

    def test_dez_porcento_sobre_o_que_ele_ia_pagar(self):
        self.assertEqual(acrescimo_do_vale(self.loja, Decimal('50.00'), 'voucher'),
                         Decimal('5.00'))

    def test_vale_por_QR_paga_o_mesmo_que_vale_integrado(self):
        """Para o cliente é o mesmo negócio: ele está pagando com vale. Como a
        cobrança acontece nos bastidores não é problema dele."""
        self.assertEqual(acrescimo_do_vale(self.loja, Decimal('50.00'), 'voucher_link'),
                         acrescimo_do_vale(self.loja, Decimal('50.00'), 'voucher'))

    def test_pix_dinheiro_e_cartao_NAO_pagam_nada(self):
        for meio in ('pix', 'cash', 'card', 'credit_card', '', None):
            self.assertEqual(acrescimo_do_vale(self.loja, Decimal('50.00'), meio),
                             Decimal('0.00'), meio)

    def test_loja_sem_configurar_nao_cobra_nada(self):
        """Padrão é ZERO: subir esta versão não muda o preço de loja nenhuma."""
        outra = Store.objects.create(
            name='Sem Acr', slug='sem-acr', owner=self.owner, status='active')
        self.assertEqual(acrescimo_do_vale(outra, Decimal('50.00'), 'voucher'),
                         Decimal('0.00'))

    def test_arredonda_para_BAIXO(self):
        """10% de R$ 50,99 é R$ 5,099. Para cima cobraria acima do anunciado —
        num percentual que o cliente vê na tela, isso é o erro caro."""
        self.assertEqual(acrescimo_do_vale(self.loja, Decimal('50.99'), 'voucher'),
                         Decimal('5.09'))

    def test_incide_sobre_o_valor_JA_com_cupom_e_frete(self):
        """A base é o que ele pagaria sem o acréscimo. Incidir sobre o subtotal
        puro cobraria a mais de quem usou cupom."""
        # subtotal 100 + frete 9 − cupom 20 = 89
        self.assertEqual(acrescimo_do_vale(self.loja, Decimal('89.00'), 'voucher'),
                         Decimal('8.90'))

    def test_percentual_negativo_e_ignorado(self):
        """Negativo viraria DESCONTO por pagar com vale — o oposto disto."""
        self.loja.metadata = {'voucher_fee_percent': -10}
        self.assertEqual(percentual_do_vale(self.loja), Decimal('0'))

    def test_percentual_acima_de_cem_e_ignorado(self):
        self.loja.metadata = {'voucher_fee_percent': 1000}
        self.assertEqual(percentual_do_vale(self.loja), Decimal('0'))

    def test_lixo_na_configuracao_nao_derruba_o_checkout(self):
        for lixo in ('abc', {}, [], 'R$ 10'):
            self.loja.metadata = {'voucher_fee_percent': lixo}
            self.assertEqual(percentual_do_vale(self.loja), Decimal('0'), repr(lixo))

    def test_aceita_virgula_como_o_lojista_digita(self):
        self.loja.metadata = {'voucher_fee_percent': '7,5'}
        self.assertEqual(percentual_do_vale(self.loja), Decimal('7.5'))

    def test_base_zero_nao_vira_acrescimo(self):
        """Pedido coberto por saldo não ganha acréscimo do nada."""
        self.assertEqual(acrescimo_do_vale(self.loja, Decimal('0.00'), 'voucher'),
                         Decimal('0.00'))

    def test_os_dois_meios_de_vale_sao_reconhecidos(self):
        self.assertTrue(e_pagamento_com_vale('voucher'))
        self.assertTrue(e_pagamento_com_vale('VOUCHER_LINK'))
        self.assertFalse(e_pagamento_com_vale('pix'))


class AcrescimoNoPedidoDeVerdadeTests(TestCase):
    """Ponta a ponta: o pedido nasce com o acréscimo somado e gravado."""

    def setUp(self):
        from apps.stores.models import StoreCart, StoreCartItem, StoreCategory, StoreProduct
        self.owner = User.objects.create_user(
            username='o-e2e', password='x', email='o-e2e@real.com')
        self.loja = Store.objects.create(
            name='Loja E2E', slug='loja-e2e', owner=self.owner, status='active',
            metadata={'voucher_fee_percent': 10})
        cat = StoreCategory.objects.create(store=self.loja, name='G', slug='g')
        self.produto = StoreProduct.objects.create(
            store=self.loja, name='Salada', price=Decimal('50.00'),
            track_stock=False, category=cat, sku='S1')
        self.cart = StoreCart.objects.create(store=self.loja, session_key='s-e2e')
        StoreCartItem.objects.create(cart=self.cart, product=self.produto, quantity=1)

    def _pedido(self, meio):
        from apps.stores.services.checkout_service import CheckoutService
        return CheckoutService.create_order(
            cart=self.cart,
            customer_data={'name': 'Cliente', 'phone': '63999990000',
                           'email': 'c@real.com'},
            payment_method=meio,
        )

    def test_pedido_no_vale_nasce_com_o_acrescimo_somado(self):
        pedido = self._pedido('voucher')
        self.assertEqual(pedido.voucher_fee, Decimal('5.00'))
        self.assertEqual(pedido.total, Decimal('55.00'))
        self.assertEqual(pedido.subtotal, Decimal('50.00'))

    def test_o_mesmo_pedido_no_pix_nao_paga_nada_a_mais(self):
        pedido = self._pedido('pix')
        self.assertEqual(pedido.voucher_fee, Decimal('0.00'))
        self.assertEqual(pedido.total, Decimal('50.00'))

    def test_o_acrescimo_fica_em_COLUNA_propria(self):
        """Dinheiro que relatório soma não pode morar em JSON."""
        from apps.stores.models import StoreOrder
        self._pedido('voucher')
        from django.db.models import Sum
        soma = StoreOrder.objects.filter(store=self.loja).aggregate(
            s=Sum('voucher_fee'))['s']
        self.assertEqual(soma, Decimal('5.00'))

    def test_a_config_publica_anuncia_o_percentual(self):
        """A tela mostra a linha no instante em que ele marca o vale. Acréscimo
        que só aparece no total é surpresa em tela de pagamento."""
        from apps.stores.api.views.storefront_views import build_store_payment_config
        cfg = build_store_payment_config(self.loja)
        self.assertEqual(cfg['voucher_fee_percent'], 10.0)

    def test_loja_sem_acrescimo_anuncia_zero(self):
        from apps.stores.api.views.storefront_views import build_store_payment_config
        self.loja.metadata = {}
        self.assertEqual(build_store_payment_config(self.loja)['voucher_fee_percent'], 0.0)


class ConfigurarOAcrescimoPeloPainelTests(TestCase):
    """Não é hardcoded: quem liga é o dono, pela taxa que ele escolher."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-cfg', password='x', email='o-cfg@real.com')
        self.loja = Store.objects.create(
            name='Loja Cfg', slug='loja-cfg', owner=self.owner, status='active',
            metadata={'owner_phone': '5563911112222'})

    def _salvar(self, valor):
        from apps.stores.api.serializers import StoreSerializer
        s = StoreSerializer(self.loja, data={'voucher_fee_percent': valor}, partial=True)
        s.is_valid(raise_exception=True)
        return s.save()

    def test_o_dono_liga_escolhendo_a_taxa(self):
        self._salvar('10')
        self.loja.refresh_from_db()
        self.assertEqual(percentual_do_vale(self.loja), Decimal('10'))

    def test_zero_desliga_e_remove_a_chave(self):
        self._salvar('10')
        self._salvar('0')
        self.loja.refresh_from_db()
        self.assertNotIn('voucher_fee_percent', self.loja.metadata)
        self.assertEqual(self.loja.metadata['owner_phone'], '5563911112222')

    def test_acima_de_cem_e_recusado(self):
        from apps.stores.api.serializers import StoreSerializer
        s = StoreSerializer(self.loja, data={'voucher_fee_percent': '150'}, partial=True)
        self.assertFalse(s.is_valid())

    def test_o_painel_le_de_volta_o_que_esta_ligado(self):
        from apps.stores.api.serializers import StoreSerializer
        self._salvar('7.5')
        self.loja.refresh_from_db()
        self.assertEqual(StoreSerializer(self.loja).data['voucher_fee_percent'], 7.5)

    def test_salvar_outra_aba_nao_desliga_o_acrescimo(self):
        from apps.stores.api.serializers import StoreSerializer
        self._salvar('10')
        s = StoreSerializer(self.loja, data={'tagline': 'oi'}, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        self.loja.refresh_from_db()
        self.assertEqual(percentual_do_vale(self.loja), Decimal('10'))


class AcrescimoSobreviveAEdicaoTests(AcrescimoNoPedidoDeVerdadeTests):
    def test_recalcular_o_pedido_nao_apaga_o_acrescimo(self):
        """Editar o pedido no painel chama `recalculate_totals`. Se o acréscimo
        não estiver na fórmula, o total cai para o valor sem ele em silêncio."""
        pedido = self._pedido('voucher')
        pedido.recalculate_totals()
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal('55.00'))
