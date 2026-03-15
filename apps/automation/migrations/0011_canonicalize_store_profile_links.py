from django.db import migrations


def canonicalize_store_profile_links(apps, schema_editor):
    CompanyProfile = apps.get_model('automation', 'CompanyProfile')
    Store = apps.get_model('stores', 'Store')
    WhatsAppAccount = apps.get_model('whatsapp', 'WhatsAppAccount')

    for store in Store.objects.all().iterator():
        account_id = getattr(store, 'whatsapp_account_id', None)
        profile = CompanyProfile.objects.filter(store_id=store.id).first()

        if profile is None and account_id:
            profile = CompanyProfile.objects.filter(account_id=account_id).first()

        if profile is None:
            profile = CompanyProfile.objects.create(
                store_id=store.id,
                account_id=account_id,
                _company_name=store.name or '',
                _description=store.description or '',
            )

        update_fields = []

        if profile.store_id != store.id:
            profile.store_id = store.id
            update_fields.append('store')

        if account_id and profile.account_id != account_id:
            profile.account_id = account_id
            update_fields.append('account')

        if not profile._company_name and store.name:
            profile._company_name = store.name
            update_fields.append('_company_name')

        if not profile._description and store.description:
            profile._description = store.description
            update_fields.append('_description')

        if not profile._legacy_whatsapp_number:
            legacy_number = store.whatsapp_number or store.phone or ''
            if legacy_number:
                profile._legacy_whatsapp_number = legacy_number
                update_fields.append('_legacy_whatsapp_number')

        if not profile._legacy_address and store.address:
            profile._legacy_address = store.address
            update_fields.append('_legacy_address')

        if store.operating_hours and not profile._business_hours:
            profile._business_hours = store.operating_hours
            update_fields.append('_business_hours')

        if not profile.menu_url and store.slug:
            profile.menu_url = f'https://{store.slug}.pastita.com.br'
            update_fields.append('menu_url')

        if not profile.order_url and store.slug:
            profile.order_url = f'https://{store.slug}.pastita.com.br/cardapio'
            update_fields.append('order_url')

        if account_id:
            account = WhatsAppAccount.objects.filter(id=account_id).first()
            if account is not None:
                if not profile.default_agent_id and getattr(account, 'default_agent_id', None):
                    profile.default_agent_id = account.default_agent_id
                    update_fields.append('default_agent')

                if (
                    getattr(account, 'default_agent_id', None)
                    and getattr(account, 'auto_response_enabled', False)
                    and not profile.use_ai_agent
                ):
                    profile.use_ai_agent = True
                    update_fields.append('use_ai_agent')

        if update_fields:
            profile.save(update_fields=list(dict.fromkeys(update_fields)))

    for profile in CompanyProfile.objects.filter(store_id__isnull=True).exclude(account_id__isnull=True).iterator():
        store = Store.objects.filter(whatsapp_account_id=profile.account_id).order_by('created_at').first()
        if store:
            profile.store_id = store.id
            profile.save(update_fields=['store'])

    for profile in CompanyProfile.objects.exclude(store_id__isnull=True).exclude(account_id__isnull=True).iterator():
        store = Store.objects.filter(id=profile.store_id).first()
        if store and not store.whatsapp_account_id:
            store.whatsapp_account_id = profile.account_id
            store.save(update_fields=['whatsapp_account'])


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0010_companyprofile_legacy_column_state'),
        ('stores', '0001_initial'),
        ('whatsapp', '0004_messagecontext_state_and_field_sync'),
    ]

    operations = [
        migrations.RunPython(canonicalize_store_profile_links, migrations.RunPython.noop),
    ]
