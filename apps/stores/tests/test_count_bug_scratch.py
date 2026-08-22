from decimal import Decimal
import pytest
from django.core.management import call_command
from django.utils import timezone
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.mark.django_db
def test_stdout_count_matches_reality(capsys):
    loja = make_store(name='Ce Saladas Count Test')
    quando = timezone.now() - timezone.timedelta(days=14)
    p = StoreOrder.objects.create(
        store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
        status='delivered', payment_status='pending', payment_method='cash',
        customer_phone='+5563984143551',
    )
    StoreOrder.objects.filter(id=p.id).update(delivered_at=quando)

    call_command('liquidar_entregas_em_dinheiro')
    captured = capsys.readouterr()
    print("STDOUT WAS:", captured.out)
    assert '1 pedidos liquidados' in captured.out, f"BUG CONFIRMED, got: {captured.out!r}"
