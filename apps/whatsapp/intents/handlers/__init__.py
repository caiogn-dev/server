from typing import Optional

from apps.whatsapp.intents.detector import IntentType  # noqa: F401 — re-exported

from .base import HandlerResult, IntentHandler, _normalize_text, _parse_items_from_text_dynamic
from .catalog import MenuRequestHandler, PriceCheckHandler, ProductMentionHandler, ProductNotFoundHandler
from .fallback import AffirmativeHandler, HumanHandoffHandler, UnknownHandler
from .greeting import GreetingHandler
from .info import BusinessHoursHandler, ContactHandler, DeliveryInfoHandler, FAQHandler, LocationHandler
from .interactive import InteractiveReplyHandler
from .order import CancelOrderHandler, CreateOrderHandler, QuickOrderHandler, TrackOrderHandler
from .payment import CopyPixHandler, PaymentStatusHandler, ViewQRCodeHandler

__all__ = [
    'HandlerResult', 'IntentHandler',
    '_normalize_text', '_parse_items_from_text_dynamic',
    'GreetingHandler',
    'PriceCheckHandler', 'ProductMentionHandler', 'MenuRequestHandler', 'ProductNotFoundHandler',
    'TrackOrderHandler', 'CreateOrderHandler', 'QuickOrderHandler', 'CancelOrderHandler',
    'PaymentStatusHandler', 'ViewQRCodeHandler', 'CopyPixHandler',
    'BusinessHoursHandler', 'DeliveryInfoHandler', 'LocationHandler', 'ContactHandler', 'FAQHandler',
    'AffirmativeHandler', 'HumanHandoffHandler', 'UnknownHandler',
    'InteractiveReplyHandler',
    'get_handler',
]

HANDLER_MAP = {
    IntentType.GREETING: GreetingHandler,
    IntentType.PRICE_CHECK: PriceCheckHandler,
    IntentType.PRODUCT_MENTION: ProductMentionHandler,
    IntentType.MENU_REQUEST: MenuRequestHandler,
    IntentType.BUSINESS_HOURS: BusinessHoursHandler,
    IntentType.DELIVERY_INFO: DeliveryInfoHandler,
    IntentType.TRACK_ORDER: TrackOrderHandler,
    IntentType.PAYMENT_STATUS: PaymentStatusHandler,
    IntentType.CONFIRM_PAYMENT: PaymentStatusHandler,
    IntentType.REQUEST_PIX: PaymentStatusHandler,
    IntentType.MODIFY_ORDER: UnknownHandler,
    IntentType.VIEW_QR_CODE: ViewQRCodeHandler,
    IntentType.COPY_PIX: CopyPixHandler,
    IntentType.LOCATION: LocationHandler,
    IntentType.CONTACT: ContactHandler,
    IntentType.CREATE_ORDER: CreateOrderHandler,
    IntentType.ADD_TO_CART: QuickOrderHandler,
    IntentType.CANCEL_ORDER: CancelOrderHandler,
    IntentType.HUMAN_HANDOFF: HumanHandoffHandler,
    IntentType.FRUSTRATION: HumanHandoffHandler,
    IntentType.FAQ: FAQHandler,
    IntentType.UNKNOWN: UnknownHandler,
    IntentType.AFFIRMATIVE: AffirmativeHandler,
}


def get_handler(intent_type: IntentType, account, conversation) -> Optional[IntentHandler]:
    handler_class = HANDLER_MAP.get(intent_type)
    if handler_class:
        return handler_class(account, conversation)
    return None
