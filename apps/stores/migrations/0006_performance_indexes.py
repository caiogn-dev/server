"""
Performance indexes for high-traffic query patterns.

New indexes added:
- Store: owner+status, status+is_active
- StoreProduct: store+status, store+category+status
- StoreCart: user+store+is_active (is_active compound not covered by existing index)
- StoreOrder: customer+store, store+created_at desc
- StoreCustomer: phone, store+user
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0005_store_url_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Store ──────────────────────────────────────────────────────────────
        # Owner + status: dashboard listing ("my active stores")
        migrations.AddIndex(
            model_name='store',
            index=models.Index(fields=['owner', 'status'], name='store_owner_status_idx'),
        ),
        # Status + is_active: admin/public filtering
        migrations.AddIndex(
            model_name='store',
            index=models.Index(fields=['status', 'is_active'], name='store_status_active_idx'),
        ),

        # ── StoreProduct ───────────────────────────────────────────────────────
        # store + status: storefront product listing (most frequent query)
        migrations.AddIndex(
            model_name='storeproduct',
            index=models.Index(fields=['store', 'status'], name='product_store_status_idx'),
        ),
        # store + category + status: category-browse queries
        migrations.AddIndex(
            model_name='storeproduct',
            index=models.Index(fields=['store', 'category', 'status'], name='product_store_cat_status_idx'),
        ),

        # ── StoreCart ──────────────────────────────────────────────────────────
        # user + store + is_active: cart lookup on every authenticated storefront request
        # Existing index covers (store, user) but not with is_active filter
        migrations.AddIndex(
            model_name='storecart',
            index=models.Index(fields=['user', 'store', 'is_active'], name='cart_user_store_active_idx'),
        ),

        # ── StoreOrder ─────────────────────────────────────────────────────────
        # customer + store: "my orders" customer history page
        migrations.AddIndex(
            model_name='storeorder',
            index=models.Index(fields=['customer', 'store'], name='order_customer_store_idx'),
        ),
        # store + created_at: dashboard order list sorted by newest (DESC)
        migrations.AddIndex(
            model_name='storeorder',
            index=models.Index(fields=['store', 'created_at'], name='order_store_created_idx'),
        ),

        # ── StoreCustomer ──────────────────────────────────────────────────────
        # phone: signal-based lookup (sync_store_order_to_unified_user, checkout identity)
        migrations.AddIndex(
            model_name='storecustomer',
            index=models.Index(fields=['phone'], name='customer_phone_idx'),
        ),
        # store + user: get_or_create guard + profile lookup
        migrations.AddIndex(
            model_name='storecustomer',
            index=models.Index(fields=['store', 'user'], name='customer_store_user_idx'),
        ),
    ]
