"""Os comentários reais do post, do lado de quem entrou na promoção.

Serve ao lojista (ver o post sem sair do painel) e à Meta: a permissão
instagram_business_manage_comments exige `api_precheck` — uma chamada de
verdade à API de comentários, que o webhook sozinho não produz.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.instagram.models import (
    CampanhaDeComentario,
    InstagramAccount,
    ParticipacaoNoComentario,
)
from apps.instagram.services.instagram_api import InstagramAPIException

RESPOSTA = {
    'data': [
        {'id': 'c1', 'text': 'EU QUERO', 'username': 'ana', 'timestamp': '2026-09-21T10:00:00+0000', 'like_count': 2},
        {'id': 'c2', 'text': 'que lindo', 'username': 'bia', 'timestamp': '2026-09-21T10:05:00+0000', 'like_count': 0},
        {'id': 'c3', 'text': 'EU QUERO', 'username': 'caio', 'timestamp': '2026-09-21T10:07:00+0000', 'like_count': 0},
    ],
}


@pytest.fixture
def cenario(db):
    user = get_user_model().objects.create_user(username='dono-com', password='x')
    conta = InstagramAccount.objects.create(
        user=user, username='loja', instagram_business_id='ig-3', access_token='t',
    )
    campanha = CampanhaDeComentario.objects.create(
        account=conta, nome='Cupom', media_id='m1', palavra_chave='EU QUERO', mensagem_dm='oi',
    )
    ParticipacaoNoComentario.objects.create(
        campanha=campanha, comment_id='c1', usuario_id='u1', username='ana',
        aceita=True, dm_enviada=True,
    )
    ParticipacaoNoComentario.objects.create(
        campanha=campanha, comment_id='c2', usuario_id='u2', username='bia',
        aceita=False, motivo='sem_palavra',
    )
    return user, campanha


def _cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _pedir(user, campanha):
    return _cliente(user).get(
        f'/api/v1/instagram/campanhas-de-comentario/{campanha.id}/comentarios/'
    )


def test_comentario_mostra_o_que_aconteceu_com_cada_um(cenario):
    user, campanha = cenario

    with patch('apps.instagram.services.instagram_api.InstagramAPI.get', return_value=RESPOSTA):
        r = _pedir(user, campanha)

    assert r.status_code == 200
    por_usuario = {c['username']: c for c in r.data}
    assert por_usuario['ana']['situacao'] == 'recebeu'
    assert por_usuario['bia']['situacao'] == 'de_fora'
    assert por_usuario['bia']['motivo'] == 'não escreveu a palavra da promoção'
    # Comentário que ainda não virou participação (webhook a caminho).
    assert por_usuario['caio']['situacao'] == 'aguardando'


def test_token_recusado_pede_reconexao(cenario):
    user, campanha = cenario

    with patch(
        'apps.instagram.services.instagram_api.InstagramAPI.get',
        side_effect=InstagramAPIException('token'),
    ):
        r = _pedir(user, campanha)

    assert r.status_code == 409
    assert r.data['codigo'] == 'reconectar'


def test_promocao_de_outro_lojista_nao_abre(cenario):
    _, campanha = cenario
    vizinho = get_user_model().objects.create_user(username='vizinho-com', password='x')

    assert _pedir(vizinho, campanha).status_code == 404
