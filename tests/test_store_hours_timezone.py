from datetime import datetime
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.stores.models import Store


class StoreBusinessHoursTimezoneTest(SimpleTestCase):
    def _make_store(self, hours):
        store = Store()
        store.operating_hours = hours
        return store

    def test_is_open_uses_local_time_not_utc(self):
        store = self._make_store({
            'monday': {'open': '09:00', 'close': '18:00'},
        })
        local_now = timezone.make_aware(
            datetime(2026, 4, 27, 16, 0, 0),
            timezone.get_current_timezone(),
        )

        with patch('apps.stores.models.base.timezone.localtime', return_value=local_now):
            self.assertTrue(store.is_open())

    def test_is_open_supports_start_end_keys(self):
        store = self._make_store({
            'monday': {'start': '09:00', 'end': '18:00'},
        })
        local_now = timezone.make_aware(
            datetime(2026, 4, 27, 16, 0, 0),
            timezone.get_current_timezone(),
        )

        with patch('apps.stores.models.base.timezone.localtime', return_value=local_now):
            self.assertTrue(store.is_open())
