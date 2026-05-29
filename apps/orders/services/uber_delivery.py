import os
import logging
import requests
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class UberDeliveryClient:
    """
    Wrapper for Uber Delivery API.
    Supports create delivery request, poll status, cancel request.
    """

    def __init__(self):
        self.base_url = os.getenv(
            'UBER_API_BASE_URL',
            'https://api.uber.com/v1/deliveries'
        )
        self.api_key = os.getenv('UBER_API_KEY')
        self.customer_id = os.getenv('UBER_CUSTOMER_ID')

        if not all([self.api_key, self.customer_id]):
            logger.warning("Uber API credentials not configured")

    def _headers(self) -> Dict[str, str]:
        """Return auth headers for Uber API."""
        return {
            'Authorization': f'Bearer {self.api_key}',
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
            items: List of item dicts with 'name', 'qty'

        Returns:
            Dict with 'delivery_request_id', 'status', or raises exception
        """
        payload = {
            'customer_id': self.customer_id,
            'pickup_address': pickup_address,
            'dropoff_address': dropoff_address,
            'customer_phone': customer_phone,
            'external_order_id': str(order_id),
            'items': items or [],
        }

        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
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
