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
import io
import logging

import os

from PIL import Image

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

    logo = logo_para_email(store)

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


#: Lado maior da logo dentro do e-mail. 480 px cobre tela retina exibindo a
#: 240 px, e nada além disso é visto por ninguém.
_LADO_MAXIMO_DA_LOGO = 480


def logo_para_email(store) -> str:
    """URL de uma versão leve da logo, gerada uma vez e reaproveitada.

    A logo da Cê Saladas é 3531×3905 px e 698 KB — para ser exibida com 48 px de
    altura. É o mesmo arquivo que causou o problema de LCP no site. Num e-mail é
    pior: pesa na abertura e imagem grande conta ponto contra em filtro de spam.

    Se a geração falhar por qualquer motivo, devolve a original: e-mail com logo
    pesada é ruim, e-mail que não sai é pior.
    """
    original = _logo_absoluta(store)
    if not original:
        return ''

    arquivo = getattr(store, 'logo', None)
    if not arquivo or not getattr(arquivo, 'name', ''):
        return original

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    nome = arquivo.name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    destino = f'stores/logos/email/{nome}-{_LADO_MAXIMO_DA_LOGO}.jpg'

    try:
        if not default_storage.exists(destino):
            with arquivo.open('rb') as fh:
                imagem = Image.open(fh)
                imagem = imagem.convert('RGB')
                imagem.thumbnail(
                    (_LADO_MAXIMO_DA_LOGO, _LADO_MAXIMO_DA_LOGO), Image.LANCZOS,
                )
                buffer = io.BytesIO()
                imagem.save(buffer, format='JPEG', quality=82, optimize=True)
            default_storage.save(destino, ContentFile(buffer.getvalue()))
    except Exception as exc:
        logger.warning('[marca] Não consegui gerar a logo de e-mail: %s', exc)
        return original

    from django.conf import settings

    base = (getattr(settings, 'BASE_URL', '') or '').rstrip('/')
    media = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/')
    return f'{base}{media}{destino}'


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

    # A logo vai numa FAIXA BRANCA, não em cima da cor da loja. Logo de lojista
    # costuma vir com fundo próprio chapado (a da Cê Saladas é um quadrado
    # laranja inteiro) — sobreposta a um degradê verde, vira um bloco recortado.
    # Branco funciona com qualquer logo, com ou sem transparência.
    faixa_da_logo = (
        f'<tr><td style="background-color:#ffffff;padding:24px 20px 20px;text-align:center;">'
        f'<img src="{logo}" alt="{nome}" width="120" '
        f'style="width:120px;max-width:60%;height:auto;display:inline-block;border:0;">'
        f'</td></tr>'
        if logo else ''
    )
    # Sem logo o nome da loja assume o topo, senão o e-mail abre sem identidade.
    cabecalho = '' if logo else f'<h1 style="color:#ffffff;margin:0;font-size:28px;">{nome}</h1>'
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
    {faixa_da_logo}
    <tr>
      <td style="background-color:{primaria};padding:32px 20px;text-align:center;">
        {cabecalho}
        <h1 style="color:#ffffff;margin:0;font-size:26px;line-height:1.3;">{titulo}</h1>
      </td>
    </tr>
    <tr><td style="height:4px;background-color:{secundaria};font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:40px 30px;">{corpo}{botao}</td></tr>
    <tr>
      <td style="background-color:#f9f9f9;padding:30px;text-align:center;">
        <p style="color:#999;font-size:12px;margin:0;">{nome}{rodape_assinatura}</p>
      </td>
    </tr>
  </table>
</body>
</html>"""
