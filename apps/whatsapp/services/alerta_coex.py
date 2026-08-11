"""Aviso ativo quando a ponte de coexistência cai (ou volta).

Existe porque `logger.error` não é alerta. Em 08/ago a Cê Saladas caiu, o
sistema registrou o erro em todo envio por dois dias, e ninguém foi avisado — o
dono descobriu estranhando o silêncio, depois que um cliente já tinha ficado sem
nenhuma das 4 notificações do pedido dele.

Canal: e-mail via Resend, direto. NÃO via `django.core.mail`: o servidor roda
com `config.settings.development`, onde `EMAIL_BACKEND` é o console — mandar por
ali seria escrever no log de novo, que é exatamente o que já não funcionava.

Nunca levanta para o chamador: um alerta quebrado não pode custar o
processamento do webhook.
"""
import logging
import os

from django.conf import settings

from apps.marketing.services.marca_da_loja import REMETENTE_DA_PLATAFORMA

logger = logging.getLogger(__name__)

_ASSUNTO_QUEDA = '🔴 {loja}: WhatsApp desconectado — a loja está muda'
_ASSUNTO_VOLTA = '🟢 {loja}: WhatsApp reconectado'

_CORPO_QUEDA = """
<p><strong>A ponte de coexistência da {loja} caiu.</strong></p>
<p>Enquanto durar, <strong>todo envio falha com (#133010)</strong> — confirmação
de pedido, status, avaliação e até mensagem manual pelo painel. Mensagens que os
clientes mandarem também não chegam.</p>
<p>Número: {telefone}<br>
Motivo informado pela Meta: <code>{reason}</code><br>
Origem: <code>{source}</code></p>
<p><strong>Como resolver (só o dono consegue, ~2 min):</strong><br>
Painel → avatar no canto superior direito → Integrações → Conexões →
<em>Nova Conexão → WhatsApp → Conectar WhatsApp (oficial)</em>.<br>
Escaneie o QR que aparece no pop-up da Meta usando o celular:
<em>WhatsApp Business → Configurações → Dispositivos conectados → Conectar um
dispositivo</em>.</p>
<p>Não desinstale o WhatsApp Business do celular — em coexistência é ele que
sustenta a ponte.</p>
""".strip()

_CORPO_VOLTA = """
<p><strong>O WhatsApp da {loja} voltou.</strong></p>
<p>Número {telefone} reconectado à Cloud API. Os envios já funcionam.</p>
<p>As mensagens que falharam enquanto estava fora <strong>não são reenviadas
sozinhas</strong> — vale conferir os pedidos do período.</p>
""".strip()


def destinatarios(account) -> list:
    """E-mails que devem receber o aviso desta conta.

    Dono da loja vinculada + a lista fixa de operação, se configurada. Conta sem
    loja não é erro: existe conta de teste e conta recém-criada.
    """
    emails = []
    try:
        from apps.automation.models import CompanyProfile

        perfis = CompanyProfile.objects.filter(
            account=account, store__isnull=False,
        ).select_related('store__owner')
        for perfil in perfis:
            dono = getattr(perfil.store, 'owner', None)
            if dono and getattr(dono, 'email', ''):
                emails.append(dono.email)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning('[coex] Não consegui resolver o dono da loja: %s', exc)

    emails.extend(getattr(settings, 'COEX_ALERT_EMAILS', None) or [])
    return list(dict.fromkeys(e for e in emails if e))


def _nome_da_loja(account) -> str:
    try:
        from apps.automation.models import CompanyProfile

        perfil = CompanyProfile.objects.filter(
            account=account, store__isnull=False,
        ).select_related('store').first()
        if perfil:
            return perfil.store.name
    except Exception:  # pragma: no cover - defensivo
        pass
    return account.name or 'Loja'


def enviar_alerta(*, account, caiu: bool, reason=None, source=None) -> bool:
    """Manda o aviso. Devolve True se algum e-mail saiu.

    Assinatura só por keyword de propósito: `caiu=True/False` no meio de uma
    lista de posicionais é o tipo de argumento que se inverte sem ninguém ver.
    """
    para = destinatarios(account)
    if not para:
        logger.warning(
            '[coex] Ponte mudou de estado e não há para quem avisar',
            extra={'account_id': str(account.id), 'caiu': caiu},
        )
        return False

    loja = _nome_da_loja(account)
    contexto = {
        'loja': loja,
        'telefone': account.phone_number or account.display_phone_number or '—',
        'reason': reason or 'não informado',
        'source': source or 'não informada',
    }
    assunto = (_ASSUNTO_QUEDA if caiu else _ASSUNTO_VOLTA).format(**contexto)
    corpo = (_CORPO_QUEDA if caiu else _CORPO_VOLTA).format(**contexto)

    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        logger.error(
            '[coex] RESEND_API_KEY ausente — alerta NÃO enviado: %s', assunto,
            extra={'account_id': str(account.id)},
        )
        return False

    try:
        import resend

        resend.api_key = api_key
        resend.Emails.send({
            'from': REMETENTE_DA_PLATAFORMA,
            'to': para,
            'subject': assunto,
            'html': corpo,
        })
    except Exception as exc:
        logger.error(
            '[coex] Falha ao enviar alerta por e-mail: %s', exc,
            extra={'account_id': str(account.id), 'assunto': assunto},
        )
        return False

    logger.info(
        '[coex] Alerta enviado para %s', ', '.join(para),
        extra={'account_id': str(account.id), 'caiu': caiu},
    )
    return True
