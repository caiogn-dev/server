"""A campanha de comentário no painel do lojista.

Campanha é da CONTA de quem conectou: um lojista nunca pode ver nem sortear a
promoção de outro. O painel também precisa do placar — quantos entraram e
quantos ficaram de fora e por quê.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.instagram.models import (
    CampanhaDeComentario,
    InstagramAccount,
    ParticipacaoNoComentario,
)


def _conta(sufixo):
    user = get_user_model().objects.create_user(username=f'lojista-{sufixo}', password='x')
    conta = InstagramAccount.objects.create(
        user=user, username=f'loja{sufixo}', instagram_business_id=f'ig-{sufixo}',
        access_token='t',
    )
    return user, conta


@pytest.fixture
def cenario(db):
    dono, conta = _conta('a')
    outro, conta_do_outro = _conta('b')
    campanha = CampanhaDeComentario.objects.create(
        account=conta, nome='Cupom', media_id='m1', mensagem_dm='oi',
    )
    alheia = CampanhaDeComentario.objects.create(
        account=conta_do_outro, nome='Do vizinho', media_id='m9', mensagem_dm='oi',
    )
    return dono, outro, conta, campanha, alheia


def _cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_lojista_ve_so_as_campanhas_da_conta_dele(cenario):
    dono, _, _, campanha, alheia = cenario

    r = _cliente(dono).get('/api/v1/instagram/campanhas-de-comentario/')

    assert r.status_code == 200
    nomes = [c['nome'] for c in (r.data['results'] if 'results' in r.data else r.data)]
    assert nomes == [campanha.nome]


def test_nao_da_para_sortear_campanha_alheia(cenario):
    dono, _, _, _, alheia = cenario

    r = _cliente(dono).post(f'/api/v1/instagram/campanhas-de-comentario/{alheia.id}/sortear/')

    assert r.status_code == 404


def test_placar_mostra_quem_entrou_e_quem_ficou_de_fora(cenario):
    _, _, _, campanha, _ = cenario
    dono = campanha.account.user
    ParticipacaoNoComentario.objects.create(
        campanha=campanha, comment_id='c1', usuario_id='u1', username='ana', aceita=True,
    )
    ParticipacaoNoComentario.objects.create(
        campanha=campanha, comment_id='c2', usuario_id='u2', username='bia',
        aceita=False, motivo='sem_palavra',
    )

    r = _cliente(dono).get(f'/api/v1/instagram/campanhas-de-comentario/{campanha.id}/placar/')

    assert r.status_code == 200
    assert r.data['participando'] == 1
    assert r.data['de_fora'] == 1
    assert r.data['motivos'][0]['motivo'] == 'não escreveu a palavra da promoção'


def test_sortear_devolve_o_ganhador(cenario):
    _, _, _, campanha, _ = cenario
    dono = campanha.account.user
    ParticipacaoNoComentario.objects.create(
        campanha=campanha, comment_id='c1', usuario_id='u1', username='ana', aceita=True,
    )

    r = _cliente(dono).post(
        f'/api/v1/instagram/campanhas-de-comentario/{campanha.id}/sortear/',
        {'quantidade': 1}, format='json',
    )

    assert r.status_code == 200
    assert r.data['ganhadores'][0]['username'] == 'ana'
