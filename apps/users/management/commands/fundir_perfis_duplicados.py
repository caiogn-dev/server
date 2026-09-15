"""Funde perfis de CRM duplicados pelo formato do telefone (nono dígito, +, 55).

SEM `--aplicar` NÃO ESCREVE NADA.
"""
from django.core.management.base import BaseCommand

from apps.users import fusao_de_perfis


class Command(BaseCommand):
    help = 'Funde UnifiedUser duplicados por telefone.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, aplicar=False, **kwargs):
        planos = fusao_de_perfis.planejar()
        self.stdout.write(f'pessoas com perfil duplicado: {len(planos)} | perfis a fundir: {sum(len(p.saem) for p in planos)}')
        for p in planos[:30]:
            self.stdout.write(f'  {p.telefone[-4:]}: fica {p.fica.phone_number} ({(p.fica.name or "")[:20]}) '
                              f'← {[s.phone_number for s in p.saem]}')
        if not aplicar:
            self.stdout.write('simulação — nada gravado (use --aplicar)')
            return
        n = fusao_de_perfis.aplicar(planos)
        self.stdout.write(f'aplicado — {n} perfis fundidos')
