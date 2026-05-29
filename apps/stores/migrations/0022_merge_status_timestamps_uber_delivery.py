# Merge migration for parallel stores migration branches.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0002_add_status_timestamps'),
        ('stores', '0021_add_uber_delivery_fields'),
    ]

    operations = []
