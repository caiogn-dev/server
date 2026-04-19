"""
TocaDeliveryProvider — integrates server2 StoreOrder with the Toca Delivery SaaS
(api.tocadelivery.com.br).

Authentication: JWT Bearer via POST /auth/login.
Token is cached in Django's cache backend (TTL 55min, token expires in 60min).

Configuration (settings or env):
    TOCA_DELIVERY_API_URL  — base URL, e.g. https://api.tocadelivery.com.br
    TOCA_DELIVERY_EMAIL    — empresa login email
    TOCA_DELIVERY_PASSWORD — empresa login password
    TOCA_DELIVERY_ENABLED  — 'true' to enable auto-dispatch

Status mapping (CorridaStatus → StoreOrder.OrderStatus):
    criada    → (no change)
    ofertada  → (no change, driver searching)
    aceita    → out_for_delivery
    em_coleta → out_for_delivery
    coletada  → out_for_delivery
    em_rota   → out_for_delivery
    entregue  → delivered
    cancelada → (logged, no auto-cancel — requires human decision)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

from .base import DeliveryProvider, DeliveryProviderError, DeliveryQuote, DeliveryResult

logger = logging.getLogger(__name__)

_TOKEN_CACHE_KEY = 'toca_delivery:access_token'
_TOKEN_TTL = 55 * 60  # 55 minutes

# CorridaStatus → StoreOrder.OrderStatus
_STATUS_MAP = {
    'aceita': 'out_for_delivery',
    'em_coleta': 'out_for_delivery',
    'coletada': 'out_for_delivery',
    'em_rota': 'out_for_delivery',
    'entregue': 'delivered',
}

TRACKING_URL_TEMPLATE = '{base}/rastreio/{codigo}'


class TocaDeliveryProvider(DeliveryProvider):
    """Calls the Toca Delivery FastAPI at api.tocadelivery.com.br."""

    def __init__(
        self,
        api_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ):
        self._api_url = (api_url or getattr(settings, 'TOCA_DELIVERY_API_URL', '')).rstrip('/')
        self._email = email or getattr(settings, 'TOCA_DELIVERY_EMAIL', '')
        self._password = password or getattr(settings, 'TOCA_DELIVERY_PASSWORD', '')

    @property
    def name(self) -> str:
        return 'toca'

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        token = cache.get(_TOKEN_CACHE_KEY)
        if token:
            return token
        return self._authenticate()

    def _authenticate(self) -> str:
        if not self._email or not self._password:
            raise DeliveryProviderError('TOCA_DELIVERY_EMAIL / TOCA_DELIVERY_PASSWORD not configured')

        resp = requests.post(
            f'{self._api_url}/auth/login',
            json={'email': self._email, 'password': self._password},
            timeout=10,
        )
        if resp.status_code != 200:
            raise DeliveryProviderError(f'Toca auth failed: {resp.status_code} {resp.text[:200]}')

        data = resp.json()
        token = data.get('access_token')
        if not token:
            raise DeliveryProviderError('Toca auth response missing access_token')

        cache.set(_TOKEN_CACHE_KEY, token, _TOKEN_TTL)
        return token

    def _headers(self) -> dict:
        return {'Authorization': f'Bearer {self._get_token()}', 'Content-Type': 'application/json'}

    def _request(self, method: str, path: str, **kwargs):
        url = f'{self._api_url}{path}'
        try:
            resp = requests.request(method, url, headers=self._headers(), timeout=15, **kwargs)
        except requests.RequestException as exc:
            raise DeliveryProviderError(f'Toca request error: {exc}') from exc

        if resp.status_code == 401:
            # Token expired — invalidate cache and retry once
            cache.delete(_TOKEN_CACHE_KEY)
            try:
                resp = requests.request(
                    method, url, headers=self._headers(), timeout=15, **kwargs
                )
            except requests.RequestException as exc:
                raise DeliveryProviderError(f'Toca request error after re-auth: {exc}') from exc

        return resp

    # ------------------------------------------------------------------
    # Address helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_float(value) -> Optional[float]:
        """Convert Decimal/str/int to float, or None if falsy."""
        return float(value) if value is not None and value != '' else None

    @staticmethod
    def _build_address(addr: dict, store=None) -> dict:
        """Convert a delivery_address dict (server2 format) to Toca EnderecoSchema."""
        lat_raw = addr.get('lat') or addr.get('latitude')
        lng_raw = addr.get('lng') or addr.get('longitude')
        return {
            'logradouro': addr.get('street') or addr.get('logradouro') or '',
            'numero': addr.get('number') or addr.get('numero') or 'S/N',
            'complemento': addr.get('complement') or addr.get('complemento') or None,
            'bairro': addr.get('neighborhood') or addr.get('bairro') or '',
            'cidade': addr.get('city') or addr.get('cidade') or 'Palmas',
            'estado': addr.get('state') or addr.get('estado') or 'TO',
            'cep': addr.get('zip_code') or addr.get('cep') or None,
            'lat': float(lat_raw) if lat_raw else None,
            'lng': float(lng_raw) if lng_raw else None,
        }

    @staticmethod
    def _store_address(store) -> dict:
        """Build the pickup (store) address from the Store model."""
        meta = getattr(store, 'metadata', {}) or {}
        addr_data = getattr(store, 'address_data', {}) or {}
        lat_raw = getattr(store, 'latitude', None) or addr_data.get('lat')
        lng_raw = getattr(store, 'longitude', None) or addr_data.get('lng')
        return {
            'logradouro': getattr(store, 'address', '') or meta.get('address', ''),
            'numero': getattr(store, 'number', '') or meta.get('number', 'S/N') or 'S/N',
            'complemento': getattr(store, 'complement', None) or meta.get('complement'),
            'bairro': getattr(store, 'neighborhood', '') or meta.get('neighborhood', ''),
            'cidade': getattr(store, 'city', 'Palmas') or 'Palmas',
            'estado': getattr(store, 'state', 'TO') or 'TO',
            'cep': getattr(store, 'zip_code', None) or meta.get('zip_code'),
            'lat': float(lat_raw) if lat_raw else None,
            'lng': float(lng_raw) if lng_raw else None,
        }

    # ------------------------------------------------------------------
    # DeliveryProvider interface
    # ------------------------------------------------------------------

    def quote(self, store, order) -> DeliveryQuote:
        origem = self._store_address(store)
        destino = self._build_address(order.delivery_address or {})

        resp = self._request('POST', '/corridas/calcular-preco', json={
            'origem': origem,
            'destino': destino,
        })

        if resp.status_code != 200:
            raise DeliveryProviderError(f'Toca quote failed: {resp.status_code} {resp.text[:200]}')

        data = resp.json()
        return DeliveryQuote(
            distance_km=float(data.get('distancia_km', 0)),
            fee=Decimal(str(data.get('valor_total', '0'))),
            zone_name=data.get('zona_nome'),
            provider=self.name,
        )

    def create(self, store, order) -> DeliveryResult:
        origem = self._store_address(store)
        destino = self._build_address(order.delivery_address or {})

        payload = {
            'tipo': 'imediata',
            'origem': origem,
            'destino': destino,
            'destinatario_nome': order.customer_name or '',
            'destinatario_tel': order.customer_phone or None,
            'observacoes': (order.delivery_notes or '').strip() or None,
        }

        resp = self._request('POST', '/corridas', json=payload)

        if resp.status_code not in (200, 201):
            raise DeliveryProviderError(
                f'Toca create_delivery failed: {resp.status_code} {resp.text[:400]}'
            )

        data = resp.json()
        corrida_id = str(data.get('id', ''))
        codigo = data.get('codigo', '')
        tracking_url = TRACKING_URL_TEMPLATE.format(
            base=self._api_url.replace('/api', '').replace('api.', '').rstrip('/'),
            codigo=codigo,
        )

        return DeliveryResult(
            external_id=corrida_id,
            external_code=codigo,
            external_status=data.get('status', 'criada'),
            tracking_url=tracking_url,
            polyline=data.get('route_polyline'),
            extra={
                'distancia_km': data.get('route_distance_meters', 0) / 1000 if data.get('route_distance_meters') else None,
                'valor_total': data.get('valor_total'),
            },
        )

    def cancel(self, external_id: str, reason: str = 'Cancelado pelo sistema') -> bool:
        resp = self._request('POST', f'/corridas/{external_id}/cancelar', json={'motivo': reason})
        if resp.status_code == 200:
            return True
        logger.warning('Toca cancel failed: %s %s', resp.status_code, resp.text[:200])
        return False

    def get_status(self, external_id: str) -> Optional[str]:
        resp = self._request('GET', f'/corridas/{external_id}')
        if resp.status_code == 200:
            return resp.json().get('status')
        logger.warning('Toca get_status failed: %s %s', resp.status_code, resp.text[:200])
        return None

    def map_status_to_order(self, external_status: str) -> Optional[str]:
        return _STATUS_MAP.get(external_status)
