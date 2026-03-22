"""
Management command to merge duplicate conversations caused by phone number format inconsistency.

Duplicates arise when the same phone number is stored in different formats, e.g.:
  - "556399547790"   (inbound webhook — no + prefix)
  - "+556399547790"  (outbound notification — with + prefix)

This command normalizes all phone numbers and merges duplicate (account, phone_number)
pairs by moving all messages from the "empty" duplicate into the canonical conversation
(the one with more messages / a contact_name), then deleting the duplicate.

Usage:
    python manage.py merge_duplicate_conversations [--dry-run]
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.utils import normalize_phone_number

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Merge duplicate conversations caused by phone number format differences (+55 vs 55)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without making changes',
        )

    def handle(self, *args, **options):
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import Message

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be made\n'))

        # Step 1: Find all conversations whose phone_number is not already normalized
        unnormalized = Conversation.objects.all()
        to_normalize = [
            c for c in unnormalized
            if c.phone_number != normalize_phone_number(c.phone_number)
        ]
        self.stdout.write(f'Found {len(to_normalize)} conversations with non-normalized phone numbers')

        merged = 0
        normalized_only = 0

        for conv in to_normalize:
            normalized = normalize_phone_number(conv.phone_number)
            # Is there already a conversation with the normalized number for the same account?
            try:
                canonical = Conversation.objects.get(account=conv.account, phone_number=normalized)
            except Conversation.DoesNotExist:
                canonical = None

            if canonical and canonical.pk != conv.pk:
                # There are two conversations for the same number — merge conv into canonical
                self.stdout.write(
                    f'  MERGE: {conv.phone_number} (id={conv.id}, msgs={conv.message_count}) '
                    f'→ {canonical.phone_number} (id={canonical.id}, msgs={canonical.message_count})'
                )
                if not dry_run:
                    with transaction.atomic():
                        # Re-point all messages from the duplicate to the canonical conversation
                        moved = Message.objects.filter(conversation=conv).update(conversation=canonical)
                        self.stdout.write(f'    Moved {moved} messages')

                        # Carry over contact_name if canonical lacks it
                        if conv.contact_name and not canonical.contact_name:
                            canonical.contact_name = conv.contact_name
                            canonical.save(update_fields=['contact_name', 'updated_at'])
                            self.stdout.write(f'    Copied contact_name: {conv.contact_name}')

                        # Update canonical timestamps
                        if conv.last_message_at and (
                            not canonical.last_message_at or
                            conv.last_message_at > canonical.last_message_at
                        ):
                            canonical.last_message_at = conv.last_message_at
                            canonical.save(update_fields=['last_message_at', 'updated_at'])

                        # Delete the duplicate
                        conv.delete()
                        self.stdout.write(f'    Deleted duplicate conversation {conv.id}')
                merged += 1
            else:
                # No canonical exists yet — just rename this conversation
                self.stdout.write(
                    f'  NORMALIZE: {conv.phone_number} → {normalized} (id={conv.id})'
                )
                if not dry_run:
                    # Use queryset update to bypass save() and avoid re-triggering normalization
                    Conversation.objects.filter(pk=conv.pk).update(phone_number=normalized)
                normalized_only += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Merged: {merged}, Normalized-only: {normalized_only}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('(dry run — nothing was written)'))
