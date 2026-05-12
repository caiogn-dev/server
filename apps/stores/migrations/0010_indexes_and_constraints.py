from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0009_storeprintjob_target_agent'),
    ]

    operations = [
        # ── Store: indexes em phone, whatsapp_number e status ──────────────
        migrations.AddIndex(
            model_name='store',
            index=models.Index(fields=['status'], name='store_status_idx'),
        ),
        migrations.AddIndex(
            model_name='store',
            index=models.Index(fields=['phone'], name='store_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='store',
            index=models.Index(fields=['whatsapp_number'], name='store_whatsapp_idx'),
        ),

        # ── StoreOrder: CHECK constraints em campos financeiros ─────────────
        migrations.AddConstraint(
            model_name='storeorder',
            constraint=models.CheckConstraint(
                check=models.Q(subtotal__gte=0),
                name='order_subtotal_gte_0',
            ),
        ),
        migrations.AddConstraint(
            model_name='storeorder',
            constraint=models.CheckConstraint(
                check=models.Q(discount__gte=0),
                name='order_discount_gte_0',
            ),
        ),
        migrations.AddConstraint(
            model_name='storeorder',
            constraint=models.CheckConstraint(
                check=models.Q(total__gte=0),
                name='order_total_gte_0',
            ),
        ),
        migrations.AddConstraint(
            model_name='storeorder',
            constraint=models.CheckConstraint(
                check=models.Q(delivery_fee__gte=0),
                name='order_delivery_fee_gte_0',
            ),
        ),
        migrations.AddConstraint(
            model_name='storeorder',
            constraint=models.CheckConstraint(
                check=models.Q(tax__gte=0),
                name='order_tax_gte_0',
            ),
        ),

        # ── StoreProduct: CHECK constraint em preço ─────────────────────────
        migrations.AddConstraint(
            model_name='storeproduct',
            constraint=models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='product_price_gte_0',
            ),
        ),
    ]
