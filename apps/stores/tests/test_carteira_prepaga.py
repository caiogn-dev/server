"""Carteira pré-paga: o cliente compra saldo adiantado e ganha bônus.

TRÊS REGRAS QUE ESTES TESTES TRAVAM (todas custam dinheiro se quebrarem):

1. **O saldo paga COMIDA, não frete.** O frete é repasse: a loja cobra R$ 10,72
   e paga R$ 10,72 ao entregador, margem zero. Deixar o saldo pagar o frete
   transforma um pacote de 8 saladas em 6 saladas + 5 fretes — a loja perde
   R$ 14 de margem e o cliente sente o saldo evaporando sem comer.

2. **Cada real ganha bônus UMA vez.** Quem pagou com saldo já recebeu 11%
   adiantado; dar mais 3% de cashback em cima seria pagar duas vezes pelo mesmo
   dinheiro — e o bônus que gera cashback que gera bônus é um laço que só anda
   contra a loja. Base do cashback = o que entrou em dinheiro NOVO, sem frete.

3. **Crédito de carteira é IDEMPOTENTE por cobrança.** O webhook do Mercado
   Pago reenvia a mesma notificação; creditar duas vezes é dar um pacote de
   graça. A garantia é constraint de banco (`source_ref`), não `if` em Python —
   o mesmo motivo do `cashback_unico_por_pedido_e_origem`.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService

TELEFONE = '5563991386719'


@pytest.fixture
def dono(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_user(
        username='dono-carteira', email='dono-carteira@teste.local', password='x',
    )


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-carteira', store_type='food',
        status='active',
        metadata={
            'cashback_enabled': True,
            'cashback_percent': '3',
            'cashback_expiry_days': '30',
            'carteira_tiers': [
                {'id': 'leve', 'nome': 'Leve', 'paga': '139.00', 'credito': '152.00'},
                {'id': 'padrao', 'nome': 'Padrão', 'paga': '270.00', 'credito': '304.00'},
                {'id': 'familia', 'nome': 'Família', 'paga': '395.00', 'credito': '456.00'},
            ],
        },
    )


def _pedido(loja, subtotal, frete, discount=Decimal('0'), phone=TELEFONE):
    subtotal, frete, discount = map(lambda v: Decimal(str(v)), (subtotal, frete, discount))
    return StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_phone=phone,
        subtotal=subtotal, delivery_fee=frete, discount=discount,
        total=subtotal + frete - discount, payment_status='paid',
    )


@pytest.mark.django_db
class TestCompraDeSaldo:

    def test_credita_o_valor_do_pacote_e_nao_o_valor_pago(self, loja):
        """O cliente paga 270 e recebe 304. O bônus é o produto."""
        lote = CashbackService.credit_prepaid(
            loja, TELEFONE, tier_id='padrao', source_ref='mp:12345',
        )
        assert lote is not None
        assert lote.amount == Decimal('304.00')
        assert lote.origin == StoreCashbackLot.Origin.PREPAID
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('304.00')

    def test_saldo_comprado_dura_mais_que_o_cashback(self):
        """São dois dinheiros com dois prazos, e este teste cobra o certo.

        Nasceu cravado em 30 dias, herdados do cashback. O padrão virou 90 em
        seguida, com a conta escrita no código: os 30 dias obrigavam quem
        comprou o pacote Família a comer R$ 15,20 de salada por dia, e das dez
        melhores clientes da Cê uma só conseguiria. O teste ficou vermelho por
        cinco semanas apontando para a regra velha.
        """
        from apps.stores.services.cashback_service import (
            DIAS_DA_CARTEIRA_PADRAO, DIAS_PARA_VENCER,
        )

        assert DIAS_DA_CARTEIRA_PADRAO > DIAS_PARA_VENCER, (
            'o saldo que a cliente PAGOU não pode vencer antes do bônus'
        )

    def test_saldo_vence_na_validade_da_carteira(self, loja):
        from apps.stores.services.cashback_service import DIAS_DA_CARTEIRA_PADRAO

        lote = CashbackService.credit_prepaid(
            loja, TELEFONE, tier_id='padrao', source_ref='mp:1',
        )
        dias = (lote.expires_at - timezone.now()).days
        assert DIAS_DA_CARTEIRA_PADRAO - 1 <= dias <= DIAS_DA_CARTEIRA_PADRAO, (
            f'esperava ~{DIAS_DA_CARTEIRA_PADRAO} dias, veio {dias}'
        )

    def test_webhook_repetido_nao_credita_duas_vezes(self, loja):
        """A mesma cobrança chega duas vezes — o segundo crédito é um pacote de graça."""
        primeiro = CashbackService.credit_prepaid(
            loja, TELEFONE, tier_id='padrao', source_ref='mp:99',
        )
        segundo = CashbackService.credit_prepaid(
            loja, TELEFONE, tier_id='padrao', source_ref='mp:99',
        )
        assert primeiro is not None
        assert segundo is None, 'a mesma cobrança creditou de novo'
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('304.00')

    def test_tier_desconhecido_nao_credita_nada(self, loja):
        """Pacote que não está no catálogo da loja não vira saldo inventado."""
        assert CashbackService.credit_prepaid(
            loja, TELEFONE, tier_id='pacote-que-nao-existe', source_ref='mp:2',
        ) is None
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('0.00')

    def test_cobrancas_diferentes_somam(self, loja):
        CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:a')
        CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:b')
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('304.00')


@pytest.mark.django_db
class TestSaldoPagaComidaNaoFrete:
    """Regra 1, provada no caminho real: um checkout com frete de verdade."""

    def _carrinho(self, loja, preco_unitario, quantidade=1):
        from apps.stores.models import (
            StoreCart, StoreCartItem, StoreCategory, StoreProduct,
        )
        cat = StoreCategory.objects.create(store=loja, name='Saladas', slug='sal')
        prod = StoreProduct.objects.create(
            store=loja, category=cat, name='Queridinha', slug='queridinha',
            price=Decimal(str(preco_unitario)), status='active', track_stock=False,
        )
        cart = StoreCart.objects.create(store=loja, session_key='sess-carteira')
        StoreCartItem.objects.create(cart=cart, product=prod, quantity=quantidade)
        return cart

    def test_o_saldo_nao_paga_o_frete_no_checkout(self, loja):
        """8 saladas viram 6 saladas + 5 fretes se o saldo cobrir a entrega."""
        from apps.stores.services.checkout_service import CheckoutService

        CashbackService.credit_prepaid(loja, TELEFONE, tier_id='padrao', source_ref='mp:1')
        cart = self._carrinho(loja, preco_unitario='38.00', quantidade=2)

        pedido = CheckoutService.create_order(
            cart=cart,
            customer_data={'name': 'Cliente', 'email': '', 'phone': TELEFONE, 'cpf': ''},
            delivery_data={'method': 'delivery', 'address': {}},
            use_cashback=True,
            telefone_verificado=True,  # saldo comprado exige o dono comprovado
            trusted_delivery_fee=Decimal('10.72'),
        )

        assert pedido.subtotal == Decimal('76.00')
        assert pedido.delivery_fee == Decimal('10.72')
        assert pedido.discount == Decimal('76.00'), (
            f'o saldo abateu {pedido.discount} — deveria abater só a comida (76,00)'
        )
        assert pedido.total == Decimal('10.72'), 'o cliente ainda paga o frete'
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('228.00')

    def test_aplicavel_limita_ao_subtotal(self, loja):
        CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:1')
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('300.00'), verificado=True) == Decimal('152.00')
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('40.00'), verificado=True) == Decimal('40.00')

    def test_sem_saldo_nao_abate(self, loja):
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('76.00')) == Decimal('0.00')


@pytest.mark.django_db
class TestCadaRealGanhaBonusUmaVez:

    def test_cashback_nao_incide_sobre_o_frete(self, loja):
        """Regra 2, parte a. 3% do frete é dinheiro do entregador saindo do caixa."""
        pedido = _pedido(loja, subtotal=100, frete=10.72)
        lote = CashbackService.credit_purchase(pedido)
        assert lote.amount == Decimal('3.00'), (
            f'esperava 3% de 100 (comida), veio {lote.amount} — o frete entrou na base'
        )

    def test_cashback_so_sobre_o_que_entrou_em_dinheiro_novo(self, loja):
        """Regra 2, parte b — a conta que o dono descreveu: 100 − 80 = 20, 3% de 20."""
        pedido = _pedido(loja, subtotal=100, frete=10.72, discount=80)
        lote = CashbackService.credit_purchase(pedido)
        assert lote.amount == Decimal('0.60')

    def test_pedido_todo_pago_com_saldo_nao_gera_cashback(self, loja):
        """Quem pagou com saldo já recebeu o bônus na compra do pacote."""
        pedido = _pedido(loja, subtotal=76, frete=10.72, discount=76)
        assert CashbackService.credit_purchase(pedido) is None


@pytest.mark.django_db
class TestPacoteOculto:
    """Pacote de teste do dono não pode aparecer para os clientes.

    Sem a ocultação, testar a compra de ponta a ponta com valor baixo obrigaria
    a pendurar "R$ 1 vira R$ 2" na vitrine — e alguém compraria.
    """

    @pytest.fixture
    def loja_com_oculto(self, loja):
        md = dict(loja.metadata)
        md['carteira_tiers'] = md['carteira_tiers'] + [
            {'id': 'teste', 'nome': 'Teste', 'paga': '1.00',
             'credito': '2.00', 'oculto': True},
        ]
        loja.metadata = md
        loja.save(update_fields=['metadata'])
        return loja

    def test_nao_aparece_na_vitrine(self, loja_com_oculto):
        ids = [t['id'] for t in CashbackService.tiers(loja_com_oculto)]
        assert 'teste' not in ids
        assert 'padrao' in ids

    def test_mas_continua_comprável_por_quem_tem_o_id(self, loja_com_oculto):
        pacote = CashbackService.tier(loja_com_oculto, 'teste')
        assert pacote is not None and pacote['paga'] == Decimal('1.00')

    def test_e_credita_normalmente(self, loja_com_oculto):
        lote = CashbackService.credit_prepaid(
            loja_com_oculto, TELEFONE, 'teste', 'carteira-teste-x-1',
        )
        assert lote.amount == Decimal('2.00')
