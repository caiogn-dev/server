"""Devolve ao bot as conversas presas em modo humano sem ninguém esperando.

Até 19/09/2026 não existia volta do modo humano: uma resposta pelo celular
emudecia o bot com aquele cliente para sempre (331 de 599 conversas). A regra
do dia seguinte (`devolver_ao_bot_se_venceu`) resolve daqui para frente; este
comando limpa o passado, uma vez.

Decisão do dono (19/09): volta ao bot quem não teve atendimento humano nas
últimas 24h. Quem tem cliente esperando resposta FICA — aparece na fila.

Prévia por padrão. Só grava com --aplicar.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.conversations.models import Conversation
from apps.conversations.services.atendimento_humano import (
    devolver_ao_bot,
    ultima_atividade_humana,
)
from apps.conversations.services.fila_humana import _esta_esperando


class Command(BaseCommand):
    help = 'Devolve ao bot conversas em modo humano paradas há +24h sem cliente esperando.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Grava. Sem isto, só prévia.')
        parser.add_argument('--horas', type=int, default=24)

    def handle(self, *args, **opts):
        corte = timezone.now() - timedelta(hours=opts['horas'])
        humanas = (
            Conversation.objects
            .filter(is_active=True, mode=Conversation.ConversationMode.HUMAN)
            .select_related('handover')
        )
        soltar, esperando, recentes = [], 0, 0
        for conversa in humanas:
            if _esta_esperando(conversa):
                esperando += 1
                continue
            marco = ultima_atividade_humana(conversa)
            if marco and marco > corte:
                recentes += 1
                continue
            soltar.append(conversa)

        self.stdout.write(f'Em modo humano: {humanas.count()}')
        self.stdout.write(f'  ficam — cliente esperando resposta: {esperando}')
        self.stdout.write(f"  ficam — atendimento humano nas últimas {opts['horas']}h: {recentes}")
        self.stdout.write(f'  voltam ao bot: {len(soltar)}')

        if not opts['aplicar']:
            self.stdout.write('Prévia: nada foi gravado. Rode com --aplicar.')
            return
        feitas = sum(
            1 for conversa in soltar
            if devolver_ao_bot(conversa, 'Parada em modo humano (limpeza de 19/09)')
        )
        self.stdout.write(self.style.SUCCESS(f'Devolvidas ao bot: {feitas}'))
