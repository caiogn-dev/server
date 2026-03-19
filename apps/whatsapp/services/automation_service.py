"""
DEPRECATED — WhatsAppAutomationService

This module is no longer used. The canonical inbound-message automation pipeline is:

    WebhookService.post_process_inbound_message()
        → apps.automation.services.UnifiedService  (alias: LLMOrchestratorService)
            1. IntentDetector   (regex + LLM fallback)
            2. Intent handlers  (apps.whatsapp.intents.handlers)
            3. AutoMessage templates
            4. LLM Agent        (apps.agents.services.LangchainService)
            5. Fallback text

Do NOT import from this module. It will be deleted in a future cleanup pass.
"""
import logging

logger = logging.getLogger(__name__)


class WhatsAppAutomationService:  # noqa: N801
    """Deprecated stub — do not use."""

    def __init__(self, *args, **kwargs):
        logger.warning(
            'WhatsAppAutomationService is deprecated. '
            'Use apps.automation.services.UnifiedService instead.'
        )

    def process_message(self, *args, **kwargs):
        raise NotImplementedError(
            'WhatsAppAutomationService is deprecated. '
            'Use apps.automation.services.UnifiedService instead.'
        )


def process_whatsapp_message(*args, **kwargs):
    """Deprecated stub — do not use."""
    raise NotImplementedError(
        'process_whatsapp_message is deprecated. '
        'Use apps.automation.services.UnifiedService instead.'
    )
