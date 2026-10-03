"""Aviso da fatura de assinatura ao dono da loja (03/10/2026).

Até aqui a fatura PIX só existia na tela de Plano: nenhum código avisava o
dono. Agora sai por e-mail em três momentos — 3 dias antes, véspera e dia do
vencimento —, cada um uma vez só (`metadata.sent_steps`).

WhatsApp fica de fora: a plataforma não tem número próprio nem modelo de
mensagem aprovado para cobrança. Conta sem e-mail real (cadastro só com
celular, '@cardapidex.local') não recebe nada por aqui.
"""
from __future__ import annotations

import logging
from html import escape
from zoneinfo import ZoneInfo

from django.conf import settings

logger = logging.getLogger(__name__)

BRT = ZoneInfo('America/Sao_Paulo')
DOMINIO_FALSO = '@cardapidex.local'

ASSUNTO = {
    'd3': 'Sua fatura Cardapidex vence em 3 dias',
    'd1': 'Sua fatura Cardapidex vence amanhã',
    'd0': 'Sua fatura Cardapidex vence hoje',
}


def passo_do_aviso(vencimento, agora) -> str:
    """'d3' (2+ dias), 'd1' (véspera) ou 'd0' (no dia ou depois), no fuso de Brasília."""
    dias = (vencimento.astimezone(BRT).date() - agora.astimezone(BRT).date()).days
    if dias >= 2:
        return 'd3'
    if dias == 1:
        return 'd1'
    return 'd0'


def email_do_dono(store) -> str:
    dono = getattr(store, 'owner', None)
    email = (getattr(dono, 'email', '') or '').strip()
    if not email or email.endswith(DOMINIO_FALSO) or '@' not in email:
        return ''
    return email


def _valor(v) -> str:
    return f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _corpo(fatura, vencimento, passo) -> str:
    loja = fatura.store
    nome = (getattr(loja.owner, 'first_name', '') or '').strip() or 'Olá'
    painel = getattr(settings, 'DASHBOARD_URL', 'https://painel.cardapidex.com.br').rstrip('/')
    quando = {'d3': f'vence em {vencimento.astimezone(BRT):%d/%m}', 'd1': 'vence amanhã', 'd0': 'vence hoje'}[passo]
    return (
        f'<p>{escape(nome)},</p>'
        f'<p>A assinatura da <strong>{escape(loja.name)}</strong> no Cardapidex {quando}.</p>'
        f'<p style="font-size:20px"><strong>R$ {_valor(fatura.amount)}</strong></p>'
        '<p>PIX copia e cola:</p>'
        f'<p style="font-family:monospace;word-break:break-all;background:#f4f4f4;padding:12px">'
        f'{escape(fatura.qr_code or "")}</p>'
        f'<p>Ou pague pelo painel: <a href="{painel}/plano">{painel}/plano</a></p>'
        '<p>Se a fatura não for paga até o vencimento, a loja volta para o plano Grátis.</p>'
    )


def _enviar_email(para: str, assunto: str, corpo_html: str) -> bool:
    from apps.marketing.services.email_marketing_service import EmailMarketingService
    from apps.marketing.services.marca_da_loja import REMETENTE_DA_PLATAFORMA

    resultado = EmailMarketingService().send_single_email(
        to_email=para, subject=assunto, html_content=corpo_html,
        from_email=REMETENTE_DA_PLATAFORMA, from_name='Cardapidex',
    )
    if not resultado.get('success'):
        logger.warning('Aviso de fatura não saiu para %s: %s', para, resultado.get('error'))
    return bool(resultado.get('success'))


def avisar(fatura, *, vencimento, agora) -> str | None:
    """Manda o aviso do passo atual se ainda não saiu. Devolve o passo enviado."""
    from apps.stores.models import StorePayment

    if fatura is None or fatura.status != StorePayment.PaymentStatus.PENDING or not vencimento:
        return None
    passo = passo_do_aviso(vencimento, agora)
    metadata = dict(fatura.metadata or {})
    enviados = list(metadata.get('sent_steps') or [])
    if passo in enviados:
        return None
    para = email_do_dono(fatura.store)
    if not para:
        return None
    if not _enviar_email(para, ASSUNTO[passo], _corpo(fatura, vencimento, passo)):
        return None
    enviados.append(passo)
    metadata['sent_steps'] = enviados
    fatura.metadata = metadata
    fatura.save(update_fields=['metadata', 'updated_at'])
    return passo
