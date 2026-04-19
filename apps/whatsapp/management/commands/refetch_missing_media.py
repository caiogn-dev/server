"""
Re-downloads media files whose file is missing from storage but media_id is known.
Safe to re-run: skips files that already exist.
"""
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.core.utils import build_absolute_media_url, mime_to_extension
from apps.whatsapp.models import Message
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService


class Command(BaseCommand):
    help = 'Re-download missing WhatsApp media files from Meta API'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--message-id', help='Re-fetch a specific message UUID')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        qs = Message.objects.filter(
            message_type__in=['audio', 'image', 'video', 'document', 'sticker'],
        ).exclude(media_id='').select_related('account')

        if options['message_id']:
            qs = qs.filter(id=options['message_id'])
        else:
            # Only messages where file is missing: url empty OR url is relative (starts with /media/)
            from django.db.models import Q
            qs = qs.filter(Q(media_url='') | Q(media_url__startswith='/media/'))

        total = qs.count()
        self.stdout.write(f"Found {total} messages with missing/relative media")

        ok = fail = skip = 0

        for msg in qs.iterator():
            label = f"[{msg.message_type}] {msg.media_id} (msg {msg.id})"

            extension = mime_to_extension(msg.media_mime_type)
            filename = f"whatsapp/{msg.account_id}/{msg.media_id}{extension}"

            if default_storage.exists(filename):
                new_url = build_absolute_media_url(default_storage.url(filename))
                if not dry_run:
                    msg.media_url = new_url
                    msg.save(update_fields=['media_url'])
                self.stdout.write(f"  SKIP (file exists): {label}")
                skip += 1
                continue

            if dry_run:
                self.stdout.write(f"  Would fetch: {label}")
                ok += 1
                continue

            try:
                api = WhatsAppAPIService(msg.account)
                url = api.get_media_url(msg.media_id)
                if not url:
                    self.stdout.write(self.style.WARNING(f"  No URL from Meta: {label}"))
                    fail += 1
                    continue

                media_bytes = api.download_media(url)
                saved_path = default_storage.save(filename, ContentFile(media_bytes))
                new_url = build_absolute_media_url(default_storage.url(saved_path))

                msg.media_url = new_url
                msg.save(update_fields=['media_url'])

                self.stdout.write(self.style.SUCCESS(f"  OK ({len(media_bytes)} bytes): {label}"))
                ok += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  FAIL: {label} — {exc}"))
                fail += 1

        self.stdout.write(f"\nDone: {ok} fetched, {skip} skipped (already on disk), {fail} failed")
