"""Nota autorizada no e-mail do destinatário, com a marca da loja.

O dono baixava o DANFE no painel e mandava pelo próprio Gmail. Aqui a nota sai
da loja (nome dela no remetente, resposta volta para o e-mail dela) com o PDF e
o XML anexos — o XML é o que a contabilidade de quem compra precisa.
"""
import logging
from html import escape

import requests
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from apps.marketing.services.email_marketing_service import EmailMarketingService
from apps.marketing.services.marca_da_loja import marca_da_loja, moldura

from .documents import classificar, limpar
from .models import DestinatarioFiscal, FiscalDocument
from .services import documento_do_consumidor

logger = logging.getLogger(__name__)

NOME_MODELO = {FiscalDocument.Modelo.NFE: 'NF-e', FiscalDocument.Modelo.NFCE: 'NFC-e'}
# Acima disso o anexo não entra; o e-mail vai só com os links.
TAMANHO_MAXIMO_DO_ANEXO = 5 * 1024 * 1024


class EnvioInvalido(ValueError):
    """O operador consegue corrigir (nota não autorizada, e-mail errado) — 400."""


class EnvioFalhou(Exception):
    """O provedor de e-mail recusou ou está fora — 502, tentar de novo."""


def _destinatario_salvo(doc: FiscalDocument):
    _, documento = classificar(documento_do_consumidor(doc.order))
    if not documento:
        return None
    return DestinatarioFiscal.objects.filter(store=doc.store, documento=documento).first()


def email_sugerido(doc: FiscalDocument) -> str:
    """Para onde a nota iria sem ninguém digitar: o cadastro do destinatário."""
    salvo = _destinatario_salvo(doc)
    return salvo.email if salvo else ''


def _valor(total) -> str:
    inteiro, centavos = f'{total:.2f}'.split('.')
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f'R$ {".".join(grupos)},{centavos}'


def _baixar(url: str) -> bytes | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        logger.warning('nota por e-mail: arquivo não baixou (%s)', type(exc).__name__)
        return None
    if resp.status_code != 200 or not resp.content or len(resp.content) > TAMANHO_MAXIMO_DO_ANEXO:
        logger.warning('nota por e-mail: arquivo respondeu %s', resp.status_code)
        return None
    return resp.content


def _corpo(doc: FiscalDocument, nome_do_modelo: str) -> str:
    order = doc.order
    linhas = [
        ('Número', f'{doc.numero} · série {doc.serie}' if doc.numero and doc.serie else doc.numero),
        ('Pedido', order.order_number),
        ('Valor', _valor(order.total)),
        ('Chave de acesso', doc.chave_acesso),
    ]
    tabela = ''.join(
        f'<tr><td style="padding:8px 0;color:#6b7280;font-size:14px;width:140px;vertical-align:top;">{rotulo}</td>'
        f'<td style="padding:8px 0;color:#111827;font-size:14px;word-break:break-all;">{escape(str(valor))}</td></tr>'
        for rotulo, valor in linhas if valor
    )
    links = ' &nbsp;·&nbsp; '.join(
        f'<a href="{escape(url, quote=True)}" style="color:#111827;font-weight:bold;">{rotulo}</a>'
        for rotulo, url in (('Abrir DANFE', doc.danfe_url), ('Baixar XML', doc.xml_url)) if url
    )
    return (
        f'<p style="color:#374151;font-size:16px;line-height:1.6;margin:0 0 20px;">'
        f'Segue a {nome_do_modelo} da sua compra.</p>'
        f'<table width="100%" cellpadding="0" cellspacing="0">{tabela}</table>'
        + (f'<p style="margin:24px 0 0;font-size:14px;">{links}</p>' if links else '')
    )


def enviar_nota_por_email(doc: FiscalDocument, email: str = '') -> FiscalDocument:
    """Manda a nota ao destinatário e registra para quem e quando foi."""
    if doc.status != FiscalDocument.Status.AUTHORIZED:
        raise EnvioInvalido('Só a nota autorizada pode ser enviada por e-mail.')

    salvo = _destinatario_salvo(doc)
    para = (email or '').strip().lower() or (salvo.email if salvo else '')
    if not para:
        raise EnvioInvalido('Informe o e-mail do destinatário.')
    try:
        validate_email(para)
    except ValidationError as exc:
        raise EnvioInvalido('E-mail inválido — confira o endereço.') from exc

    nome_do_modelo = NOME_MODELO.get(doc.modelo, 'Nota fiscal')
    base = f'{nome_do_modelo}-{limpar(doc.numero) or doc.order.order_number}'
    anexos = []
    for extensao, url in (('pdf', doc.danfe_url), ('xml', doc.xml_url)):
        conteudo = _baixar(url)
        if conteudo:
            anexos.append({'filename': f'{base}.{extensao}', 'content': conteudo})

    marca = marca_da_loja(doc.store)
    numero = f' nº {doc.numero}' if doc.numero else ''
    resultado = EmailMarketingService().send_single_email(
        to_email=para,
        subject=f'{nome_do_modelo}{numero} — {marca["nome"]}',
        html_content=moldura(marca, titulo=f'{nome_do_modelo}{numero}', corpo=_corpo(doc, nome_do_modelo)),
        from_email=marca['from_email'],
        from_name=marca['from_name'],
        reply_to=marca['reply_to'] or None,
        attachments=anexos,
    )
    if not resultado.get('success'):
        raise EnvioFalhou(resultado.get('error') or 'Falha ao enviar e-mail.')

    doc.email_enviado_para = para
    doc.email_enviado_em = timezone.now()
    doc.save(update_fields=['email_enviado_para', 'email_enviado_em', 'updated_at'])

    # O endereço que funcionou vira o do cadastro: na próxima nota já vem.
    if salvo is not None and salvo.email != para:
        salvo.email = para
        salvo.save(update_fields=['email', 'updated_at'])
    return doc


def guardar_envio_para_depois(doc: FiscalDocument) -> FiscalDocument:
    """A SEFAZ ainda está processando: guarda o endereço e deixa o envio para
    quando a consulta trouxer a autorização. `email_enviado_em` vazio com
    `email_enviado_para` preenchido é exatamente esse "falta mandar"."""
    salvo = _destinatario_salvo(doc)
    if salvo is None or not salvo.email:
        return doc
    doc.email_enviado_para = salvo.email
    doc.email_enviado_em = None
    doc.save(update_fields=['email_enviado_para', 'email_enviado_em', 'updated_at'])
    return doc


def enviar_se_ficou_pendente(doc: FiscalDocument) -> FiscalDocument:
    """Nota que acabou de ser autorizada e tinha envio guardado: manda agora.
    Falha aqui não derruba a lista — fica registrada e o operador reenvia."""
    if (
        doc.status != FiscalDocument.Status.AUTHORIZED
        or not doc.email_enviado_para
        or doc.email_enviado_em is not None
    ):
        return doc
    try:
        return enviar_nota_por_email(doc, doc.email_enviado_para)
    except (EnvioInvalido, EnvioFalhou):
        logger.warning('nota %s: envio guardado não saiu', doc.id)
        return doc
