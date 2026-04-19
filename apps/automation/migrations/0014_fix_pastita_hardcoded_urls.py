from django.db import migrations


def fix_pastita_hardcoded_urls(apps, schema_editor):
    CompanyProfile = apps.get_model('automation', 'CompanyProfile')

    for profile in CompanyProfile.objects.select_related('store').iterator():
        store = profile.store
        update_fields = []

        website_url = getattr(store, 'website_url', '') if store else ''
        website_url = (website_url or '').rstrip('/')

        if 'pastita.com.br' in (profile.menu_url or ''):
            profile.menu_url = website_url or ''
            update_fields.append('menu_url')

        if 'pastita.com.br' in (profile.order_url or ''):
            profile.order_url = f"{website_url}/cardapio" if website_url else ''
            update_fields.append('order_url')

        if update_fields:
            profile.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0013_company_profile_store_or_account_constraint'),
    ]

    operations = [
        migrations.RunPython(
            fix_pastita_hardcoded_urls,
            migrations.RunPython.noop,
        ),
    ]
