"""O único lugar que fala com a Meta numa campanha de comentário.

Resposta privada (Private Reply) é uma mensagem endereçada ao COMENTÁRIO, não
ao usuário: vale uma vez por comentário e por 7 dias. Resposta pública é um
reply no próprio comentário.
"""
import logging

logger = logging.getLogger(__name__)


def responder_no_privado(api, account, comment_id: str, texto: str) -> bool:
    """Manda a DM presa ao comentário. Levanta exceção se a Meta recusar."""
    remetente = account.facebook_page_id or account.instagram_business_id
    api.post(
        f'{remetente}/messages',
        data={'recipient': {'comment_id': comment_id}, 'message': {'text': texto}},
    )
    return True


def responder_em_publico(api, comment_id: str, texto: str) -> bool:
    api.post(f'{comment_id}/replies', data={'message': texto})
    return True


def segue_a_loja(api, usuario_id: str):
    """`is_user_follow_business` só existe depois que a pessoa manda DM.

    Devolve None quando a Meta não responde — e aí a campanha não pode punir
    quem talvez siga.
    """
    try:
        dados = api.get(usuario_id, params={'fields': 'is_user_follow_business'})
    except Exception as erro:  # pragma: no cover - rede
        logger.warning('Instagram: não deu para checar se %s segue: %s', usuario_id, erro)
        return None
    return dados.get('is_user_follow_business')
