"""Registra o modelo `aviso_de_pedido` na Meta para as contas de WhatsApp ativas.

    python manage.py criar_modelo_aviso_de_pedido            # todas as contas ativas com WABA
    python manage.py criar_modelo_aviso_de_pedido --conta ID # uma só

A aprovação de modelo de utilidade costuma levar minutos; o status chega pelo
webhook de templates ou pelo "sincronizar modelos" do painel.
"""
from django.core.management.base import BaseCommand

from apps.automation.mensageiro import modelo
from apps.whatsapp.models import WhatsAppAccount


class Command(BaseCommand):
    help = 'Cria o modelo de utilidade aviso_de_pedido nas contas de WhatsApp'

    def add_arguments(self, parser):
        parser.add_argument('--conta', help='id da conta; sem ele, todas as ativas com WABA')

    def handle(self, *args, **options):
        contas = WhatsAppAccount.objects.filter(status=WhatsAppAccount.AccountStatus.ACTIVE).exclude(waba_id='')
        if options['conta']:
            contas = contas.filter(id=options['conta'])
        for conta in contas:
            try:
                linha = modelo.criar_na_meta(conta)
            except Exception as exc:  # noqa: BLE001 — uma conta com erro não trava as outras
                self.stderr.write(f'{conta.name}: FALHOU — {exc}')
                continue
            self.stdout.write(f'{conta.name} ({conta.display_phone_number}): {linha.name} → {linha.status}')
