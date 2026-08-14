"""O endereço do pedido tem que virar endereço SALVO do cliente.

Relatado pelo dono em 14/ago: "ao fazer um pedido novo de um cliente que já
pediu, o endereço não está sendo vinculado a ela quando eu puxo pelo PDV... o
bot consegue puxar mas o PDV não".

A queixa procede, e a assimetria explica tudo: o bot lê o `delivery_address` do
ÚLTIMO PEDIDO; o PDV lê o caderno de endereços do cliente (`UserAddress`). E o
caderno só era preenchido quando o cliente mandava um pin no WhatsApp — está
escrito no docstring do próprio model. Pedido comum nunca salvava nada.

Medido na Cê Saladas: **45 clientes já pediram com entrega, 7 têm endereço
salvo. 38 aparecem vazios no PDV.**

O campo `delivery_address` é JSON livre e em produção tem CINCO formatos
diferentes, incluindo 18 pedidos que são só `{"address": "texto livre"}`. Todos
estão cobertos abaixo — o normalizador não pode assumir um formato só.

⚠️ O gancho é o signal de `StoreOrder`, não o checkout: existem TRÊS
implementações de criação de pedido neste repo, e corrigir numa só deixaria o
bug vivo nas outras duas.
"""
import pytest

from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store
from apps.users.models import UnifiedUser, UserAddress
from apps.users.caderno_de_enderecos import guardar_endereco_do_pedido

# Os cinco formatos medidos em produção, com a contagem de cada um.
COMPLETO = {  # 32 pedidos
    'street': 'Quadra 506 Norte Rua 5', 'number': '381-297',
    'neighborhood': 'Plano Diretor Norte', 'city': 'Palmas', 'state': 'Tocantins',
    'zip_code': '77006628', 'complement': 'ao lado da GoFit',
    'lat': -10.164419, 'lng': -48.313784, 'label': 'Quadra 506 Norte',
    'raw_address': 'Quadra 506 Norte Rua 5, 381-297',
}
TEXTO_LIVRE = {'address': 'secretaria da cidadania e justiça'}  # 18 pedidos
SO_CEP = {'street': 'Rua 5', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77006628'}  # 8
COM_ROTA = {  # 1 — vem da cotação de frete
    'city': 'Palmas', 'state': 'TO', 'lat': -10.16, 'lng': -48.31,
    'raw_address': 'Av. JK', 'distance_km': 3.2, 'duration_minutes': 11,
}


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas', city='Palmas', state='TO')


@pytest.fixture
def cliente(db):
    return UnifiedUser.objects.create(phone_number='+5563984143551', name='Dyana')


def _pedido(loja, endereco, telefone='+5563984143551'):
    return StoreOrder.objects.create(
        store=loja, total=100, subtotal=100, status='pending',
        payment_status='pending', payment_method='pix',
        customer_phone=telefone, delivery_address=endereco,
    )


@pytest.mark.django_db
class TestOsCincoFormatosReais:
    def test_formato_completo(self, loja, cliente):
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO))

        e = UserAddress.objects.get(unified_user=cliente)
        assert e.street == 'Quadra 506 Norte Rua 5'
        assert e.number == '381-297'
        assert e.neighborhood == 'Plano Diretor Norte'
        assert e.city == 'Palmas'
        assert e.zip_code == '77006628'

    def test_texto_livre_nao_pode_ser_descartado(self, loja, cliente):
        """18 pedidos reais são só isto. Descartar = perder 18 endereços."""
        guardar_endereco_do_pedido(_pedido(loja, TEXTO_LIVRE))

        e = UserAddress.objects.get(unified_user=cliente)
        assert 'secretaria da cidadania' in e.street.lower()

    def test_texto_livre_herda_cidade_da_loja(self, loja, cliente):
        """`city`/`state` são obrigatórios; sem fallback o endereço nasce torto."""
        guardar_endereco_do_pedido(_pedido(loja, TEXTO_LIVRE))

        e = UserAddress.objects.get(unified_user=cliente)
        assert e.city == 'Palmas'
        assert e.state == 'TO'

    def test_formato_so_com_cep(self, loja, cliente):
        guardar_endereco_do_pedido(_pedido(loja, SO_CEP))

        assert UserAddress.objects.get(unified_user=cliente).zip_code == '77006628'

    def test_formato_da_cotacao_de_rota(self, loja, cliente):
        guardar_endereco_do_pedido(_pedido(loja, COM_ROTA))

        e = UserAddress.objects.get(unified_user=cliente)
        assert e.street == 'Av. JK'
        assert e.lat is not None

    def test_coordenadas_sao_preservadas(self, loja, cliente):
        """Sem lat/lng o frete precisa geocodificar de novo — e custa dinheiro."""
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO))

        e = UserAddress.objects.get(unified_user=cliente)
        assert e.lat is not None and e.lng is not None


@pytest.mark.django_db
class TestNaoPodeDuplicar:
    def test_dez_pedidos_do_mesmo_lugar_geram_UM_endereco(self, loja, cliente):
        """O signal roda em todo save — inclusive em cada mudança de status."""
        for _ in range(10):
            guardar_endereco_do_pedido(_pedido(loja, COMPLETO))

        assert UserAddress.objects.filter(unified_user=cliente).count() == 1

    def test_o_mesmo_pedido_salvo_de_novo_nao_duplica(self, loja, cliente):
        p = _pedido(loja, COMPLETO)
        guardar_endereco_do_pedido(p)
        guardar_endereco_do_pedido(p)

        assert UserAddress.objects.filter(unified_user=cliente).count() == 1

    def test_endereco_diferente_vira_outro_registro(self, loja, cliente):
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO))
        guardar_endereco_do_pedido(_pedido(loja, SO_CEP))

        assert UserAddress.objects.filter(unified_user=cliente).count() == 2


@pytest.mark.django_db
class TestOQueNaoPodeAcontecer:
    def test_endereco_fica_na_loja_do_pedido(self, loja, cliente):
        """A busca do PDV filtra por `tenant` — sem isso o endereço some da tela."""
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO))

        assert UserAddress.objects.get(unified_user=cliente).tenant_id == loja.id

    def test_uma_loja_nao_ve_o_endereco_da_outra(self, loja, cliente):
        outra = make_store(name='Kero Kero', city='Palmas', state='TO')
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO))

        assert not UserAddress.objects.filter(unified_user=cliente, tenant=outra).exists()

    def test_retirada_na_loja_nao_cria_endereco(self, loja, cliente):
        guardar_endereco_do_pedido(_pedido(loja, {}))

        assert not UserAddress.objects.filter(unified_user=cliente).exists()

    def test_cliente_desconhecido_nao_levanta(self, loja):
        """Pedido de balcão sem cadastro é normal — não pode derrubar o save."""
        guardar_endereco_do_pedido(_pedido(loja, COMPLETO, telefone='+5563900000000'))

    def test_pedido_sem_telefone_nao_levanta(self, loja):
        p = StoreOrder.objects.create(
            store=loja, total=10, subtotal=10, status='pending',
            payment_status='pending', payment_method='cash',
            customer_phone='', delivery_address=COMPLETO,
        )
        guardar_endereco_do_pedido(p)

    def test_lixo_no_campo_nao_levanta(self, loja, cliente):
        """`delivery_address` é JSON livre — já veio string e já veio None."""
        for lixo in ('uma string', None, [], 42):
            p = _pedido(loja, {})
            p.delivery_address = lixo
            guardar_endereco_do_pedido(p)
