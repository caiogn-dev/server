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
                    f'  MERGE: {conv.phone_number} (id={conv.id}, msgs={Message.objects.filter(conversation=conv).count()}) '
                    f'→ {canonical.phone_number} (id={canonical.id}, msgs={Message.objects.filter(conversation=canonical).count()})'
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

        merged += self._merge_by_ninth_digit(dry_run)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Merged: {merged}, Normalized-only: {normalized_only}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('(dry run — nothing was written)'))

    def _merge_by_ninth_digit(self, dry_run: bool) -> int:
        """Une conversas do MESMO celular gravadas com e sem o nono dígito.

        A normalização acima não resolve este caso: `556392618115` e
        `5563992618115` já estão ambos normalizados — são 12 e 13 dígitos, e
        `normalize_phone_number` só acrescenta o DDI. O WhatsApp entrega o
        `wa_id` sem o nono dígito e o site grava com ele, então o cliente ficava
        com duas conversas: a real (com histórico) e uma fantasma sem nome, que
        recebia as notificações do pedido.

        Vence a conversa com `wa_id` preenchido — é a que o WhatsApp reconhece e
        para onde as respostas do cliente chegam. Sem `wa_id`, vence a que tem
        mais mensagens.
        """
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import Message
        from apps.core.utils import phone_variants

        self.stdout.write('\nUnificando por nono dígito...')

        grupos = {}
        for conv in Conversation.objects.all():
            variantes = phone_variants(conv.phone_number)
            if not variantes:
                continue
            # Chave canônica estável: a menor variante só-dígitos do conjunto.
            chave = (conv.account_id, min(v for v in variantes if v.isdigit()))
            grupos.setdefault(chave, []).append(conv)

        merged = 0
        for (_account_id, chave), convs in grupos.items():
            if len(convs) < 2:
                continue

            convs.sort(key=lambda c: (
                bool(c.wa_id),
                Message.objects.filter(conversation=c).count(),
                c.last_message_at or c.created_at,
            ), reverse=True)
            canonical, duplicatas = convs[0], convs[1:]

            self.stdout.write(
                f'  GRUPO {chave}: mantendo {canonical.phone_number} '
                f'(id={canonical.id}, wa_id={"sim" if canonical.wa_id else "nao"}, '
                f'nome={canonical.contact_name or "-"})'
            )

            for dup in duplicatas:
                qtd = Message.objects.filter(conversation=dup).count()
                self.stdout.write(
                    f'    MERGE {dup.phone_number} (id={dup.id}, msgs={qtd}) → {canonical.id}'
                )
                if dry_run:
                    merged += 1
                    continue

                with transaction.atomic():
                    Message.objects.filter(conversation=dup).update(conversation=canonical)

                    campos = []
                    if dup.contact_name and not canonical.contact_name:
                        canonical.contact_name = dup.contact_name
                        campos.append('contact_name')
                    if dup.wa_id and not canonical.wa_id:
                        canonical.wa_id = dup.wa_id
                        campos.append('wa_id')
                    if dup.last_message_at and (
                        not canonical.last_message_at
                        or dup.last_message_at > canonical.last_message_at
                    ):
                        canonical.last_message_at = dup.last_message_at
                        campos.append('last_message_at')
                    if campos:
                        canonical.save(update_fields=campos + ['updated_at'])

                    dup.delete()
                merged += 1

        return merged
