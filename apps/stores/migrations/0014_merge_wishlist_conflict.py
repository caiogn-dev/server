from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0006_convert_wishlist_to_items'),
        ('stores', '0013_merge_stores'),
    ]

    operations = [
        # Merge migration to resolve the conflicting leaf nodes created by
        # 0006_convert_wishlist_to_items and 0013_merge_stores. No state changes
        # are necessary as 0006 updates the DB and the state to match models.
    ]
