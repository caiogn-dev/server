import logging
from typing import Any, Dict

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class BusinessHoursHandler(IntentHandler):
    """Handler para horário de funcionamento."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[BusinessHoursHandler] Respondendo horário de forma determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )
        from datetime import datetime
        today = datetime.now().strftime('%A').lower()
        day_names = {
            'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
            'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo',
        }
        try:
            hours = self.store.operating_hours or {}
            today_hours = hours.get(today, {})
            if today_hours:
                open_time = today_hours.get('open', '10:00')
                close_time = today_hours.get('close', '20:00')
                response = (
                    f"🕐 *Horário de hoje ({day_names.get(today, 'Hoje')}):*\n"
                    f"{open_time} às {close_time}\n\n"
                )
            else:
                response = "🕐 *Horário de hoje:* Fechado\n\n"
            response += "*Horário da semana:*\n"
            for day_code, day_name in day_names.items():
                day_hours = hours.get(day_code, {})
                if day_hours:
                    response += f"{day_name}: {day_hours.get('open', '--:--')} às {day_hours.get('close', '--:--')}\n"
                else:
                    response += f"{day_name}: Fechado\n"
            return HandlerResult.text(response)
        except Exception as e:
            logger.error(f"Error getting business hours: {e}")
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
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
