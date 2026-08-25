"""
Unified Delivery Service — Single source of truth for delivery fee calculation.

TODAS as taxas de entrega devem passar por aqui. Nenhum outro serviço calcula fee diretamente.
Garante consistência entre WhatsApp, Admin, Checkout, Checkout Flow e Pedidos Futuros.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from apps.stores.models import Store

logger = logging.getLogger(__name__)


class UnifiedDeliveryService:
    """
    Serviço centralizado e único para cálculo de taxa de entrega.

    Replaces:
    - DeliveryQuoteService.calculate_for_payload()
    - GeoService.calculate_delivery_fee()
    - CheckoutService.calculate_delivery_fee_for_payload()
    - WhatsApp legacy fee calculation

    Entry point único: calculate_delivery_fee(store, address_or_coords)
    """

    @staticmethod
    def calculate_delivery_fee(
        store: Store,
        delivery_method: str = 'delivery',
        address_text: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        rain_surcharge: bool = False,
    ) -> Dict[str, Any]:
        """
        Calcula taxa de entrega com prioridade única.

        Entrada aceita:
        - address_text: "Rua das Flores, 123, Palmas, TO" → geocodifica via Google
        - lat/lng: -10.19, -48.30 → calcula distância direto

        Retorna:
        {
            'success': bool,
            'fee': Decimal,
            'distance_km': float,
            'duration_minutes': int,
            'method': str,  # 'delivery' ou 'pickup'
            'zone_name': str,  # Qual zona foi usada (fixa/db/dinâmica)
            'reason': str,  # Motivo se falhou (ex: "fora da área")
            'raw_address': str,  # Endereço parseado
            'address_components': dict,  # Componentes estruturados
        }
        """
        if delivery_method == 'pickup':
            return {
                'success': True,
                'fee': Decimal('0'),
                'distance_km': 0,
                'duration_minutes': 0,
                'method': 'pickup',
                'zone_name': 'Retirada',
                'reason': 'Pickup — sem taxa',
            }

        # 1. Resolver coords: address_text → geocodificar, ou usar lat/lng direto
        coords = UnifiedDeliveryService._resolve_coordinates(
            store=store,
            address_text=address_text,
            lat=lat,
            lng=lng,
        )

        if not coords.get('success'):
            return {
                'success': False,
                'fee': None,
                'reason': coords.get('error', 'Não consegui verificar o endereço'),
            }

        # 2. Calcular distância via Google Maps (ou Haversine como fallback)
        distance_info = UnifiedDeliveryService._calculate_distance_and_duration(
            store=store,
            dest_lat=coords['lat'],
            dest_lng=coords['lng'],
        )

        if not distance_info.get('success'):
            return {
                'success': False,
                'fee': None,
                'reason': distance_info.get('error', 'Não consegui calcular a distância'),
            }

        distance_km = distance_info['distance_km']
        duration_minutes = distance_info['duration_minutes']
        distancia_aproximada = bool(distance_info.get('aproximada'))

        # 3. Verificar se está dentro da área de entrega máxima
        max_km = store.metadata.get('delivery_max_km', 16)
        if distance_km > float(max_km):
            return {
                'success': False,
                'fee': None,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'distancia_aproximada': distancia_aproximada,
                'reason': f'Endereço muito longe ({distance_km:.1f} km, máximo {max_km} km)',
            }

        # 4. Procurar taxa em zonas fixas (metadata)
        fixed_zone_fee = UnifiedDeliveryService._check_fixed_price_zones(
            store=store,
            distance_km=distance_km,
            dest_lat=coords['lat'],
            dest_lng=coords['lng'],
        )

        if fixed_zone_fee is not None:
            fee = fixed_zone_fee['fee']
            if rain_surcharge:
                fee += Decimal('2.00')
            return {
                'success': True,
                'fee': float(fee),
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'distancia_aproximada': distancia_aproximada,
                'method': 'delivery',
                'zone_name': fixed_zone_fee['zone_name'],
                'reason': f'Zona fixa: {fixed_zone_fee["zone_name"]}',
                'raw_address': coords.get('formatted_address', ''),
                'address_components': coords.get('address_components', {}),
            }

        # 5. Procurar taxa em zonas do banco (distance_band)
        db_zone_fee = UnifiedDeliveryService._check_database_zones(
            store=store,
            distance_km=distance_km,
        )

        if db_zone_fee is not None:
            fee = db_zone_fee['fee']
            if rain_surcharge:
                fee += Decimal('2.00')
            return {
                'success': True,
                'fee': float(fee),
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'distancia_aproximada': distancia_aproximada,
                'method': 'delivery',
                'zone_name': db_zone_fee['zone_name'],
                'reason': f'Zona do banco: {db_zone_fee["zone_name"]}',
                'raw_address': coords.get('formatted_address', ''),
                'address_components': coords.get('address_components', {}),
            }

        # 6. Cálculo dinâmico (fallback padrão)
        dynamic_fee = UnifiedDeliveryService._calculate_dynamic_fee(
            store=store,
            distance_km=distance_km,
        )

        if rain_surcharge:
            dynamic_fee += Decimal('2.00')

        return {
            'success': True,
            'fee': float(dynamic_fee),
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'distancia_aproximada': distancia_aproximada,
            'method': 'delivery',
            'zone_name': 'Dinâmica',
            'reason': f'Cálculo dinâmico ({distance_km:.1f} km)',
            'raw_address': coords.get('formatted_address', ''),
            'address_components': coords.get('address_components', {}),
        }

    @staticmethod
    def _resolve_coordinates(
        store: Store,
        address_text: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Resolver endereço para coords."""
        if lat is not None and lng is not None:
            return {
                'success': True,
                'lat': lat,
                'lng': lng,
                'formatted_address': '',
                'address_components': {},
            }

        if address_text:
            from apps.stores.services.geo.service import GeoService
            try:
                geo = GeoService()
                result = geo.geocode(address_text)
                if result and isinstance(result, dict) and result.get('lat') and result.get('lng'):
                    return {
                        'success': True,
                        'lat': result.get('lat'),
                        'lng': result.get('lng'),
                        'formatted_address': result.get('formatted_address', ''),
                        'address_components': result.get('address_components', {}),
                    }
            except Exception as e:
                logger.error(f"[UnifiedDeliveryService] Geocoding error: {e}", exc_info=True)

        return {
            'success': False,
            'error': 'Endereço ou coordenadas não fornecidos',
        }

    @staticmethod
    def _calculate_distance_and_duration(
        store: Store,
        dest_lat: float,
        dest_lng: float,
    ) -> Dict[str, Any]:
        """Calcular distância e duração via Google Maps."""
        from apps.stores.services.geo.service import GeoService

        try:
            geo = GeoService()
            result = geo.calculate_route(
                origin=(store.latitude, store.longitude),
                destination=(dest_lat, dest_lng),
            )

            if result and isinstance(result, dict) and result.get('distance_km'):
                return {
                    'success': True,
                    'distance_km': result.get('distance_km', 0),
                    'duration_minutes': result.get('duration_minutes', 0),
                    # `fallback` = o Directions falhou e isto é haversine.
                    # Ninguém lia esta flag: a régua trocava de rota para linha
                    # reta em silêncio, e toda a área de entrega crescia junto.
                    'aproximada': bool(result.get('fallback')),
                }
        except Exception as e:
            logger.error(f"[UnifiedDeliveryService] Route calculation error: {e}", exc_info=True)

        return {
            'success': False,
            'error': 'Não consegui calcular a rota',
        }

    @staticmethod
    def _check_fixed_price_zones(
        store: Store,
        distance_km: float,
        dest_lat: float,
        dest_lng: float,
    ) -> Optional[Dict[str, Any]]:
        """Verificar zonas com preço fixo (metadata)."""
        metadata = store.metadata or {}
        fixed_zones = metadata.get('fixed_price_zones', [])

        for zone in fixed_zones:
            if zone.get('enabled', False):
                if distance_km <= zone.get('max_km', 999):
                    return {
                        'zone_name': zone.get('name', 'Zona Fixa'),
                        'fee': Decimal(str(zone.get('fee', '0'))),
                    }

        return None

    @staticmethod
    def _check_database_zones(
        store: Store,
        distance_km: float,
    ) -> Optional[Dict[str, Any]]:
        """Verificar zonas do banco (distance_band)."""
        from apps.stores.models import StoreDeliveryZone

        try:
            zones = StoreDeliveryZone.objects.filter(
                store=store,
                is_active=True,
                zone_type='distance_band',
            ).order_by('min_km')

            for zone in zones:
                if zone.matches_distance(distance_km):
                    fee = zone.calculate_fee(distance_km)
                    return {
                        'zone_name': zone.name,
                        'fee': fee,
                    }
        except Exception as e:
            logger.error(f"[UnifiedDeliveryService] Database zone check error: {e}")

        return None

    @staticmethod
    def _calculate_dynamic_fee(
        store: Store,
        distance_km: float,
    ) -> Decimal:
        """Calcular fee dinâmica (padrão)."""
        from apps.stores.services.delivery_quote_service import DeliveryQuoteService

        result = DeliveryQuoteService.calculate_dynamic_fee(
            store=store,
            distance_km=Decimal(str(distance_km)),
        )

        return Decimal(str(result.get('fee', '0')))
