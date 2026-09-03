"""A cobrança de pacote paga vira saldo — e vira venda, sem virar comida.

Três buracos que este teste fecha, todos vistos antes neste repositório:

- **Saldo pago e não creditado.** A cobrança de carteira não tem pedido, e o
  caminho de cobrança avulsa transformaria os R$ 270 num pedido genérico
  "Cobrança por link de pagamento" — dinheiro dentro, cliente sem saldo.

- **Venda que some do relatório.** Se a compra do pacote não virar pedido, os
  R$ 270 não entram no faturamento e os pedidos seguintes saem com desconto:
  o mês fecha como se a loja não tivesse vendido.

- **Comanda de comida que não existe.** O pedido do pacote nasce `digital`; se
  nascesse `delivery`, a impressora cuspiria "*** ENTREGA ***" e a cozinha
  montaria uma salada que ninguém pediu (foi o caso de 15/ago).
"""
from decimal import Decimal

import pytest

from apps.stores.models import Store, StoreCashbackLot, StoreOrder, StorePayment
from apps.stores.services.carteira_service import decompor
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.checkout_service import CheckoutService

TELEFONE = '5563991386719'


@pytest.fixture
def loja(db):
    from django.contrib.auth import get_user_model
    dono = get_user_model().objects.create_user(
        username='dono-cart-wh', email='dono-cart-wh@teste.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-carteira-wh', store_type='food',
        status='active',
        metadata={
            'cashback_enabled': True,
            'cashback_percent': '3',
            'cashback_expiry_days': '30',
            'carteira_tiers': [
                {'id': 'padrao', 'nome': 'Padrão', 'paga': '270.00', 'credito': '304.00'},
            ],
        },
    )


def _cobranca_paga(loja, external_reference, amount='270.00'):
    """Simula a cobrança PIX que o Mercado Pago acabou de aprovar."""
    return StorePayment.objects.create(
        store=loja, order=None, amount=Decimal(amount),
        payment_method=StorePayment.PaymentMethod.PIX,
        status=StorePayment.PaymentStatus.PENDING,
        external_reference=external_reference,
        external_id='mp-987654',
        payer_name='Leani Rodrigues',
    )


@pytest.mark.django_db
class TestCobrancaDePacotePaga:

    def _aprovar(self, cobranca):
        return CheckoutService._handle_storepayment_webhook(cobranca, 'approved')

    def test_o_saldo_entra_com_o_bonus(self, loja):
        ref = f'carteira-padrao-{TELEFONE}-abc123'
        self._aprovar(_cobranca_paga(loja, ref))

        assert CashbackService.balance(loja, TELEFONE) == Decimal('304.00'), (
            'pagou 270 e não recebeu os 304 de crédito'
        )
        lote = StoreCashbackLot.objects.get(store=loja, phone=TELEFONE)
        assert lote.origin == StoreCashbackLot.Origin.PREPAID
        assert lote.source_ref == ref

    def test_vira_venda_pelo_valor_recebido_nao_pelo_credito(self, loja):
        """Faturamento é dinheiro que entrou: R$ 270, nunca os R$ 304."""
        self._aprovar(_cobranca_paga(loja, f'carteira-padrao-{TELEFONE}-x1'))

        pedido = StoreOrder.objects.get(store=loja)
        assert pedido.total == Decimal('270.00')
        assert pedido.payment_status == StoreOrder.PaymentStatus.PAID
        assert pedido.source == 'carteira'
        assert pedido.metadata.get('credito_concedido') == '304.00'

    def test_nao_manda_comida_para_a_cozinha(self, loja):
        self._aprovar(_cobranca_paga(loja, f'carteira-padrao-{TELEFONE}-x2'))

        pedido = StoreOrder.objects.get(store=loja)
        assert pedido.delivery_method == StoreOrder.DeliveryMethod.DIGITAL
        item = pedido.items.get()
        assert item.product_id is None, 'apontou para um produto do cardápio'
        assert 'Pacote' in item.product_name

    def test_webhook_reentregue_nao_dobra_saldo_nem_faturamento(self, loja):
        """O Mercado Pago reentrega. Duas entregas = um pacote de graça."""
        cobranca = _cobranca_paga(loja, f'carteira-padrao-{TELEFONE}-x3')
        self._aprovar(cobranca)
        cobranca.refresh_from_db()
        self._aprovar(cobranca)

        assert CashbackService.balance(loja, TELEFONE) == Decimal('304.00')
        assert StoreOrder.objects.filter(store=loja).count() == 1

    def test_cobranca_avulsa_comum_segue_o_caminho_antigo(self, loja):
        """Guarda: a trava da carteira não pode sequestrar link de pagamento."""
        self._aprovar(_cobranca_paga(loja, f'avulso:{loja.id}', amount='50.00'))

        pedido = StoreOrder.objects.get(store=loja)
        assert pedido.source == 'payment_link'
        assert CashbackService.balance(loja, TELEFONE) == Decimal('0.00')


@pytest.mark.django_db
class TestReferencia:

    def test_duas_compras_do_mesmo_pacote_pelo_mesmo_cliente(self, loja):
        """Sem nonce, a 2ª compra legítima seria recusada pela idempotência —
        o cliente pagaria e não receberia nada."""
        from apps.stores.services.carteira_service import _ref
        a, b = _ref('padrao', TELEFONE), _ref('padrao', TELEFONE)
        assert a != b
        assert decompor(a) == ('padrao', TELEFONE)

    def test_pacote_com_hifen_no_id_ainda_e_lido(self, loja):
        """O id do pacote é livre no painel; `meu-pacote` partiria um parse
        posicional da esquerda."""
        from apps.stores.services.carteira_service import _ref
        ref = _ref('meu-pacote-top', TELEFONE)
        assert decompor(ref) == ('meu-pacote-top', TELEFONE)

    def test_referencia_de_outro_vocabulario_nao_e_carteira(self, loja):
        assert decompor('splink:abc') is None
        assert decompor(f'avulso:{loja.id}') is None
        assert decompor('subpix:uuid:2026-09') is None
        # `subpix` com hífen na competência tem 4 partes ao dividir por '-'…
        assert decompor('subpix-uuid-2026-09') is None
