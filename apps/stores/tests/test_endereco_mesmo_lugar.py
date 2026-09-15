"""Endereço não cresce nem se repete — o caso da Flávia (Cê Saladas).

Produção, 15/set: o endereço dela ganhou uma cópia inteira de si mesmo a cada
pedido e a comanda saiu com "Recepção da ortolife" três vezes:

    25/ago  street = "Quadra 501 Sul Avenida NS 1"
    01/set  street = "Quadra 501 Sul Avenida NS 1, 9, Recepção da ortolife , espaço life - Centro, Palmas, TO"
    10/set  street = (a mesma cauda três vezes)

O cadastro ficou com 4 endereços do mesmo lugar. `_tirar_cauda_de_rotulo`
(10/set) só tirava ", Palmas, TO" — a cauda aqui é o `formatted` inteiro
(número, complemento, bairro, cidade, UF). E o cadastro só reconhecia repetido
por `formatted` idêntico, então cada geração virava endereço novo.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreCustomer, StoreCustomerAddress, StoreOrder

User = get_user_model()

BASE = 'Quadra 501 Sul Avenida NS 1'
CAUDA = ', 9, Recepção da ortolife , espaço life - Centro, Palmas, TO'


def _endereco(rua, numero='9', complemento='Recepção da ortolife , espaço life ', bairro='Centro'):
    return {
        'street': rua, 'number': numero, 'complement': complemento,
        'neighborhood': bairro, 'city': 'Palmas', 'state': 'TO', 'zip_code': '77016006',
    }


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_endereco_lugar', password='x')
    return Store.objects.create(owner=dono, name='Loja Endereço', slug='loja-endereco-lugar',
                                city='Palmas', state='TO')


class TestRuaSemCauda:

    @pytest.mark.parametrize('rua', [BASE, BASE + CAUDA, BASE + CAUDA * 2, BASE + CAUDA * 3])
    def test_rua_empilhada_volta_a_ser_a_rua(self, rua):
        registro = CustomerIdentityService._build_address_record(_endereco(rua))
        assert registro['street'] == BASE

    def test_rua_que_so_tem_virgula_nao_e_cortada(self):
        rua = 'Quadra 103 Norte, Rua NO-5, Lote 02'
        registro = CustomerIdentityService._build_address_record(_endereco(rua, numero='02', complemento='', bairro=''))
        assert registro['street'] == rua

    def test_numero_no_meio_da_rua_nao_e_cortado(self):
        rua = 'Alameda 9, Quadra 501 Sul'
        registro = CustomerIdentityService._build_address_record(_endereco(rua))
        assert registro['street'] == rua


@pytest.mark.django_db
class TestComandaDePedidoAntigo:

    def test_comanda_imprime_a_rua_uma_vez(self, loja):
        from apps.stores.services.print_service import _extract_address_lines
        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('40'), subtotal=Decimal('40'), delivery_method='delivery',
            delivery_address=_endereco(BASE + CAUDA * 3),
        )

        linhas = _extract_address_lines(pedido)

        assert linhas[0] == f'{BASE}, nº 9'
        assert ' '.join(linhas).lower().count('ortolife') == 1


@pytest.mark.django_db
class TestCadastroNaoRepeteOMesmoLugar:

    def _checkout(self, loja, endereco):
        CustomerIdentityService.sync_checkout_customer(
            store=loja, customer_name='Flavia Martins', phone='5563991112222',
            delivery_method='delivery', delivery_address=endereco,
        )

    def _enderecos(self, loja):
        cliente = StoreCustomer.objects.get(store=loja)
        return list(StoreCustomerAddress.objects.filter(customer=cliente))

    def test_pedidos_com_a_rua_crescendo_viram_um_endereco(self, loja):
        for rua in (BASE, BASE + CAUDA, BASE + CAUDA * 2):
            self._checkout(loja, _endereco(rua))

        enderecos = self._enderecos(loja)
        assert len(enderecos) == 1
        assert enderecos[0].street == BASE
        assert enderecos[0].is_default

    def test_maiuscula_e_acento_nao_fazem_outro_endereco(self, loja):
        self._checkout(loja, _endereco('Secretaria da Cidadania e Justiça', numero='', complemento='', bairro=''))
        self._checkout(loja, _endereco('SECRETARIA DA CIDADANIA E JUSTICA', numero='', complemento='', bairro=''))

        assert len(self._enderecos(loja)) == 1

    def test_outro_numero_e_outro_endereco(self, loja):
        self._checkout(loja, _endereco('Alameda 18', numero='3', complemento='', bairro=''))
        self._checkout(loja, _endereco('Alameda 18', numero='11', complemento='', bairro=''))

        enderecos = self._enderecos(loja)
        assert len(enderecos) == 2
        assert sum(e.is_default for e in enderecos) == 1
