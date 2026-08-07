"""BI Fase 2 — colunas denormalizadas para relatórios exatos.

- StoreOrder.source derivado no create (metadata.source → whatsapp/pdv; sem
  fonte = web) e indexável.
- StoreOrder.delivery_lat/lng copiados do delivery_address JSON no create.
- StoreOrderItem.unit_cost = snapshot do cost_price do produto no momento da
  venda (margem histórica não muda quando o custo é editado depois).
- StoreOrder.cancel_reason estruturado (cancel_order gravava só em notes).
- StoreCouponRedemption: trilha cupom×pedido.
- Comando backfill_bi_fase2 preenche o histórico.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.stores.models import (
    Store,
    StoreCategory,
    StoreCoupon,
    StoreCouponRedemption,
    StoreOrder,
    StoreOrderItem,
    StoreProduct,
)

User = get_user_model()


class BiFase2Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner-f2', email='f2@x.com', password='x')
        self.store = Store.objects.create(name='Loja F2', slug='loja-f2', owner=self.owner, status='active')

    def order(self, **kwargs):
        defaults = dict(
            store=self.store, customer_name='C', customer_phone='5563999880001',
            subtotal=Decimal('10'), total=Decimal('10'),
        )
        defaults.update(kwargs)
        return StoreOrder.objects.create(**defaults)


class SourceColumnTest(BiFase2Base):
    def test_source_derivado_do_metadata_no_create(self):
        self.assertEqual(self.order(metadata={'source': 'whatsapp'}).source, 'whatsapp')
        self.assertEqual(self.order(metadata={'source': 'whatsapp_automation'}).source, 'whatsapp')
        self.assertEqual(self.order(metadata={'source': 'dashboard_order_create'}).source, 'pdv')
        self.assertEqual(self.order(metadata={'source': 'dashboard'}).source, 'pdv')
        self.assertEqual(self.order().source, 'web')

    def test_source_explicito_nao_e_sobrescrito(self):
        self.assertEqual(self.order(source='app').source, 'app')


class GeoColumnsTest(BiFase2Base):
    def test_lat_lng_copiados_do_delivery_address(self):
        o = self.order(delivery_address={'street': 'Rua A', 'lat': -10.25, 'lng': -48.31})
        self.assertAlmostEqual(float(o.delivery_lat), -10.25)
        self.assertAlmostEqual(float(o.delivery_lng), -48.31)

    def test_sem_coordenada_fica_null(self):
        o = self.order(delivery_address={'street': 'Rua B'})
        self.assertIsNone(o.delivery_lat)
        self.assertIsNone(o.delivery_lng)


class UnitCostSnapshotTest(BiFase2Base):
    def test_item_snapshota_cost_price_do_produto(self):
        cat = StoreCategory.objects.create(store=self.store, name='C', slug='c-f2')
        p = StoreProduct.objects.create(
            store=self.store, category=cat, name='Prato', slug='prato-f2',
            price=Decimal('30'), cost_price=Decimal('12'),
        )
        o = self.order()
        item = StoreOrderItem.objects.create(
            order=o, product=p, product_name='Prato',
            unit_price=Decimal('30'), quantity=2, subtotal=Decimal('60'),
        )
        self.assertEqual(item.unit_cost, Decimal('12'))
        # Editar o custo do produto DEPOIS não muda o histórico
        p.cost_price = Decimal('99')
        p.save(update_fields=['cost_price'])
        item.refresh_from_db()
        self.assertEqual(item.unit_cost, Decimal('12'))

    def test_produto_sem_custo_fica_null(self):
        o = self.order()
        item = StoreOrderItem.objects.create(
            order=o, product_name='Avulso', unit_price=Decimal('10'), quantity=1, subtotal=Decimal('10'),
        )
        self.assertIsNone(item.unit_cost)


class CancelReasonTest(BiFase2Base):
    def test_cancel_order_grava_motivo_estruturado(self):
        from apps.stores.services.order_service import OrderService
        o = self.order(status='pending')
        OrderService().cancel_order(o, reason='Cliente desistiu', restore_stock=False)
        o.refresh_from_db()
        self.assertEqual(o.cancel_reason, 'Cliente desistiu')
        self.assertEqual(o.status, 'cancelled')


class CouponRedemptionTest(BiFase2Base):
    def test_record_redemption_e_idempotente(self):
        from apps.stores.services.checkout_service import CheckoutService
        coupon = StoreCoupon.objects.create(
            store=self.store, code='FASE2', discount_type='fixed', discount_value=Decimal('5'),
            valid_from='2020-01-01T00:00:00Z', valid_until='2030-01-01T00:00:00Z',
        )
        o = self.order(coupon_code='FASE2', discount=Decimal('5'))
        CheckoutService.record_coupon_redemption(o, coupon)
        CheckoutService.record_coupon_redemption(o, coupon)  # repetido não duplica
        red = StoreCouponRedemption.objects.get(order=o)
        self.assertEqual(red.coupon_id, coupon.id)
        self.assertEqual(red.code, 'FASE2')
        self.assertEqual(red.amount, Decimal('5'))
        # Escopado ao cupom do teste: o count() global media resgates de outras
        # suítes no banco compartilhado e falhava sozinho (19 != 1). O que o
        # teste quer provar é a idempotência — dois registros do MESMO resgate
        # não podem virar duas linhas.
        self.assertEqual(
            StoreCouponRedemption.objects.filter(coupon=coupon).count(), 1,
        )


class BackfillCommandTest(BiFase2Base):
    def test_backfill_preenche_legado(self):
        cat = StoreCategory.objects.create(store=self.store, name='C', slug='c-bf')
        p = StoreProduct.objects.create(
            store=self.store, category=cat, name='X', slug='x-bf',
            price=Decimal('20'), cost_price=Decimal('8'),
        )
        coupon = StoreCoupon.objects.create(
            store=self.store, code='LEGADO', discount_type='fixed', discount_value=Decimal('3'),
            valid_from='2020-01-01T00:00:00Z', valid_until='2030-01-01T00:00:00Z',
        )
        o = self.order(
            metadata={'source': 'whatsapp'},
            delivery_address={'lat': -10.1, 'lng': -48.3},
            coupon_code='legado', discount=Decimal('3'),
        )
        item = StoreOrderItem.objects.create(
            order=o, product=p, product_name='X', unit_price=Decimal('20'), quantity=1, subtotal=Decimal('20'),
        )
        # Simula legado: zera as colunas novas direto no banco
        StoreOrder.objects.filter(pk=o.pk).update(source='', delivery_lat=None, delivery_lng=None)
        StoreOrderItem.objects.filter(pk=item.pk).update(unit_cost=None)

        call_command('backfill_bi_fase2', stdout=StringIO())

        o.refresh_from_db(); item.refresh_from_db()
        self.assertEqual(o.source, 'whatsapp')
        self.assertAlmostEqual(float(o.delivery_lat), -10.1)
        self.assertEqual(item.unit_cost, Decimal('8'))
        red = StoreCouponRedemption.objects.get(order=o)
        self.assertEqual(red.coupon_id, coupon.id)  # match case-insensitive
