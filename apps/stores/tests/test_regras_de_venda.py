"""
Regras de venda do produto (do admin do Prefiro): dia e horário, só retirada,
quantidade mínima e máxima por pedido.

A vitrine só desenha o aviso; quem barra é o servidor — no checkout (vale para
vitrine, bot e agente, que passam todos por `create_order`) e no
`disponiveis()`, para o bot não oferecer o almoço às 20h.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store, StoreCart, StoreCartItem, StoreProduct
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.regras_de_venda import (
    RegraInvalida, erros_do_carrinho, normalizar, quando_vende, vende_agora,
)

pytestmark = pytest.mark.django_db

ALMOCO = {'dias': [0, 1, 2, 3, 4], 'de': '11:00', 'ate': '15:00'}


def _quando(iso):
    return timezone.make_aware(datetime.fromisoformat(iso))


# 2026-10-23 é sexta (4); 2026-10-24 é sábado (5).
class TestRegra:
    @pytest.mark.parametrize('iso,vende', [
        ('2026-10-23T10:59', False), ('2026-10-23T11:00', True),
        ('2026-10-23T14:59', True), ('2026-10-23T15:00', False),
        ('2026-10-24T12:00', False),
    ])
    def test_janela_e_dias(self, iso, vende):
        assert vende_agora(ALMOCO, datetime.fromisoformat(iso)) is vende

    def test_sem_regra_vende_sempre(self):
        assert vende_agora({}, datetime(2026, 10, 24, 3, 0)) is True

    def test_quando_vende_em_portugues(self):
        assert quando_vende({'dias': [5, 6], 'de': '11:00', 'ate': '15:00'}) == 'sábado e domingo, das 11:00 às 15:00'

    def test_normalizar_descarta_o_que_nao_tem_efeito(self):
        assert normalizar({'dias': list(range(7)), 'de': '', 'ate': '', 'so_retirada': False,
                           'minimo': 1, 'maximo': None}) == {}

    @pytest.mark.parametrize('dados', [
        {'de': '11:00'},
        {'de': '9:00', 'ate': '15:00'},
        {'de': '22:00', 'ate': '02:00'},
        {'dias': [7]},
        {'minimo': 10, 'maximo': 5},
        {'maximo': 0},
    ])
    def test_normalizar_recusa(self, dados):
        with pytest.raises(RegraInvalida):
            normalizar(dados)

    def test_erros_do_carrinho(self):
        class P:
            name = 'Bolo inteiro'
            regras_de_venda = {'so_retirada': True, 'minimo': 2, 'maximo': 3}
        erros = erros_do_carrinho([(P(), 1)], 'delivery', datetime(2026, 10, 23, 12))
        assert erros == ['Bolo inteiro é só para retirada na loja.', 'Bolo inteiro: o mínimo é 2 unidades.']
        assert erros_do_carrinho([(P(), 3)], 'pickup', datetime(2026, 10, 23, 12)) == []


@pytest.fixture
def loja():
    dono = User.objects.create_user(username='dono-regras', email='dono-regras@example.com', password='x')
    return Store.objects.create(name='Regras', slug='regras', owner=dono, status=Store.StoreStatus.ACTIVE,
                                min_order_value=Decimal('0'))


def _produto(loja, nome, regras):
    return StoreProduct.objects.create(store=loja, name=nome, slug=nome.lower().replace(' ', '-'),
                                       price=Decimal('30'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
                                       regras_de_venda=regras)


class TestDisponiveis:
    def test_bot_nao_ve_o_almoco_fora_da_janela(self, loja):
        _produto(loja, 'Almoco', ALMOCO)
        _produto(loja, 'Suco', {})
        _produto(loja, 'Bolo', {'so_retirada': True})
        with patch.object(timezone, 'localtime', return_value=_quando('2026-10-23T20:00')):
            nomes = set(StoreProduct.disponiveis(loja).values_list('name', flat=True))
        assert nomes == {'Suco', 'Bolo'}
        with patch.object(timezone, 'localtime', return_value=_quando('2026-10-23T12:00')):
            nomes = set(StoreProduct.disponiveis(loja).values_list('name', flat=True))
        assert nomes == {'Almoco', 'Suco', 'Bolo'}


class TestCheckout:
    def _pedir(self, loja, produto, quantidade, metodo='pickup', iso='2026-10-23T12:00'):
        cart = StoreCart.objects.create(store=loja, session_key=f'c-{produto.slug}-{quantidade}-{metodo}')
        StoreCartItem.objects.create(cart=cart, product=produto, quantity=quantidade)
        with patch.object(timezone, 'localtime', return_value=_quando(iso)):
            return CheckoutService.create_order(
                cart=cart,
                customer_data={'name': 'Cliente', 'email': 'c@example.com', 'phone': '+5563999990001'},
                delivery_data={'method': metodo},
            )

    def test_recusa_fora_da_janela_com_frase_para_o_cliente(self, loja):
        p = _produto(loja, 'Almoco', ALMOCO)
        with pytest.raises(ValueError, match='Almoco só é vendido segunda, terça, quarta, quinta e sexta, das 11:00 às 15:00'):
            self._pedir(loja, p, 1, iso='2026-10-23T16:00')

    def test_recusa_quantidade_fora_da_faixa(self, loja):
        p = _produto(loja, 'Salgado', {'minimo': 10})
        with pytest.raises(ValueError, match='o mínimo é 10'):
            self._pedir(loja, p, 5)

    def test_dentro_das_regras_passa(self, loja):
        p = _produto(loja, 'Salgado', {'minimo': 10, 'maximo': 50, **ALMOCO})
        assert self._pedir(loja, p, 10).store_id == loja.id


class TestPainelGrava:
    def test_painel_grava_normalizado_e_recusa_invalido(self, loja):
        p = _produto(loja, 'Bolo', {})
        api = APIClient()
        api.force_authenticate(user=loja.owner)
        url = f'/api/v1/stores/products/{p.id}/'
        r = api.patch(url, {'regras_de_venda': {'so_retirada': True, 'minimo': 1, 'dias': []}}, format='json')
        assert r.status_code == 200, r.content
        p.refresh_from_db()
        assert p.regras_de_venda == {'so_retirada': True}
        r = api.patch(url, {'regras_de_venda': {'de': '15:00', 'ate': '11:00'}}, format='json')
        assert r.status_code == 400
        assert 'meia-noite' in str(r.content.decode())

    def test_vitrine_recebe_as_regras(self, loja):
        _produto(loja, 'Bolo', {'so_retirada': True})
        r = APIClient().get(f'/api/v1/public/{loja.slug}/products/')
        assert r.status_code == 200, r.content
        dados = r.json()
        linhas = dados['results'] if isinstance(dados, dict) else dados
        assert linhas[0]['regras_de_venda'] == {'so_retirada': True}
