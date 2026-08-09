"""
`metadata` do combo precisa trafegar pela API do painel.

O agente de WhatsApp lê `StoreCombo.metadata['inclui']` para saber o brinde
fixo do combo ("na compra de 8 rondellis, ganhe 2 molhos"). O campo existe no
model desde sempre, mas o StoreComboSerializer não o listava — então o lojista
não tinha como cadastrar e o dado só entrava por shell.
"""
import pytest

from apps.stores.api.serializers import StoreComboSerializer
from apps.stores.models import StoreCombo
from apps.stores.tests.factories import make_store


@pytest.fixture
def combo(db):
    store = make_store()
    return StoreCombo.objects.create(
        store=store, name="Combo 8", slug="combo-8", price="336.00", is_active=True,
    )


def test_metadata_sai_na_leitura(combo):
    combo.metadata = {"inclui": ["2 Molhos grátis"]}
    combo.save(update_fields=["metadata"])

    data = StoreComboSerializer(combo).data

    assert data["metadata"] == {"inclui": ["2 Molhos grátis"]}


def test_metadata_entra_na_escrita(combo):
    s = StoreComboSerializer(
        combo, data={"metadata": {"inclui": ["2 Molhos grátis"]}}, partial=True
    )

    assert s.is_valid(), s.errors
    s.save()
    combo.refresh_from_db()
    assert combo.metadata["inclui"] == ["2 Molhos grátis"]


def test_metadata_preserva_chaves_que_nao_sao_do_painel(combo):
    """`loyalty_units` vive no mesmo JSON — salvar `inclui` não pode apagá-lo.

    O painel manda o objeto inteiro, então quem garante isso é o front; aqui
    fica registrado que o backend faz substituição total do JSON.
    """
    combo.metadata = {"loyalty_units": 3}
    combo.save(update_fields=["metadata"])

    s = StoreComboSerializer(
        combo,
        data={"metadata": {"loyalty_units": 3, "inclui": ["2 Molhos"]}},
        partial=True,
    )
    assert s.is_valid(), s.errors
    s.save()

    combo.refresh_from_db()
    assert combo.metadata == {"loyalty_units": 3, "inclui": ["2 Molhos"]}
