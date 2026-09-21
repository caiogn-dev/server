"""A janela de 24 h vista pelo mensageiro.

A Meta só aceita texto livre dentro de 24 h da última mensagem do cliente
(erro 131047 fora disso). Quem é alvo de reengajamento — inativo há 10 a 30
dias — está sempre fora: em 21/09, 72 de 74 envios falharam por isso, e cada
falha ainda pedia retry.

O tamanho da janela mora em `apps.campaigns.services.janela`: uma cópia só.
"""
from apps.campaigns.services.janela import JANELA_HORAS

JANELA_FECHADA = '131047'


def aberta(conta, telefone: str, agora=None) -> bool:
    """A loja pode mandar texto livre para este número agora?"""
    from datetime import timedelta

    from django.utils import timezone

    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.conversations.models import Conversation

    agora = agora or timezone.now()
    limite = agora - timedelta(hours=JANELA_HORAS)
    chave = chave_do_telefone(telefone)

    for conversa in Conversation.objects.filter(
        account=conta, last_customer_message_at__gt=limite,
    ).only('phone_number', 'last_customer_message_at'):
        if chave_do_telefone(conversa.phone_number) == chave:
            return True
    return False


def e_janela_fechada(erro: Exception) -> bool:
    """131047 não é falha passageira: repetir dá o mesmo resultado."""
    return JANELA_FECHADA in str(erro)
