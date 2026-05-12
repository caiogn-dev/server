"""
Management command to deduplicate UnifiedUser records.

Runs safe merging: keeps the oldest record, updates FKs from duplicates,
then deletes duplicates. Groups by normalized phone first, then by email.

Usage:
    python manage.py deduplicate_unified_users [--dry-run]
"""
from __future__ import annotations

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Deduplicate UnifiedUser records by normalized phone and email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be merged without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        mode = "DRY RUN" if dry_run else "LIVE"
        self.stdout.write(f"\n=== deduplicate_unified_users [{mode}] ===\n")

        from apps.users.models import UnifiedUser
        from apps.core.utils import normalize_phone_number

        total_merged = 0

        # ── Pass 1: group by normalized phone ─────────────────────────────────
        self.stdout.write("Pass 1: phone duplicates...")
        seen_phones: dict[str, UnifiedUser] = {}

        for user in UnifiedUser.objects.order_by("first_seen_at"):
            if not user.phone_number:
                continue
            norm = normalize_phone_number(user.phone_number)
            if not norm:
                continue

            if norm in seen_phones:
                primary = seen_phones[norm]
                self.stdout.write(
                    f"  MERGE {user.id} ({user.phone_number}) → {primary.id} ({primary.phone_number})"
                )
                if not dry_run:
                    total_merged += self._merge(primary, user)
            else:
                seen_phones[norm] = user

        # ── Pass 2: group by email ─────────────────────────────────────────────
        self.stdout.write("Pass 2: email duplicates...")
        seen_emails: dict[str, UnifiedUser] = {}

        for user in UnifiedUser.objects.filter(email__isnull=False).order_by("first_seen_at"):
            email_key = user.email.strip().lower()
            if not email_key:
                continue
            if email_key in seen_emails:
                primary = seen_emails[email_key]
                if primary.id == user.id:
                    continue
                self.stdout.write(
                    f"  MERGE {user.id} ({user.email}) → {primary.id} ({primary.email})"
                )
                if not dry_run:
                    total_merged += self._merge(primary, user)
            else:
                seen_emails[email_key] = user

        self.stdout.write(f"\nDone. Merged {total_merged} duplicate(s).\n")

    @transaction.atomic
    def _merge(self, primary: "UnifiedUser", duplicate: "UnifiedUser") -> int:
        """Reassigns all FKs from duplicate to primary, then deletes duplicate."""
        from apps.users.models import UnifiedUserActivity
        from apps.stores.models import StoreCustomer
        from apps.automation.models import CustomerSession

        # Reassign activities
        UnifiedUserActivity.objects.filter(user=duplicate).update(user=primary)

        # Reassign store_customers
        for sc in StoreCustomer.objects.filter(unified_user=duplicate):
            if not StoreCustomer.objects.filter(unified_user=primary, store=sc.store).exists():
                sc.unified_user = primary
                sc.save(update_fields=["unified_user"])
            # else: leave conflicting one as-is

        # Reassign customer_sessions
        CustomerSession.objects.filter(unified_user=duplicate).update(unified_user=primary)

        # Merge missing fields into primary
        updates = []
        if not primary.email and duplicate.email:
            primary.email = duplicate.email
            updates.append("email")
        if not primary.name or primary.name == "Desconhecido":
            if duplicate.name and duplicate.name != "Desconhecido":
                primary.name = duplicate.name
                updates.append("name")
        if not primary.django_user_id and duplicate.django_user_id:
            primary.django_user_id = duplicate.django_user_id
            updates.append("django_user")
        if updates:
            primary.save(update_fields=updates)

        duplicate.delete()
        return 1
