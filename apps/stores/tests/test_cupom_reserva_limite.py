"""
Cupom com usage_limit não pode conceder desconto além do limite.

Regressão (S2-ARCH-005 / S2-RACE-008): `increment_usage()` já era atômico — o
UPDATE carrega `used_count__lt=usage_limit` no WHERE e devolve True/False. Mas o
checkout descartava esse retorno e incrementava só no FIM do pedido, depois de já
ter aplicado o desconto no total. Clássico check-then-act: N checkouts leem
used_count=99/100, todos passam na validação, todos ganham o desconto, um só
incrementa. O contador termina em 100 (parece certo) enquanto 111 pedidos saíram
com desconto — o dono não tem como perceber o vazamento.

O conserto trata o incremento como RESERVA: reserva antes de aplicar o desconto,
e sem vaga não há desconto. Como tudo roda dentro de `_create_order_atomic`, um
rollback do pedido também desfaz a reserva.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCoupon

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_cup', password='x')
    return Store.objects.create(owner=dono, name='Loja Cupom', slug='loja-cupom-test')


def _cupom(loja, limite, usados=0):
    c = StoreCoupon.objects.create(
        store=loja,
        code='PRIMEIROS',
        discount_type='percentage',
        discount_value=Decimal('50'),
        usage_limit=limite,
        is_active=True,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )
    if usados:
        StoreCoupon.objects.filter(pk=c.pk).update(used_count=usados)
        c.refresh_from_db()
    return c


@pytest.mark.django_db
class TestReservaDeCupom:

    def test_increment_usage_devolve_false_quando_esgotado(self, loja):
        """A garantia do modelo — base de tudo. Já passava, fica travada."""
        c = _cupom(loja, limite=1)
        assert c.increment_usage() is True
        assert c.increment_usage() is False

    def test_ultima_vaga_e_dada_a_um_so(self, loja):
        """Duas reservas na última vaga: uma ganha, a outra não."""
        c = _cupom(loja, limite=100, usados=99)
        primeiro = StoreCoupon.objects.get(pk=c.pk).increment_usage()
        segundo = StoreCoupon.objects.get(pk=c.pk).increment_usage()
        assert (primeiro, segundo) == (True, False)
        c.refresh_from_db()
        assert c.used_count == 100, 'contador não pode passar do limite'

    def test_cupom_sem_limite_nunca_recusa(self, loja):
        c = _cupom(loja, limite=None)
        assert all(StoreCoupon.objects.get(pk=c.pk).increment_usage() for _ in range(5))
        c.refresh_from_db()
        assert c.used_count == 5


@pytest.mark.django_db
class TestCheckoutConsomeAReserva:
    """O ponto do bug: o checkout precisa LER o retorno da reserva."""

    def test_checkout_nao_aplica_desconto_quando_a_reserva_falha(self, loja):
        from apps.stores.services.checkout_service import CheckoutService
        import inspect

        src = inspect.getsource(CheckoutService._create_order_atomic)
        assert 'increment_usage()' in src, 'a reserva sumiu do checkout'
        # A reserva tem que ser condicional — o retorno não pode ser descartado.
        assert 'if candidate.increment_usage()' in src or 'if coupon.increment_usage()' in src, (
            'increment_usage() continua sendo chamado como efeito colateral, '
            'sem consumir o booleano que diz se havia vaga'
        )
