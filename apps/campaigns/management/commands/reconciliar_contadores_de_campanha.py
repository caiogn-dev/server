"""Reconstrói os contadores da campanha a partir das linhas de destinatário.

Os contadores de `Campaign` foram apagados pelo `save()` sem `update_fields`
do lote de envio (ver `campaign_service.process_campaign_batch`). As LINHAS de
`CampaignRecipient` sempre estiveram certas — `delivered_at` e `read_at` foram
gravados corretamente pelo recibo. Então a fonte para reconstruir é a linha.

Medido em 28/ago/2026, antes da correção:

    campanha    contador    linhas
    24/ago      16          138
    25/ago      24          223
    28/ago      21          246

Rode com `--dry-run` primeiro: mostra o que mudaria sem gravar.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.campaigns.models import Campaign, CampaignRecipient


class Command(BaseCommand):
    help = 'Recalcula messages_delivered/read/sent/failed a partir dos destinatários'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='só mostra')

    def handle(self, *args, **options):
        seco = options['dry_run']
        mudadas = 0

        for campanha in Campaign.objects.all():
            reais = campanha.recipients.aggregate(
                enviadas=Count('id', filter=Q(sent_at__isnull=False)),
                entregues=Count('id', filter=Q(delivered_at__isnull=False)),
                lidas=Count('id', filter=Q(read_at__isnull=False)),
                falhas=Count('id', filter=Q(
                    status=CampaignRecipient.RecipientStatus.FAILED
                )),
            )

            atual = (
                campanha.messages_sent, campanha.messages_delivered,
                campanha.messages_read, campanha.messages_failed,
            )
            novo = (
                reais['enviadas'], reais['entregues'],
                reais['lidas'], reais['falhas'],
            )
            if atual == novo:
                continue

            mudadas += 1
            self.stdout.write(
                f'{campanha.name} ({campanha.created_at:%d/%m}): '
                f'env {atual[0]}->{novo[0]}  ent {atual[1]}->{novo[1]}  '
                f'lid {atual[2]}->{novo[2]}  falha {atual[3]}->{novo[3]}'
            )

            if not seco:
                Campaign.objects.filter(pk=campanha.pk).update(
                    messages_sent=novo[0], messages_delivered=novo[1],
                    messages_read=novo[2], messages_failed=novo[3],
                )

        self.stdout.write(self.style.SUCCESS(
            f'{mudadas} campanha(s) {"seriam corrigidas" if seco else "corrigidas"}'
        ))
