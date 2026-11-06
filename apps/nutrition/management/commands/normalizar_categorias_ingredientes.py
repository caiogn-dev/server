"""Junta categorias duplicadas de ingrediente. Sem --apply só mostra (dry-run).

Reversível: grava um JSON {id: categoria_antiga} em --backup antes de aplicar;
`--restaurar ARQUIVO` desfaz. Categorias estrangeiras não são alteradas aqui
(só somem da exibição) — apagar dado de origem não é reversível sem backup.
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand

from apps.nutrition.categorias import mapa_de_categorias
from apps.nutrition.models import NutritionIngredient


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Só mostra (padrão).')
        parser.add_argument('--apply', action='store_true', help='Grava as mudanças.')
        parser.add_argument('--backup', default='categorias_ingredientes_backup.json')
        parser.add_argument('--restaurar', help='Arquivo de backup a restaurar.')

    def handle(self, *args, **o):
        if o['restaurar']:
            with open(o['restaurar']) as f:
                antigo = json.load(f)
            for pk, cat in antigo.items():
                NutritionIngredient.objects.filter(pk=pk).update(category=cat)
            self.stdout.write(f'Restaurados {len(antigo)} ingredientes.')
            return
        contagens = Counter(NutritionIngredient.objects.values_list('category', flat=True))
        mapa = mapa_de_categorias(contagens)
        mudancas = {c: novo for c, novo in mapa.items() if novo is not None and novo != c}
        for c, novo in sorted(mudancas.items()):
            self.stdout.write(f'{c!r} -> {novo!r} ({contagens[c]})')
        estrangeiras = [c for c, novo in mapa.items() if novo is None]
        self.stdout.write(f'{len(estrangeiras)} categorias estrangeiras (só escondidas na tela): {sorted(estrangeiras)[:20]}')
        if not o['apply']:
            self.stdout.write('DRY-RUN: nada gravado. Use --apply.')
            return
        antigo = {}
        for c in mudancas:
            for pk in NutritionIngredient.objects.filter(category=c).values_list('pk', flat=True):
                antigo[str(pk)] = c
        with open(o['backup'], 'w') as f:
            json.dump(antigo, f)
        for c, novo in mudancas.items():
            NutritionIngredient.objects.filter(category=c).update(category=novo)
        self.stdout.write(f'Aplicado em {len(antigo)} ingredientes. Backup: {o["backup"]}')
