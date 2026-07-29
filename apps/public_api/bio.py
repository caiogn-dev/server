"""Payload e resolução de links da página pública Link na Bio."""
import re
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.stores import billing

AUTO_KEYS = ('menu', 'whatsapp', 'maps', 'instagram')
DEFAULT_SETTINGS = {'headline': '', 'links': {}, 'instagram_url': ''}


def bio_settings(store):
    raw = (store.metadata or {}).get('bio_settings') or {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
    return merged


def _auto_link_urls(store):
    cfg = bio_settings(store)
    urls = {}
    base = settings.STOREFRONT_BASE_URL.rstrip('/')
    metadata = store.metadata or {}
    menu_url = metadata.get('menu_url') or metadata.get('frontend_url')
    urls['menu'] = menu_url or f'{base}/{store.slug}'
    digits = re.sub(r'\D', '', store.whatsapp_number or '')
    if digits:
        if len(digits) <= 11:
            digits = f'55{digits}'
        urls['whatsapp'] = f'https://wa.me/{digits}'
    if store.latitude is not None and store.longitude is not None:
        urls['maps'] = f'https://www.google.com/maps/search/?api=1&query={store.latitude},{store.longitude}'
    elif store.address:
        q = quote(f'{store.address} {store.city or ""} {store.state or ""}'.strip())
        urls['maps'] = f'https://www.google.com/maps/search/?api=1&query={q}'
    insta = (cfg.get('instagram_url') or '').strip()
    if insta:
        urls['instagram'] = insta
    return urls


AUTO_TITLES = {'menu': 'Fazer pedido', 'whatsapp': 'Fale Conosco', 'maps': 'Como chegar', 'instagram': 'Instagram'}
AUTO_ICONS = {'menu': '🍽️', 'whatsapp': '💬', 'maps': '📍', 'instagram': '📸'}


def bio_links(store):
    """Lista ordenada de links visíveis: automáticos habilitados + customizados ativos (se o plano permite)."""
    cfg = bio_settings(store)
    toggles = cfg.get('links') or {}
    urls = _auto_link_urls(store)
    links = []
    for key in AUTO_KEYS:
        if key in urls and toggles.get(key, True) is not False:
            links.append({'key': f'auto:{key}', 'title': AUTO_TITLES[key], 'icon': AUTO_ICONS[key], 'url': urls[key]})
    if billing.plan_allows(store, 'bio_custom_links'):
        for link in store.bio_links.filter(is_active=True):
            links.append({'key': f'custom:{link.id}', 'title': link.title, 'icon': link.icon, 'url': link.url})
    return links


def resolve_link_url(store, key):
    """Resolve uma link_key pra URL de destino, ou None. Nunca lê URL do request (anti open-redirect)."""
    if key.startswith('auto:'):
        short = key.split(':', 1)[1]
        cfg = bio_settings(store)
        if (cfg.get('links') or {}).get(short, True) is False:
            return None
        return _auto_link_urls(store).get(short)
    if key.startswith('custom:'):
        if not billing.plan_allows(store, 'bio_custom_links'):
            return None
        try:
            link = store.bio_links.filter(id=key.split(':', 1)[1], is_active=True).first()
        except (ValueError, ValidationError):
            return None
        return link.url if link else None
    return None


def bio_page_url(store):
    return f"{settings.BIO_BASE_URL.rstrip('/')}/{store.slug}"


def _logo_url(store, request=None):
    """Replica PublicStoreSerializer.get_logo_url (apps/public_api/serializers.py)."""
    if store.logo:
        url = store.logo.url
        return request.build_absolute_uri(url) if request else url
    return store.logo_url or None


def bio_payload(store, request=None):
    cfg = bio_settings(store)
    return {
        'store': {
            'name': store.name,
            'slug': store.slug,
            'logo_url': _logo_url(store, request=request),
            'primary_color': store.primary_color,
            'secondary_color': store.secondary_color,
            'clarity_id': store.clarity_id,
            'clarity_enabled': store.clarity_enabled,
            'meta_pixel_id': store.meta_pixel_id,
            'meta_pixel_enabled': store.meta_pixel_enabled,
        },
        'headline': cfg.get('headline') or '',
        'links': bio_links(store),
        'show_branding': not billing.plan_allows(store, 'bio_custom_links'),
    }
