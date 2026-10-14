"""Prazo de entrega que o CLIENTE vê (14/10).

Reclamações de demora (Matheus, 14/10) com a vitrine dizendo "~3 min": a barra
de entrega mostrava só o trajeto da rota, sem preparo. O dono quer prometer
uma faixa — "entre 30 e 45 min" — e atraso passa a ser só o que passar dela.

O prazo é dado da loja, em colunas (não no metadata): `prazo_entrega_min` e
`prazo_entrega_max`. Zero no máximo = a loja não mostra prazo.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.services import prazo_de_entrega as prazo

BRT = ZoneInfo('America/Sao_Paulo')


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-prazo', password='x')
    return Store.objects.create(owner=dono, name='Cê Prazo', slug='ce-prazo', status='active',
                                prazo_entrega_min=30, prazo_entrega_max=45)


class TestFaixa:
    def test_texto_da_faixa(self, loja):
        assert prazo.texto(loja) == '30–45 min'

    def test_sem_maximo_nao_promete_nada(self, loja):
        loja.prazo_entrega_max = 0
        assert prazo.faixa(loja) is None
        assert prazo.texto(loja) == ''

    def test_so_o_maximo_vira_ate(self, loja):
        loja.prazo_entrega_min = 0
        assert prazo.texto(loja) == 'até 45 min'

    def test_janela_em_horario_de_relogio(self, loja):
        pago = datetime(2026, 10, 14, 12, 44, tzinfo=BRT)
        assert prazo.janela(loja, pago) == '13:14 e 13:29'


@pytest.mark.django_db
class TestVitrineEPainel:
    def test_app_config_leva_a_faixa(self, loja):
        r = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/')
        assert r.status_code == 200
        assert r.json()['delivery']['prazo_de_entrega'] == {'min': 30, 'max': 45, 'texto': '30–45 min'}

    def test_app_config_sem_prazo_manda_nulo(self, loja):
        Store.objects.filter(pk=loja.pk).update(prazo_entrega_max=0)
        r = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/')
        assert r.json()['delivery']['prazo_de_entrega'] is None

    def test_painel_grava_e_recusa_faixa_invertida(self, loja):
        api = APIClient()
        api.force_authenticate(loja.owner)
        r = api.patch(f'/api/v1/stores/stores/{loja.slug}/', {'prazo_entrega_min': 50, 'prazo_entrega_max': 40},
                      format='json')
        assert r.status_code == 400
        r = api.patch(f'/api/v1/stores/stores/{loja.slug}/', {'prazo_entrega_min': 25, 'prazo_entrega_max': 40},
                      format='json')
        assert r.status_code == 200, r.content
        loja.refresh_from_db()
        assert (loja.prazo_entrega_min, loja.prazo_entrega_max) == (25, 40)
