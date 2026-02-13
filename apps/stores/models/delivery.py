"""
Store delivery zone model.
"""
import uuid
from decimal import Decimal
from django.db import models


class StoreDeliveryZone(models.Model):
    """Delivery zones for a store with flexible zone definitions."""

    class ZoneType(models.TextChoices):
        DISTANCE_BAND = 'distance_band', 'Distance Band'
        CUSTOM_DISTANCE = 'custom_distance', 'Custom Distance Range'
        ZIP_RANGE = 'zip_range', 'ZIP Code Range'
        POLYGON = 'polygon', 'Custom Polygon'
        TIME_BASED = 'time_based', 'Time-based (Isochrone)'

    DISTANCE_BAND_CHOICES = [
        ('0_2', '0-2 km'),
        ('2_5', '2-5 km'),
        ('5_8', '5-8 km'),
        ('8_12', '8-12 km'),
        ('12_15', '12-15 km'),
        ('15_20', '15-20 km'),
        ('20_30', '20-30 km'),
        ('30_plus', '30+ km'),
    ]

    DISTANCE_BAND_RANGES = {
        '0_2': (Decimal('0.00'), Decimal('2.00')),
        '2_5': (Decimal('2.00'), Decimal('5.00')),
        '5_8': (Decimal('5.00'), Decimal('8.00')),
        '8_12': (Decimal('8.00'), Decimal('12.00')),
        '12_15': (Decimal('12.00'), Decimal('15.00')),
        '15_20': (Decimal('15.00'), Decimal('20.00')),
        '20_30': (Decimal('20.00'), Decimal('30.00')),
        '30_plus': (Decimal('30.00'), Decimal('999.00')),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='delivery_zones'
    )
    name = models.CharField(max_length=100)
    zone_type = models.CharField(
        max_length=20,
        choices=ZoneType.choices,
        default=ZoneType.DISTANCE_BAND
    )
    distance_band = models.CharField(max_length=10, choices=DISTANCE_BAND_CHOICES, blank=True, null=True)
    min_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    max_km = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    zip_code_start = models.CharField(max_length=8, blank=True, null=True)
    zip_code_end = models.CharField(max_length=8, blank=True, null=True)
    min_minutes = models.PositiveIntegerField(blank=True, null=True)
    max_minutes = models.PositiveIntegerField(blank=True, null=True)
    polygon_coordinates = models.JSONField(default=list, blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    min_fee = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fee_per_km = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    estimated_minutes = models.PositiveIntegerField(default=30)
    estimated_days = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=7, default='#722F37')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_delivery_zones'
        verbose_name = 'Delivery Zone'
        verbose_name_plural = 'Delivery Zones'
        ordering = ['store', 'sort_order', 'distance_band', 'min_km']

    def __str__(self):
        return f"{self.store.name} - {self.name}"

    def get_distance_range(self):
        if self.distance_band:
            return self.DISTANCE_BAND_RANGES.get(self.distance_band, (None, None))
        return (self.min_km, self.max_km)

    def matches_distance(self, distance_km):
        min_km, max_km = self.get_distance_range()
        if min_km is None or max_km is None:
            return False
        return min_km <= Decimal(str(distance_km)) < max_km

    def matches_zip_code(self, zip_code):
        if not self.zip_code_start or not self.zip_code_end:
            return False
        clean_zip = zip_code.replace('-', '').replace('.', '')
        return self.zip_code_start <= clean_zip <= self.zip_code_end

    def calculate_fee(self, distance_km=None):
        fee = self.delivery_fee
        if self.fee_per_km and distance_km:
            fee += self.fee_per_km * Decimal(str(distance_km))
        if self.min_fee:
            fee = max(fee, self.min_fee)
        return fee
