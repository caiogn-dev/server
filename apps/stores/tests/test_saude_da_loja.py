"""
Saúde da loja: o checklist acusa o que impede a loja de vender.

Medido em 03/10/2026:
- o passo 'delivery' olhava só `delivery_zones.exists()`. Cê, Kero-Kero e
  Pastita apareciam PRONTAS com 16 faixas todas desligadas; a Agrião aparecia
  PENDENTE com a entrega funcionando por fórmula; e 3 lojas (uma delas
  cliente pagante) tinham entrega ligada SEM coordenadas — sem coordenada não
  existe distância, e o frete não sai.
- o cardápio inteiro da Agrião ficou escondido (categoria desligada) e nada
  avisou; a Ivoneth tinha 3 produtos à venda escondidos do mesmo jeito.
- havia produto ativo a R$ 0,00.
"""
from decimal import Decimal

from django.test import TestCase

from apps.stores.models import StoreCategory, StoreDeliveryZone
from apps.stores.services.onboarding_checklist import build_checklist
from apps.stores.tests.factories import make_product, make_store


def _passo(checklist, key):
    return next(s for s in checklist['steps'] if s['key'] == key)


def _alerta(checklist, key):
    return next((a for a in checklist['alertas'] if a['key'] == key), None)


class PassoDeEntregaTest(TestCase):
    def test_entrega_ligada_sem_coordenada_esta_pendente_mesmo_com_faixas(self):
        loja = make_store(delivery_enabled=True)
        StoreDeliveryZone.objects.create(store=loja, name='0-2km', is_active=False, delivery_fee=Decimal('8'))
        assert _passo(build_checklist(loja), 'delivery')['done'] is False

    def test_entrega_com_coordenada_esta_pronta_sem_faixa_nenhuma(self):
        # A taxa por fórmula (calculate_dynamic_fee) só precisa da distância.
        loja = make_store(delivery_enabled=True, latitude=Decimal('-10.19'), longitude=Decimal('-48.30'))
        assert _passo(build_checklist(loja), 'delivery')['done'] is True

    def test_loja_so_de_retirada_nao_fica_pendente(self):
        loja = make_store(delivery_enabled=False)
        assert _passo(build_checklist(loja), 'delivery')['done'] is True


class AlertasDeSaudeTest(TestCase):
    def test_loja_saudavel_nao_tem_alerta(self):
        loja = make_store(delivery_enabled=True, latitude=Decimal('-10.19'), longitude=Decimal('-48.30'))
        make_product(loja, price=Decimal('23.00'))
        assert build_checklist(loja)['alertas'] == []

    def test_entrega_ligada_sem_endereco_no_mapa(self):
        loja = make_store(delivery_enabled=True)
        alerta = _alerta(build_checklist(loja), 'entrega_sem_endereco')
        assert alerta == {'key': 'entrega_sem_endereco', 'quantidade': 1}

    def test_produto_a_venda_por_zero(self):
        loja = make_store(delivery_enabled=False)
        make_product(loja, price=Decimal('0.00'))
        make_product(loja, price=Decimal('0.00'))
        make_product(loja, price=Decimal('10.00'))
        pausado = make_product(loja, price=Decimal('0.00'))
        pausado.status = 'inactive'
        pausado.save(update_fields=['status'])
        assert _alerta(build_checklist(loja), 'produto_sem_preco') == {'key': 'produto_sem_preco', 'quantidade': 2}

    def test_produto_a_venda_escondido_por_categoria_desligada(self):
        loja = make_store(delivery_enabled=False)
        desligada = StoreCategory.objects.create(store=loja, name='Linha Fit', slug='linha-fit', is_active=False)
        for _ in range(3):
            p = make_product(loja, price=Decimal('23.00'))
            p.category = desligada
            p.save(update_fields=['category'])
        pausado = make_product(loja, price=Decimal('23.00'))
        pausado.category, pausado.status = desligada, 'inactive'
        pausado.save(update_fields=['category', 'status'])
        assert _alerta(build_checklist(loja), 'produto_escondido') == {'key': 'produto_escondido', 'quantidade': 3}
