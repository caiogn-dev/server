import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _telefone_e164(telefone: str) -> str:
    """Telefone do cliente em E.164, com o '+' que a Uber exige.

    Antes: `'+55' if not x.startswith('+55') else '' + x.lstrip('+')`.
    A precedência do `if` ternário faz o ramo verdadeiro devolver a string
    `'+55'` SOZINHA — todo pedido cujo telefone não começasse com `+55` (ou
    seja, praticamente todos, porque gravamos sem o '+') mandava o literal
    `+55` como telefone do cliente e do restaurante. O entregador nunca
    conseguiu ligar para ninguém.
    """
    from apps.core.utils import normalize_phone_number

    normalizado = normalize_phone_number(telefone or '')
    return f'+{normalizado}' if normalizado else ''


class UberDeliveryClient:
    """
    Wrapper for Uber Delivery API.
    Supports create delivery request, poll status, cancel request.
    Uses OAuth 2.0 Client Credentials flow for authentication.
    """

    def __init__(self):
        self.base_url = os.getenv(
            'UBER_API_BASE_URL',
            'https://api.uber.com/v1/deliveries'
        )
        self.client_id = os.getenv('UBER_API_KEY')
        self.client_secret = os.getenv('UBER_CLIENT_SECRET')
        self.customer_id = os.getenv('UBER_CUSTOMER_ID')
        self.token_url = 'https://auth.uber.com/oauth/v2/token'

        self._access_token = None
        self._token_expires_at = None

        if not all([self.client_id, self.client_secret, self.customer_id]):
            logger.warning("Uber API credentials not configured")

    def _get_access_token(self) -> str:
        """
        Get OAuth access token using Client Credentials flow.
        Cached until expiration.
        """
        if self._access_token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._access_token

        try:
            response = requests.post(
                self.token_url,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials',
                    'scope': 'direct.organizations',
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data['access_token']
            expires_in = data.get('expires_in', 2592000)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

            logger.info("Uber OAuth token obtained successfully")
            return self._access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Uber OAuth error: {str(e)}")
            raise

    def _headers(self) -> Dict[str, str]:
        """Return auth headers for Uber API."""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def create_delivery_request(
        self,
        pickup_address: str,
        dropoff_address: str,
        customer_phone: str,
        order_id: int,
        items: list = None,
    ) -> Dict:
        """
        Create a delivery request on Uber.

        Args:
            pickup_address: Store address (pickup location)
            dropoff_address: Customer address (delivery location)
            customer_phone: Customer phone number
            order_id: StoreOrder ID (for reference)
            items: List of item dicts with 'name', 'quantity'

        Returns:
            Dict with 'delivery_request_id', 'status', or raises exception
        """
        payload = {
            'customer_id': self.customer_id,
            'pickup': {
                'name': 'Restaurant',
                'address': pickup_address,
                'phone_number': _telefone_e164(customer_phone),
            },
            'dropoff': {
                'name': 'Customer',
                'address': dropoff_address,
                'phone_number': _telefone_e164(customer_phone),
            },
            'external_order_id': str(order_id),
            'items': items or [],
        }

        try:
            logger.info(f"Uber delivery request payload: {payload}")
            resp = requests.post(
                self.base_url,
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            logger.info(f"Uber API response status: {resp.status_code}")
            if not resp.ok:
                logger.error(f"Uber API response body: {resp.text}")
            resp.raise_for_status()
            data = resp.json()

            logger.info(
                f"Uber delivery request created: {data.get('delivery_request_id')} "
                f"for order {order_id}"
            )
            return {
                'delivery_request_id': data.get('delivery_request_id'),
                'status': data.get('status', 'pending'),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Uber API error creating delivery: {str(e)}")
            raise

    def poll_delivery_status(
        self,
        delivery_request_id: str,
    ) -> Dict:
        """
        Poll Uber for delivery status.

        Args:
            delivery_request_id: Uber's delivery request ID

        Returns:
            Dict with 'status', 'driver' (if assigned), or raises exception
        """
        url = f'{self.base_url}/{delivery_request_id}'

        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            result = {'status': data.get('status', 'pending')}

            # If driver assigned, extract driver details
            if data.get('driver'):
                driver = data['driver']
                result['driver'] = {
                    'id': driver.get('id'),
                    'name': driver.get('name'),
                    'phone': driver.get('phone'),
                    'vehicle': driver.get('vehicle', {}).get('display_name'),
                    'rating': driver.get('rating'),
                    'eta_minutes': driver.get('eta', {}).get('estimated_minutes_to_pickup'),
                    'pickup_instructions': data.get('special_instructions', ''),
                }

            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Uber API error polling status: {str(e)}")
            raise

    def cancel_delivery_request(
        self,
        delivery_request_id: str,
    ) -> Dict:
        """
        Cancel a delivery request on Uber.

        Args:
            delivery_request_id: Uber's delivery request ID

        Returns:
            Dict with 'status': 'cancelled'
        """
        url = f'{self.base_url}/{delivery_request_id}/cancel'

        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()

            logger.info(f"Uber delivery request cancelled: {delivery_request_id}")
            return {'status': 'cancelled'}
        except requests.exceptions.RequestException as e:
            logger.error(f"Uber API error cancelling delivery: {str(e)}")
            raise
