"""Campanha de comentário: quem comenta na publicação recebe DM da loja.

É o produto que a loja vende no Instagram — "comente CUPOM e receba", "marque
2 amigos e concorra". A Meta deixa responder UMA vez no privado por comentário,
até 7 dias; por isso cada comentário vira UMA participação e UMA DM, e falha de
envio não pode apagar quem participou.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.instagram.campanhas import comentarios, regras, sorteio
from apps.instagram.models import (
    CampanhaDeComentario,
    InstagramAccount,
    ParticipacaoNoComentario,
)

MEDIA = 'media-1'


@pytest.fixture
def conta(db):
    user = get_user_model().objects.create_user(username='lojista-camp', password='x')
    return InstagramAccount.objects.create(
        user=user, username='loja', instagram_business_id='ig-1', access_token='t',
    )


@pytest.fixture
def campanha(conta):
    return CampanhaDeComentario.objects.create(
        account=conta, nome='Cupom de setembro', media_id=MEDIA,
        palavra_chave='EU QUERO', mensagem_dm='Seu cupom: SET10',
    )


def comentario(texto='eu quero', usuario='u1', username='cliente', comment_id='c1'):
    return {
        'id': comment_id,
        'text': texto,
        'media': {'id': MEDIA},
        'from': {'id': usuario, 'username': username},
    }


@pytest.fixture
def canal():
    with patch.object(comentarios, 'canal') as c:
        c.responder_no_privado.return_value = True
        c.responder_em_publico.return_value = True
        c.segue_a_loja.return_value = True
        yield c


# ── regras puras ──────────────────────────────────────────────────────────────

def test_palavra_chave_ignora_acento_e_caixa():
    assert regras.tem_a_palavra('Eu Quero!!', 'eu querô')
    assert not regras.tem_a_palavra('quero não', 'eu quero')


def test_conta_marcacoes_distintas_sem_a_propria_loja():
    assert regras.contar_marcacoes('@ana @bia @ana @loja', propria='loja') == 2


# ── o caminho do comentário ───────────────────────────────────────────────────

def test_comentario_valido_vira_participacao_e_dm(conta, campanha, canal):
    comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    p = ParticipacaoNoComentario.objects.get(campanha=campanha)
    assert p.aceita and p.dm_enviada and p.username == 'cliente'
    canal.responder_no_privado.assert_called_once()
    assert 'SET10' in canal.responder_no_privado.call_args.kwargs['texto']


def test_sem_a_palavra_chave_nao_recebe_dm(conta, campanha, canal):
    comentarios.processar_comentario(conta, comentario(texto='que legal'), api=MagicMock())

    p = ParticipacaoNoComentario.objects.get(campanha=campanha)
    assert not p.aceita and p.motivo == regras.SEM_PALAVRA
    canal.responder_no_privado.assert_not_called()


def test_marcar_amigos_de_menos_nao_participa(conta, campanha, canal):
    campanha.exige_marcar_amigos = 2
    campanha.save(update_fields=['exige_marcar_amigos'])

    comentarios.processar_comentario(conta, comentario(texto='eu quero @ana'), api=MagicMock())

    p = ParticipacaoNoComentario.objects.get(campanha=campanha)
    assert not p.aceita and p.motivo == regras.POUCOS_AMIGOS
    canal.responder_no_privado.assert_not_called()


def test_mesma_pessoa_comentando_de_novo_nao_ganha_segunda_dm(conta, campanha, canal):
    comentarios.processar_comentario(conta, comentario(comment_id='c1'), api=MagicMock())
    comentarios.processar_comentario(conta, comentario(comment_id='c2'), api=MagicMock())

    assert canal.responder_no_privado.call_count == 1
    segunda = ParticipacaoNoComentario.objects.get(comment_id='c2')
    assert not segunda.aceita and segunda.motivo == regras.JA_PARTICIPOU


def test_o_mesmo_comentario_chegando_duas_vezes_nao_duplica(conta, campanha, canal):
    for _ in range(2):
        comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    assert ParticipacaoNoComentario.objects.count() == 1
    assert canal.responder_no_privado.call_count == 1


def test_comentario_da_propria_loja_e_ignorado(conta, campanha, canal):
    comentarios.processar_comentario(
        conta, comentario(usuario='ig-1', username='loja'), api=MagicMock(),
    )

    assert not ParticipacaoNoComentario.objects.exists()
    canal.responder_no_privado.assert_not_called()


def test_campanha_encerrada_nao_responde(conta, campanha, canal):
    campanha.termina_em = timezone.now() - timedelta(hours=1)
    campanha.save(update_fields=['termina_em'])

    comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    assert not ParticipacaoNoComentario.objects.exists()
    canal.responder_no_privado.assert_not_called()


def test_dm_que_falha_nao_apaga_a_participacao(conta, campanha, canal):
    canal.responder_no_privado.side_effect = RuntimeError('janela fechada')

    comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    p = ParticipacaoNoComentario.objects.get(campanha=campanha)
    assert p.aceita and not p.dm_enviada and p.erro_da_dm


def test_resposta_publica_sai_quando_configurada(conta, campanha, canal):
    campanha.resposta_publica = 'Te mandei no direct!'
    campanha.save(update_fields=['resposta_publica'])

    comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    canal.responder_em_publico.assert_called_once()


def test_exige_seguir_so_valida_depois_da_dm(conta, campanha, canal):
    campanha.exige_seguir = True
    campanha.save(update_fields=['exige_seguir'])
    canal.segue_a_loja.return_value = False

    comentarios.processar_comentario(conta, comentario(), api=MagicMock())

    p = ParticipacaoNoComentario.objects.get(campanha=campanha)
    assert p.dm_enviada, 'a DM é o único jeito de saber se a pessoa segue'
    assert not p.aceita and p.motivo == regras.NAO_SEGUE


# ── sorteio ───────────────────────────────────────────────────────────────────

def _participar(campanha, quantos, aceita=True):
    marca = 'ok' if aceita else 'no'
    for i in range(quantos):
        ParticipacaoNoComentario.objects.create(
            campanha=campanha, comment_id=f'c-{marca}-{i}', usuario_id=f'u-{marca}-{i}',
            username=f'p{i}', aceita=aceita,
        )


def test_sorteio_so_pega_quem_esta_valendo(conta, campanha):
    _participar(campanha, 3)
    _participar(campanha, 2, aceita=False)

    ganhadores = sorteio.sortear(campanha, quantidade=2)

    assert len(ganhadores) == 2
    assert all(g.aceita for g in ganhadores)
    assert ParticipacaoNoComentario.objects.filter(ganhador=True).count() == 2


def test_sorteio_nao_repete_quem_ja_ganhou(conta, campanha):
    _participar(campanha, 2)
    primeiro = sorteio.sortear(campanha, quantidade=1)[0]

    segundo = sorteio.sortear(campanha, quantidade=1)[0]

    assert segundo.id != primeiro.id


def test_sorteio_sem_gente_devolve_vazio(conta, campanha):
    assert sorteio.sortear(campanha, quantidade=1) == []


# ── o webhook de verdade ──────────────────────────────────────────────────────

def test_webhook_de_comentario_aciona_a_campanha(conta, campanha, canal):
    from apps.instagram.services.instagram_webhook_service import InstagramWebhookService

    payload = {
        'object': 'instagram',
        'entry': [{
            'id': conta.instagram_business_id,
            'changes': [{'field': 'comments', 'value': comentario()}],
        }],
    }

    InstagramWebhookService().process_webhook(payload)

    assert ParticipacaoNoComentario.objects.filter(campanha=campanha, aceita=True).exists()
