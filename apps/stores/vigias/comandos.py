"""O dono pausa e retoma os avisos respondendo no próprio WhatsApp.

Só frases exatas, e só do telefone cadastrado no vigia. "parar" sozinho é a
palavra do cliente para sair das promoções — se virasse comando aqui, um
cliente qualquer (ou o dono pedindo salada) mexeria na configuração.
"""
from __future__ import annotations

import re
import unicodedata

from django.utils import timezone

PARAR = {'parar avisos', 'pausar avisos', 'parar aviso', 'parar vigia', 'parar vigias'}
VOLTAR = {'voltar avisos', 'retomar avisos', 'voltar aviso', 'religar avisos', 'voltar vigia', 'voltar vigias'}


def _normalizar(texto: str) -> str:
    plano = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.sub(r'[^a-z ]+', ' ', plano).split())


def responder(loja, telefone: str, texto: str):
    """A resposta ao dono, ou None quando a mensagem não é comando de vigia."""
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.stores.models import VigiaConfig

    frase = _normalizar(texto)
    if frase not in PARAR and frase not in VOLTAR:
        return None
    config = VigiaConfig.objects.filter(store=loja).first()
    if config is None or not config.telefone:
        return None
    if chave_do_telefone(telefone) != chave_do_telefone(config.telefone):
        return None

    if frase in PARAR:
        VigiaConfig.objects.filter(pk=config.pk).update(pausado_em=timezone.now())
        return ('Avisos pausados ✋. Para voltar a receber, responda VOLTAR AVISOS '
                'ou religue em Vigias no painel.')
    VigiaConfig.objects.filter(pk=config.pk).update(pausado_em=None)
    return f'Avisos de volta ✅. O próximo resumo chega às {config.hora_resumo:%H:%M} de um dia de loja aberta.'


def e_comando_do_dono(loja, telefone: str, texto: str) -> bool:
    """Sem efeito colateral: o webhook pergunta antes de calar a automação.

    O modo humano cala o bot, mas não pode calar o dono pausando os próprios
    avisos — senão "PARAR AVISOS" some justamente quando há atendente na conversa.
    """
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.stores.models import VigiaConfig

    frase = _normalizar(texto)
    if loja is None or (frase not in PARAR and frase not in VOLTAR):
        return False
    config = VigiaConfig.objects.filter(store=loja).only('telefone').first()
    return bool(config and config.telefone
                and chave_do_telefone(telefone) == chave_do_telefone(config.telefone))
