"""
Catálogo de planos do go-live de cobrança.

A escada anterior era invertida: o plano Grátis permitia 30 pedidos/mês e a maior
loja da plataforma fazia 32 — ninguém encostava no teto, então não existia dor de
upgrade. E o Essencial de R$ 99,90 não entregava feature nova, só removia limites
que ninguém atingia, com margem de -R$ 31/mês depois do custo de suporte
(92 min/loja/mês).

Catálogo novo (estrategia-monetizacao-2026-08-02.md):
  Grátis            R$   0    20 produtos, 15 pedidos/mês
  Loja              R$ 179    ilimitado, PDV/KDS/impressão/fidelidade
  Loja + WhatsApp   R$ 329    + bot oficial, BI, domínio próprio
  Rede              R$ 549    + até 3 lojas
  Implantação       R$ 1.200  única (gated por BILLING_SETUP_FEE_ENABLED)
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores import billing
from apps.stores.models import Store

User = get_user_model()


class TestCatalogoDePlanos:

    def test_gratis_tem_teto_que_a_loja_real_encosta(self):
        """15 pedidos/mês: a maior loja faz ~37, então o teto DÓI — que é o ponto."""
        limites = billing.plan_limits('free')
        assert limites['max_orders_per_month'] == 15
        assert limites['max_products'] == 20

    @pytest.mark.parametrize('chave,preco', [
        ('starter', '179.00'),
        ('pro', '329.00'),
        ('premium', '549.00'),
    ])
    def test_precos_do_go_live(self, chave, preco):
        assert billing.get_plan(chave)['monthly_price'] == Decimal(preco)

    def test_gratis_nao_cobra_nada(self):
        plano = billing.get_plan('free')
        assert plano['monthly_price'] == Decimal('0.00')
        assert plano['setup_fee'] == Decimal('0.00')
        assert plano['charges_setup_fee'] is False

    def test_implantacao_de_1200_nos_planos_pagos(self):
        for chave in ('starter', 'pro', 'premium'):
            plano = billing.get_plan(chave)
            assert plano['setup_fee'] == Decimal('1200.00'), chave
            assert plano['charges_setup_fee'] is True, chave

    def test_bot_do_whatsapp_e_o_motivo_de_subir_de_loja_para_loja_whatsapp(self):
        """O bot é o único motivo real de comprar — não pode vir no plano de entrada."""
        assert billing.plan_limits('starter')['whatsapp_bot'] is False
        assert billing.plan_limits('pro')['whatsapp_bot'] is True

    def test_dominio_proprio_a_partir_do_plano_com_whatsapp(self):
        assert billing.plan_limits('starter')['custom_domain'] is False
        assert billing.plan_limits('pro')['custom_domain'] is True

    def test_planos_pagos_nao_tem_teto_de_pedidos(self):
        for chave in ('starter', 'pro', 'premium'):
            assert billing.plan_limits(chave)['max_orders_per_month'] is None, chave
            assert billing.plan_limits(chave)['max_products'] is None, chave


@pytest.mark.django_db
class TestLojasGrandfatheredContinuamIntocadas:
    """As 4 lojas reais são billing_exempt. Mudar o catálogo NÃO pode afetá-las."""

    @pytest.fixture
    def loja_isenta(self):
        dono = User.objects.create_user(username='dono_gf', password='x')
        return Store.objects.create(
            owner=dono, name='Cê Saladas', slug='ce-saladas-gf-test',
            plan='starter', billing_exempt=True,
        )

    def test_isenta_mantem_o_bot_mesmo_num_plano_sem_bot(self, loja_isenta):
        """starter não tem whatsapp_bot no catálogo novo — a isenta usa assim mesmo."""
        assert billing.plan_limits('starter')['whatsapp_bot'] is False
        assert billing.bot_order_allowed(loja_isenta) is True

    def test_isenta_nao_tem_teto_de_produto(self, loja_isenta):
        assert billing.within_product_limit(loja_isenta, current_count=99999) is True

    def test_isenta_libera_qualquer_feature(self, loja_isenta):
        for feature in ('custom_domain', 'ai_agent', 'advanced_reports', 'coupon_banner'):
            assert billing.plan_allows(loja_isenta, feature) is True, feature

    def test_loja_free_nao_isenta_continua_limitada(self):
        dono = User.objects.create_user(username='dono_free', password='x')
        loja = Store.objects.create(
            owner=dono, name='Nova', slug='nova-free-test',
            plan='free', billing_exempt=False,
        )
        assert billing.bot_order_allowed(loja) is False
        assert billing.within_product_limit(loja, current_count=20) is False
