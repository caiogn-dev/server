"""Quem compra saldo vira cliente da loja — e aparece no painel.

26/09, Cê Saladas: Flaviane comprou o Pacote Leve (pagou R$ 139, ganhou
R$ 152). Nasceram o lote e o "pedido" de carteira, mas nenhum usuário nem
StoreCustomer: ela não existia em Clientes, e na aba de cashback (69
clientes ordenados por vencimento) caiu na página 2. O dono concluiu que o
pedido tinha sumido.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot, StoreCustomer, StorePayment
from apps.stores.services.carteira_service import CarteiraService
from apps.stores.services.cashback_service import CashbackService

TELEFONE = '5511976457452'


@pytest.fixture
def dono(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_user(username='dono-cria-cliente', email='dcc@t.local', password='x')


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-cria-cliente', store_type='food', status='active',
        metadata={'cashback_enabled': True, 'cashback_percent': '3', 'cashback_expiry_days': '30',
                  'carteira_tiers': [{'id': 'leve', 'nome': 'Leve', 'paga': '139.00', 'credito': '152.00'}]},
    )


@pytest.mark.django_db
class TestCompraCriaCliente:
    def _venda(self, loja):
        lote = CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:flaviane')
        pagamento = StorePayment.objects.create(
            store=loja, amount=Decimal('139.00'), payment_method='pix', payer_name='Flaviane Paes',
            paid_at=timezone.now(), external_reference='carteira-leve-x', status='paid',
        )
        return CarteiraService._venda_do_pacote(pagamento, 'leve', lote)

    def test_cria_usuario_e_cliente_da_loja_com_nome(self, loja):
        pedido = self._venda(loja)
        cliente = StoreCustomer.objects.get(store=loja, phone=TELEFONE)
        assert cliente.user is not None
        assert cliente.user.first_name == 'Flaviane'
        assert pedido.customer_id == cliente.user_id

    def test_segunda_compra_nao_duplica_o_cliente(self, loja):
        self._venda(loja)
        lote2 = CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:flaviane-2')
        pagamento2 = StorePayment.objects.create(
            store=loja, amount=Decimal('139.00'), payment_method='pix', payer_name='Flaviane Paes',
            paid_at=timezone.now(), external_reference='carteira-leve-y', status='paid',
        )
        CarteiraService._venda_do_pacote(pagamento2, 'leve', lote2)
        assert StoreCustomer.objects.filter(store=loja, phone=TELEFONE).count() == 1


@pytest.mark.django_db
class TestSaldoCompradoPrimeiro:
    def test_recorte_por_origem_e_mais_recente_primeiro(self, loja, dono):
        # Cashback antigo vencendo antes (iria primeiro na ordem padrão)...
        CashbackService.credit_prepaid(loja, '5563900000001', tier_id='leve', source_ref='mp:a')
        antigo = StoreCashbackLot.objects.get(phone='5563900000001')
        StoreCashbackLot.objects.filter(pk=antigo.pk).update(
            origin=StoreCashbackLot.Origin.PURCHASE, created_at=timezone.now() - timezone.timedelta(days=20),
        )
        # ...e a compra de hoje.
        CashbackService.credit_prepaid(loja, TELEFONE, tier_id='leve', source_ref='mp:b')

        c = APIClient(); c.force_authenticate(dono)
        padrao = c.get(f'/api/v1/stores/{loja.slug}/cashback/').json()['results']
        assert padrao[0]['phone'] == '5563900000001', 'a ordem padrão continua por vencimento'

        recorte = c.get(f'/api/v1/stores/{loja.slug}/cashback/', {'origem': 'prepaid', 'ordem': 'recente'}).json()['results']
        assert [r['phone'] for r in recorte] == [TELEFONE]
        assert Decimal(str(recorte[0]['saldo_carteira'])) == Decimal('152.00')
