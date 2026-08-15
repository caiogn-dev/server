"""Recupera as vendas entregues em dinheiro que nunca liquidaram.

O conserto do Task 1 vale de agora em diante. Este comando resolve o passivo:
R$ 306,00 medidos em 14/08 (CE-2607316642, R$ 95,00, e KER2608076764,
R$ 211,00) — entregues, dinheiro recebido em mãos, `payment_status=pending`.

⚠️ `paid_at` recebe `delivered_at`, NUNCA `now()`. Uma venda de 31/07 marcada
como paga hoje apareceria no faturamento de hoje: o furo do relatório sairia do
lugar em vez de fechar.
"""
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _entregue_sem_liquidar(loja, metodo='cash', dias_atras=14):
    quando = timezone.now() - timezone.timedelta(days=dias_atras)
    p = StoreOrder.objects.create(
        store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
        status='delivered', payment_status='pending', payment_method=metodo,
        customer_phone='+5563984143551',
    )
    StoreOrder.objects.filter(id=p.id).update(delivered_at=quando)
    p.refresh_from_db()
    return p


@pytest.mark.django_db
class TestRecuperacao:
    def test_marca_pago(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'paid'

    def test_paid_at_e_a_data_da_ENTREGA(self, loja):
        """Marcar com `now()` moveria a venda de 31/07 para o faturamento de hoje."""
        p = _entregue_sem_liquidar(loja, dias_atras=14)
        entrega = p.delivered_at

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.paid_at == entrega

    def test_dry_run_nao_grava(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro', dry_run=True)

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_rodar_duas_vezes_nao_muda_nada(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro')
        p.refresh_from_db()
        primeiro = p.paid_at
        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.paid_at == primeiro

    def test_filtra_por_loja(self, loja):
        outra = make_store(name='Kero Kero')
        de_outra = _entregue_sem_liquidar(outra)

        call_command('liquidar_entregas_em_dinheiro', loja=loja.slug)

        de_outra.refresh_from_db()
        assert de_outra.payment_status == 'pending'


@pytest.mark.django_db
class TestOQueNaoPodeSerTocado:
    def test_pix_entregue_e_pendente_NAO_vira_pago(self, loja):
        """Não pagou. Marcar aqui inventaria receita."""
        p = _entregue_sem_liquidar(loja, metodo='pix')

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_cancelado_em_dinheiro_nao_vira_pago(self, loja):
        p = _entregue_sem_liquidar(loja)
        StoreOrder.objects.filter(id=p.id).update(status='cancelled')

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_sem_delivered_at_nao_inventa_data(self, loja):
        """Sem data de entrega não há data de pagamento defensável."""
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='delivered', payment_status='pending', payment_method='cash',
            customer_phone='+5563984143551',
        )

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'
