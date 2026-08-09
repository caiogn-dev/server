"""Avaliação por pilares: comida, entrega e atendimento.

"Nota 4,6" não diz o que consertar. A loja pode estar com a comida impecável e
a entrega atrasando, ou o contrário — e a decisão é oposta em cada caso:
contratar entregador ou revisar a cozinha.

TRÊS DECISÕES QUE OS TESTES FIXAM:

1. Os pilares são OPCIONAIS. A avaliação já funcionava com uma nota só, e
   exigir três reduz a taxa de resposta — que numa loja com 4 avaliações é o
   recurso mais escasso. Quem responde só a geral continua sendo aceito.

2. Retirada no balcão NÃO tem pilar de entrega. Perguntar "como foi a entrega"
   para quem buscou o pedido produz nota inventada, e nota inventada estraga a
   média de um pilar que existe para orientar decisão.

3. A nota geral continua sendo a fonte de verdade da média da loja. Quando o
   cliente dá só os pilares, ela é DERIVADA deles — senão a loja teria duas
   médias diferentes na mesma tela.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StoreReview

User = get_user_model()


@pytest.fixture(autouse=True)
def _throttle_zerado():
    """O endpoint de avaliação limita 10 POSTs/hora por IP.

    Na suíte todos os testes vêm do mesmo IP, então a partir da décima
    avaliação o POST passava a devolver 429 — e como `_avaliar` nem sempre
    checa o status, o sintoma aparecia longe da causa: um `pior_pilar: None`
    inexplicável, porque a avaliação simplesmente não tinha sido criada.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-pilar', email='pilar@x.com', password='x')
    # `billing_exempt`: o relatório de avaliações é feature Pro, e o assunto
    # aqui são os pilares — não o gate de plano, que tem teste próprio.
    return Store.objects.create(
        name='Loja Pilar', slug='loja-pilar', owner=dono,
        status='active', billing_exempt=True,
    )


def _pedido(loja, metodo='delivery'):
    return StoreOrder.objects.create(
        store=loja,
        status=StoreOrder.OrderStatus.DELIVERED,
        payment_status=StoreOrder.PaymentStatus.PAID,
        delivery_method=metodo,
        subtotal=Decimal('50'), total=Decimal('50'),
    )


def _avaliar(pedido, payload):
    api = APIClient()
    return api.post(
        f'/api/v1/stores/orders/by-token/{pedido.access_token}/review/',
        payload, format='json',
    )


@pytest.mark.django_db
class TestPilares:
    def test_grava_os_tres_pilares(self, loja):
        pedido = _pedido(loja)
        r = _avaliar(pedido, {
            'rating': 4,
            'rating_comida': 5,
            'rating_entrega': 3,
            'rating_atendimento': 4,
            'comment': 'Comida ótima, entrega demorou',
        })
        assert r.status_code == 201, r.content

        review = StoreReview.objects.get(order=pedido)
        assert review.rating_comida == 5
        assert review.rating_entrega == 3
        assert review.rating_atendimento == 4

    def test_avaliacao_so_com_nota_geral_continua_valendo(self, loja):
        # O fluxo antigo não pode quebrar: exigir três notas derruba a taxa de
        # resposta, e resposta é o recurso mais escasso de uma loja com 4
        # avaliações.
        pedido = _pedido(loja)
        r = _avaliar(pedido, {'rating': 5})
        assert r.status_code == 201, r.content

        review = StoreReview.objects.get(order=pedido)
        assert review.rating == 5
        assert review.rating_comida is None

    def test_sem_nota_geral_ela_vem_da_media_dos_pilares(self, loja):
        # Senão a loja teria duas médias diferentes na mesma tela: a de
        # `rating` (vazia) e a dos pilares.
        pedido = _pedido(loja)
        r = _avaliar(pedido, {'rating_comida': 5, 'rating_entrega': 4, 'rating_atendimento': 3})
        assert r.status_code == 201, r.content

        review = StoreReview.objects.get(order=pedido)
        assert review.rating == 4  # (5+4+3)/3

    def test_arredonda_a_geral_derivada_para_cima_no_meio(self, loja):
        # 4,5 vira 5 e não 4: arredondar para baixo pune uma avaliação que o
        # cliente deu como boa.
        pedido = _pedido(loja)
        _avaliar(pedido, {'rating_comida': 5, 'rating_entrega': 4})
        assert StoreReview.objects.get(order=pedido).rating == 5

    def test_avaliacao_sem_nota_nenhuma_e_recusada(self, loja):
        # Comentário sem nota não vira avaliação: a média da loja é o que essa
        # tela alimenta.
        pedido = _pedido(loja)
        r = _avaliar(pedido, {'comment': 'só passando para elogiar'})
        assert r.status_code == 400

    def test_retirada_no_balcao_recusa_pilar_de_entrega(self, loja):
        # Quem buscou o pedido não tem o que avaliar em "entrega". Aceitar a
        # nota produziria média inventada num pilar que existe para orientar
        # decisão (contratar entregador ou não).
        pedido = _pedido(loja, metodo='pickup')
        r = _avaliar(pedido, {'rating': 5, 'rating_entrega': 1})
        assert r.status_code == 400
        assert 'entrega' in str(r.content).lower()

    def test_nota_fora_da_escala_e_recusada(self, loja):
        pedido = _pedido(loja)
        assert _avaliar(pedido, {'rating': 5, 'rating_comida': 9}).status_code == 400
        assert _avaliar(pedido, {'rating': 5, 'rating_comida': 0}).status_code == 400


@pytest.mark.django_db
class TestRelatorioPorPilar:
    def _relatorio(self, loja):
        api = APIClient()
        api.force_authenticate(user=loja.owner)
        r = api.get('/api/v1/stores/reports/reviews/', {'store': loja.slug})
        assert r.status_code == 200, r.content
        return r.json()

    def test_media_de_cada_pilar_com_seu_proprio_volume(self, loja):
        # O volume por pilar é diferente: quem retira não avalia entrega, e os
        # pilares são opcionais. Mostrar "4,2" sem dizer sobre quantas notas
        # repete o problema que a nota geral já tinha.
        _avaliar(_pedido(loja), {'rating_comida': 5, 'rating_entrega': 3, 'rating_atendimento': 5})
        _avaliar(_pedido(loja), {'rating_comida': 3, 'rating_atendimento': 5})

        d = self._relatorio(loja)
        pilares = {p['chave']: p for p in d['pilares']}
        assert pilares['comida']['media'] == 4.0
        assert pilares['comida']['total'] == 2
        assert pilares['entrega']['total'] == 1

    def test_pilar_sem_nenhuma_nota_aparece_vazio_em_vez_de_zero(self, loja):
        # "Entrega 0,0" leria como serviço péssimo; a verdade é que ninguém
        # avaliou esse pilar ainda.
        _avaliar(_pedido(loja), {'rating_comida': 5})

        d = self._relatorio(loja)
        entrega = next(p for p in d['pilares'] if p['chave'] == 'entrega')
        assert entrega['media'] is None
        assert entrega['total'] == 0

    def test_o_pior_pilar_vem_identificado(self, loja):
        # É a única informação que vira ação direta: "a entrega é o seu ponto
        # fraco" diz o que atacar primeiro.
        _avaliar(_pedido(loja), {'rating_comida': 5, 'rating_entrega': 2, 'rating_atendimento': 5})

        d = self._relatorio(loja)
        assert d['pior_pilar'] == 'entrega'

    def test_sem_pilares_nao_elege_pior(self, loja):
        _avaliar(_pedido(loja), {'rating': 5})
        assert self._relatorio(loja)['pior_pilar'] is None
