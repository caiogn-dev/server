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


def _normalize_text(value):
    if value is None:
        return ''
    return ''.join(str(value).strip().lower().split())


def _split_name(full_name):
    parts = [part for part in str(full_name or '').strip().split() if part]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], parts[-1]


def _get_client_ip(request):
    if request is None:
        return ''

    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_event_source_url(request, tracking_data):
    explicit_url = (tracking_data or {}).get('event_source_url')
    if explicit_url:
        return str(explicit_url)[:2048]

    if request is None:
        return ''

    referer = request.headers.get('Referer') or request.headers.get('Origin') or ''
    if referer:
        return referer[:2048]

    try:
        return request.build_absolute_uri()[:2048]
    except Exception:
        return ''


def _valid_cookie_value(value):
    value = str(value or '').strip()
    if not value:
        return ''
    return value[:500]


def _build_user_data(order, request=None, tracking_data=None):
    user_data = {}
    tracking_data = tracking_data or {}

    email_hash = _sha256(order.customer_email)
    if email_hash:
        user_data['em'] = [email_hash]

    phone_hash = _sha256(_normalize_phone(order.customer_phone))
    if phone_hash:
        user_data['ph'] = [phone_hash]

    external_id = _sha256(order.id)
    if external_id:
        user_data['external_id'] = [external_id]

    first_name, last_name = _split_name(order.customer_name)
    first_name_hash = _sha256(first_name)
    last_name_hash = _sha256(last_name)
    if first_name_hash:
        user_data['fn'] = [first_name_hash]
    if last_name_hash:
        user_data['ln'] = [last_name_hash]

    delivery_address = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    city_hash = _sha256(_normalize_text(delivery_address.get('city')))
    state_hash = _sha256(_normalize_text(delivery_address.get('state')))
    zip_hash = _sha256(_normalize_text(delivery_address.get('zip_code')))
    country_hash = _sha256('br')
    if city_hash:
        user_data['ct'] = [city_hash]
    if state_hash:
        user_data['st'] = [state_hash]
    if zip_hash:
        user_data['zp'] = [zip_hash]
    if country_hash:
        user_data['country'] = [country_hash]

    fbp = _valid_cookie_value(tracking_data.get('fbp'))
    fbc = _valid_cookie_value(tracking_data.get('fbc'))
    if fbp:
        user_data['fbp'] = fbp
    if fbc:
        user_data['fbc'] = fbc

    client_ip = _get_client_ip(request)
    if client_ip:
        user_data['client_ip_address'] = client_ip

    user_agent = request.META.get('HTTP_USER_AGENT', '') if request is not None else ''
    if user_agent:
        user_data['client_user_agent'] = user_agent[:1000]

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


def _get_order_meta(order):
    return order.metadata if isinstance(order.metadata, dict) else {}


def _mark_purchase_sent(order, event_id):
    metadata = _get_order_meta(order).copy()
    capi_meta = metadata.get('meta_capi') if isinstance(metadata.get('meta_capi'), dict) else {}
    capi_meta.update({
        'purchase_sent_at': int(time.time()),
        'purchase_event_id': str(event_id),
    })
    metadata['meta_capi'] = capi_meta
    order.metadata = metadata
    order.save(update_fields=['metadata', 'updated_at'])


def _build_event_id(order, tracking_data):
    tracking_event_id = (tracking_data or {}).get('event_id')
    if tracking_event_id:
        return str(tracking_event_id)[:255]
    order_id = order.order_number or order.id
    return f'Purchase:{order_id}'


def send_purchase_event(order, request=None, tracking_data=None, force=False):
    pixel_id = getattr(settings, 'META_PIXEL_ID', '').strip()
    access_token = getattr(settings, 'META_CAPI_ACCESS_TOKEN', '').strip()
    allowed_store_slugs = set(getattr(settings, 'META_CAPI_STORE_SLUGS', []) or [])

    if not pixel_id or not access_token:
        return False

    store_slug = getattr(getattr(order, 'store', None), 'slug', '')
    if allowed_store_slugs and store_slug not in allowed_store_slugs:
        return False

    metadata = _get_order_meta(order)
    capi_meta = metadata.get('meta_capi') if isinstance(metadata.get('meta_capi'), dict) else {}
    if capi_meta.get('purchase_sent_at') and not force:
        return True

    contents, num_items = _build_contents(order)
    order_id = order.order_number or order.id
    tracking_data = tracking_data or {}
    event_id = _build_event_id(order, tracking_data)
    event_source_url = _get_event_source_url(request, tracking_data)

    event = {
        'event_name': 'Purchase',
        'event_time': int(time.time()),
        'event_id': event_id,
        'action_source': 'website',
        'user_data': _build_user_data(order, request=request, tracking_data=tracking_data),
        'custom_data': {
            'currency': 'BRL',
            'value': float(order.total or 0),
            'contents': contents,
            'content_type': 'product',
            'num_items': num_items,
            'order_id': str(order_id),
        },
    }
    if event_source_url:
        event['event_source_url'] = event_source_url

    payload = {'data': [event]}

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

    _mark_purchase_sent(order, event_id)
    return True
