"""
Data migration: popula StoreTeamMember a partir do campo M2M store.staff existente.
Owner recebe role='owner', demais staff recebem role='operator'.
"""
from django.db import migrations
import uuid


def migrate_staff_to_team(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    StoreTeamMember = apps.get_model('stores', 'StoreTeamMember')

    for store in Store.objects.select_related('owner').prefetch_related('staff'):
        if store.owner_id:
            StoreTeamMember.objects.get_or_create(
                tenant=store,
                user_id=store.owner_id,
                defaults={
                    'id': uuid.uuid4(),
                    'role': 'owner',
                    'is_active': True,
                },
            )
        for staff_user in store.staff.all():
            if staff_user.pk != store.owner_id:
                StoreTeamMember.objects.get_or_create(
                    tenant=store,
                    user=staff_user,
                    defaults={
                        'id': uuid.uuid4(),
                        'role': 'operator',
                        'is_active': True,
                    },
                )


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0019_storeorder_created_by_staff_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_staff_to_team, migrations.RunPython.noop),
    ]
