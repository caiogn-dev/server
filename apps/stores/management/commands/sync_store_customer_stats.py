"""
Backfill StoreCustomer identity links and order statistics.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreCustomer, StoreOrder
from apps.automation.models import CustomerSession


class Command(BaseCommand):
    help = "Sync StoreCustomer records and stats from StoreOrder history."

    def add_arguments(self, parser):
        parser.add_argument('--store', help='Store id or slug to limit the sync')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        store_filter = options.get('store')
        dry_run = options.get('dry_run')

        orders = StoreOrder.objects.select_related('store', 'customer').order_by('created_at')
        if store_filter:
            stores = Store.objects.filter(slug=store_filter)
            if not stores.exists():
                stores = Store.objects.filter(id=store_filter)
            orders = orders.filter(store__in=stores)

        touched_customer_ids = set()
        linked_orders = 0
        updated_sessions = 0

        with transaction.atomic():
            for order in orders:
                customer_record = CustomerIdentityService.sync_checkout_customer(
                    store=order.store,
                    customer_name=order.customer_name,
                    email=order.customer_email,
                    phone=order.customer_phone,
                    delivery_method=order.delivery_method,
                    delivery_address=order.delivery_address,
                )
                customer_user = customer_record.get('user')
                store_customer = customer_record.get('store_customer')
                if store_customer:
                    touched_customer_ids.add(store_customer.id)

                if customer_user and order.customer_id != customer_user.id:
                    order.customer = customer_user
                    metadata = order.metadata if isinstance(order.metadata, dict) else {}
                    metadata['customer'] = {
                        **metadata.get('customer', {}),
                        'user_id': str(customer_user.id),
                        'store_customer_id': str(store_customer.id) if store_customer else '',
                        'source': 'sync_store_customer_stats',
                    }
                    order.metadata = metadata
                    linked_orders += 1
                    if not dry_run:
                        order.save(update_fields=['customer', 'metadata', 'updated_at'])

                sessions = CustomerSession.objects.filter(
                    Q(order=order) |
                    Q(external_order_id=order.order_number) |
                    Q(payment_id=str(order.id))
                ).distinct()
                if sessions.exists():
                    if order.status in {
                        StoreOrder.OrderStatus.DELIVERED,
                        StoreOrder.OrderStatus.COMPLETED,
                    }:
                        session_status = CustomerSession.SessionStatus.COMPLETED
                    elif order.payment_status == StoreOrder.PaymentStatus.PAID:
                        session_status = CustomerSession.SessionStatus.PAYMENT_CONFIRMED
                    elif (
                        order.status in {
                            StoreOrder.OrderStatus.CANCELLED,
                            StoreOrder.OrderStatus.FAILED,
                            StoreOrder.OrderStatus.REFUNDED,
                        }
                        or order.payment_status in {
                            StoreOrder.PaymentStatus.FAILED,
                            StoreOrder.PaymentStatus.REFUNDED,
                        }
                    ):
                        session_status = CustomerSession.SessionStatus.EXPIRED
                    elif order.payment_status in {
                        StoreOrder.PaymentStatus.PENDING,
                        StoreOrder.PaymentStatus.PROCESSING,
                    }:
                        session_status = CustomerSession.SessionStatus.PAYMENT_PENDING
                    else:
                        session_status = CustomerSession.SessionStatus.ORDER_PLACED

                    session_update = {
                        'order': order,
                        'external_order_id': order.order_number,
                        'cart_total': order.total,
                        'cart_items_count': order.items.count(),
                        'status': session_status,
                    }
                    if order.customer_name:
                        session_update['customer_name'] = order.customer_name
                    if order.customer_email:
                        session_update['customer_email'] = order.customer_email

                    updated_sessions += sessions.count()
                    if not dry_run:
                        sessions.update(**session_update)

            for customer in StoreCustomer.objects.filter(id__in=touched_customer_ids):
                if not dry_run:
                    customer.update_stats()

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {orders.count()} orders, linked {linked_orders}, "
                f"updated {len(touched_customer_ids)} customers, "
                f"updated {updated_sessions} sessions"
            )
        )
