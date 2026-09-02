"""Cupons de código FIXO, no lugar dos três geradores.

O sistema criava um código único por pessoa em três lugares — AVALIA5-XXXXXX
(quem avaliava no Google), INDICA-XXXX (quem pedia para indicar) e AMIGO5-XXXX
(quem foi indicado). O resultado medido em produção na Cê Saladas:

    AVALIA5-  13 criados   0 usados
    INDICA-    0 criados   0 usados
    AMIGO5-    0 criados   0 usados

Ninguém digita AVALIA5-F34854 no carrinho. Código fixo e curto é ditável no
WhatsApp, cabe num print e o cliente lembra dele no dia seguinte.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreCoupon
from apps.stores.services.cupons_fixos import (
    CODIGO_DE_FEEDBACK, CODIGO_DE_INDICACAO, CuponsFixos,
)


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(
        username='dono-cf', email='dono-cf@teste.local', password='x',
    )


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Loja CF', slug='loja-cf', store_type='food', status='active',
    )


@pytest.mark.django_db
class TestCupomDeFeedback:
    def test_cria_com_codigo_fixo_e_ditavel(self, loja):
        cupom = CuponsFixos.de_feedback(loja)
        assert cupom.code == CODIGO_DE_FEEDBACK == 'FEEDBACK10'

    def test_dez_porcento_mil_usos_um_por_cliente(self, loja):
        cupom = CuponsFixos.de_feedback(loja)
        assert cupom.discount_value == Decimal('10')
        assert cupom.usage_limit == 1000
        assert cupom.usage_limit_per_user == 1

    def test_chamar_duas_vezes_nao_cria_um_segundo(self, loja):
        """O gerador antigo criava um cupom por clique. Este é o mesmo sempre."""
        a = CuponsFixos.de_feedback(loja)
        b = CuponsFixos.de_feedback(loja)
        assert a.id == b.id
        assert StoreCoupon.objects.filter(store=loja, code=CODIGO_DE_FEEDBACK).count() == 1

    def test_cupom_vencido_e_revalidado_em_vez_de_duplicado(self, loja):
        from django.utils import timezone
        from datetime import timedelta
        cupom = CuponsFixos.de_feedback(loja)
        StoreCoupon.objects.filter(id=cupom.id).update(
            valid_until=timezone.now() - timedelta(days=1), is_active=False,
        )
        renovado = CuponsFixos.de_feedback(loja)
        assert renovado.id == cupom.id
        assert renovado.is_active is True
        assert renovado.valid_until > timezone.now()

    def test_nao_zera_o_contador_de_uso_ao_renovar(self, loja):
        cupom = CuponsFixos.de_feedback(loja)
        StoreCoupon.objects.filter(id=cupom.id).update(used_count=7)
        assert CuponsFixos.de_feedback(loja).used_count == 7

    def test_cada_loja_tem_o_seu(self, loja, dono):
        outra = Store.objects.create(
            owner=dono, name='Outra', slug='outra-cf', store_type='food', status='active',
        )
        assert CuponsFixos.de_feedback(loja).id != CuponsFixos.de_feedback(outra).id


@pytest.mark.django_db
class TestCupomDeIndicacao:
    def test_codigo_fixo_e_so_primeiro_pedido(self, loja):
        cupom = CuponsFixos.de_indicacao(loja)
        assert cupom.code == CODIGO_DE_INDICACAO == 'INDICA10'
        assert cupom.first_order_only is True

    def test_nao_duplica(self, loja):
        assert CuponsFixos.de_indicacao(loja).id == CuponsFixos.de_indicacao(loja).id

    def test_nao_carrega_telefone_de_ninguem(self, loja):
        """O INDICA-XXXX antigo guardava referrer_phone no metadata porque era
        pessoal. Este é de todo mundo — a atribuição virou cashback."""
        assert 'referrer_phone' not in (CuponsFixos.de_indicacao(loja).metadata or {})


@pytest.mark.django_db
class TestLimpezaDosOrfaos:
    def _gerado(self, loja, code, usos=0):
        from django.utils import timezone
        from datetime import timedelta
        agora = timezone.now()
        c = StoreCoupon.objects.create(
            store=loja, code=code, discount_type='percentage', discount_value=5,
            usage_limit=1, valid_from=agora, valid_until=agora + timedelta(days=30),
        )
        StoreCoupon.objects.filter(id=c.id).update(used_count=usos)
        return c

    def test_desativa_os_gerados_sem_nenhum_uso(self, loja):
        self._gerado(loja, 'AVALIA5-F34854')
        self._gerado(loja, 'INDICA-A3F9')
        self._gerado(loja, 'AMIGO5-B2C1')
        assert CuponsFixos.aposentar_gerados(loja) == 3
        assert StoreCoupon.objects.filter(store=loja, is_active=True).count() == 0

    def test_nao_toca_no_que_o_cliente_ja_usou(self, loja):
        """Desativar cupom já usado quebraria quem está com ele na mão."""
        usado = self._gerado(loja, 'AVALIA5-USADO1', usos=1)
        CuponsFixos.aposentar_gerados(loja)
        usado.refresh_from_db()
        assert usado.is_active is True

    def test_nao_toca_em_cupom_de_verdade(self, loja):
        real = self._gerado(loja, 'SALADA10')
        parceiro = self._gerado(loja, 'NUTRI.MARI')
        CuponsFixos.aposentar_gerados(loja)
        real.refresh_from_db()
        parceiro.refresh_from_db()
        assert real.is_active is True
        assert parceiro.is_active is True

    def test_nao_desativa_os_novos_fixos(self, loja):
        CuponsFixos.de_feedback(loja)
        CuponsFixos.de_indicacao(loja)
        CuponsFixos.aposentar_gerados(loja)
        assert StoreCoupon.objects.filter(store=loja, is_active=True).count() == 2
