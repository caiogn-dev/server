"""Cota no Uber Direct as entregas já feitas e mostra Uber × frete cobrado.

Cotar não cria entrega nem cobra. O preço é o de AGORA (hora em que roda),
não o da hora do pedido — para o efeito do horário, use o modo sombra.

    python manage.py cotar_uber_historico --loja ce-saladas --dias 30
"""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.stores.models import Store, StoreOrder, UberCotacao
from apps.stores.services.uber_resumo import resumo_por_faixa
from apps.stores.tasks import cotar_uber_sombra


class Command(BaseCommand):
    help = 'Cota no Uber Direct as entregas dos últimos N dias (sem despachar) e resume por km.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', required=True, help='slug da loja')
        parser.add_argument('--dias', type=int, default=30)
        parser.add_argument('--limite', type=int, default=300)
        parser.add_argument('--so-resumo', action='store_true', help='não cota, só mostra o que já tem')

    def handle(self, *args, loja, dias, limite, so_resumo, **kw):
        store = Store.objects.filter(slug=loja).first()
        if not store:
            raise CommandError(f'loja {loja!r} não existe')

        if not so_resumo:
            ja = UberCotacao.objects.filter(store=store, origem='historico').values('order_id')
            pedidos = list(
                StoreOrder.objects.filter(
                    store=store, delivery_method='delivery',
                    created_at__gte=timezone.now() - timedelta(days=dias),
                ).exclude(status='cancelled').exclude(id__in=ja)
                .order_by('-created_at').values_list('id', flat=True)[:limite]
            )
            self.stdout.write(f'Cotando {len(pedidos)} entregas de {store.name}...')
            for i, oid in enumerate(pedidos, 1):
                cotar_uber_sombra(str(oid), origem='historico')
                if i % 20 == 0:
                    self.stdout.write(f'  {i}/{len(pedidos)}')
                time.sleep(0.3)  # gentil com a API

        cots = UberCotacao.objects.filter(store=store)
        falhas = cots.filter(fee__isnull=True).count()
        sem_km = cots.filter(fee__isnull=False, distancia_km__isnull=True).count()
        self.stdout.write('')
        self.stdout.write(f'{"faixa":<9} {"n":>4} {"média Uber":>11} {"P75 Uber":>9} '
                          f'{"cobrado":>8} {"prejuízo":>9} {"saldo":>9}')
        for f in resumo_por_faixa(cots):
            self.stdout.write(
                f'{f["faixa"]:<9} {f["n"]:>4} {f["media_uber"]:>11} {f["p75_uber"]:>9} '
                f'{(f["media_cobrada"] or "-"):>8} {f["no_prejuizo"]:>5}/{f["n"]:<3} {f["saldo"]:>9}'
            )
        self.stdout.write(f'\nUber recusou: {falhas} | sem coordenada (fora das faixas): {sem_km}')
