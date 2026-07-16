"""
MercadoPago Orders API (Checkout Transparente via Orders).
Monta um payload RICO a partir do pedido real (itens, pagador, endereço,
statement_descriptor) — melhora a aprovação e a nota de qualidade do MP.

POST https://api.mercadopago.com/v1/orders  (a SDK 2.x não expõe orders → REST).
Single-seller: usa o access_token do gateway da loja (sem OAuth por enquanto).
"""
import re
import unicodedata
import uuid
import requests

ORDERS_URL = 'https://api.mercadopago.com/v1/orders'


def split_name(full_name):
    parts = (full_name or '').strip().split()
    if not parts:
        return 'Cliente', ''
    return parts[0], ' '.join(parts[1:]) if len(parts) > 1 else ''


def phone_parts(phone):
    digits = re.sub(r'\D', '', phone or '')
    digits = re.sub(r'^55', '', digits)  # tira DDI
    if len(digits) >= 10:
        return digits[:2], digits[2:]
    return '', digits


def statement_descriptor(store):
    # Nome na fatura do cartão. Usa o descriptor da plataforma (config), não o
    # nome da loja — o lojista quer "Cardapidex". O MP só honra isto se a conta
    # também tiver "Nome para extratos" configurado.
    from django.conf import settings
    name = getattr(settings, 'MERCADO_PAGO_STATEMENT_DESCRIPTOR', '') or 'CARDAPIDEX'
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^A-Za-z0-9 ]', '', name).upper().strip()[:13]
    return name or 'CARDAPIDEX'


def build_items(order):
    items = []
    for it in order.items.all():
        items.append({
            'title': (it.product_name or 'Item')[:256],
            'unit_price': str(it.unit_price),
            'quantity': int(it.quantity or 1),
            'external_code': it.sku or str(getattr(it, 'product_id', '') or ''),
            'category_id': 'food',
            'description': (it.product_name or '')[:256],
        })
    if not items:  # fallback: 1 item com o total
        items = [{'title': f'Pedido {order.order_number}', 'unit_price': str(order.total),
                  'quantity': 1, 'category_id': 'food'}]
    return items


def build_payer(order, payer_email, payer_data=None):
    payer_data = payer_data or {}
    first, last = split_name(order.customer_name)
    payer = {'email': payer_email or order.customer_email, 'first_name': first, 'last_name': last}

    id_type = payer_data.get('identification_type') or payer_data.get('identificationType')
    id_num = payer_data.get('identification_number') or payer_data.get('identificationNumber')
    if id_type and id_num:
        payer['identification'] = {'type': id_type, 'number': re.sub(r'\D', '', str(id_num))}

    area, num = phone_parts(order.customer_phone)
    if num:
        payer['phone'] = {'area_code': area, 'number': num}

    address = _order_address(order)
    if address:
        payer['address'] = address
    return payer


def clean_document(document):
    digits = re.sub(r'\D', '', str(document or ''))
    return digits or None


def build_preference_items(order):
    """Itens no formato da preference (Checkout Pro): unit_price numérico +
    currency_id. A preference cobra a SOMA dos itens — o chamador é quem decide
    cair pro item único quando a soma diverge do valor cobrado (taxa/desconto)."""
    items = []
    for it in order.items.all():
        items.append({
            'title': (it.product_name or 'Item')[:256],
            'quantity': int(it.quantity or 1),
            'unit_price': float(it.unit_price),
            'currency_id': 'BRL',
            'category_id': 'food',
        })
    return items


def _order_address(order):
    addr = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    zip_code = addr.get('zip_code') or addr.get('cep') or addr.get('zip')
    street = addr.get('street_name') or addr.get('street') or addr.get('address') or addr.get('logradouro')
    number = addr.get('street_number') or addr.get('number') or addr.get('numero')
    city = addr.get('city') or addr.get('cidade')
    state = addr.get('state') or addr.get('uf') or addr.get('estado')
    address = {}
    if zip_code:
        address['zip_code'] = re.sub(r'\D', '', str(zip_code))
    if street:
        address['street_name'] = str(street)[:256]
    if number:
        address['street_number'] = str(number)[:20]
    if city:
        address['city'] = str(city)
    if state:
        address['state'] = str(state)
    return address


def build_preference_payer(order, payer_email, document=None):
    """Payer no formato da preference (name/surname, não first/last_name).
    Quanto mais dado real do comprador, melhor o score antifraude do MP."""
    first, last = split_name(order.customer_name)
    payer = {'email': payer_email or order.customer_email, 'name': first, 'surname': last}
    doc = clean_document(document)
    if doc:
        payer['identification'] = {'type': 'CPF', 'number': doc}
    area, num = phone_parts(order.customer_phone)
    if num:
        payer['phone'] = {'area_code': area, 'number': num}
    address = _order_address(order)
    if address:
        payer['address'] = address
    return payer


def build_order_payload(order, *, card_token, payment_method_id, installments,
                        payer_email, payer_data=None, payment_type='credit_card'):
    return {
        'type': 'online',
        'processing_mode': 'automatic',
        'total_amount': str(order.total),
        'external_reference': str(order.id),  # sem PII
        'description': f'Pedido {order.order_number} - {order.store.name}'[:256],
        'payer': build_payer(order, payer_email, payer_data),
        'items': build_items(order),
        'transactions': {
            'payments': [{
                'amount': str(order.total),
                'payment_method': {
                    'id': payment_method_id,
                    'type': payment_type,
                    'token': card_token,
                    'installments': max(1, int(installments or 1)),
                    'statement_descriptor': statement_descriptor(order.store),
                },
            }],
        },
    }


def create_order(access_token, payload, device_id=None, timeout=25):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Idempotency-Key': str(uuid.uuid4()),
    }
    if device_id:
        headers['X-meli-session-id'] = device_id
    r = requests.post(ORDERS_URL, headers=headers, json=payload, timeout=timeout)
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body


def interpret(status_code, body):
    """Normaliza a resposta da Orders API → (ok, status, payment_id, status_detail)."""
    body = body or {}
    payments = (body.get('transactions') or {}).get('payments') or []
    pid = str(payments[0]['id']) if payments and payments[0].get('id') else None
    detail = body.get('status_detail') or (payments[0].get('status_detail') if payments else '') or ''
    if status_code not in (200, 201):
        return False, 'failed', pid, (body.get('message') or detail or 'erro')
    status = body.get('status', '')
    if status == 'processed':
        return True, 'approved', pid, detail
    if status in ('pending', 'action_required'):
        return True, 'pending', pid, detail
    return False, 'failed', pid, detail
