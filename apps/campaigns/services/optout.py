"""Reconhecer e registrar o pedido de "não me mande mais promoções".

INCIDENTE (28/ago/2026): oito pessoas apertaram "Parar promoções" nas campanhas
da Cê Saladas e o sistema não fazia NADA — o botão chegava como mensagem comum,
o bot respondia qualquer coisa, ninguém era marcado. Cinco delas receberam a
campanha seguinte três dias depois.

DUAS PORTAS DE ENTRADA

    botão   a Meta anexa "Parar promoções" em todo template de MARKETING e
            devolve o toque como mensagem `type: button` com o título dentro;
    texto   quem não vê o botão simplesmente escreve "PARAR" ou "SAIR".

O RECONHECIMENTO DE TEXTO É DE PROPÓSITO ESTREITO: só a mensagem INTEIRA valendo
uma frase de saída conta. Um opt-out falso é irreversível na prática — a pessoa
para de receber e nunca reclama de algo que não sabe que perdeu. Já um opt-out
que escapa custa uma mensagem a mais e o cliente repete o pedido.
"""
from __future__ import annotations

import logging
import unicodedata

from django.db import models
from typing import Optional

logger = logging.getLogger(__name__)

#: Títulos do botão que a Meta anexa aos templates de marketing. A lista é por
#: idioma porque o título vem no idioma do template, não no da conta.
BOTOES_DE_SAIDA = (
    'parar promocoes',
    'parar promocao',
    'stop promotions',
    'detener promociones',
)

#: Frases que a pessoa digita. Curtas e sem ambiguidade — comparadas contra a
#: mensagem INTEIRA, nunca com `in`.
FRASES_DE_SAIDA = (
    'parar',
    'pare',
    'sair',
    'stop',
    'cancelar',
    'descadastrar',
    'nao quero receber',
    'nao quero mais receber',
    'para de mandar',
    'remover',
)

#: A resposta precisa dizer o que PAROU e o que CONTINUA. Sem a segunda metade
#: a pessoa acha que se desligou da loja inteira e liga perguntando da entrega.
TEXTO_DE_CONFIRMACAO = (
    'Pronto! Você não vai mais receber nossas promoções. ✅\n\n'
    'As mensagens do seu pedido (confirmação, preparo e entrega) continuam '
    'chegando normalmente. Se mudar de ideia, é só mandar VOLTAR.'
)

#: Quem saiu e se arrependeu. Mesma exigência de mensagem inteira.
FRASES_DE_VOLTA = ('voltar', 'quero voltar', 'voltei')

TEXTO_DE_VOLTA = (
    'Que bom te ver de volta! 🎉 Você vai voltar a receber nossas promoções.'
)


def _normalizar(texto: Optional[str]) -> str:
    """Minúsculas, sem acento e sem pontuação de borda.

    "PARAR PROMOÇÕES", "parar promocoes" e "  Parar Promoções.  " são a mesma
    coisa para quem apertou o botão — e é o mesmo botão em telefones diferentes.
    """
    if not texto:
        return ''
    sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    )
    return sem_acento.casefold().strip(' \t\n\r.!?,;:').strip()


def eh_pedido_de_saida(texto: Optional[str], tipo: str = 'text') -> bool:
    """A mensagem é um pedido para parar de receber campanha?

    `tipo` é o `message_type` do webhook. Botão e texto têm réguas diferentes:
    o botão vem da Meta com título fixo, o texto vem de gente digitando.
    """
    normalizado = _normalizar(texto)
    if not normalizado:
        return False

    if tipo in ('button', 'interactive'):
        return normalizado in BOTOES_DE_SAIDA

    return normalizado in FRASES_DE_SAIDA


def eh_pedido_de_volta(texto: Optional[str], tipo: str = 'text') -> bool:
    """A pessoa está pedindo para voltar a receber."""
    normalizado = _normalizar(texto)
    if not normalizado:
        return False
    return normalizado in FRASES_DE_VOLTA


def registrar_saida(account, telefone: str, texto: str = '', tipo: str = 'button'):
    """Marca o telefone como fora das campanhas desta conta de WhatsApp.

    O opt-out é POR CONTA DE WHATSAPP, não por loja: a pessoa apertou "parar"
    numa mensagem que veio de um número, e é desse número que ela não quer mais
    saber. Uma conta que atende três lojas silencia as três — que é exatamente
    o que a pessoa pediu.

    Atribui a saída à campanha mais recente que mandou mensagem para ela, para
    o painel poder dizer "esta campanha custou 3 descadastros".
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.campaigns.models import Campaign, CampaignOptOut, CampaignRecipient
    from apps.campaigns.services.contatos import chave_do_telefone, telefone_para_envio

    chave = chave_do_telefone(telefone)
    if not chave:
        return None

    # A campanha culpada é a última que efetivamente enviou para esta pessoa.
    # A janela existe porque uma campanha de dois meses atrás não explica um
    # "parar" de hoje — sem ela, a primeira campanha da loja levaria a culpa
    # de todo descadastro futuro.
    limite = timezone.now() - timedelta(days=7)
    ultimo_envio = (
        CampaignRecipient.objects
        .filter(
            campaign__account=account,
            sent_at__gte=limite,
        )
        .filter(phone_number__endswith=chave[-8:])
        .order_by('-sent_at')
        .first()
    )
    campanha = ultimo_envio.campaign if ultimo_envio else None

    registro, criado = CampaignOptOut.objects.update_or_create(
        account=account,
        phone_key=chave,
        defaults={
            'phone_number': telefone_para_envio(telefone),
            'campaign': campanha,
            'origem': tipo,
            'texto_recebido': (texto or '')[:255],
            'revogado_em': None,
        },
    )

    # O contador só sobe quando a saída é NOVA. Reenviar o mesmo webhook (a
    # Meta reenvia) não pode inflar "3 descadastros" para 9.
    if criado and campanha is not None:
        Campaign.objects.filter(pk=campanha.pk).update(
            messages_opted_out=models.F('messages_opted_out') + 1
        )

    logger.info(
        'Opt-out registrado: conta=%s campanha=%s origem=%s novo=%s',
        account.id, campanha.id if campanha else None, tipo, criado,
    )
    return registro


def revogar_saida(account, telefone: str):
    """A pessoa mandou VOLTAR: reativa o envio sem apagar o histórico.

    Apagar a linha perderia a prova de que houve um pedido de oposição e quando
    ele foi atendido — que é justamente o que a LGPD manda guardar.
    """
    from django.utils import timezone

    from apps.campaigns.models import CampaignOptOut
    from apps.campaigns.services.contatos import chave_do_telefone

    chave = chave_do_telefone(telefone)
    if not chave:
        return None

    atualizadas = CampaignOptOut.objects.filter(
        account=account, phone_key=chave, revogado_em__isnull=True
    ).update(revogado_em=timezone.now())
    return atualizadas


def chaves_bloqueadas(account) -> set:
    """Telefones (forma canônica) que não podem receber campanha desta conta."""
    from apps.campaigns.models import CampaignOptOut

    return set(
        CampaignOptOut.objects
        .filter(account=account, revogado_em__isnull=True)
        .values_list('phone_key', flat=True)
    )

