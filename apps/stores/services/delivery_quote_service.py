"""
Canonical delivery quote service.

This module is the single backend contract for storefront checkout, route
previews, WhatsApp order flows, and internal delivery pricing.
"""
import logging
from decimal import Decimal

from apps.stores.models import Store, StoreDeliveryZone

logger = logging.getLogger(__name__)


def delivery_address_text(delivery_address: dict) -> str:
    if not isinstance(delivery_address, dict):
        return ''

    return ', '.join(
        str(part).strip()
        for part in [
            delivery_address.get('raw_address'),
            delivery_address.get('street'),
            delivery_address.get('number'),
            delivery_address.get('complement'),
            delivery_address.get('neighborhood'),
            delivery_address.get('city'),
            delivery_address.get('state'),
            delivery_address.get('zip_code'),
        ]
        if str(part or '').strip()
    )


class DeliveryQuoteService:
    """Resolve and normalize delivery quotes from every supported input."""

    @staticmethod
    def calculate_dynamic_fee(store: Store, distance_km: Decimal = None) -> dict:
        metadata = store.metadata or {}
        base_fee = Decimal(str(metadata.get('delivery_base_fee', store.default_delivery_fee or '9.00')))
        fee_per_km = Decimal(str(metadata.get('delivery_fee_per_km', '1.00')))
        flat_km = Decimal(str(metadata.get('delivery_flat_km') or metadata.get('delivery_free_km') or '4.0'))
        max_km_raw = metadata.get('delivery_max_km') or metadata.get('max_delivery_distance_km')
        max_km = Decimal(str(max_km_raw)) if max_km_raw is not None else Decimal('16.0')
        max_fee_raw = metadata.get('delivery_max_fee')
        max_fee = Decimal(str(max_fee_raw)) if max_fee_raw not in (None, '') else None

        if distance_km is None:
            return {
                'fee': float(base_fee),
                'delivery_fee': float(base_fee),
                'is_valid': True,
                'available': True,
                'zone_name': 'Padrão',
                'estimated_minutes': 30,
                'estimated_days': 0,
                'distance_km': None,
                'calculation': 'dynamic',
            }

        distance = Decimal(str(distance_km))
        if max_fee is None and distance > max_km:
            return {
                'fee': None,
                'delivery_fee': None,
                'is_valid': False,
                'available': False,
                'zone_name': 'Fora da área',
                'estimated_minutes': None,
                'estimated_days': 0,
                'distance_km': float(distance),
                'calculation': 'out_of_range',
                'reason': 'out_of_range',
                'message': 'Distância acima de 16 km — entrar em contato para combinar frete',
            }

        if distance <= flat_km:
            fee = base_fee
            zone_name = 'Próximo'
        else:
            fee = base_fee + ((distance - flat_km) * fee_per_km)
            if distance <= 8:
                zone_name = 'Padrão'
            elif distance <= 12:
                zone_name = 'Distante'
            else:
                zone_name = 'Remoto'

        if max_fee is not None:
            fee = min(fee, max_fee)

        fee = fee.quantize(Decimal('0.01'))
        return {
            'fee': float(fee),
            'delivery_fee': float(fee),
            'is_valid': True,
            'available': True,
            'zone_name': zone_name,
            'estimated_minutes': int(15 + (float(distance) * 3)),
            'estimated_days': 0,
            'distance_km': float(distance),
            'calculation': 'dynamic',
        }

    @staticmethod
    def calculate_for_distance(store: Store, distance_km: Decimal = None, zip_code: str = None) -> dict:
        if distance_km is not None:
            logger.info("Calculating delivery fee for distance: %s km", distance_km)
            zones = StoreDeliveryZone.objects.filter(
                store=store,
                is_active=True,
                zone_type='custom_distance',
                min_km__isnull=False,
                max_km__isnull=False,
            ).order_by('min_km')

            for zone in zones:
                if zone.min_km <= distance_km < zone.max_km:
                    fee = zone.delivery_fee
                    if zone.fee_per_km:
                        fee += zone.fee_per_km * distance_km
                    return {
                        'fee': float(fee),
                        'delivery_fee': float(fee),
                        'is_valid': True,
                        'available': True,
                        'zone_id': str(zone.id),
                        'zone_name': zone.name,
                        'estimated_minutes': zone.estimated_minutes,
                        'estimated_days': zone.estimated_days,
                        'distance_km': float(distance_km),
                    }

        return DeliveryQuoteService.calculate_dynamic_fee(store, distance_km)

    @staticmethod
    def normalize(info: dict, route: dict = None) -> dict:
        payload = dict(info or {})
        route_payload = dict(route or {})

        def json_safe(value):
            if isinstance(value, Decimal):
                return float(value)
            return value

        fee = json_safe(payload.get('fee', payload.get('delivery_fee')))
        is_valid = payload.get('is_valid')
        if is_valid is None:
            is_valid = payload.get('available')
        if is_valid is None:
            is_valid = payload.get('is_within_area')
        if is_valid is None:
            is_valid = fee is not None

        zone = payload.get('zone') if isinstance(payload.get('zone'), dict) else {}
        zone_name = payload.get('zone_name') or payload.get('delivery_zone') or zone.get('name')
        distance_km = json_safe(payload.get('distance_km', route_payload.get('distance_km')))
        duration_minutes = json_safe(payload.get('duration_minutes', route_payload.get('duration_minutes')))
        estimated_minutes = json_safe(payload.get('estimated_minutes') or duration_minutes)
        reason = payload.get('reason') or (None if is_valid else payload.get('calculation') or 'unavailable')

        stable = {
            'is_valid': bool(is_valid),
            'valid': bool(is_valid),
            'available': bool(is_valid),
            'fee': fee,
            'delivery_fee': fee,
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'estimated_minutes': estimated_minutes,
            'zone_name': zone_name,
            'delivery_zone': zone_name,
            'zone': zone or ({'name': zone_name} if zone_name else None),
            'message': payload.get('message') or ('Entrega disponível' if is_valid else 'Entrega indisponível'),
            'reason': reason,
            'calculation': payload.get('calculation'),
            'polyline': payload.get('polyline') or route_payload.get('polyline'),
            'provider': payload.get('provider') or route_payload.get('provider') or 'internal_geo',
            'rain_surcharge_applied': bool(payload.get('rain_surcharge_applied', False)),
        }
        payload.update({k: v for k, v in stable.items() if v is not None})
        return payload

    @staticmethod
    def calculate_for_payload(store: Store, delivery_payload: dict) -> dict:
        payload = dict(delivery_payload or {})
        address = dict(payload.get('address') or {})
        lat = address.get('lat') or address.get('latitude')
        lng = address.get('lng') or address.get('longitude')
        address_text = delivery_address_text(address)

        if lat is not None and lng is not None:
            from apps.stores.services.geo.service import geo_service

            return geo_service.calculate_delivery_fee(
                store=store,
                customer_lat=float(lat),
                customer_lng=float(lng),
                customer_address_text=address_text,
            )

        if address_text:
            from apps.stores.services.geo.service import geo_service

            return geo_service.calculate_delivery_fee(
                store=store,
                destination_address=address_text,
                customer_address_text=address_text,
            )

        distance = payload.get('distance_km')
        if distance:
            return DeliveryQuoteService.calculate_for_distance(
                store,
                distance_km=Decimal(str(distance)),
                zip_code=payload.get('zip_code'),
            )

        return DeliveryQuoteService.calculate_for_distance(
            store,
            distance_km=None,
            zip_code=payload.get('zip_code'),
        )


delivery_quote_service = DeliveryQuoteService()
