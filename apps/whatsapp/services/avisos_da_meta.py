"""Avisos da Meta sobre a conta: template aprovado/recusado e qualidade do número.

Até 19/09 o app nem assinava esses campos e o webhook descartaria os dois. O
painel mostrava template "pendente" para sempre, e uma queda de qualidade do
número (que reduz quantas conversas a loja pode abrir por dia) passava calada.
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

CAMPO_TEMPLATE = 'message_template_status_update'
CAMPO_QUALIDADE = 'phone_number_quality_update'
CAMPOS = (CAMPO_TEMPLATE, CAMPO_QUALIDADE)

#: Estados da Meta → o que o nosso modelo sabe guardar.
_STATUS = {
    'APPROVED': 'approved',
    'REJECTED': 'rejected',
    'DISABLED': 'rejected',
    'PAUSED': 'approved',  # continua aprovado, mas a Meta suspendeu o uso
    'PENDING': 'pending',
    'IN_APPEAL': 'pending',
    'PENDING_DELETION': 'rejected',
    'DELETED': 'rejected',
}
_FORA_DE_USO = {'PAUSED', 'DISABLED', 'PENDING_DELETION', 'DELETED', 'REJECTED'}

#: Eventos de qualidade que merecem alerta (o número está perdendo limite).
_QUEDA = {'FLAGGED', 'DOWNGRADE'}


def aplicar_template(account, value: dict) -> None:
    from apps.whatsapp.models import MessageTemplate

    evento = (value.get('event') or '').upper()
    status = _STATUS.get(evento)
    template_id = str(value.get('message_template_id') or '')
    nome = value.get('message_template_name') or ''
    idioma = value.get('message_template_language') or ''

    templates = MessageTemplate.objects.filter(account__waba_id=account.waba_id)
    alvo = templates.filter(template_id=template_id) if template_id else templates.none()
    if not alvo.exists() and nome:
        alvo = templates.filter(name=nome, language=idioma)

    if status is None or not alvo.exists():
        logger.info(
            'Aviso de template sem correspondência (%s %s/%s)', evento, nome, idioma,
            extra={'account_id': str(account.id), 'template_id': template_id},
        )
        return

    alvo.update(status=status, is_active=evento not in _FORA_DE_USO, updated_at=timezone.now())
    nivel = logging.WARNING if evento in _FORA_DE_USO else logging.INFO
    logger.log(
        nivel, 'Template %s (%s): %s %s', nome, idioma, evento, value.get('reason') or '',
        extra={'account_id': str(account.id), 'template_id': template_id},
    )


def aplicar_qualidade(account, value: dict) -> None:
    evento = (value.get('event') or '').upper()
    account.metadata = {
        **(account.metadata or {}),
        'qualidade': {
            'evento': evento,
            'limite': value.get('current_limit') or '',
            'em': timezone.now().isoformat(),
        },
    }
    account.save(update_fields=['metadata', 'updated_at'])
    nivel = logging.ERROR if evento in _QUEDA else logging.INFO
    logger.log(
        nivel, 'Qualidade do número %s: %s (limite %s)',
        account.display_phone_number, evento, value.get('current_limit') or '?',
        extra={'account_id': str(account.id)},
    )
