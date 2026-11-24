"""Cartão de crédito pela Pagar.me (o app manda o token; o número nunca passa
por aqui). Funções de montagem + resolução de conta; a cobrança em si mora em
`CheckoutService._cobrar_cartao_pagarme`, no molde do vale.

QUAL CONTA COBRA

- A loja com Pagar.me própria habilitada (chave secreta + pública) cobra nela.
- Loja da conta da PLATAFORMA (`usa_gateway_da_plataforma`: as lojas do dono)
  sem Pagar.me própria cobra na Pagar.me da loja `PAGARME_LOJA_DA_PLATAFORMA`
  — o mesmo dono, a mesma regra do Mercado Pago da plataforma.
- Loja de cliente sem Pagar.me própria: sem cartão pela Pagar.me (o app cai no
  Mercado Pago, como antes). Dinheiro de terceiro nunca passa pela conta do dono.
"""
from django.conf import settings

from apps.stores.services import pagarme_orders


def _habilitado(gateway):
    return bool(gateway and gateway.is_enabled and gateway.api_key and gateway.public_key)


def _pagarme_da_loja(store):
    from apps.stores.models import StorePaymentGateway
    return (
        StorePaymentGateway.objects
        .filter(store=store, gateway_type=StorePaymentGateway.GatewayType.PAGARME, is_enabled=True)
        .order_by('-updated_at')
        .first()
    )


def gateway_do_cartao(store):
    propria = _pagarme_da_loja(store)
    if _habilitado(propria):
        return propria
    if not getattr(store, 'usa_gateway_da_plataforma', False):
        return None
    slug = getattr(settings, 'PAGARME_LOJA_DA_PLATAFORMA', '') or ''
    if not slug:
        return None
    from apps.stores.models import Store
    dona = Store.objects.filter(slug=slug).first()
    gateway = _pagarme_da_loja(dona) if dona else None
    return gateway if _habilitado(gateway) else None


def config_publica(store):
    """O que o app precisa para tokenizar (só a chave PÚBLICA), ou None.

    24/11: desligado por padrão — a Pagar.me cobra 5% (MP 4,99%) e o
    antifraude da conta reprovava toda compra que o banco aprovava. Sem isto
    o app cai no cartão do Mercado Pago. Religar: PAGARME_CARTAO_APP=1."""
    if not getattr(settings, 'PAGARME_CARTAO_APP', False):
        return None
    gateway = gateway_do_cartao(store)
    if gateway is None:
        return None
    return {'gateway': 'pagarme', 'public_key': gateway.public_key}


def _endereco_de_cobranca(order):
    """Pagar.me v5 exige billing_address com card_token. Entrega = endereço do
    pedido; retirada (sem endereço) = o da loja."""
    end = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    loja = order.store
    rua = end.get('street') or end.get('street_name') or end.get('address') or getattr(loja, 'address', '') or ''
    numero = end.get('number') or end.get('street_number') or ''
    bairro = end.get('neighborhood') or ''
    partes = [p for p in (str(numero).strip(), str(rua).strip(), str(bairro).strip()) if p]
    return {
        'line_1': ', '.join(partes)[:256] or 'Sem endereço',
        'zip_code': pagarme_orders.somente_digitos(
            end.get('zip_code') or end.get('postal_code') or end.get('cep') or getattr(loja, 'zip_code', '') or ''
        ),
        'city': (end.get('city') or getattr(loja, 'city', '') or 'Palmas')[:64],
        'state': (end.get('state') or getattr(loja, 'state', '') or 'TO')[:2].upper(),
        'country': 'BR',
    }


def _telefone(phone):
    d = pagarme_orders.somente_digitos(phone)
    if d.startswith('55') and len(d) > 11:
        d = d[2:]
    if len(d) < 10:
        return None
    return {'country_code': '55', 'area_code': d[:2], 'number': d[2:]}


def _email_do_cliente(order) -> str:
    """E-mail real se válido; senão um técnico estável (mesmo cliente = mesmo e-mail)."""
    email = pagarme_orders.email_aceito_pelo_gateway(getattr(order, 'customer_email', ''))
    if email:
        return email
    chave = pagarme_orders.somente_digitos(order.customer_phone) or str(order.order_number).lower()
    return f'cliente-{chave}@clientes.cardapidex.com.br'


def build_payload(order, *, card_token, holder_name, holder_document, total=None, ip=''):
    items = pagarme_orders.build_items(order, total=total)
    valor = pagarme_orders.soma_dos_itens(items)
    cliente = {
        'name': (order.customer_name or holder_name or 'Cliente')[:64],
        'type': 'individual',
    }
    documento = pagarme_orders.somente_digitos(holder_document)
    if documento:
        cliente['document'] = documento
    # Sempre com e-mail: sem ele o antifraude da Pagar.me dá "Buyer.Emails min"
    # e a Pagar.me cancela sozinha a venda que o banco aprovou (23/11).
    cliente['email'] = _email_do_cliente(order)
    fone = _telefone(order.customer_phone)
    if fone:
        cliente['phones'] = {'mobile_phone': fone}
    payload = {
        'items': items,
        'customer': cliente,
        'payments': [{
            'payment_method': 'credit_card',
            'amount': valor,
            'credit_card': {
                'installments': 1,
                'operation_type': 'auth_and_capture',
                'statement_descriptor': pagarme_orders.statement_descriptor(order),
                'card_token': card_token,
                'card': {'billing_address': _endereco_de_cobranca(order)},
            },
        }],
        'metadata': {'pedido': str(order.order_number)},
    }
    from django.conf import settings
    payload['antifraud_enabled'] = bool(getattr(settings, 'PAGARME_CARTAO_ANTIFRAUDE', False))
    # Mais sinal para o antifraude (24/11 reprovou compra aprovada pelo banco):
    # IP do cliente e, na entrega, o endereço de entrega.
    if ip:
        payload['ip'] = ip[:45]
    entrega = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    if entrega and (entrega.get('street') or entrega.get('address')):
        payload['shipping'] = {
            # 0 de propósito: o frete já está nos itens (build_items fecha no
            # total); somar de novo aqui quebraria a conta itens == pagamento.
            'amount': 0,
            'description': 'Entrega',
            'recipient_name': cliente['name'],
            **({'recipient_phone': f"{fone['area_code']}{fone['number']}"} if fone else {}),
            'address': _endereco_de_cobranca(order),
        }
    return payload


MENSAGENS_DE_RECUSA = {
    'antifraude': 'A análise de segurança não aprovou esta compra e nada foi cobrado. Pague no PIX ou tente outro cartão.',
    'saldo insuficiente': 'O cartão não tem limite para este valor. Use outro cartão ou pague no PIX.',
    'limite': 'O cartão não tem limite para este valor. Use outro cartão ou pague no PIX.',
    'cartao expirado': 'Este cartão está vencido. Use outro cartão ou pague no PIX.',
    'cartao vencido': 'Este cartão está vencido. Use outro cartão ou pague no PIX.',
    'cartao invalido': 'Confira o número, a validade e o CVV e tente de novo.',
    'verifique os dados do cartao': 'Confira o número, a validade e o CVV e tente de novo.',
    'cartao bloqueado': 'Este cartão está bloqueado. Fale com o seu banco ou pague no PIX.',
    'transacao nao permitida': 'O banco não liberou esta compra. Fale com o seu banco ou pague no PIX.',
}
RECUSA_GENERICA = 'O cartão não foi autorizado. Use outro cartão ou pague no PIX.'


def motivo_real(corpo, motivo) -> str:
    """Antifraude reprovado chega com acquirer_message 'Approved' (o banco
    aprovou, a Pagar.me desfez — 24/11). O motivo de verdade é o antifraude."""
    for cobranca in (corpo or {}).get('charges') or []:
        antifraude = ((cobranca or {}).get('last_transaction') or {}).get('antifraud_response') or {}
        if str(antifraude.get('status') or '').lower() in ('reproved', 'analysis_error'):
            return 'antifraude'
    return motivo


def mensagem_de_recusa(motivo) -> str:
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(motivo or '')).encode('ascii', 'ignore').decode('ascii').lower()
    for chave, mensagem in MENSAGENS_DE_RECUSA.items():
        if chave in texto:
            return mensagem
    return RECUSA_GENERICA
