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


class EnvioFalhou(Exception):
    """O WhatsApp recusou ou não respondeu — a tarefa deve tentar de novo."""


def _meta(evento: str) -> dict:
    return {'automatico': True, 'evento': evento}


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


def enviar_texto(conta, telefone: str, texto: str, evento: str):
    from apps.whatsapp.services.message_service import MessageService

    return _enviar(lambda: MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto, metadata=_meta(evento),
    ))


def enviar_botoes(conta, telefone: str, texto: str, botoes: list, evento: str):
    from apps.whatsapp.services.message_service import MessageService

    return _enviar(lambda: MessageService().send_interactive_buttons(
        account_id=str(conta.id), to=telefone, body_text=texto, buttons=botoes,
        metadata=_meta(evento),
    ))
