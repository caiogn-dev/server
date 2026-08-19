"""
MercadoPago Orders API (Checkout Transparente via Orders).
Monta um payload RICO a partir do pedido real (itens, pagador, endereço,
statement_descriptor) — melhora a aprovação e a nota de qualidade do MP.

POST https://api.mercadopago.com/v1/orders  (a SDK 2.x não expõe orders → REST).
Single-seller: usa o access_token do gateway da loja (sem OAuth por enquanto).
"""
import re
from decimal import Decimal
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


def _soma_dos_itens(items):
    return sum(
        (Decimal(str(i['unit_price'])) * int(i['quantity']) for i in items),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))


def build_items(order):
    items = []
    for it in order.items.all():
        # MP limita external_code a 30 chars — UUID de product_id tem 36 e
        # derruba a order inteira (400 property_value).
        external_code = (it.sku or str(getattr(it, 'product_id', '') or ''))[:30]
        items.append({
            'title': (it.product_name or 'Item')[:256],
            'unit_price': str(it.unit_price),
            'quantity': int(it.quantity or 1),
            'external_code': external_code,
            'category_id': 'food',
            'description': (it.product_name or '')[:256],
        })
    if not items:  # fallback: 1 item com o total
        return [{'title': f'Pedido {order.order_number}', 'unit_price': str(order.total),
                 'quantity': 1, 'category_id': 'food'}]

    # A Orders API recusa a order INTEIRA com 400
    # `order_items_total_amount_mismatch` quando sum(items) != total_amount, e
    # total_amount é o order.total — que carrega frete e desconto. Os produtos
    # sozinhos nunca fecham a conta num pedido de delivery.
    frete = Decimal(str(getattr(order, 'delivery_fee', 0) or 0))
    if frete > Decimal('0.00'):
        items.append({
            'title': 'Taxa de entrega',
            'unit_price': str(frete.quantize(Decimal('0.01'))),
            'quantity': 1,
            'category_id': 'food',
        })

    total = Decimal(str(order.total)).quantize(Decimal('0.01'))
    if _soma_dos_itens(items) != total:
        # Desconto (cupom/fidelidade) não tem item negativo na Orders API.
        # Item único consolidado: perde granularidade, mas fecha a conta —
        # e uma order recusada não tem granularidade nenhuma.
        return [{'title': f'Pedido {order.order_number}', 'unit_price': str(total),
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


#: A Orders API recusa o payload inteiro acima disto (não trunca sozinha).
LIMITE_STREET_NUMBER = 10


def numero_do_endereco(valor) -> str:
    """Número da rua no formato que a Orders API aceita.

    11/ago/2026: "Lt 11 casa 2" (12 caracteres) devolveu 400 e derrubou uma
    venda de R$ 270,37 no cartão — o MP valida `street_number` em 10 e recusa
    a ordem inteira, não o campo. Em Palmas quadra/lote/casa é o padrão do
    endereço, então isto acontece o tempo todo.

    Prefere o primeiro número (é o que serve ao antifraude); se não houver
    número nenhum, corta no limite. O endereço de entrega de verdade continua
    inteiro no pedido — isto aqui é só o que vai para o Mercado Pago.
    """
    texto = str(valor or '').strip()
    if len(texto) <= LIMITE_STREET_NUMBER:
        return texto

    encontrado = re.search(r'\d+', texto)
    if encontrado and len(encontrado.group()) <= LIMITE_STREET_NUMBER:
        return encontrado.group()

    return texto[:LIMITE_STREET_NUMBER].strip()


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
        address['street_number'] = numero_do_endereco(number)
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


def _iso_ms(dt):
    return dt.isoformat(timespec='milliseconds')


def build_additional_info(order):
    """Industry data (quality score do MP): additional_info com chaves ACHATADAS
    ("payer.registration_date", "shipment.local_pickup", ...) — formato da
    Orders API, diferente do aninhado da Payments API antiga.

    Histórico do comprador por telefone: no delivery o guest checkout nem sempre
    tem email/usuário, mas o telefone é obrigatório e estável.
    """
    from apps.stores.models import StoreOrder

    history = StoreOrder.objects.filter(
        store=order.store, customer_phone=order.customer_phone,
    ).exclude(id=order.id)

    first_seen = history.order_by('created_at').values_list('created_at', flat=True).first()
    last_paid = (
        history.filter(payment_status=StoreOrder.PaymentStatus.PAID)
        .order_by('-created_at').values_list('created_at', flat=True).first()
    )

    info = {
        'shipment.local_pickup': order.delivery_method == StoreOrder.DeliveryMethod.PICKUP,
        'shipment.express': False,
        'payer.registration_date': _iso_ms(first_seen or order.created_at),
        'payer.is_first_purchase_online': first_seen is None,
        'payer.authentication_type': 'WEB',
    }
    if last_paid:
        info['payer.last_purchase'] = _iso_ms(last_paid)
    return info


def build_order_payload(order, *, card_token, payment_method_id, installments,
                        payer_email, payer_data=None, payment_type='credit_card'):
    return {
        'additional_info': build_additional_info(order),
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


def build_pix_order_payload(order, payer_email, payer_data=None, amount=None):
    """Payload de PIX para a Orders API.

    Espelha o build_order_payload do cartão: mesmo envelope, mesmo payer rico
    (com endereço — requisito de qualidade do MP e insumo do antifraude), só
    troca o método.

    NÃO envie `expiration_time` dentro de payment_method: a Orders API recusa
    o payload INTEIRO com 400 `unsupported_properties`. O vencimento vem
    pronto na resposta, em `date_of_expiration`.
    """
    valor = str(amount if amount is not None else order.total)
    return {
        'additional_info': build_additional_info(order),
        'type': 'online',
        'processing_mode': 'automatic',
        'total_amount': valor,
        'external_reference': str(order.id),  # sem PII
        'description': f'Pedido {order.order_number} - {order.store.name}'[:256],
        'payer': build_payer(order, payer_email, payer_data),
        'items': build_items(order),
        'transactions': {
            'payments': [{
                'amount': valor,
                'payment_method': {
                    'id': 'pix',
                    'type': 'bank_transfer',
                },
            }],
        },
    }


def extract_pix(body):
    """Puxa QR, ticket e id da resposta da Orders API. {} quando não houver."""
    pagamentos = ((body or {}).get('transactions') or {}).get('payments') or []
    if not pagamentos:
        return {}
    pagamento = pagamentos[0] or {}
    metodo = pagamento.get('payment_method') or {}
    ulid = str(pagamento['id']) if pagamento.get('id') else None
    ticket = metodo.get('ticket_url', '') or ''

    # O id da Orders API é um ULID (PAY01M0D...) e GET /v1/payments/PAY01...
    # responde 404. Quem confirma o pagamento — webhook, poller de
    # reconciliação, tasks.reconcile — consulta por `sdk.payment().get()`, que
    # só aceita o id NUMÉRICO. Salvar o ULID deixaria o cliente pagando e o
    # pedido preso para sempre em "pendente". O numérico vem no ticket_url:
    # https://www.mercadopago.com.br/payments/174584705322/ticket?...
    casado = re.search(r'/payments/(\d+)', ticket)
    numerico = casado.group(1) if casado else None

    return {
        'payment_id': numerico or ulid,
        'order_payment_id': ulid,
        'qr_code': metodo.get('qr_code', ''),
        'qr_code_base64': metodo.get('qr_code_base64', ''),
        'ticket_url': metodo.get('ticket_url', ''),
        'date_of_expiration': pagamento.get('date_of_expiration'),
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


def eh_erro_de_payload(status_code, body) -> bool:
    """True quando o MP recusou o NOSSO payload, não o cartão do cliente.

    A Orders API responde 400 com `errors[].code` de schema ('property_value',
    'validation_error', ...) quando algum campo nosso está fora do formato —
    o cartão nem chega a ser consultado. Confundir isso com recusa do emissor
    foi o que matou o pedido CE-2608113992: um `street_number` de 12
    caracteres derrubou uma venda de R$ 270,37 e sumiu com o pedido da tela.
    """
    if status_code not in (400, 422):
        return False
    erros = (body or {}).get('errors') or []
    if not isinstance(erros, list):
        return False
    return any(
        str((erro or {}).get('code', '')).lower() in ('property_value', 'validation_error', 'bad_request',
             'order_items_total_amount_mismatch', 'unsupported_properties')
        for erro in erros
    )


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
    # in_review = análise manual antifraude do MP; segue vivo (webhook decide).
    if status in ('pending', 'action_required', 'in_review'):
        return True, 'pending', pid, detail
    return False, 'failed', pid, detail
