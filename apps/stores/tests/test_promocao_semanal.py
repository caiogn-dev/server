"""Promoção que se repete toda semana — sem tarefa e sem estado para travar.

"Quarta da Almôndega": R$ 44,90 vira R$ 30,75 toda quarta. E não é um produto —
é um dia da semana para cada salada, uma rotação no cardápio inteiro.

A solução óbvia seria uma tarefa que TROCA o `price` na quarta e devolve na
quinta. Recusada de propósito: é exatamente o bug que motivou tudo. Se a tarefa
que devolve falhar — Celery caído, deploy no meio, erro num produto — o preço
fica errado indefinidamente e ninguém percebe. Foi assim que a Almôndega Premium
ficou a R$ 42,99 desde quarta, descoberto dois dias depois.

Aqui o `price` NUNCA é alterado. A promoção fica ao lado e o preço é calculado
na leitura. Sem estado, sem tarefa, sem "e se falhar": se nada rodar, nada
quebra, porque não há nada rodando.

⚠️ O risco desta feature não é o cálculo — é mostrar R$ 30,75 na vitrine e
cobrar R$ 44,90 no checkout. Por isso `preco_vigente()` é fonte única, e os
testes cobrem os dois lados.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store

# Segunda=0 … Domingo=6, igual a datetime.weekday()
QUARTA, QUINTA = 2, 3


def _quarta():
    """13:00 de uma quarta-feira real (12/08/2026)."""
    return timezone.make_aware(timezone.datetime(2026, 8, 12, 13, 0))


def _quinta():
    return timezone.make_aware(timezone.datetime(2026, 8, 13, 13, 0))


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def almondega(loja):
    return StoreProduct.objects.create(
        store=loja, name='Almôndega Premium', slug='almondega-premium',
        price=Decimal('44.90'), is_active=True, status='active',
        promo_price=Decimal('30.75'), promo_weekday=QUARTA,
    )


class TestPrecoVigente:
    def test_no_dia_da_promo_cobra_o_preco_promocional(self, almondega):
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert almondega.preco_vigente() == Decimal('30.75')

    def test_fora_do_dia_cobra_o_preco_normal(self, almondega):
        with patch('django.utils.timezone.localtime', return_value=_quinta()):
            assert almondega.preco_vigente() == Decimal('44.90')

    def test_produto_sem_promo_devolve_o_preco_normal(self, loja):
        p = StoreProduct.objects.create(
            store=loja, name='Salada Caesar', slug='caesar',
            price=Decimal('35.00'), is_active=True, status='active',
        )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert p.preco_vigente() == Decimal('35.00')

    def test_promo_sem_dia_nao_vale_nunca(self, loja):
        """Preço promocional sem dia é cadastro pela metade — não pode vazar."""
        p = StoreProduct.objects.create(
            store=loja, name='Meio cadastrado', slug='meio',
            price=Decimal('20.00'), is_active=True, status='active',
            promo_price=Decimal('10.00'), promo_weekday=None,
        )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert p.preco_vigente() == Decimal('20.00')

    def test_dia_sem_promo_tambem_nao_quebra(self, loja):
        p = StoreProduct.objects.create(
            store=loja, name='Outro meio', slug='outro-meio',
            price=Decimal('20.00'), is_active=True, status='active',
            promo_weekday=QUARTA,
        )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert p.preco_vigente() == Decimal('20.00')


class TestOPrecoOriginalNuncaEAlterado:
    """A razão de existir deste desenho."""

    def test_price_continua_intacto_no_dia_da_promo(self, almondega):
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            almondega.preco_vigente()

        almondega.refresh_from_db()
        assert almondega.price == Decimal('44.90')

    def test_nao_existe_estado_para_reverter(self, almondega):
        """Se nada rodar, nada quebra — porque não há nada rodando.

        O bug original foi um preço promocional que ficou aplicado depois do dia
        acabar. Aqui isso é impossível: a promoção nunca é 'aplicada'.
        """
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert almondega.preco_vigente() == Decimal('30.75')
        with patch('django.utils.timezone.localtime', return_value=_quinta()):
            assert almondega.preco_vigente() == Decimal('44.90')


class TestTipos:
    def test_devolve_Decimal_nunca_float(self, almondega):
        """Dinheiro em float vira R$ 30,749999. Não entra no sistema."""
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert isinstance(almondega.preco_vigente(), Decimal)

    def test_promo_maior_que_o_preco_nao_e_promocao(self, loja):
        """Cadastro errado não pode AUMENTAR o preço do cliente."""
        p = StoreProduct.objects.create(
            store=loja, name='Invertido', slug='invertido',
            price=Decimal('20.00'), is_active=True, status='active',
            promo_price=Decimal('99.00'), promo_weekday=QUARTA,
        )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert p.preco_vigente() == Decimal('20.00')


class TestRotacaoDaSemana:
    def test_cada_salada_no_seu_dia(self, loja):
        """'Um dia da semana para cada salada' — o caso real do dono."""
        dias = {'Segunda': 0, 'Terça': 1, 'Quarta': 2}
        for nome, dia in dias.items():
            StoreProduct.objects.create(
                store=loja, name=f'Salada de {nome}', slug=f'salada-{dia}',
                price=Decimal('40.00'), is_active=True, status='active',
                promo_price=Decimal('30.00'), promo_weekday=dia,
            )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            em_promo = [
                p.name for p in StoreProduct.objects.filter(store=loja)
                if p.preco_vigente() < p.price
            ]

        assert em_promo == ['Salada de Quarta'], em_promo


class TestMostrarEhIgualACobrar:
    """O risco real desta feature, num teste só.

    Mostrar R$ 30,75 na vitrine e cobrar R$ 44,90 no checkout é pior que não
    ter promoção nenhuma: vira reclamação e estorno. São dois caminhos
    diferentes lendo o mesmo dado, e eles TÊM que concordar.
    """

    def test_o_carrinho_cobra_o_preco_do_dia(self, almondega, loja):
        from apps.stores.models import StoreCart, StoreCartItem

        carrinho = StoreCart.objects.create(store=loja, session_key='k1')
        item = StoreCartItem.objects.create(
            cart=carrinho, product=almondega, quantity=2,
        )

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            assert item.unit_price == Decimal('30.75')
            assert item.subtotal == Decimal('61.50')

    def test_fora_do_dia_o_carrinho_cobra_cheio(self, almondega, loja):
        from apps.stores.models import StoreCart, StoreCartItem

        carrinho = StoreCart.objects.create(store=loja, session_key='k2')
        item = StoreCartItem.objects.create(
            cart=carrinho, product=almondega, quantity=1,
        )

        with patch('django.utils.timezone.localtime', return_value=_quinta()):
            assert item.unit_price == Decimal('44.90')

    def test_vitrine_e_carrinho_mostram_o_MESMO_numero(self, almondega, loja):
        from apps.public_api.serializers import PublicProductSerializer
        from apps.stores.models import StoreCart, StoreCartItem

        carrinho = StoreCart.objects.create(store=loja, session_key='k3')
        item = StoreCartItem.objects.create(cart=carrinho, product=almondega, quantity=1)

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            vitrine = Decimal(str(PublicProductSerializer(almondega).data['price']))
            cobrado = item.unit_price

        assert vitrine == cobrado, f'vitrine {vitrine} != cobrado {cobrado}'
