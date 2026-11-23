"""Carteira de cartões do cliente — estilo iFood.

Os cartões ficam no Mercado Pago (Customers & Cards), na conta da PLATAFORMA
(`MERCADO_PAGO_ACCESS_TOKEN`). Por isso um cartão salvo serve a todas as lojas
com `usa_gateway_da_plataforma` e a nenhuma loja com conta própria (o cartão
pertence à conta que o salvou).

Nada de número nem CVV passa por aqui: o app manda só o token de uso único que
o MP gerou. Para pagar com o cartão salvo o app gera outro token (card_id + CVV,
o MP exige o CVV toda vez) e o checkout manda `payer.customer_id`.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE = 'https://api.mercadopago.com'


class CartaoNaoSalvo(Exception):
    pass


def _mp(metodo, caminho, json=None, params=None):
    """(status, corpo) de uma chamada à conta da plataforma. Ponto único — os
    testes trocam esta função."""
    token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '') or ''
    r = requests.request(
        metodo, _BASE + caminho, json=json, params=params, timeout=15,
        headers={'Authorization': f'Bearer {token}'},
    )
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    return r.status_code, corpo


def disponivel(store):
    return bool(getattr(store, 'usa_gateway_da_plataforma', False))


def _perfil(user):
    from apps.core.models import UserProfile
    perfil, _ = UserProfile.objects.get_or_create(user=user)
    return perfil


def _email(user):
    """O MP exige e-mail para criar cliente. Quem entrou só pelo WhatsApp não
    tem — vai um endereço técnico estável, nosso, que ninguém lê."""
    email = (getattr(user, 'email', '') or '').strip()
    return email or f'cliente-{user.pk}@clientes.cardapidex.com.br'


def _customer_id(user, criar=False):
    perfil = _perfil(user)
    if perfil.mp_customer_id or not criar:
        return perfil.mp_customer_id
    email = _email(user)
    status, corpo = _mp('GET', '/v1/customers/search', params={'email': email})
    achados = (corpo or {}).get('results') or [] if status == 200 else []
    if achados:
        cid = str(achados[0].get('id') or '')
    else:
        dados = {'email': email}
        if getattr(user, 'first_name', ''):
            dados['first_name'] = user.first_name
        status, corpo = _mp('POST', '/v1/customers', json=dados)
        if status not in (200, 201) or not (corpo or {}).get('id'):
            logger.warning('[cartoes] MP não criou cliente: %s %s', status, corpo)
            raise CartaoNaoSalvo('Não conseguimos salvar o cartão agora.')
        cid = str(corpo['id'])
    perfil.mp_customer_id = cid
    perfil.save(update_fields=['mp_customer_id', 'updated_at'])
    return cid


def _formatar(c):
    pm = c.get('payment_method') or {}
    mes, ano = c.get('expiration_month'), c.get('expiration_year')
    return {
        'id': str(c.get('id') or ''),
        'bandeira': pm.get('id') or '',
        'tipo': pm.get('payment_type_id') or 'credit_card',
        'final': c.get('last_four_digits') or '',
        'validade': f'{int(mes):02d}/{int(ano) % 100:02d}' if mes and ano else '',
        'cvv': (c.get('security_code') or {}).get('length') or 3,
    }


def listar(user):
    cid = _customer_id(user)
    if not cid:
        return []
    status, corpo = _mp('GET', f'/v1/customers/{cid}/cards')
    if status != 200 or not isinstance(corpo, list):
        return []
    return [_formatar(c) for c in corpo if c.get('id')]


def salvar(user, token):
    if not token:
        raise CartaoNaoSalvo('Cartão inválido.')
    cid = _customer_id(user, criar=True)
    status, corpo = _mp('POST', f'/v1/customers/{cid}/cards', json={'token': token})
    if status not in (200, 201) or not (corpo or {}).get('id'):
        logger.info('[cartoes] MP recusou salvar cartão: %s %s', status, corpo)
        raise CartaoNaoSalvo('Não conseguimos salvar este cartão. Confira os dados.')
    return _formatar(corpo)


def remover(user, card_id):
    cid = _customer_id(user)
    if cid and card_id:
        _mp('DELETE', f'/v1/customers/{cid}/cards/{card_id}')
