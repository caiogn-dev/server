"""UberDirectProvider — Uber Direct (entrega sob demanda) no formato real da API.

Credenciais da PLATAFORMA (env), não da loja:
    UBER_CUSTOMER_ID, UBER_API_KEY (client_id), UBER_CLIENT_SECRET

Endpoints:
    POST https://auth.uber.com/oauth/v2/token            scope=eats.deliveries
    POST /v1/customers/{customer_id}/delivery_quotes     cota (não cria nada)
    POST /v1/customers/{customer_id}/deliveries          chama o entregador (COBRA)
    GET  /v1/customers/{customer_id}/deliveries/{id}
    POST /v1/customers/{customer_id}/deliveries/{id}/cancel

Endereço vai como STRING JSON ({"street_address": [...], "city", "state",
"zip_code", "country"}), e o valor volta em centavos (`fee: 1810` = R$ 18,10).
"""
from __future__ import annotations

import json
import logging
import math
import os
from decimal import Decimal
from typing import Optional

import requests
from django.core.cache import cache

from .base import DeliveryProvider, DeliveryProviderError, DeliveryQuote, DeliveryResult

logger = logging.getLogger(__name__)

API = 'https://api.uber.com/v1/customers'
TOKEN_URL = 'https://auth.uber.com/oauth/v2/token'

# Status da entrega no Direct → StoreOrder.status. Cancelada/devolvida não muda
# o pedido sozinho: alguém da loja precisa decidir (chamar outro entregador?).
_STATUS_MAP = {
    'pickup_complete': 'out_for_delivery',
    'dropoff': 'out_for_delivery',
    'delivered': 'delivered',
}


def _e164(telefone: str) -> str:
    from apps.core.utils import normalize_phone_number

    n = normalize_phone_number(telefone or '')
    return f'+{n}' if n else ''


def _float(v) -> Optional[float]:
    return float(v) if v not in (None, '') else None


def distancia_km(lat1, lng1, lat2, lng2) -> Optional[Decimal]:
    """Linha reta (haversine). Serve para agrupar por faixa, não para cobrar."""
    pts = [_float(x) for x in (lat1, lng1, lat2, lng2)]
    if any(p is None for p in pts):
        return None
    la1, lo1, la2, lo2 = map(math.radians, pts)
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return Decimal(str(round(6371 * 2 * math.asin(math.sqrt(a)), 2)))


class UberDirectProvider(DeliveryProvider):
    @property
    def name(self) -> str:
        return 'uber'

    # ── credenciais / auth ────────────────────────────────────────────────
    @property
    def _customer_id(self) -> str:
        return os.getenv('UBER_CUSTOMER_ID', '')

    def _token(self) -> str:
        client_id = os.getenv('UBER_API_KEY', '')
        secret = os.getenv('UBER_CLIENT_SECRET', '')
        if not (client_id and secret and self._customer_id):
            raise DeliveryProviderError('Uber Direct sem credenciais no ambiente')
        chave = f'uber_direct:token:{client_id}'
        token = cache.get(chave)
        if token:
            return token
        r = requests.post(TOKEN_URL, data={
            'client_id': client_id, 'client_secret': secret,
            'grant_type': 'client_credentials', 'scope': 'eats.deliveries',
        }, timeout=10)
        if not r.ok:
            raise DeliveryProviderError(f'Uber token {r.status_code}: {r.text[:200]}')
        dados = r.json()
        # Token vale 30 dias; guardamos com folga.
        cache.set(chave, dados['access_token'], timeout=max(60, int(dados.get('expires_in', 3600)) - 300))
        return dados['access_token']

    def _post(self, caminho: str, corpo: Optional[dict] = None) -> dict:
        url = f'{API}/{self._customer_id}/{caminho}'
        r = requests.post(url, json=corpo, headers={
            'Authorization': f'Bearer {self._token()}', 'Content-Type': 'application/json',
        }, timeout=15)
        if not r.ok:
            raise DeliveryProviderError(f'Uber {caminho} {r.status_code}: {r.text[:300]}')
        return r.json()

    # ── endereços ─────────────────────────────────────────────────────────
    @staticmethod
    def _endereco_loja(store) -> str:
        return json.dumps({
            'street_address': [store.address or ''],
            'city': store.city or '', 'state': store.state or '',
            'zip_code': store.zip_code or '', 'country': 'BR',
        }, ensure_ascii=False)

    @staticmethod
    def _endereco_cliente(addr: dict) -> str:
        rua = addr.get('street') or addr.get('logradouro') or ''
        numero = addr.get('number') or addr.get('numero') or ''
        linha1 = f'{rua}, {numero}' if numero else rua
        linhas = [linha1]
        complemento = addr.get('complement') or addr.get('complemento') or ''
        if complemento:
            linhas.append(complemento)
        return json.dumps({
            'street_address': linhas,
            'city': addr.get('city') or addr.get('cidade') or '',
            'state': addr.get('state') or addr.get('uf') or '',
            'zip_code': addr.get('zip_code') or addr.get('cep') or '',
            'country': 'BR',
        }, ensure_ascii=False)

    def _corpo_rota(self, store, order) -> dict:
        corpo = {
            'pickup_address': self._endereco_loja(store),
            'dropoff_address': self._endereco_cliente(order.delivery_address or {}),
        }
        coords = {
            'pickup_latitude': store.latitude, 'pickup_longitude': store.longitude,
            'dropoff_latitude': order.delivery_lat, 'dropoff_longitude': order.delivery_lng,
        }
        corpo.update({k: _float(v) for k, v in coords.items() if _float(v) is not None})
        return corpo

    # ── API ───────────────────────────────────────────────────────────────
    def cotar(self, store, order) -> dict:
        d = self._post('delivery_quotes', self._corpo_rota(store, order))
        return {
            'quote_id': d.get('id', ''),
            'fee': (Decimal(d['fee']) / 100).quantize(Decimal('0.01')),
            'duracao_min': d.get('duration'),
            'coleta_min': d.get('pickup_duration'),
            'expira': d.get('expires'),
        }

    def quote(self, store, order) -> DeliveryQuote:
        c = self.cotar(store, order)
        km = distancia_km(store.latitude, store.longitude, order.delivery_lat, order.delivery_lng)
        return DeliveryQuote(distance_km=float(km or 0), fee=c['fee'], provider=self.name)

    def create(self, store, order, quote_id: str = '') -> DeliveryResult:
        itens = [
            {'name': (i.product_name or 'Item')[:100], 'quantity': int(i.quantity or 1), 'size': 'small'}
            for i in order.items.all()
        ] or [{'name': f'Pedido {order.order_number}', 'quantity': 1, 'size': 'small'}]
        corpo = {
            **self._corpo_rota(store, order),
            'pickup_name': store.name,
            'pickup_phone_number': _e164(store.phone or store.whatsapp_number),
            'dropoff_name': order.customer_name or 'Cliente',
            'dropoff_phone_number': _e164(order.customer_phone),
            'dropoff_notes': (order.delivery_notes or '')[:280],
            'manifest_items': itens,
            'manifest_total_value': int((order.subtotal or 0) * 100),
            'external_id': order.order_number,
        }
        if quote_id:
            corpo['quote_id'] = quote_id
        d = self._post('deliveries', corpo)
        return DeliveryResult(
            external_id=d.get('id', ''),
            external_code=(d.get('id', '') or '')[-8:],
            external_status=d.get('status', 'pending'),
            tracking_url=d.get('tracking_url'),
            extra={'fee': d.get('fee')},
        )

    def cancel(self, external_id: str, reason: str = '') -> bool:
        try:
            self._post(f'deliveries/{external_id}/cancel')
            return True
        except DeliveryProviderError as e:
            logger.warning('Uber cancel %s falhou: %s', external_id, e)
            return False

    def get_status(self, external_id: str) -> Optional[str]:
        try:
            r = requests.get(f'{API}/{self._customer_id}/deliveries/{external_id}', headers={
                'Authorization': f'Bearer {self._token()}',
            }, timeout=10)
            return r.json().get('status') if r.ok else None
        except (requests.RequestException, DeliveryProviderError):
            return None

    def map_status_to_order(self, external_status: str) -> Optional[str]:
        return _STATUS_MAP.get(external_status)
