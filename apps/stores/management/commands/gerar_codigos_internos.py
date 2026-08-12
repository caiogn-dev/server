"""Gera código de barras interno para produtos que não têm código.

    # ver o que mudaria, sem gravar
    python manage.py gerar_codigos_internos --loja ce-saladas --dry-run

    # só as categorias que vão pra etiqueta
    python manage.py gerar_codigos_internos --loja ce-saladas \\
        --categoria "Saladas Especiais" --categoria "Combos Especiais"

Nunca sobrescreve código existente: código de fabricante é a identidade real
do produto, e código interno já impresso está colado na prateleira.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.stores.models import Store, StoreProduct
from apps.stores.services.codigo_interno import gerar_codigo_interno, valido_ean13


class Command(BaseCommand):
    help = 'Gera código de barras interno (EAN-13, faixa 2) para produtos sem código.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', required=True, help='slug da loja')
        parser.add_argument(
            '--categoria', action='append', default=[],
            help='nome da categoria (pode repetir). Sem isso, vale para a loja toda.',
        )
        parser.add_argument('--dry-run', action='store_true', help='só mostra, não grava')

    def handle(self, *args, **options):
        try:
            loja = Store.objects.get(slug=options['loja'])
        except Store.DoesNotExist:
            raise CommandError(f"Loja '{options['loja']}' não existe.")

        # O número da loja no código vem da ordem de criação: estável ao longo
        # do tempo (id não muda) e independente de nome, que a dona renomeia.
        numero_da_loja = list(
            Store.objects.order_by('created_at').values_list('id', flat=True)
        ).index(loja.id) + 1

        produtos = StoreProduct.objects.filter(store=loja, status='active')
        if options['categoria']:
            produtos = produtos.filter(category__name__in=options['categoria'])
            achadas = set(produtos.values_list('category__name', flat=True))
            for pedida in options['categoria']:
                if pedida not in achadas:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠ categoria "{pedida}" não achou produto ativo nesta loja'
                    ))

        produtos = produtos.order_by('created_at')
        total = produtos.count()
        ja_tem = produtos.exclude(barcode='').count()
        self.stdout.write(f'{loja.name}: {total} produto(s) no recorte, {ja_tem} já com código.')

        # O sequencial continua de onde a loja parou, para não reaproveitar
        # número de produto que já saiu impresso.
        usados = set(
            StoreProduct.objects.filter(store=loja)
            .exclude(barcode='').values_list('barcode', flat=True)
        )
        proximo = 1
        gerados = 0

        with transaction.atomic():
            for produto in produtos:
                if produto.barcode:
                    continue
                while True:
                    codigo = gerar_codigo_interno(numero_da_loja, proximo)
                    proximo += 1
                    if codigo not in usados:
                        break
                usados.add(codigo)
                gerados += 1
                self.stdout.write(f'  {codigo}  {produto.name}')
                if not options['dry_run']:
                    produto.barcode = codigo
                    produto.save(update_fields=['barcode', 'updated_at'])

            if options['dry_run']:
                transaction.set_rollback(True)

        prefixo = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefixo}{gerados} código(s) gerado(s) para {loja.name}.'
        ))
        if gerados and not options['dry_run']:
            conferidos = StoreProduct.objects.filter(
                store=loja, barcode__startswith='2',
            ).values_list('barcode', flat=True)
            invalidos = [c for c in conferidos if not valido_ean13(c)]
            if invalidos:
                raise CommandError(f'Códigos inválidos gerados: {invalidos}')
            self.stdout.write('Todos os códigos internos conferem com o dígito verificador.')
