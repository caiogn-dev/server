"""O resumo dos vigias também por e-mail ("Receber no e-mail", do Prefiro).

O WhatsApp corta em 3 itens e depende da janela de 24 h ou do modelo
aprovado; o e-mail leva TODOS os avisos do turno e chega sempre. É cópia:
falhar aqui não muda o status do envio pelo WhatsApp.
"""
from __future__ import annotations

import logging
from html import escape

from apps.stores.vigias.regras import dia_curto

logger = logging.getLogger(__name__)


def compor(loja, turno: str, dia, avisos) -> tuple[str, str, str]:
    """(assunto, html, texto)."""
    assunto = (f'Alerta da {loja.name}' if turno == 'alerta'
               else f'Vigia da {loja.name} — {dia_curto(dia)}')
    itens_html = ''.join(
        f'<li style="margin:0 0 10px"><strong>{escape(a.titulo)}</strong><br>{escape(a.texto)}</li>'
        for a in avisos
    )
    html = (
        f'<div style="font-family:system-ui,sans-serif;max-width:560px;color:#1f231e">'
        f'<h2 style="font-size:18px;margin:0 0 12px">{escape(assunto)}</h2>'
        f'<ul style="padding-left:18px;margin:0">{itens_html}</ul>'
        f'<p style="color:#6b6f6a;font-size:12px;margin-top:20px">'
        f'Para parar, desligue o e-mail em Vigias, no painel.</p></div>'
    )
    texto = '\n'.join([assunto, ''] + [f'• {a.titulo}: {a.texto}' for a in avisos])
    return assunto, html, texto


def enviar(loja, email: str, turno: str, dia, avisos) -> bool:
    if not email or not avisos:
        return False
    from apps.notifications.services.email_service import EmailService

    assunto, html, texto = compor(loja, turno, dia, avisos)
    try:
        resultado = EmailService().send_email(to=email, subject=assunto, html=html, text=texto)
    except Exception:  # noqa: BLE001 — cópia por e-mail nunca derruba o turno
        logger.exception('[vigia] e-mail falhou na loja %s', loja.id)
        return False
    return bool(resultado.get('success'))
