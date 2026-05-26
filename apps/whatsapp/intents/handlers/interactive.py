import logging
from typing import Any, Dict, List

from django.core.cache import cache

from apps.stores.models import StoreProduct

from .base import HandlerResult, IntentHandler
from .catalog import MenuRequestHandler, _is_drink_product
from .fallback import HumanHandoffHandler
from .order import CancelOrderHandler, CreateOrderHandler, TrackOrderHandler
from .payment import CopyPixHandler

logger = logging.getLogger(__name__)


class InteractiveReplyHandler(IntentHandler):
    """
    Handles interactive replies from WhatsApp (button clicks / list selections).

    ID routing conventions:
      product_<uuid>          — user selected a product from a list menu
      add_<uuid>_<qty>        — user clicked an "add N units" button
      view_menu | view_catalog | order_catalog
                              — show the product catalog list
      start_order | order_quick
                              — start/fast order flow
      track_<order_id>        — track an existing order
      contact_support         — handoff to human agent
    """

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        reply_id = intent_data.get('reply_id', '')
        reply_title = intent_data.get('reply_title', '')
        logger.info('[InteractiveReplyHandler] reply_id=%s', reply_id)

        if reply_id.startswith('product_'):
            return self._handle_product_selection(reply_id, reply_title)

        if reply_id.startswith('add_'):
            return self._handle_add_to_cart(reply_id)

        if reply_id in ('view_menu', 'view_catalog', 'order_catalog'):
            return MenuRequestHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id in ('start_order', 'order_quick'):
            return CreateOrderHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id in ('order_delivery', 'order_pickup'):
            return self._handle_delivery_choice(reply_id)

        if reply_id in ('pay_pix', 'pay_card', 'pay_pickup'):
            return self._handle_payment_choice(reply_id)

        if reply_id.startswith('pix_copy'):
            return CopyPixHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id == 'send_comprovante':
            return HandlerResult.text(
                "📤 Para enviar o comprovante, tire uma foto ou screenshot do pagamento "
                "e envie aqui na conversa.\n\n"
                "Vamos verificar e confirmar seu pedido! ✅"
            )

        if reply_id == 'continue_checkout':
            from .payment import PaymentStatusHandler
            return PaymentStatusHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id == 'cancel_order':
            return CancelOrderHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id.startswith('track_'):
            return TrackOrderHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id == 'show_options':
            return HandlerResult.list_message(
                body="O que você gostaria de fazer? 😊",
                button="Ver Opções",
                sections=[{
                    'title': 'Escolha uma opção',
                    'rows': [
                        {'id': 'view_menu',       'title': '📋 Ver Cardápio',        'description': 'Veja nossos pratos e preços'},
                        {'id': 'montar_salada',   'title': '🥗 Montar Salada',       'description': 'Monte sua salada personalizada'},
                        {'id': 'contact_support', 'title': '👤 Falar com Atendente', 'description': 'Prefere falar com um humano?'},
                    ],
                }],
            )

        if reply_id == 'montar_salada':
            return HandlerResult.text(
                "🥗 *Monte sua salada personalizada pelo nosso site!*\n\n"
                "Acesse o cardápio, escolha a base, proteína, toppings e molho do seu jeito:\n\n"
                "👉 https://cesaladas.com.br/cardapio\n\n"
                "Por lá você também faz o pedido completo, acompanha o status e paga com PIX ou cartão. 😊\n\n"
                "🎁 Use o cupom *SALADA10* e ganhe *10% de desconto* no seu pedido!"
            )

        if reply_id == 'contact_support':
            return HumanHandoffHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id == 'repeat_order':
            return self._handle_repeat_order()

        if reply_id.startswith('drink_'):
            return self._handle_drink_upsell(reply_id)

        if reply_id == 'skip_upsell':
            return self._handle_skip_upsell()

        logger.warning('[InteractiveReplyHandler] Unhandled reply_id=%s', reply_id)
        return HandlerResult.buttons(
            body=f"Você selecionou: {reply_title or reply_id}\n\nComo posso ajudar?",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
            ],
        )

    def _handle_delivery_choice(self, reply_id: str) -> HandlerResult:
        delivery_method = 'pickup' if reply_id == 'order_pickup' else 'delivery'
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao recuperar itens pendentes: %s', exc)
            items = []
        if not items:
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )
        if delivery_method == 'delivery':
            try:
                session_manager.save_pending_delivery_method('delivery')
                session_manager.set_waiting_for_address(True)
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao salvar estado de endereço: %s', exc)
            return HandlerResult.text(
                "📍 *Qual é o seu endereço de entrega?*\n\n"
                "Você pode:\n\n"
                "📌 *Compartilhar sua localização* — toque no clipe 📎 e escolha *Localização* (mais rápido e preciso!)\n\n"
                "✍️ *Ou digitar o endereço*, por exemplo:\n"
                "_Quadra 304 Sul, Alameda 2, Lote 5_\n"
                "_ARSE 72, Rua 4, Casa 3_"
            )
        logger.info('[InteractiveReplyHandler] Pickup — mostrando resumo e pedindo observações')
        try:
            session_manager.save_pending_delivery_method('pickup')
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar pickup: %s', exc)
        return self._show_order_summary_and_ask_notes(delivery_method='pickup')

    def _handle_payment_choice(self, reply_id: str) -> HandlerResult:
        payment_map = {'pay_pix': 'pix', 'pay_card': 'card', 'pay_pickup': 'cash'}
        payment_method = payment_map.get(reply_id, 'pix')
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            lock_key = f"whatsapp:checkout:{getattr(session, 'id', self.conversation.id)}"
            if not cache.add(lock_key, '1', timeout=240):
                return HandlerResult.text(
                    "Estou finalizando seu pedido e gerando o pagamento. "
                    "Pode levar alguns instantes, já te envio aqui."
                )
            items = session_manager.get_pending_order_items()
            delivery_method = session_manager.get_pending_delivery_method()
            addr_info = session_manager.get_delivery_address_info()
            customer_notes = session_manager.get_customer_notes()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao recuperar dados pendentes: %s', exc)
            lock_key = None
            session_manager = None
            items = []
            delivery_method = 'delivery'
            addr_info = {}
            customer_notes = ''
        if not items:
            try:
                session_data = session_manager.get_session_data() if session_manager else {}
            except Exception:
                session_data = {}
            if lock_key:
                cache.delete(lock_key)
            if session_data.get('pix_code'):
                return HandlerResult.text(session_data['pix_code'])
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )
        delivery_address = addr_info.get('address', '')
        delivery_fee_override = addr_info.get('fee')
        logger.info(
            '[InteractiveReplyHandler] Finalizando pedido: delivery=%s payment=%s fee=%s address=%s lat=%s lng=%s notes=%r',
            delivery_method, payment_method, delivery_fee_override,
            delivery_address[:40] if delivery_address else '',
            addr_info.get('lat'), addr_info.get('lng'),
            customer_notes[:40] if customer_notes else '',
        )
        try:
            result = self._finalize_order(
                items,
                delivery_method=delivery_method,
                payment_method=payment_method,
                delivery_address=delivery_address,
                customer_notes=customer_notes,
                delivery_fee_override=delivery_fee_override,
                addr_info=addr_info,
            )
        except Exception as exc:
            logger.exception('[InteractiveReplyHandler] _finalize_order falhou')
            result = HandlerResult.text("❌ Erro ao criar pedido. Por favor, tente novamente.")
        finally:
            if lock_key:
                cache.delete(lock_key)
        if not (result.response_text and result.response_text.startswith(('❌ Erro ao criar pedido', '❌ Loja'))):
            try:
                session_manager.clear_pending_order_items()
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao limpar itens pendentes: %s', exc)
        return result

    def _handle_product_selection(self, reply_id: str, reply_title: str) -> HandlerResult:
        product_uuid = reply_id[len('product_'):]
        try:
            product = StoreProduct.objects.get(id=product_uuid, is_active=True)
        except StoreProduct.DoesNotExist:
            logger.warning('[InteractiveReplyHandler] product_id not found: %s', product_uuid)
            return HandlerResult.text(
                "Produto não encontrado. 😕\n\nQuer ver o cardápio completo? Digite *cardápio*."
            )
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_uuid, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            session.update_context('pending_product_id', str(product.id))
            session.update_context('pending_product_name', product.name)
            session.update_context('pending_product_price', float(product.price))
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] session context save failed: %s', exc)
        return HandlerResult.buttons(
            body=(
                f"🍽️ *{product.name}*\n"
                f"💰 R$ {product.price}\n\n"
                f"Quantas unidades você quer?"
            ),
            buttons=[
                {'id': f'add_{product.id}_1', 'title': '1 unidade'},
                {'id': f'add_{product.id}_2', 'title': '2 unidades'},
                {'id': f'add_{product.id}_3', 'title': '3 unidades'},
            ],
            footer="Ou digite a quantidade desejada",
        )

    def _handle_add_to_cart(self, reply_id: str) -> HandlerResult:
        parts = reply_id.split('_')
        if len(parts) < 3:
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")
        try:
            quantity = int(parts[-1])
            product_id = '_'.join(parts[1:-1])
        except (ValueError, IndexError):
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")
        try:
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return HandlerResult.text("Produto não encontrado. 😕")
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_id, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")
        return self._create_order_for_product(product, quantity)

    def _create_order_for_product(self, product, quantity: int) -> HandlerResult:
        if not self.store:
            return HandlerResult.text("Loja não disponível no momento. 😔")
        items = [{'product_id': str(product.id), 'quantity': quantity}]
        # Upsell de bebida somente quando o item adicionado não é bebida
        if not _is_drink_product(product):
            upsell = self._show_drink_upsell(items)
            if upsell:
                return upsell
        return self._ask_delivery_method(items)

    def _get_drink_products(self) -> List:
        """Retorna produtos ativos da categoria bebidas."""
        if not self.store:
            return []
        try:
            from apps.stores.models import StoreCategory
            drink_cats = StoreCategory.objects.filter(
                store=self.store,
                is_active=True,
                name__icontains='bebida',
            ).values_list('id', flat=True)
            if not drink_cats:
                # fallback: busca por tag
                return list(
                    StoreProduct.objects.filter(
                        store=self.store,
                        is_active=True,
                        tags__contains=['bebida'],
                    ).order_by('sort_order', 'name')[:3]
                )
            return list(
                StoreProduct.objects.filter(
                    store=self.store,
                    is_active=True,
                    category__in=drink_cats,
                ).order_by('sort_order', 'name')[:3]
            )
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao buscar bebidas: %s', exc)
            return []

    def _show_drink_upsell(self, items: List[Dict]) -> HandlerResult:
        """Retorna o upsell de bebida ou None se não houver bebidas cadastradas."""
        drinks = self._get_drink_products()
        if not drinks:
            return None
        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar itens antes do upsell: %s', exc)
        # Até 2 bebidas como botões + "Continuar sem bebida"
        buttons = [
            {'id': f'drink_{d.id}', 'title': d.name[:20]}
            for d in drinks[:2]
        ]
        buttons.append({'id': 'skip_upsell', 'title': '✅ Continuar sem bebida'})
        return HandlerResult.buttons(
            body="🥤 *Quer adicionar uma bebida?*\n\nTemos opções geladas pra acompanhar sua salada 😊",
            buttons=buttons,
        )

    def _handle_drink_upsell(self, reply_id: str) -> HandlerResult:
        """Adiciona bebida ao carrinho e prossegue para entrega."""
        drink_id = reply_id[len('drink_'):]
        try:
            drink = StoreProduct.objects.get(id=drink_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return self._handle_skip_upsell()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao buscar bebida %s: %s', drink_id, exc)
            return self._handle_skip_upsell()
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
            items.append({'product_id': str(drink.id), 'quantity': 1})
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao adicionar bebida ao carrinho: %s', exc)
            items = [{'product_id': str(drink.id), 'quantity': 1}]
        return self._ask_delivery_method(items)

    def _handle_skip_upsell(self) -> HandlerResult:
        """Prossegue para entrega com os itens já salvos na sessão."""
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao recuperar itens na sessão: %s', exc)
            items = []
        if not items:
            return HandlerResult.text(
                "❌ Não encontrei itens no carrinho.\n\nDigite *cardápio* para ver as opções."
            )
        return self._ask_delivery_method(items)

    def _handle_repeat_order(self) -> HandlerResult:
        if not self.store:
            return HandlerResult.text("Loja não disponível no momento. 😔")
        try:
            from django.utils import timezone
            from datetime import timedelta
            from apps.stores.models import StoreOrder, StoreOrderItem, StoreProduct
            cutoff = timezone.now() - timedelta(days=7)
            phone = self.conversation.phone_number
            last_order = StoreOrder.objects.filter(
                store=self.store,
                customer_phone__endswith=phone[-8:],
                status__in=[
                    StoreOrder.OrderStatus.DELIVERED,
                    StoreOrder.OrderStatus.PICKED_UP,
                    StoreOrder.OrderStatus.CONFIRMED,
                    StoreOrder.OrderStatus.PAID,
                ],
                created_at__gte=cutoff,
            ).order_by('-created_at').first()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao buscar pedido para repetir: %s', exc)
            last_order = None

        if not last_order:
            return HandlerResult.buttons(
                body="😕 Não encontrei um pedido recente para repetir.\n\nQuer ver o cardápio?",
                buttons=[
                    {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                    {'id': 'contact_support', 'title': '👤 Atendente'},
                ],
            )

        try:
            order_items = StoreOrderItem.objects.filter(order=last_order).select_related('product')
            items = []
            for oi in order_items:
                if oi.product and oi.product.is_active:
                    items.append({'product_id': str(oi.product.id), 'quantity': oi.quantity})
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao carregar itens do pedido: %s', exc)
            items = []

        if not items:
            return HandlerResult.buttons(
                body="😕 Os produtos do seu último pedido não estão mais disponíveis.\n\nQuer ver o cardápio?",
                buttons=[{'id': 'view_menu', 'title': '📋 Ver Cardápio'}],
            )

        return self._ask_delivery_method(items)
