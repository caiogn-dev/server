"""Funde perfis de CRM (`UnifiedUser`) duplicados — mesma pessoa, telefone em
outro formato (com/sem nono dígito, `+`, 55).

Uma fonte só: a regra mora em `apps/users/fusao_de_perfis`. A versão antiga
deste comando mantinha o perfil MAIS ANTIGO — que em produção era justamente o
do WhatsApp, sem login, sem pedidos e sem endereços (15/set) — e não tratava
endereço repetido.

Usage:
    python manage.py deduplicate_unified_users            # simula
    python manage.py deduplicate_unified_users --aplicar  # grava
"""
from django.core.management.base import BaseCommand

from apps.users import fusao_de_perfis


class Command(BaseCommand):
    help = 'Funde UnifiedUser duplicados por telefone (simula sem --aplicar).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='(padrão) só mostra')

    def handle(self, *args, aplicar=False, **kwargs):
        planos = fusao_de_perfis.planejar()
        self.stdout.write(
            f'pessoas com perfil duplicado: {len(planos)} | perfis a fundir: {sum(len(p.saem) for p in planos)}'
        )
        for p in planos[:30]:
            self.stdout.write(
                f'  {p.telefone[-4:]}: fica {p.fica.phone_number} ({(p.fica.name or "")[:20]}) '
                f'<- {[s.phone_number for s in p.saem]}'
            )
        if not aplicar:
            self.stdout.write('simulação — nada gravado (use --aplicar)')
            return
        n = fusao_de_perfis.aplicar(planos)
        self.stdout.write(f'aplicado — {n} perfis fundidos')
