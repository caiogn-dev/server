"""Canal único das mensagens automáticas.

Seis tarefas chamavam `WhatsAppAPIService` direto: a mensagem saía e não era
gravada — 79 lembretes/reengajamentos enviados em 30 dias, 1 visível nas
conversas do painel (19/09/2026). Aqui tudo passa pelo `MessageService`, que
grava na conversa.

`automatico=True` no metadata impede que o envio conte como "uma pessoa da
loja respondeu" (`last_agent_message_at`), que é o que a Fila humana lê.

Falha do WhatsApp: o `MessageService` grava `status=failed` e repassa a
exceção da Meta, que chega de tipos variados. O canal converte tudo em
`EnvioFalhou` — um tipo só para as tarefas decidirem o retry.
"""


import logging

logger = logging.getLogger(__name__)


class EnvioFalhou(Exception):
    """O WhatsApp recusou ou não respondeu — a tarefa deve tentar de novo."""


def _meta(evento: str, extra: dict | None = None) -> dict:
    """`extra` carrega o contexto do caminho (pedido, origem) sem repetir a
    marcação: `automatico` e `evento` são do canal e não se sobrescrevem."""
    return {**(extra or {}), 'automatico': True, 'evento': evento}


def _conferir(mensagem):
    from apps.whatsapp.models import Message

    if mensagem is None or getattr(mensagem, 'status', None) == Message.MessageStatus.FAILED:
        raise EnvioFalhou(getattr(mensagem, 'error_message', '') or 'envio falhou')
    return mensagem


def _enviar(chamada):
    try:
        mensagem = chamada()
    except EnvioFalhou:
        raise
    except Exception as exc:  # noqa: BLE001 — a Meta levanta de tudo um pouco
        raise EnvioFalhou(str(exc)) from exc
    return _conferir(mensagem)


def _calado(conta, telefone: str, evento: str) -> bool:
    """Modo humano cala a automática — ver `politica.py`."""
    from . import politica

    if politica.silenciado(conta, telefone):
        logger.info('Automática %s não saiu: conversa em modo humano.', evento)
        return True
    return False


def enviar_texto(conta, telefone: str, texto: str, evento: str, extra: dict | None = None):
    """Devolve a mensagem enviada, ou `None` quando a política calou o envio."""
    from apps.whatsapp.services.message_service import MessageService

    if _calado(conta, telefone, evento):
        return None

    # Fora da janela de 24 h o texto livre é recusado (131047). Para aviso de
    # status de pedido existe o modelo de utilidade — ver `modelo.py`.
    por_modelo = _por_modelo_se_janela_fechada(conta, telefone, evento, extra)
    if por_modelo is not None:
        return por_modelo

    return _enviar(lambda: MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto, metadata=_meta(evento, extra),
    ))


def _por_modelo_se_janela_fechada(conta, telefone: str, evento: str, extra: dict | None):
    from . import janela, modelo

    if evento not in modelo.FRASES or not modelo.modelo_aprovado(conta):
        return None
    if janela.aberta(conta, telefone):
        return None
    return _enviar(lambda: modelo.enviar_aviso_de_pedido(conta, telefone, evento, extra, _meta(evento, extra)))


def enviar_botoes(conta, telefone: str, texto: str, botoes: list, evento: str,
                  extra: dict | None = None):
    """Devolve a mensagem enviada, ou `None` quando a política calou o envio."""
    from apps.whatsapp.services.message_service import MessageService

    if _calado(conta, telefone, evento):
        return None

    return _enviar(lambda: MessageService().send_interactive_buttons(
        account_id=str(conta.id), to=telefone, body_text=texto, buttons=botoes,
        metadata=_meta(evento, extra),
    ))
