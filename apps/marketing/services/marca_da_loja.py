"""A identidade que vai no e-mail é a da LOJA, não a da plataforma.

Existe porque em 10/ago uma campanha real da Cê Saladas saiu assinada
`Pastita <contato@pastita.com.br>`, com botão para `pastita.com.br/cardapio`, na
paleta vinho da Pastita antiga e rodapé "Massas Artesanais" — numa loja de
saladas, para 39 pessoas. Nada disso precisava ser inventado: nome, tagline,
logo e as duas cores já estavam no `Store` e eram simplesmente ignorados.

⚠️ O ENDEREÇO do remetente é o do domínio verificado no Resend, hoje
`cardapidex.com.br` (`GET /domains`). O NOME exibido é o da loja. Enviar de um
domínio não verificado não é "menos bonito", é entrega falhando com
`domain is not verified` — aconteceu em 11/ago, entre trocar o domínio no Resend
e o código saber disso.

Loja com domínio próprio pode enviar do endereço dela (`email_remetente`), mas
só depois de `remetente_verificado` — ver `_remetente`.
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

#: Remetente da plataforma. FONTE ÚNICA — este endereço já esteve escrito à mão
#: em três arquivos, e quando o dono trocou o domínio verificado no Resend
#: (pastita.com.br → cardapidex.com.br) o envio caiu inteiro porque nenhum dos
#: três sabia da troca. A env continua mandando: trocar de domínio de novo não
#: pode exigir deploy.
REMETENTE_DA_PLATAFORMA = os.getenv('RESEND_FROM_EMAIL', 'contato@cardapidex.com.br')
NOME_DA_PLATAFORMA = os.getenv('RESEND_FROM_NAME', 'Cardapidex')

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
    from_email = REMETENTE_DA_PLATAFORMA
    plataforma = NOME_DA_PLATAFORMA

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

    logo = _logo_absoluta(store)

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
        'from_email': _remetente(store, from_email),
        'reply_to': _reply_to(store, _remetente(store, from_email)),
    }


def _remetente(store, padrao_da_plataforma: str) -> str:
    """De qual endereço a loja envia.

    Padrão: o domínio da plataforma, com o NOME da loja — é o que serve todas
    as lojas, inclusive as que nunca terão domínio próprio.

    A loja só envia do endereço dela quando alguém confirmou que o domínio está
    verificado no provedor. Endereço em domínio não verificado não é "menos
    bonito": é todo envio daquela loja falhando, sem erro visível para ela.
    """
    proprio = (getattr(store, 'email_remetente', '') or '').strip()
    if proprio and getattr(store, 'remetente_verificado', False):
        return proprio
    return padrao_da_plataforma


def _logo_absoluta(store) -> str:
    """Endereço completo da logo.

    `store.logo.url` devolve `/media/...`, que só resolve para quem está
    navegando no domínio do backend. Num e-mail aberto no Gmail aquilo é caminho
    para lugar nenhum — foi por isso que a logo não apareceu no primeiro teste
    real. O arquivo já era público; faltava o host.
    """
    logo = (getattr(store, 'logo_url', '') or '').strip()
    if not logo and getattr(store, 'logo', None):
        try:
            logo = store.logo.url
        except Exception:  # pragma: no cover - storage ausente
            return ''
    if not logo:
        return ''
    if logo.startswith(('http://', 'https://')):
        return logo
    from django.conf import settings

    base = (getattr(settings, 'BASE_URL', '') or '').rstrip('/')
    return f'{base}{logo}' if base else ''


def _reply_to(store, from_email: str) -> str:
    """Para onde volta a resposta do cliente.

    O remetente é uma caixa que existe só para ENVIAR: o Resend exige o domínio
    verificado, não o mailbox. `contato@cardapidex.com.br` não é lido por
    ninguém: o MX que o Resend pede fica em `send.cardapidex.com.br` e serve só
    para bounce do SES — a raiz não recebe nada, então a resposta do cliente nem
    bounce gera, evapora.

    Ordem: e-mail cadastrado da loja → e-mail do dono. Nunca o próprio
    remetente, que equivale a não ter reply_to.
    """
    candidatos = [
        (getattr(store, 'email', '') or '').strip(),
        (getattr(getattr(store, 'owner', None), 'email', '') or '').strip(),
    ]
    for candidato in candidatos:
        if candidato and candidato.lower() != (from_email or '').lower():
            return candidato
    return ''


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
