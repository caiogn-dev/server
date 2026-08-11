"""A identidade que vai no e-mail é a da LOJA, não a da plataforma.

Existe porque em 10/ago uma campanha real da Cê Saladas saiu assinada
`Pastita <contato@pastita.com.br>`, com botão para `pastita.com.br/cardapio`, na
paleta vinho da Pastita antiga e rodapé "Massas Artesanais" — numa loja de
saladas, para 39 pessoas. Nada disso precisava ser inventado: nome, tagline,
logo e as duas cores já estavam no `Store` e eram simplesmente ignorados.

⚠️ O ENDEREÇO do remetente continua em `@pastita.com.br`: é o único domínio
verificado no Resend (`GET /domains`). Enviar de um domínio não verificado não é
"menos bonito", é entrega falhando. Quando `cardapidex.com.br` for verificado
lá, basta mexer em `RESEND_FROM_EMAIL` — nada aqui muda.
"""
import logging

import os

logger = logging.getLogger(__name__)

#: Sufixos que o PRÓPRIO sistema inventa para cliente sem e-mail (WhatsApp,
#: balcão). Não são caixas de verdade: mandar para lá não entrega nada e cada
#: bounce corrói a reputação do domínio no Resend.
ENDERECOS_FALSOS = (
    '@local.invalid',
    '@whatsapp.bot',
    '@cliente.pastita.com.br',
    '@pastita.local',
)

_COR_PRIMARIA_PADRAO = '#1f2937'
_COR_SECUNDARIA_PADRAO = '#6b7280'


def _endereco_e_falso(email: str) -> bool:
    email = (email or '').strip().lower()
    return not email or email.endswith(ENDERECOS_FALSOS)


def contatos_reais(destinatarios):
    """Filtra os endereços inventados pelo sistema.

    Aceita strings ou objetos com `.email` (Subscriber, EmailRecipient), porque
    os dois caminhos existem no envio de campanha.
    """
    if not destinatarios:
        return []
    saida = []
    for item in destinatarios:
        email = item if isinstance(item, str) else getattr(item, 'email', '')
        if not _endereco_e_falso(email):
            saida.append(item)
    return saida


def marca_da_loja(store) -> dict:
    """Identidade visual e de remetente para um e-mail desta loja."""
    from_email = os.getenv('RESEND_FROM_EMAIL', 'contato@pastita.com.br')
    plataforma = os.getenv('RESEND_FROM_NAME', 'Cardapidex')

    if store is None:
        return {
            'nome': plataforma,
            'url': '',
            'assinatura': '',
            'logo_url': '',
            'cor_primaria': _COR_PRIMARIA_PADRAO,
            'cor_secundaria': _COR_SECUNDARIA_PADRAO,
            'from_name': plataforma,
            'from_email': from_email,
            'reply_to': '',
        }

    try:
        from apps.stores.services.checkout_service import CheckoutService

        url = CheckoutService.get_storefront_base_url(store).rstrip('/')
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning('[marca] Não consegui resolver a URL da loja: %s', exc)
        url = ''

    logo = getattr(store, 'logo_url', '') or ''
    if not logo and getattr(store, 'logo', None):
        try:
            logo = store.logo.url
        except Exception:  # pragma: no cover - storage ausente
            logo = ''

    return {
        'nome': store.name,
        'url': url,
        # Sem tagline fica VAZIO de propósito. Assinatura genérica é como
        # "Massas Artesanais" apareceu numa loja de saladas.
        'assinatura': (getattr(store, 'tagline', '') or '').strip(),
        'logo_url': logo,
        'cor_primaria': (getattr(store, 'primary_color', '') or '').strip() or _COR_PRIMARIA_PADRAO,
        'cor_secundaria': (getattr(store, 'secondary_color', '') or '').strip() or _COR_SECUNDARIA_PADRAO,
        'from_name': store.name,
        'from_email': from_email,
        'reply_to': (getattr(store, 'email', '') or '').strip(),
    }


def moldura(marca: dict, *, titulo: str, corpo: str,
            cta_texto: str = '', cta_url: str = '') -> str:
    """Casca HTML dos e-mails de marketing, pintada com a marca da loja.

    Uma só porque antes eram duas idênticas (cupom e boas-vindas), e quando a
    paleta mudou só uma foi acompanhada. Tabela e estilo inline porque cliente
    de e-mail ignora CSS externo e flexbox.
    """
    primaria = marca.get('cor_primaria') or _COR_PRIMARIA_PADRAO
    secundaria = marca.get('cor_secundaria') or _COR_SECUNDARIA_PADRAO
    nome = marca.get('nome') or ''
    assinatura = (marca.get('assinatura') or '').strip()
    logo = marca.get('logo_url') or ''

    cabecalho = (
        f'<img src="{logo}" alt="{nome}" height="48" '
        f'style="height:48px;max-width:220px;object-fit:contain;margin:0 0 12px;">'
        if logo else ''
    )
    botao = (
        f'<div style="text-align:center;margin:32px 0 0;">'
        f'<a href="{cta_url}" style="display:inline-block;background-color:{primaria};'
        f'color:#ffffff;text-decoration:none;padding:16px 40px;border-radius:8px;'
        f'font-size:16px;font-weight:bold;">{cta_texto} →</a></div>'
        if cta_texto and cta_url else ''
    )
    # Sem tagline não imprime a linha: rodapé com um <br> solto e nada embaixo
    # é o rastro de "assinatura genérica" que este módulo existe para matar.
    rodape_assinatura = f'<br>{assinatura}' if assinatura else ''

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background-color:#f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background-color:#ffffff;">
    <tr>
      <td style="background:linear-gradient(135deg,{primaria} 0%,{secundaria} 100%);padding:40px 20px;text-align:center;">
        {cabecalho}
        <h1 style="color:#ffffff;margin:0;font-size:28px;">{titulo}</h1>
      </td>
    </tr>
    <tr><td style="padding:40px 30px;">{corpo}{botao}</td></tr>
    <tr>
      <td style="background-color:#f9f9f9;padding:30px;text-align:center;">
        <p style="color:#999;font-size:12px;margin:0;">{nome}{rodape_assinatura}</p>
      </td>
    </tr>
  </table>
</body>
</html>"""
