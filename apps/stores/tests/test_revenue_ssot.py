"""
Receita tem UMA definição só: pedido pago E não cancelado E não é teste.

Antes existiam três regras diferentes em três arquivos, e os três davam números
diferentes para a mesma loja:

  BI/analytics   payment_status='paid'                    -> R$ 2.324,35
  resumo de IA   exclude(cancelled/refunded/failed)       -> R$ 2.419,35
  gráfico 30d    (nenhum filtro)                          -> R$ 5.056,42  ← na home
  correto        pago E não cancelado                     -> R$ 2.324,35

O gráfico da home mostrava mais que o DOBRO do faturamento real, somando os
cancelados. E nenhum dos três excluía os pedidos de teste do próprio dono, que
eram 40% do volume.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.stores.metrics import (
    STATUS_SEM_RECEITA, eh_pedido_de_teste, marcar_como_teste, pedidos_de_receita,
)

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_rev', password='x')
    return Store.objects.create(owner=dono, name='Loja Rev', slug='loja-rev-test')


def _pedido(loja, total, status='delivered', pagamento='paid', metadata=None):
    return StoreOrder.objects.create(
        store=loja, total=Decimal(total), subtotal=Decimal(total), status=status,
        payment_status=pagamento, metadata=metadata or {},
    )


@pytest.mark.django_db
class TestReceitaSSOT:

    def test_conta_pedido_pago_e_entregue(self, loja):
        _pedido(loja, '100.00')
        assert pedidos_de_receita(loja).count() == 1

    @pytest.mark.parametrize('status', sorted(STATUS_SEM_RECEITA))
    def test_nao_conta_cancelado_estornado_nem_falho(self, loja, status):
        """Era isto que inflava o gráfico da home em mais de 2x."""
        _pedido(loja, '100.00', status=status)
        assert pedidos_de_receita(loja).count() == 0

    def test_nao_conta_cancelado_mesmo_estando_pago(self, loja):
        """Pedido pago e depois cancelado sem estorno entrava como receita no BI."""
        _pedido(loja, '100.00', status='cancelled', pagamento='paid')
        assert pedidos_de_receita(loja).count() == 0

    def test_nao_conta_entregue_com_pagamento_pendente(self, loja):
        """O resumo de IA contava — olhava só o status, não o pagamento."""
        _pedido(loja, '95.00', status='delivered', pagamento='pending')
        assert pedidos_de_receita(loja).count() == 0

    def test_nao_conta_pedido_de_teste(self, loja):
        _pedido(loja, '100.00', metadata={'is_test': True})
        assert pedidos_de_receita(loja).count() == 0

    def test_soma_so_o_que_e_receita_de_verdade(self, loja):
        _pedido(loja, '100.00')                                     # conta
        _pedido(loja, '50.00')                                      # conta
        _pedido(loja, '999.00', status='cancelled')                 # não
        _pedido(loja, '888.00', pagamento='pending')                # não
        _pedido(loja, '777.00', metadata={'is_test': True})         # não
        from django.db.models import Sum
        total = pedidos_de_receita(loja).aggregate(t=Sum('total'))['t']
        assert total == Decimal('150.00')

    def test_incluir_teste_quando_pedido_explicitamente(self, loja):
        """A operação do dia a dia (KDS, fila) precisa ver o pedido de teste."""
        _pedido(loja, '100.00', metadata={'is_test': True})
        assert pedidos_de_receita(loja, incluir_teste=True).count() == 1


@pytest.mark.django_db
class TestMarcacaoDeTeste:

    def test_marca_e_reconhece(self, loja):
        p = _pedido(loja, '10.00')
        assert eh_pedido_de_teste(p) is False
        marcar_como_teste(p)
        p.refresh_from_db()
        assert eh_pedido_de_teste(p) is True

    def test_marcar_preserva_o_resto_do_metadata(self, loja):
        p = _pedido(loja, '10.00', metadata={'source': 'whatsapp', 'suppress_notifications': True})
        marcar_como_teste(p)
        p.refresh_from_db()
        assert p.metadata['source'] == 'whatsapp'
        assert p.metadata['suppress_notifications'] is True
        assert p.metadata['is_test'] is True

    def test_metadata_vazio_nao_e_teste(self, loja):
        """No banco metadata é NOT NULL, então o caso real é {}."""
        p = _pedido(loja, '10.00', metadata={})
        assert eh_pedido_de_teste(p) is False

    def test_metadata_none_em_objeto_solto_nao_quebra(self, loja):
        """Objeto ainda não persistido pode ter metadata None — não pode estourar."""
        p = StoreOrder(store=loja, total=Decimal('10.00'), subtotal=Decimal('10.00'))
        p.metadata = None
        assert eh_pedido_de_teste(p) is False
        marcar_como_teste(p, salvar=False)
        assert eh_pedido_de_teste(p) is True
