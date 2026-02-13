import hashlib
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _sha256(value):
    if not value:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _normalize_phone(phone):
    if not phone:
        return ''
    return ''.join(ch for ch in str(phone) if ch.isdigit())


def _build_user_data(order):
    user_data = {}

    email_hash = _sha256(order.customer_email)
    if email_hash:
        user_data['em'] = [email_hash]

    phone_hash = _sha256(_normalize_phone(order.customer_phone))
    if phone_hash:
        user_data['ph'] = [phone_hash]

    external_id = _sha256(order.id)
    if external_id:
        user_data['external_id'] = [external_id]

    return user_data


def _build_contents(order):
    contents = []
    num_items = 0

    for item in order.items.all():
        content_id = (
            getattr(item, 'product_id', None)
            or getattr(item, 'product', None)
            or getattr(item, 'id', None)
            or item.product_name
            or 'item'
        )
        quantity = int(item.quantity or 1)
        item_price = float(item.unit_price or 0)

        contents.append({
            'id': str(content_id),
            'quantity': quantity,
            'item_price': item_price,
        })
        num_items += quantity

    return contents, num_items


def send_purchase_event(order):
    pixel_id = getattr(settings, 'META_PIXEL_ID', '').strip()
    access_token = getattr(settings, 'META_CAPI_ACCESS_TOKEN', '').strip()

    if not pixel_id or not access_token:
        return False

    contents, num_items = _build_contents(order)
    order_id = order.order_number or order.id

    payload = {
        'data': [
            {
                'event_name': 'Purchase',
                'event_time': int(time.time()),
                'event_id': str(order_id),
                'action_source': 'website',
                'user_data': _build_user_data(order),
                'custom_data': {
                    'currency': 'BRL',
                    'value': float(order.total or 0),
                    'contents': contents,
                    'content_type': 'product',
                    'num_items': num_items,
                    'order_id': str(order_id),
                },
            }
        ]
    }

    test_event_code = getattr(settings, 'META_CAPI_TEST_EVENT_CODE', '').strip()
    if test_event_code:
        payload['test_event_code'] = test_event_code

    api_version = getattr(settings, 'META_CAPI_VERSION', 'v20.0').strip() or 'v20.0'
    url = f'https://graph.facebook.com/{api_version}/{pixel_id}/events'

    try:
        response = requests.post(
            url,
            params={'access_token': access_token},
            json=payload,
            timeout=3,
        )
        if not response.ok:
            logger.warning('Meta CAPI error: %s', response.text)
            return False
    except requests.RequestException as exc:
        logger.warning('Meta CAPI request failed: %s', exc)
        return False

    return True
