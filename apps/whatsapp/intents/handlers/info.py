import logging
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone as dj_timezone

from apps.stores.services.horario_de_funcionamento import (
    dia_esta_aberto as _dia_esta_aberto,
    faixa_do_dia as _faixa_do_dia,
)

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)

DIAS_DA_SEMANA = {
    'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
    'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado',
    'sunday': 'Domingo',
}


def _agora_da_loja(store):
    """Agora no fuso da LOJA, nunca o do servidor.

    O container roda em UTC. `datetime.now()` naive devolvia 02:00 de quinta
    quando em Brasília ainda eram 23:00 de quarta — então das 21h à meia-noite
    o bot anunciava o horário do dia seguinte. Cada loja tem seu `timezone`,
    então isto vale para qualquer uma sem lista por slug.
    """
    nome = (getattr(store, 'timezone', None) or settings.TIME_ZONE or 'UTC')
    try:
        fuso = ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("[BusinessHours] fuso inválido na loja: %r", nome)
        fuso = ZoneInfo(settings.TIME_ZONE)
    return dj_timezone.now().astimezone(fuso)


class BusinessHoursHandler(IntentHandler):
    """Handler para horário de funcionamento."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[BusinessHoursHandler] Respondendo horário de forma determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store or not (self.store.operating_hours or {}):
            # Sem horário configurado não se chuta: a resposta antiga
            # ("Segunda a Sábado 10h às 20h") era uma loja inventada falando
            # pelo cliente, e valia igual para todas as lojas.
            return HandlerResult.text(
                "🕐 Ainda não tenho o horário de atendimento por aqui. "
                "Me chama que eu confirmo pra você!"
            )

        try:
            horarios = self.store.operating_hours or {}
            hoje = _agora_da_loja(self.store).strftime('%A').lower()

            horario_de_hoje = horarios.get(hoje, {})
            nome_de_hoje = DIAS_DA_SEMANA.get(hoje, 'Hoje')
            if not _dia_esta_aberto(horario_de_hoje):
                estado_de_hoje = 'Fechado'
            else:
                estado_de_hoje = _faixa_do_dia(horario_de_hoje) or 'Aberto'
            resposta = f"🕐 *Horário de hoje ({nome_de_hoje}):*\n{estado_de_hoje}\n\n"

            resposta += "*Horário da semana:*\n"
            for codigo, nome in DIAS_DA_SEMANA.items():
                horario_do_dia = horarios.get(codigo, {})
                if _dia_esta_aberto(horario_do_dia):
                    faixa = _faixa_do_dia(horario_do_dia) or 'Aberto'
                    resposta += f"{nome}: {faixa}\n"
                else:
                    resposta += f"{nome}: Fechado\n"
            return HandlerResult.text(resposta)
        except Exception as e:
            logger.error("Error getting business hours: %s", e, exc_info=True)
            return HandlerResult.text(
                "🕐 Tive um problema para consultar o horário agora. "
                "Me chama que eu confirmo pra você!"
            )


class DeliveryInfoHandler(IntentHandler):
    """Handler para informações de entrega."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[DeliveryInfoHandler] Respondendo entrega de forma determinística")
        text = self._build_delivery_info_text(intent_data.get('original_message', ''))
        store = self.store
        delivery_enabled = getattr(store, 'delivery_enabled', True) if store else True
        pickup_enabled = getattr(store, 'pickup_enabled', True) if store else True
        buttons = []
        if delivery_enabled:
            buttons.append({'id': 'view_menu', 'title': '📋 Ver Cardápio'})
        if pickup_enabled and delivery_enabled:
            buttons.append({'id': 'order_pickup', 'title': '🏪 Quero Retirar'})
        if not buttons:
            return HandlerResult.text(text)
        return HandlerResult.buttons(body=text, buttons=buttons[:3])


class LocationHandler(IntentHandler):
    """Handler para localização/endereço."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[LocationHandler] Respondendo localização de forma determinística")
        return HandlerResult.text(self._build_location_text())


class ContactHandler(IntentHandler):
    """Handler para contato."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[ContactHandler] Respondendo contato de forma determinística")
        return HandlerResult.text(self._build_contact_text())


class FAQHandler(IntentHandler):
    """Handler para perguntas frequentes — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[FAQHandler] Delegando ao LLM")
        return HandlerResult.needs_llm()
