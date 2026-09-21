"""O caminho de um comentário até a DM da loja.

Ordem importa: as regras que dá para checar no texto vêm primeiro, porque
comentário recusado não pode consumir a única resposta privada permitida. Já
"segue a loja?" só existe DEPOIS da DM — a Meta só conta como seguidor quem
tem conversa aberta —, então nesse caso a DM sai e a validação vem atrás.
"""
import logging
from typing import Dict, Optional

from django.db import IntegrityError, transaction

from apps.instagram.models import CampanhaDeComentario, ParticipacaoNoComentario

from . import canal, regras

logger = logging.getLogger(__name__)


def campanhas_no_ar(account, media_id: str):
    return [
        c for c in CampanhaDeComentario.objects.filter(
            account=account, media_id=media_id, ativa=True,
        )
        if c.esta_no_ar()
    ]


def _e_da_propria_loja(account, usuario_id: str, username: str) -> bool:
    return usuario_id in {account.instagram_business_id, account.facebook_page_id} or (
        username and username.lower() == (account.username or '').lower()
    )


def processar_comentario(account, valor: Dict, api=None) -> Optional[ParticipacaoNoComentario]:
    """Trata um evento `comments` do webhook. Devolve a participação criada."""
    media_id = (valor.get('media') or {}).get('id') or valor.get('media_id') or ''
    comment_id = valor.get('id')
    autor = valor.get('from') or {}
    usuario_id = autor.get('id') or ''
    username = autor.get('username') or ''
    texto = valor.get('text') or ''

    if not comment_id or _e_da_propria_loja(account, usuario_id, username):
        return None

    campanhas = campanhas_no_ar(account, media_id)
    if not campanhas:
        return None
    campanha = campanhas[0]

    if ParticipacaoNoComentario.objects.filter(
        campanha=campanha, comment_id=comment_id,
    ).exists():
        return None

    marcados = regras.contar_marcacoes(texto, propria=account.username)
    motivo = ''
    if not regras.tem_a_palavra(texto, campanha.palavra_chave):
        motivo = regras.SEM_PALAVRA
    elif marcados < campanha.exige_marcar_amigos:
        motivo = regras.POUCOS_AMIGOS
    elif ParticipacaoNoComentario.objects.filter(
        campanha=campanha, usuario_id=usuario_id, aceita=True,
    ).exists():
        motivo = regras.JA_PARTICIPOU

    try:
        with transaction.atomic():
            participacao = ParticipacaoNoComentario.objects.create(
                campanha=campanha, comment_id=comment_id, usuario_id=usuario_id,
                username=username, texto=texto, amigos_marcados=marcados,
                aceita=not motivo, motivo=motivo,
            )
    except IntegrityError:
        # O mesmo comentário chegando duas vezes: a Meta reenvia webhook.
        return None

    if motivo:
        return participacao

    api = api or _api(account)
    _responder(api, account, campanha, participacao)

    if campanha.exige_seguir and participacao.dm_enviada:
        segue = canal.segue_a_loja(api, participacao.usuario_id)
        if segue is False:
            participacao.aceita = False
            participacao.motivo = regras.NAO_SEGUE
            participacao.save(update_fields=['aceita', 'motivo'])

    return participacao


def _responder(api, account, campanha, participacao) -> None:
    """A DM é o prêmio; se ela falhar, a participação continua valendo."""
    try:
        canal.responder_no_privado(
            api, account, comment_id=participacao.comment_id, texto=campanha.mensagem_dm,
        )
        participacao.dm_enviada = True
    except Exception as erro:
        participacao.erro_da_dm = str(erro)[:200]
        logger.warning(
            'Instagram: DM da campanha %s falhou para %s: %s',
            campanha.nome, participacao.username, erro,
        )
    participacao.save(update_fields=['dm_enviada', 'erro_da_dm'])

    if campanha.resposta_publica:
        try:
            canal.responder_em_publico(
                api, comment_id=participacao.comment_id, texto=campanha.resposta_publica,
            )
        except Exception as erro:  # pragma: no cover - rede
            logger.warning('Instagram: resposta pública falhou: %s', erro)


def _api(account):
    from apps.instagram.services.instagram_api import InstagramAPI

    return InstagramAPI(account)
