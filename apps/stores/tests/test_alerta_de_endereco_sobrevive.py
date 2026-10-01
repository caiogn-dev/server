"""O aviso de endereço divergente SUMIA — 0 pedidos marcados em 30 dias (01/10).

A task gravava `metadata['endereco_divergente']` 0,2 s depois de criar o
pedido, e o próprio checkout salvava o pedido de novo logo em seguida com o
`metadata` que tinha em memória — sem o aviso. O Thiago (407 Sul → pin na 106
Norte) foi detectado no log e apagado do pedido. Agora o aviso mora numa
tabela própria, que salvar o pedido não toca, e o painel continua lendo
`metadata.endereco_divergente` (o serializer injeta).

E o caso da Simone (704 Sul → pin numa "Alameda 9" sem quadra no endereço do
pin) não era nem detectado: sem quadra no pin, a conferência calava.
"""
from unittest.mock import patch

import pytest

from apps.stores.api.serializers import StoreOrderSerializer
from apps.stores.models import StoreOrder
from apps.stores.services.conferencia_de_endereco import conferir
from apps.stores.tasks import conferir_endereco_do_pedido
from apps.stores.tests.factories import make_store

THIAGO = {
    'street': '407 sul, alameda circular 02, Qi-21 lote 19', 'number': '19', 'neighborhood': 'Centro',
    'city': 'Palmas', 'state': 'TO', 'lat': -10.1809059, 'lng': -48.3216431,
    'coordinate_source': 'customer_selected_pin', 'coordinates_confirmed': True,
}
SIMONE = {
    'street': '704 Sul Al 09 Hm 09 Residencial Boulevard', 'number': '1', 'neighborhood': 'Plano Diretor Sul',
    'city': 'Palmas', 'state': 'TO', 'lat': -10.2115663, 'lng': -48.346633,
}
REVERSE = 'apps.stores.services.conferencia_de_endereco._reverse_do_geoservice'
GEOCODE = 'apps.stores.services.conferencia_de_endereco._geocode_do_geoservice'


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas', city='Palmas', state='TO')


def _pedido(loja, endereco):
    return StoreOrder.objects.create(
        store=loja, total=40, subtotal=40, status='pending', payment_status='pending',
        payment_method='pix', customer_phone='+5563999999999', delivery_address=endereco,
    )


@pytest.mark.django_db
def test_aviso_sobrevive_ao_checkout_salvar_o_pedido_de_novo(loja):
    pedido = _pedido(loja, THIAGO)
    em_memoria = StoreOrder.objects.get(pk=pedido.pk)  # o checkout segura esta cópia
    with patch(REVERSE, return_value={'formatted_address': 'Q. 106 Norte Alameda 10, Palmas - TO'}):
        conferir_endereco_do_pedido(str(pedido.id))
    em_memoria.metadata = {**(em_memoria.metadata or {}), 'cashback_aplicado': 0.57}
    em_memoria.save()  # o salvamento que apagava o aviso
    dados = StoreOrderSerializer(StoreOrder.objects.get(pk=pedido.pk)).data
    assert dados['metadata']['endereco_divergente']['digitado'] == '407 sul'
    assert dados['metadata']['endereco_divergente']['pin'] == '106 norte'
    assert dados['metadata']['cashback_aplicado'] == 0.57


def test_pin_sem_quadra_confere_pela_distancia_ao_texto():
    # Pin cai numa "Alameda 9" sem quadra; o texto (704 Sul) fica a ~2,5 km.
    with patch(REVERSE, return_value={'formatted_address': 'Alameda 9, 11 - Plano Diretor Sul, Palmas - TO'}), \
         patch(GEOCODE, return_value={'lat': -10.2265355, 'lng': -48.3278873, 'street': 'Quadra 704 Sul Alameda 12'}):
        d = conferir(SIMONE)
    assert d is not None
    assert d['digitado'] == '704 sul'
    assert d['distancia_km'] > 1.5


def test_pin_sem_quadra_e_perto_do_texto_nao_acusa():
    with patch(REVERSE, return_value={'formatted_address': 'Alameda 9, Plano Diretor Sul, Palmas - TO'}), \
         patch(GEOCODE, return_value={'lat': -10.2120, 'lng': -48.3470, 'street': 'Quadra 704 Sul Alameda 9'}):
        assert conferir(SIMONE) is None
