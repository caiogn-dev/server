"""
Entregadores da loja e ranking da operação (do admin do Prefiro).

Entregador: cadastrado pela loja, atribuído no pedido. Atendente: quem lançou
o pedido no painel (`created_by_staff`). Cancelado não conta; o faturado do
atendente é sem frete.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Entregador, StoreOrder
from apps.stores.services.ranking_da_operacao import ranking_da_operacao
from apps.stores.tests.factories import make_store

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja():
    return make_store()


def _pedido(loja, **campos):
    dados = {
        'customer_name': 'C', 'customer_phone': '5563900000000',
        'total': Decimal('60'), 'subtotal': Decimal('50'), 'delivery_fee': Decimal('10'),
        'status': 'delivered', 'payment_status': 'paid', 'delivery_method': 'delivery', **campos,
    }
    return StoreOrder.objects.create(store=loja, **dados)


def _api(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


class TestRanking:
    def test_entregador_conta_entregas_frete_e_tempo(self, loja):
        joao = Entregador.objects.create(store=loja, nome='João')
        saiu = timezone.now() - timedelta(hours=2)
        _pedido(loja, entregador=joao, out_for_delivery_at=saiu, delivered_at=saiu + timedelta(minutes=20))
        _pedido(loja, entregador=joao, out_for_delivery_at=saiu, delivered_at=saiu + timedelta(minutes=30))
        _pedido(loja, entregador=joao, status='cancelled')
        _pedido(loja)  # entrega sem entregador

        r = ranking_da_operacao(loja, dias=30)

        assert r['entregadores'] == [
            {'id': str(joao.id), 'nome': 'João', 'entregas': 2, 'frete': 20.0, 'minutos_medios': 25},
        ]
        assert r['sem_entregador'] == 1

    def test_atendente_conta_pedidos_lancados_sem_frete(self, loja):
        ana = User.objects.create_user(username='ana-atende', first_name='Ana', password='x')
        _pedido(loja, created_by_staff=ana)
        _pedido(loja, created_by_staff=ana)

        assert ranking_da_operacao(loja)['atendentes'][0] == {'id': ana.id, 'nome': 'Ana', 'pedidos': 2, 'faturado': 100.0}

    def test_equipe_aparece_mesmo_sem_pedido(self, loja):
        """Dono cadastrou o colaborador e o quadro dizia 'nenhum' (22/10): a
        equipe inteira aparece, com zero até lançar o primeiro pedido."""
        from apps.stores.models import StoreTeamMember
        bia = User.objects.create_user(username='bia-equipe', first_name='Bia', password='x')
        StoreTeamMember.objects.create(tenant=loja, user=bia)
        saiu = User.objects.create_user(username='saiu-equipe', first_name='Saiu', password='x')
        StoreTeamMember.objects.create(tenant=loja, user=saiu, is_active=False)

        nomes = {a['nome']: a for a in ranking_da_operacao(loja)['atendentes']}
        assert nomes['Bia'] == {'id': bia.id, 'nome': 'Bia', 'pedidos': 0, 'faturado': 0.0}
        assert loja.owner.id in {a['id'] for a in nomes.values()}
        assert 'Saiu' not in nomes


class TestApi:
    def test_cadastra_atribui_e_ve_no_pedido(self, loja):
        api = _api(loja.owner)
        r = api.post(f'/api/v1/stores/{loja.slug}/entregadores/', {'nome': ' Carlos ', 'telefone': '63999'}, format='json')
        assert r.status_code == 201, r.content
        assert r.data['nome'] == 'Carlos'
        pedido = _pedido(loja)

        r = api.post(f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/', {'entregador': r.data['id']}, format='json')
        assert r.status_code == 200, r.content
        assert r.data['entregador_nome'] == 'Carlos'
        pedido.refresh_from_db()
        assert pedido.entregador.nome == 'Carlos'

        r = api.post(f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/', {'entregador': None}, format='json')
        pedido.refresh_from_db()
        assert pedido.entregador is None

    def test_entregador_de_outra_loja_nao_entra(self, loja):
        outra = make_store()
        alheio = Entregador.objects.create(store=outra, nome='Vizinho')
        pedido = _pedido(loja)
        r = _api(loja.owner).post(
            f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/', {'entregador': str(alheio.id)}, format='json',
        )
        assert r.status_code == 404

    def test_loja_alheia_responde_nao_encontrada(self, loja):
        vizinho = User.objects.create_user(username='vizinho-rk', password='x')
        assert _api(vizinho).get(f'/api/v1/stores/{loja.slug}/ranking/').status_code == 404
        assert _api(vizinho).get(f'/api/v1/stores/{loja.slug}/entregadores/').status_code == 404

    def test_ranking_pela_api(self, loja):
        r = _api(loja.owner).get(f'/api/v1/stores/{loja.slug}/ranking/?dias=7')
        assert r.status_code == 200
        assert r.data['dias'] == 7
