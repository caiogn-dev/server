"""Converte as fotos antigas do cardápio para WebP ≤1280px (ver services/foto_do_cardapio).

Simula por padrão; `--aplicar` grava. O arquivo original fica no disco — só o
campo passa a apontar para o .webp novo. Foto que já está em WebP dentro do
limite é pulada.
"""
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.stores.services.foto_do_cardapio import CAMPOS_DE_FOTO, LADO_MAXIMO, normalizar_bytes


class Command(BaseCommand):
    help = 'Padroniza as fotos já enviadas do cardápio (WebP, lado máximo 1280px).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Grava (sem isto só simula).')
        parser.add_argument('--loja', help='Slug de uma loja só.')

    def handle(self, *args, aplicar=False, loja=None, **opts):
        from PIL import Image

        antes = depois = convertidas = puladas = falhas = 0
        for nome_modelo, campos in CAMPOS_DE_FOTO.items():
            modelo = apps.get_model('stores', nome_modelo)
            qs = modelo.objects.all()
            if loja:
                filtro = 'store__slug' if any(f.name == 'store' for f in modelo._meta.fields) else None
                if filtro:
                    qs = qs.filter(**{filtro: loja})
            for obj in qs.iterator():
                for campo_nome in campos:
                    campo = getattr(obj, campo_nome)
                    if not campo or not campo.name:
                        continue
                    try:
                        with campo.open('rb') as f:
                            bruto = f.read()
                        img = Image.open(campo.path if hasattr(campo, 'path') else campo)
                        if img.format == 'WEBP' and max(img.size) <= LADO_MAXIMO:
                            puladas += 1
                            continue
                    except Exception:
                        falhas += 1
                        continue
                    novo = normalizar_bytes(bruto)
                    if novo is None:
                        puladas += 1
                        continue
                    antes += len(bruto)
                    depois += len(novo)
                    convertidas += 1
                    if aplicar:
                        base = campo.name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
                        campo.save(f'{base}.webp', ContentFile(novo), save=False)
                        type(obj).objects.filter(pk=obj.pk).update(**{campo_nome: campo.name})
        modo = 'APLICADO' if aplicar else 'SIMULAÇÃO (use --aplicar)'
        self.stdout.write(
            f'{modo}: {convertidas} convertidas, {puladas} já ok, {falhas} sem arquivo — '
            f'{antes / 1e6:.1f} MB → {depois / 1e6:.1f} MB'
        )
