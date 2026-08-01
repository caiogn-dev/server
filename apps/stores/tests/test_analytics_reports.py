"""
Testes dos endpoints de analytics/BI (Fase 1 do plano de relatórios):
heatmap dia×hora, curva ABC, canais, geografia, SLA, financeiro,
RFM/inativos, funil do bot e avaliações.

Todos os valores monetários seguem a regra canônica de receita:
payment_status='paid' (RevenueReportView). Datas de teste são fixadas em
horário local (America/Sao_Paulo) para o heatmap não depender do fuso.
"""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store,
    StoreCustomer,
    StoreOrder,
    StoreOrderItem,
    StorePayment,
    StorePaymentGateway,
    StoreProduct,
    StoreCategory,
    StoreReview,
)
from apps.automation.models import CompanyProfile, CustomerSession

User = get_user_model()

TZ = ZoneInfo('America/Sao_Paulo')
BASE = '/api/v1/stores/reports/'


def local_dt(year, month, day, hour):
    return timezone.datetime(year, month, day, hour, 30, tzinfo=TZ)


class AnalyticsReportsBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='o@x.com', password='x')
        self.other = User.objects.create_user(username='other', email='i@x.com', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner, status='active')
        self.other_store = Store.objects.create(name='Outra', slug='outra', owner=self.other, status='active')
        self.client.force_authenticate(self.owner)

    def _get(self, path, **params):
        params.setdefault('store', self.store.slug)
        return self.client.get(f'{BASE}{path}', params)

    def order(self, total='100.00', paid=True, store=None, created=None, **kwargs):
        o = StoreOrder.objects.create(
            store=store or self.store,
            customer_name='Cliente',
            customer_phone=kwargs.pop('phone', '5563999000001'),
            subtotal=Decimal(total),
            total=Decimal(total),
            payment_status='paid' if paid else 'pending',
            status=kwargs.pop('status', 'delivered'),
            **kwargs,
        )
        if created is not None:
            StoreOrder.objects.filter(pk=o.pk).update(created_at=created)
            o.refresh_from_db()
        return o


class HeatmapReportTest(AnalyticsReportsBase):
    def test_cells_and_peak(self):
        d = timezone.now().astimezone(TZ) - timedelta(days=3)
        # 2 pedidos no mesmo slot, 1 em outro
        self.order(total='50.00', created=d.replace(hour=19, minute=10))
        self.order(total='30.00', created=d.replace(hour=19, minute=40))
        self.order(total='20.00', created=d.replace(hour=11, minute=5))
        resp = self._get('heatmap/')
        self.assertEqual(resp.status_code, 200, resp.content)
        cells = {(c['weekday'], c['hour']): c for c in resp.data['cells']}
        wd = d.weekday()
        self.assertEqual(cells[(wd, 19)]['orders'], 2)
        self.assertAlmostEqual(float(cells[(wd, 19)]['revenue']), 80.0)
        self.assertEqual(cells[(wd, 11)]['orders'], 1)
        self.assertEqual(resp.data['peak']['hour'], 19)

    def test_ignores_unpaid_and_other_store(self):
        d = timezone.now().astimezone(TZ) - timedelta(days=2)
        self.order(total='10.00', paid=False, created=d.replace(hour=9))
        self.order(total='10.00', store=self.other_store, created=d.replace(hour=9))
        resp = self._get('heatmap/')
        self.assertEqual(resp.data['cells'], [])

    def test_requires_store(self):
        resp = self.client.get(f'{BASE}heatmap/')
        self.assertEqual(resp.status_code, 400)


class AbcReportTest(AnalyticsReportsBase):
    def test_abc_classes_and_cumulative(self):
        cat = StoreCategory.objects.create(store=self.store, name='Cat', slug='cat')
        p1 = StoreProduct.objects.create(store=self.store, category=cat, name='Top', slug='top', price=Decimal('10'))
        p2 = StoreProduct.objects.create(store=self.store, category=cat, name='Meio', slug='meio', price=Decimal('10'))
        p3 = StoreProduct.objects.create(store=self.store, category=cat, name='Cauda', slug='cauda', price=Decimal('10'))
        o = self.order(total='1000.00')
        StoreOrderItem.objects.create(order=o, product=p1, product_name='Top', unit_price=Decimal('10'), quantity=80, subtotal=Decimal('800'))
        StoreOrderItem.objects.create(order=o, product=p2, product_name='Meio', unit_price=Decimal('10'), quantity=15, subtotal=Decimal('150'))
        StoreOrderItem.objects.create(order=o, product=p3, product_name='Cauda', unit_price=Decimal('10'), quantity=5, subtotal=Decimal('50'))
        resp = self._get('abc/')
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.data['products']
        self.assertEqual(rows[0]['product_name'], 'Top')
        self.assertEqual(rows[0]['abc_class'], 'A')
        self.assertAlmostEqual(rows[0]['cumulative_pct'], 80.0, places=1)
        self.assertEqual(rows[1]['abc_class'], 'B')   # 95% acumulado
        self.assertEqual(rows[2]['abc_class'], 'C')
        self.assertAlmostEqual(float(resp.data['summary']['total_revenue']), 1000.0)


class ChannelsReportTest(AnalyticsReportsBase):
    def test_source_mapping_and_dimensions(self):
        self.order(total='100.00', metadata={'source': 'whatsapp'}, payment_method='pix', delivery_method='delivery')
        self.order(total='60.00', metadata={'source': 'dashboard_order_create'}, payment_method='cash', delivery_method='pickup')
        self.order(total='40.00', payment_method='pix', delivery_method='delivery')  # sem source => web
        resp = self._get('channels/')
        self.assertEqual(resp.status_code, 200, resp.content)
        by_source = {r['channel']: r for r in resp.data['by_source']}
        self.assertEqual(by_source['bot']['orders'], 1)
        self.assertEqual(by_source['pdv']['orders'], 1)
        self.assertEqual(by_source['web']['orders'], 1)
        self.assertAlmostEqual(float(by_source['bot']['revenue']), 100.0)
        by_pay = {r['payment_method']: r for r in resp.data['by_payment_method']}
        self.assertEqual(by_pay['pix']['orders'], 2)
        by_del = {r['delivery_method']: r for r in resp.data['by_delivery_method']}
        self.assertEqual(by_del['pickup']['orders'], 1)


class GeographyReportTest(AnalyticsReportsBase):
    def test_neighborhoods_bands_points(self):
        self.order(
            total='100.00',
            delivery_method='delivery',
            delivery_address={'neighborhood': 'Centro', 'city': 'Palmas', 'lat': -10.1, 'lng': -48.3},
            metadata={'delivery_quote': {'distance_km': 1.2, 'zone_name': 'Zona 1'}},
        )
        self.order(
            total='50.00',
            delivery_method='delivery',
            delivery_address={'neighborhood': 'centro ', 'city': 'Palmas'},
            metadata={'delivery_quote': {'distance_km': 5.0, 'zone_name': 'Zona 2'}},
        )
        resp = self._get('geography/')
        self.assertEqual(resp.status_code, 200, resp.content)
        hoods = {r['name']: r for r in resp.data['neighborhoods']}
        self.assertIn('Centro', hoods)          # normalizado (trim/título)
        self.assertEqual(hoods['Centro']['orders'], 2)
        bands = {r['band']: r['orders'] for r in resp.data['distance_bands']}
        self.assertEqual(bands.get('0-2 km'), 1)
        self.assertEqual(bands.get('4-6 km'), 1)
        self.assertEqual(len(resp.data['points']), 1)
        zones = {r['name']: r['orders'] for r in resp.data['zones']}
        self.assertEqual(zones['Zona 1'], 1)


class SlaReportTest(AnalyticsReportsBase):
    def test_stage_durations(self):
        base = timezone.now() - timedelta(days=1)
        o = self.order(total='80.00', delivery_method='delivery', created=base)
        StoreOrder.objects.filter(pk=o.pk).update(
            confirmed_at=base + timedelta(minutes=5),
            ready_at=base + timedelta(minutes=25),
            out_for_delivery_at=base + timedelta(minutes=30),
            delivered_at=base + timedelta(minutes=50),
        )
        resp = self._get('sla/')
        self.assertEqual(resp.status_code, 200, resp.content)
        stages = {s['stage']: s for s in resp.data['stages']}
        self.assertAlmostEqual(stages['confirmacao']['avg_minutes'], 5.0, places=1)
        self.assertAlmostEqual(stages['preparo']['avg_minutes'], 20.0, places=1)
        self.assertAlmostEqual(stages['entrega']['avg_minutes'], 20.0, places=1)
        self.assertAlmostEqual(stages['total']['avg_minutes'], 50.0, places=1)
        self.assertEqual(stages['total']['count'], 1)


class FinanceReportTest(AnalyticsReportsBase):
    def test_gross_fee_net(self):
        o = self.order(total='100.00')
        gateway = StorePaymentGateway.objects.create(
            store=self.store, name='mercadopago', gateway_type='mercadopago',
        )
        StorePayment.objects.create(
            store=self.store, order=o, gateway=gateway, payment_id='mp-1',
            status='completed', amount=Decimal('100.00'), fee=Decimal('4.99'),
            net_amount=Decimal('95.01'), payment_method='pix',
        )
        resp = self._get('finance/')
        self.assertEqual(resp.status_code, 200, resp.content)
        s = resp.data['summary']
        self.assertAlmostEqual(float(s['gross']), 100.0)
        self.assertAlmostEqual(float(s['fees']), 4.99)
        self.assertAlmostEqual(float(s['net']), 95.01)
        gw = {r['gateway']: r for r in resp.data['by_gateway']}
        self.assertAlmostEqual(float(gw['mercadopago']['net']), 95.01)


class RfmReportTest(AnalyticsReportsBase):
    def _cust(self, tag, orders, spent, days_ago):
        u = User.objects.create_user(username=f'u{tag}', email=f'{tag}@x.com', password='x')
        return StoreCustomer.objects.create(
            store=self.store, user=u, phone=f'55639990{tag}',
            total_orders=orders, total_spent=Decimal(spent),
            last_order_at=timezone.now() - timedelta(days=days_ago) if days_ago is not None else None,
        )

    def test_segments_and_inactive_list(self):
        self._cust('01', 6, '600.00', 10)    # campeão
        self._cust('02', 3, '200.00', 45)    # leal
        self._cust('03', 2, '90.00', 80)     # em risco
        self._cust('04', 1, '30.00', 200)    # perdido
        self._cust('05', 1, '40.00', 15)     # novo
        resp = self._get('rfm/')
        self.assertEqual(resp.status_code, 200, resp.content)
        seg = {r['segment']: r['count'] for r in resp.data['segments']}
        self.assertEqual(seg['campeoes'], 1)
        self.assertEqual(seg['leais'], 1)
        self.assertEqual(seg['em_risco'], 1)
        self.assertEqual(seg['perdidos'], 1)
        self.assertEqual(seg['novos'], 1)
        inactive = resp.data['inactive']
        self.assertTrue(any(c['days_since'] >= 60 for c in inactive))
        self.assertTrue(all('phone' in c for c in inactive))


class BotFunnelReportTest(AnalyticsReportsBase):
    def test_funnel_and_conversion(self):
        profile, _ = CompanyProfile.objects.get_or_create(store=self.store)
        o = self.order(total='70.00')
        CustomerSession.objects.create(company=profile, session_id='s1', phone_number='1', status='order_placed', order=o)
        CustomerSession.objects.create(company=profile, session_id='s2', phone_number='2', status='cart_abandoned')
        CustomerSession.objects.create(company=profile, session_id='s3', phone_number='3', status='active')
        resp = self._get('bot-funnel/')
        self.assertEqual(resp.status_code, 200, resp.content)
        funnel = {r['status']: r['count'] for r in resp.data['funnel']}
        self.assertEqual(funnel['order_placed'], 1)
        self.assertEqual(funnel['cart_abandoned'], 1)
        conv = resp.data['conversion']
        self.assertEqual(conv['sessions'], 3)
        self.assertEqual(conv['with_order'], 1)
        self.assertAlmostEqual(conv['rate'], 33.3, places=1)


class ReviewsReportTest(AnalyticsReportsBase):
    def test_summary_distribution_recent(self):
        for rating in (5, 5, 3):
            o = self.order(total='10.00', phone=f'5563999111{rating}{timezone.now().microsecond}')
            StoreReview.objects.create(store=self.store, order=o, rating=rating, comment=f'nota {rating}', customer_name='C')
        resp = self._get('reviews/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['summary']['count'], 3)
        self.assertAlmostEqual(resp.data['summary']['avg_rating'], 4.33, places=1)
        dist = {r['rating']: r['count'] for r in resp.data['distribution']}
        self.assertEqual(dist[5], 2)
        self.assertEqual(dist[3], 1)
        self.assertEqual(len(resp.data['recent']), 3)


class CouponsReportTest(AnalyticsReportsBase):
    def test_roi_per_code(self):
        self.order(total='90.00', coupon_code='BEMVINDO', discount=Decimal('10.00'))
        self.order(total='45.00', coupon_code='bemvindo', discount=Decimal('5.00'))
        self.order(total='100.00')  # sem cupom
        resp = self._get('coupons/')
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = {r['code']: r for r in resp.data['coupons']}
        self.assertEqual(rows['BEMVINDO']['orders'], 2)   # case-insensitive
        self.assertAlmostEqual(float(rows['BEMVINDO']['discount_total']), 15.0)
        self.assertAlmostEqual(float(rows['BEMVINDO']['revenue']), 135.0)
        s = resp.data['summary']
        self.assertEqual(s['orders_with_coupon'], 2)
        self.assertAlmostEqual(s['coupon_usage_pct'], 66.7, places=1)


class BasketReportTest(AnalyticsReportsBase):
    def test_top_pairs(self):
        for i in range(2):
            o = self.order(total='50.00', phone=f'55639991n{i}')
            StoreOrderItem.objects.create(order=o, product_name='Salada', unit_price=Decimal('30'), quantity=1, subtotal=Decimal('30'))
            StoreOrderItem.objects.create(order=o, product_name='Suco', unit_price=Decimal('10'), quantity=1, subtotal=Decimal('10'))
        o = self.order(total='30.00')
        StoreOrderItem.objects.create(order=o, product_name='Salada', unit_price=Decimal('30'), quantity=1, subtotal=Decimal('30'))
        resp = self._get('basket/')
        self.assertEqual(resp.status_code, 200, resp.content)
        top = resp.data['pairs'][0]
        self.assertEqual({top['product_a'], top['product_b']}, {'Salada', 'Suco'})
        self.assertEqual(top['orders_together'], 2)


class CancellationsReportTest(AnalyticsReportsBase):
    def test_rate_and_lost_value(self):
        self.order(total='100.00')
        o = self.order(total='60.00', paid=False, status='cancelled')
        StoreOrder.objects.filter(pk=o.pk).update(cancelled_at=timezone.now())
        resp = self._get('cancellations/')
        self.assertEqual(resp.status_code, 200, resp.content)
        s = resp.data['summary']
        self.assertEqual(s['cancelled'], 1)
        self.assertEqual(s['total_orders'], 2)
        self.assertAlmostEqual(s['rate'], 50.0)
        self.assertAlmostEqual(float(s['lost_value']), 60.0)


class SchedulingReportTest(AnalyticsReportsBase):
    def test_by_date_and_slot(self):
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        self.order(total='50.00', scheduled_date=tomorrow, scheduled_time='10:00-11:00')
        self.order(total='30.00', scheduled_date=tomorrow, scheduled_time='10:00-11:00', phone='5563999333')
        resp = self._get('scheduling/')
        self.assertEqual(resp.status_code, 200, resp.content)
        days = {str(r['date']): r for r in resp.data['by_date']}
        self.assertEqual(days[str(tomorrow)]['orders'], 2)
        slots = {r['slot']: r['orders'] for r in resp.data['by_slot']}
        self.assertEqual(slots['10:00-11:00'], 2)


class CashHistoryReportTest(AnalyticsReportsBase):
    def test_closed_sessions_with_difference(self):
        from apps.stores.models import StoreCashSession
        s = StoreCashSession.objects.create(
            store=self.store, status='closed', opening_amount=Decimal('100.00'),
            opened_by=self.owner, closed_by=self.owner,
            counted_amount=Decimal('480.00'), expected_amount=Decimal('500.00'),
            difference=Decimal('-20.00'), closed_at=timezone.now(),
        )
        StoreCashSession.objects.filter(pk=s.pk).update(opened_at=timezone.now() - timedelta(hours=8))
        resp = self._get('cash-history/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data['sessions']), 1)
        row = resp.data['sessions'][0]
        self.assertAlmostEqual(float(row['difference']), -20.0)
        self.assertAlmostEqual(float(resp.data['summary']['total_difference']), -20.0)


class StaffReportTest(AnalyticsReportsBase):
    def test_orders_and_discounts_by_staff(self):
        self.order(total='80.00', created_by_staff=self.owner,
                   manual_discount_type='fixed', manual_discount_value=Decimal('5.00'))
        self.order(total='40.00', created_by_staff=self.owner)
        self.order(total='30.00')  # sem staff (web)
        resp = self._get('staff/')
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.data['staff']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['orders'], 2)
        self.assertAlmostEqual(float(rows[0]['revenue']), 120.0)
        self.assertAlmostEqual(float(rows[0]['manual_discounts']), 5.0)


class OverviewReportTest(AnalyticsReportsBase):
    def test_current_vs_previous_period(self):
        now = timezone.now()
        # Período atual (7d): 2 pedidos pagos, 1 cancelado
        self.order(total='100.00', created=now - timedelta(days=1))
        self.order(total='60.00', created=now - timedelta(days=2), phone='5563999222')
        self.order(total='40.00', paid=False, status='cancelled', created=now - timedelta(days=3), phone='5563999333')
        # Período anterior (7-14d atrás): 1 pedido pago
        self.order(total='80.00', created=now - timedelta(days=10), phone='5563999444')
        resp = self._get('overview/', period='7d')
        self.assertEqual(resp.status_code, 200, resp.content)
        cur, prev = resp.data['current'], resp.data['previous']
        self.assertEqual(cur['orders'], 2)
        self.assertAlmostEqual(float(cur['revenue']), 160.0)
        self.assertAlmostEqual(float(cur['avg_ticket']), 80.0)
        self.assertAlmostEqual(cur['cancel_rate'], 33.3, places=1)
        self.assertEqual(prev['orders'], 1)
        self.assertAlmostEqual(float(prev['revenue']), 80.0)
        # Delta % de receita: (160-80)/80 = +100%
        self.assertAlmostEqual(resp.data['delta']['revenue_pct'], 100.0, places=1)


class MenuMatrixReportTest(AnalyticsReportsBase):
    def test_quadrants_by_popularity_and_margin(self):
        cat = StoreCategory.objects.create(store=self.store, name='Cat', slug='cat')

        def prod(name, price, cost):
            return StoreProduct.objects.create(
                store=self.store, category=cat, name=name, slug=name.lower(),
                price=Decimal(price), cost_price=Decimal(cost),
            )
        estrela = prod('Estrela', '30', '9')      # margem 70%, muito vendido
        burro = prod('Burro', '20', '14')         # margem 30%, muito vendido
        enigma = prod('Enigma', '40', '10')       # margem 75%, pouco vendido
        abacaxi = prod('Abacaxi', '15', '11')     # margem ~27%, pouco vendido
        o = self.order(total='1000.00')
        for p, qty in ((estrela, 20), (burro, 18), (enigma, 2), (abacaxi, 1)):
            StoreOrderItem.objects.create(
                order=o, product=p, product_name=p.name,
                unit_price=p.price, quantity=qty, subtotal=p.price * qty,
            )
        resp = self._get('menu-matrix/')
        self.assertEqual(resp.status_code, 200, resp.content)
        quad = {r['product_name']: r['quadrant'] for r in resp.data['products']}
        self.assertEqual(quad['Estrela'], 'estrela')
        self.assertEqual(quad['Burro'], 'burro_de_carga')
        self.assertEqual(quad['Enigma'], 'enigma')
        self.assertEqual(quad['Abacaxi'], 'abacaxi')

    def test_products_without_cost_listed_apart(self):
        cat = StoreCategory.objects.create(store=self.store, name='Cat', slug='cat')
        p = StoreProduct.objects.create(store=self.store, category=cat, name='SemCusto', slug='semcusto', price=Decimal('10'))
        o = self.order(total='10.00')
        StoreOrderItem.objects.create(order=o, product=p, product_name='SemCusto', unit_price=Decimal('10'), quantity=1, subtotal=Decimal('10'))
        resp = self._get('menu-matrix/')
        self.assertEqual(resp.data['products'], [])
        self.assertEqual(resp.data['missing_cost'][0]['product_name'], 'SemCusto')


class CohortReportTest(AnalyticsReportsBase):
    def test_monthly_retention(self):
        now = timezone.now()
        m0 = (now - timedelta(days=65)).replace(day=5)   # ~2 meses atrás
        # Cliente A: primeiro pedido em m0, voltou no mês seguinte
        self.order(total='50.00', phone='5563999000111', created=m0)
        self.order(total='50.00', phone='5563999000111', created=m0 + timedelta(days=32))
        # Cliente B: primeiro pedido em m0, nunca voltou
        self.order(total='30.00', phone='5563999000222', created=m0)
        resp = self._get('cohort/')
        self.assertEqual(resp.status_code, 200, resp.content)
        cohort = next((c for c in resp.data['cohorts'] if c['size'] == 2), None)
        self.assertIsNotNone(cohort, resp.data)
        # M+1: 1 de 2 voltou = 50%
        self.assertAlmostEqual(cohort['retention'][0], 50.0, places=1)


ALL_PATHS = (
    'heatmap/', 'abc/', 'channels/', 'geography/', 'sla/', 'finance/', 'rfm/',
    'bot-funnel/', 'reviews/', 'coupons/', 'basket/', 'cancellations/',
    'scheduling/', 'cash-history/', 'staff/', 'overview/', 'menu-matrix/', 'cohort/',
)


class TenantIsolationTest(AnalyticsReportsBase):
    def test_other_user_cannot_access_store(self):
        self.client.force_authenticate(self.other)
        for path in ALL_PATHS:
            resp = self.client.get(f'{BASE}{path}', {'store': self.store.slug})
            self.assertEqual(resp.status_code, 404, f'{path} vazou: {resp.status_code}')
