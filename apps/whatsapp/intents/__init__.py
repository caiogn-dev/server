"""
WhatsApp Intents Package

Sistema de detecção e processamento de intenções do usuário.
"""
from .detector import (
    IntentType,
    IntentDetector,
    intent_detector,
    IntentData,
)
from .handlers import (
    IntentHandler,
    HandlerResult,
    HANDLER_MAP,
    get_handler,
    GreetingHandler,
    PriceCheckHandler,
    MenuRequestHandler,
    BusinessHoursHandler,
    DeliveryInfoHandler,
    TrackOrderHandler,
    PaymentStatusHandler,
    CreateOrderHandler,
    LocationHandler,
    ContactHandler,
    HumanHandoffHandler,
)

__all__ = [
    # Detector
    'IntentType',
    'IntentDetector',
    'intent_detector',
    'IntentData',
    # Handlers
    'IntentHandler',
    'HandlerResult',
    'HANDLER_MAP',
    'get_handler',
    'GreetingHandler',
    'PriceCheckHandler',
    'MenuRequestHandler',
    'BusinessHoursHandler',
    'DeliveryInfoHandler',
    'TrackOrderHandler',
    'PaymentStatusHandler',
    'CreateOrderHandler',
    'LocationHandler',
    'ContactHandler',
    'HumanHandoffHandler',
]
