from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):
    dependencies = [('stores', '0052_storesubscription_billing_cycle_and_more')]

    operations = [
        migrations.AddField(model_name='store', name='meta_pixel_id', field=models.CharField(blank=True, default='', max_length=32)),
        migrations.AddField(model_name='store', name='meta_pixel_enabled', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='store', name='meta_capi_access_token', field=apps.core.fields.EncryptedCharField(blank=True, default='', max_length=1000)),
        migrations.AddField(model_name='store', name='meta_capi_enabled', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='store', name='meta_capi_test_event_code', field=models.CharField(blank=True, default='', max_length=100)),
    ]
