"""Backfill das colunas do BI Fase 2 no histórico.

- StoreOrder.source ← metadata.source (whatsapp*/dashboard*→pdv; senão web)
- StoreOrder.delivery_lat/lng ← delivery_address JSON
- StoreOrderItem.unit_cost ← cost_price ATUAL do produto (aproximação p/ o
  legado; dali em diante o snapshot no create garante exatidão)
- StoreCouponRedemption ← pedidos com coupon_code (match case-insensitive)

Idempotente: só preenche o que está vazio.
"""
from django.core.management.base import BaseCommand
from django.db.models import OuterRef, Subquery


class Command(BaseCommand):
    help = 'Preenche source, lat/lng, unit_cost e resgates de cupom no histórico'

    def handle(self, *args, **options):
        from apps.stores.models import (
            StoreCoupon, StoreCouponRedemption, StoreOrder, StoreOrderItem,
        )

        # source
        filled_source = 0
        for order in StoreOrder.objects.filter(source='').only('id', 'metadata').iterator():
            raw = str((order.metadata or {}).get('source') or '')
            source = next(
                (canonical for prefix, canonical in StoreOrder._SOURCE_MAP_PREFIXES if raw.startswith(prefix)),
                'web',
            )
            StoreOrder.objects.filter(pk=order.pk).update(source=source)
            filled_source += 1
        self.stdout.write(f'source: {filled_source} pedidos preenchidos')

        # lat/lng
        filled_geo = 0
        geo_qs = StoreOrder.objects.filter(delivery_lat__isnull=True).exclude(delivery_address={})
        for order in geo_qs.only('id', 'delivery_address').iterator():
            addr = order.delivery_address or {}
            lat, lng = addr.get('lat'), addr.get('lng')
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                StoreOrder.objects.filter(pk=order.pk).update(delivery_lat=lat, delivery_lng=lng)
                filled_geo += 1
        self.stdout.write(f'lat/lng: {filled_geo} pedidos preenchidos')

        # unit_cost (aproximação: custo atual) — update com join não é
        # permitido, então o custo entra via Subquery correlacionada.
        from apps.stores.models import StoreProduct
        cost_sq = StoreProduct.objects.filter(pk=OuterRef('product_id')).values('cost_price')[:1]
        updated_cost = StoreOrderItem.objects.filter(
            unit_cost__isnull=True,
            product__isnull=False,
            product__cost_price__gt=0,
        ).update(unit_cost=Subquery(cost_sq))
        self.stdout.write(f'unit_cost: {updated_cost} itens preenchidos (custo atual)')

        # resgates de cupom
        created_red = 0
        coupon_orders = StoreOrder.objects.exclude(coupon_code='').filter(coupon_redemption__isnull=True)
        for order in coupon_orders.select_related('store').iterator():
            coupon = StoreCoupon.objects.filter(
                store=order.store, code__iexact=order.coupon_code.strip()
            ).first()
            StoreCouponRedemption.objects.get_or_create(
                order=order,
                defaults={
                    'store': order.store,
                    'coupon': coupon,
                    'code': order.coupon_code.strip().upper(),
                    'amount': order.discount or 0,
                    'customer_phone': order.customer_phone or '',
                },
            )
            created_red += 1
        self.stdout.write(f'cupons: {created_red} resgates registrados')
        self.stdout.write(self.style.SUCCESS('Backfill BI Fase 2 concluído.'))
