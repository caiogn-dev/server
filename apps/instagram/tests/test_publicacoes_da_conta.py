"""Escolher a publicação é ver as fotos, não digitar um código.

O primeiro desenho da promoção pedia o link do post colado à mão. Quem publica
no Instagram pelo celular não tem esse link na mão — tem a foto na cabeça.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPIException

RESPOSTA = {
    'data': [
        {
            'id': '17900000000000001',
            'caption': 'Salada nova no cardápio 🥗',
            'media_type': 'IMAGE',
            'media_url': 'https://cdn/1.jpg',
            'thumbnail_url': None,
            'permalink': 'https://instagram.com/p/AAA/',
            'timestamp': '2026-09-20T12:00:00+0000',
            'comments_count': 12,
        },
        {
            'id': '17900000000000002',
            'caption': None,
            'media_type': 'VIDEO',
            'media_url': 'https://cdn/2.mp4',
            'thumbnail_url': 'https://cdn/2.jpg',
            'permalink': 'https://instagram.com/p/BBB/',
            'timestamp': '2026-09-19T12:00:00+0000',
            'comments_count': 0,
        },
    ],
}


@pytest.fixture
def conta(db):
    user = get_user_model().objects.create_user(username='dono-pub', password='x')
    conta = InstagramAccount.objects.create(
        user=user, username='loja', instagram_business_id='ig-7', access_token='t',
    )
    return conta


def _cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_lista_as_publicacoes_prontas_para_a_grade(conta):
    with patch('apps.instagram.services.instagram_api.InstagramAPI.get', return_value=RESPOSTA):
        r = _cliente(conta.user).get(f'/api/v1/instagram/accounts/{conta.id}/publicacoes/')

    assert r.status_code == 200
    primeira = r.data[0]
    assert primeira['id'] == '17900000000000001'
    assert primeira['legenda'] == 'Salada nova no cardápio 🥗'
    assert primeira['imagem'] == 'https://cdn/1.jpg'
    assert primeira['comentarios'] == 12
    # Vídeo usa a miniatura: media_url de vídeo não renderiza em <img>.
    assert r.data[1]['imagem'] == 'https://cdn/2.jpg'


def test_token_recusado_vira_recado_de_reconectar(conta):
    with patch(
        'apps.instagram.services.instagram_api.InstagramAPI.get',
        side_effect=InstagramAPIException('Page Access Token inválido'),
    ):
        r = _cliente(conta.user).get(f'/api/v1/instagram/accounts/{conta.id}/publicacoes/')

    assert r.status_code == 409
    assert r.data['codigo'] == 'reconectar'


def test_conta_de_outro_lojista_nao_abre(conta):
    outro = get_user_model().objects.create_user(username='vizinho', password='x')

    r = _cliente(outro).get(f'/api/v1/instagram/accounts/{conta.id}/publicacoes/')

    assert r.status_code == 404
