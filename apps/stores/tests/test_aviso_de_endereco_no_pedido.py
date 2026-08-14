"""O aviso de endereço divergente tem que CHEGAR ao painel.

De nada adianta detectar a divergência num serviço se ela morre em log. O
serializer do pedido já expõe `metadata`, então o aviso vai para lá e aparece
sem encanamento novo.

Origem: CE-2608140823 — texto "110 sul", pin na 706 Sul, 5,15 km. A cliente
pagou R$ 11,00 de frete onde antes pagou R$ 7,00, e a entrega foi para o lugar
errado.
"""
from unittest.mock import patch

import pytest

from apps.stores.models import StoreOrder
from apps.stores.tasks import conferir_endereco_do_pedido
from apps.stores.tests.factories import make_store

BARBARA = {
    'street': 'Av jk 110 sul Clínica DVI ', 'number': 'Lote 21',
    'city': 'Palmas', 'state': 'TO',
    'lat': -10.2298952, 'lng': -48.3205388,
    'coordinate_source': 'customer_selected_pin', 'coordinates_confirmed': True,
}
PIN_NA_706 = {'formatted_address': 'Q. 706 Sul Avenida LO 19, Palmas - TO'}
PIN_NA_110 = {'formatted_address': 'Q. 110 Sul Alameda 1, Palmas - TO'}


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas', city='Palmas', state='TO')


def _pedido(loja, endereco):
    return StoreOrder.objects.create(
        store=loja, total=47.74, subtotal=36.74, status='pending',
        payment_status='pending', payment_method='pix',
        customer_phone='+5563981414138', delivery_address=endereco,
    )


@pytest.mark.django_db
class TestOAvisoChegaNoPedido:
    def test_divergencia_vira_metadata_do_pedido(self, loja):
        p = _pedido(loja, BARBARA)

        with patch('apps.stores.services.conferencia_de_endereco._reverse_do_geoservice',
                   return_value=PIN_NA_706):
            conferir_endereco_do_pedido(str(p.id))

        p.refresh_from_db()
        aviso = p.metadata['endereco_divergente']
        assert aviso['digitado'] == '110 sul'
        assert aviso['pin'] == '706 sul'
        assert '110 sul' in aviso['aviso'] and '706 sul' in aviso['aviso']

    def test_endereco_coerente_nao_suja_o_pedido(self, loja):
        p = _pedido(loja, BARBARA)

        with patch('apps.stores.services.conferencia_de_endereco._reverse_do_geoservice',
                   return_value=PIN_NA_110):
            conferir_endereco_do_pedido(str(p.id))

        p.refresh_from_db()
        assert 'endereco_divergente' not in (p.metadata or {})

    def test_nao_apaga_o_que_ja_estava_na_metadata(self, loja):
        """`metadata` é compartilhada — sobrescrever perderia dado de outro fluxo."""
        p = _pedido(loja, BARBARA)
        StoreOrder.objects.filter(id=p.id).update(metadata={'origem': 'whatsapp'})

        with patch('apps.stores.services.conferencia_de_endereco._reverse_do_geoservice',
                   return_value=PIN_NA_706):
            conferir_endereco_do_pedido(str(p.id))

        p.refresh_from_db()
        assert p.metadata['origem'] == 'whatsapp'
        assert 'endereco_divergente' in p.metadata

    def test_pedido_inexistente_nao_levanta(self, loja):
        import uuid
        assert conferir_endereco_do_pedido(str(uuid.uuid4())) is None


@pytest.mark.django_db
class TestNaoPodeAtrapalharAVenda:
    def test_geocoder_fora_do_ar_nao_derruba_a_conferencia(self, loja):
        p = _pedido(loja, BARBARA)

        with patch('apps.stores.services.conferencia_de_endereco._reverse_do_geoservice',
                   side_effect=RuntimeError('google fora')):
            assert conferir_endereco_do_pedido(str(p.id)) is None

    def test_criar_pedido_nao_espera_o_google(self, loja, django_capture_on_commit_callbacks):
        """A conferência é rede; entrar no checkout atrasaria toda venda.

        `django_capture_on_commit_callbacks` porque o enfileiramento acontece em
        `transaction.on_commit` — que é justamente o ponto: nada dispara antes
        de a venda estar salva.
        """
        with patch('apps.stores.tasks.conferir_endereco_do_pedido.delay') as fila:
            with django_capture_on_commit_callbacks(execute=True):
                _pedido(loja, BARBARA)

        fila.assert_called_once()

    def test_retirada_na_loja_nao_enfileira_nada(self, loja, django_capture_on_commit_callbacks):
        with patch('apps.stores.tasks.conferir_endereco_do_pedido.delay') as fila:
            with django_capture_on_commit_callbacks(execute=True):
                _pedido(loja, {})

        fila.assert_not_called()
