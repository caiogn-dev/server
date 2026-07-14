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

        # 'add_more_items' antes do prefixo 'add_' — senão cai no parser de
        # add_{produto}_{qty} e vira "Erro ao processar pedido".
        if reply_id in ('view_menu', 'view_catalog', 'order_catalog', 'add_more_items'):
            return MenuRequestHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id.startswith('add_'):
            return self._handle_add_to_cart(reply_id)

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
                        {'id': 'contact_support', 'title': '👤 Falar com Atendente', 'description': 'Prefere falar com um humano?'},
                    ],
                }],
            )

        if reply_id == 'montar_salada':
            # Multi-tenant: link dinâmico do profile, sem hardcode de loja/cupom.
            menu_url = self.company_profile.get_menu_url() if self.company_profile else ''
            link = f"\n\n👉 {menu_url}" if menu_url else ""
            return HandlerResult.text(
                "🛒 *Monte seu pedido do seu jeito pelo nosso site!*\n\n"
                "Acesse o cardápio e escolha cada detalhe:"
                f"{link}\n\n"
                "Por lá você também faz o pedido completo, acompanha o status e paga com PIX ou cartão. 😊"
            )

        if reply_id.startswith('qty_'):
            return self._handle_quantity_picker(reply_id)

        if reply_id.startswith('setqty_'):
            return self._handle_set_quantity(reply_id)

        if reply_id == 'checkout_now':
            return self._handle_checkout_now()

        if reply_id == 'contact_support':
            return HumanHandoffHandler(self.account, self.conversation, self.company_profile).handle(intent_data)

        if reply_id == 'repeat_order':
            return self._handle_repeat_order()

        if reply_id.startswith('drink_'):
            return self._handle_drink_upsell(reply_id)

        if reply_id == 'skip_upsell':
            return self._handle_skip_upsell()

        if reply_id.startswith('sauce_'):
            return self._handle_sauce_upsell(reply_id)

        if reply_id == 'skip_sauce':
            return self._handle_skip_sauce()

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
        try:
            session_data = session_manager.get_session_data() if session_manager else {}
        except Exception:
            session_data = {}

        # Idempotência ESCOPADA ao checkout atual: só reenvia o PIX existente se
        # for reclique de pay_pix SEM itens novos no carrinho. Com itens novos é
        # um pedido NOVO — reenviar o código antigo cobraria o valor errado.
        if (
            reply_id == 'pay_pix'
            and session_data.get('pix_code')
            and not items
            and session_data.get('status') == 'payment_pending'
        ):
            if lock_key:
                cache.delete(lock_key)
            logger.info('[InteractiveReplyHandler] Reclique de PIX no mesmo checkout — reenviando código')
            return HandlerResult.buttons(
                body=session_data['pix_code'],
                buttons=[{'id': 'pix_copy', 'title': 'COPIAR CODIGO PIX'}],
            )

        if not items:
            if lock_key:
                cache.delete(lock_key)
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )
        logger.info(
            '[InteractiveReplyHandler] Enfileirando finalização: delivery=%s payment=%s itens=%d',
            delivery_method, payment_method, len(items),
        )
        # Parte lenta (criar pedido + Mercado Pago) roda em task — cliente
        # recebe ack na hora e o pagamento chega em seguida. O lock segura
        # recliques até o task terminar (ele libera no finally).
        try:
            from apps.whatsapp.tasks.checkout_tasks import finalize_whatsapp_order_task
            finalize_whatsapp_order_task.delay(
                account_id=str(self.account.id),
                conversation_id=str(self.conversation.id),
                profile_id=str(self.company_profile.id) if self.company_profile else None,
                payment_method=payment_method,
                lock_key=lock_key,
            )
        except Exception:
            logger.exception('[InteractiveReplyHandler] Falha ao enfileirar — finalizando síncrono')
            try:
                result = self._finalize_order(
                    items,
                    delivery_method=delivery_method,
                    payment_method=payment_method,
                    delivery_address=addr_info.get('address', ''),
                    customer_notes=customer_notes,
                    delivery_fee_override=addr_info.get('fee'),
                    addr_info=addr_info,
                )
            except Exception:
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

        ack_by_method = {
            'pix': "🧾 *Pedido recebido!*\n\n⏳ Estou gerando seu código PIX — chega aqui em instantes! 🙏",
            'card': "🧾 *Pedido recebido!*\n\n⏳ Gerando seu link de pagamento seguro do Mercado Pago...",
            'cash': "🧾 *Pedido recebido!*\n\n⏳ Registrando seu pedido...",
        }
        return HandlerResult.text(ack_by_method.get(payment_method, ack_by_method['pix']))

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
        return self._create_order_for_product(product, 1)

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
        # MULTI-PRODUTO: acumula nos itens pendentes (mesmo produto soma qty);
        # antes cada seleção descartava o carrinho anterior.
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao ler itens pendentes: %s', exc)
            session_manager = None
            items = []
        for it in items:
            if str(it.get('product_id')) == str(product.id):
                it['quantity'] = int(it.get('quantity', 1)) + quantity
                break
        else:
            items.append({'product_id': str(product.id), 'quantity': quantity})
        if session_manager:
            try:
                session_manager.save_pending_order_items(items)
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao salvar itens: %s', exc)
        return self._cart_summary_result(items, last_product=product)

    def _cart_summary_result(self, items, last_product=None) -> HandlerResult:
        """Resumo parcial do pedido + ações: adicionar mais, quantidade, fechar."""
        products = {
            str(pr.id): pr
            for pr in StoreProduct.objects.filter(id__in=[i['product_id'] for i in items])
        }
        lines, total = [], 0.0
        for it in items:
            pr = products.get(str(it['product_id']))
            if not pr:
                continue
            qty = int(it.get('quantity', 1))
            total += qty * float(pr.price)
            lines.append(f"• {qty}x {pr.name} — R$ {qty * float(pr.price):.2f}")
        header = f"✅ *{last_product.name}* adicionado!\n\n" if last_product else ""
        body = (
            f"{header}🛒 *Seu pedido até agora:*\n"
            + "\n".join(lines)
            + f"\n\n💰 Subtotal: *R$ {total:.2f}*"
        )
        buttons = [
            {'id': 'add_more_items', 'title': '➕ Adicionar mais'},
        ]
        if last_product:
            buttons.append({'id': f'qty_{last_product.id}', 'title': '🔢 Quantidade'})
        buttons.append({'id': 'checkout_now', 'title': '✅ Fechar pedido'})
        return HandlerResult.buttons(body=body, buttons=buttons)

    def _handle_quantity_picker(self, reply_id: str) -> HandlerResult:
        product_id = reply_id[len('qty_'):]
        try:
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except Exception:
            return HandlerResult.text("Produto não encontrado. 😕")
        rows = [
            {'id': f'setqty_{product.id}_{n}', 'title': f'{n} unidade' + ('s' if n > 1 else ''),
             'description': f'R$ {n * float(product.price):.2f}'}
            for n in range(1, 10)
        ]
        return HandlerResult.list_message(
            body=f"Quantas unidades de *{product.name}*?",
            button="Escolher quantidade",
            sections=[{'title': 'Quantidade', 'rows': rows}],
        )

    def _handle_set_quantity(self, reply_id: str) -> HandlerResult:
        parts = reply_id.split('_')
        try:
            quantity = max(1, int(parts[-1]))
            product_id = '_'.join(parts[1:-1])
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except Exception:
            return HandlerResult.text("Erro ao ajustar quantidade. Tente novamente.")
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
        except Exception:
            session_manager, items = None, []
        for it in items:
            if str(it.get('product_id')) == str(product.id):
                it['quantity'] = quantity
                break
        else:
            items.append({'product_id': str(product.id), 'quantity': quantity})
        if session_manager:
            try:
                session_manager.save_pending_order_items(items)
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao salvar qty: %s', exc)
        return self._cart_summary_result(items, last_product=product)

    def _handle_checkout_now(self) -> HandlerResult:
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
        except Exception:
            items = []
        if not items:
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\nDigite *cardápio* para ver as opções."
            )
        product_ids = [i['product_id'] for i in items]
        has_non_drink = any(
            not _is_drink_product(pr)
            for pr in StoreProduct.objects.filter(id__in=product_ids)
        )
        already_has_drink = any(
            _is_drink_product(pr)
            for pr in StoreProduct.objects.filter(id__in=product_ids)
        )
        if has_non_drink and not already_has_drink:
            upsell = self._show_drink_upsell(items)
            if upsell:
                return upsell
        sauce_upsell = self._show_sauce_upsell(items)
        return sauce_upsell if sauce_upsell else self._ask_delivery_method(items)

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
            body="🥤 *Quer adicionar uma bebida?*\n\nTemos opções geladas pra acompanhar seu pedido 😊",
            buttons=buttons,
        )

    def _handle_drink_upsell(self, reply_id: str) -> HandlerResult:
        """Adiciona bebida ao carrinho e avança para upsell de molho."""
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
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao adicionar bebida: %s', exc)
            items = [{'product_id': str(drink.id), 'quantity': 1}]
        sauce_upsell = self._show_sauce_upsell(items)
        result = sauce_upsell if sauce_upsell else self._ask_delivery_method(items)
        return self._prepend_body(result, f"✅ *{drink.name}* adicionado ao seu pedido!")

    def _handle_skip_upsell(self) -> HandlerResult:
        """Pula bebida e avança para upsell de molho."""
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
        sauce_upsell = self._show_sauce_upsell(items)
        return sauce_upsell if sauce_upsell else self._ask_delivery_method(items)

    def _get_sauce_products(self) -> List:
        """Retorna produtos de molho/extra do cardápio."""
        if not self.store:
            return []
        try:
            from apps.stores.models import StoreCategory
            sauce_cats = StoreCategory.objects.filter(
                store=self.store,
                is_active=True,
                name__icontains='molho',
            ).values_list('id', flat=True)
            if sauce_cats:
                return list(
                    StoreProduct.objects.filter(
                        store=self.store,
                        is_active=True,
                        category__in=sauce_cats,
                    ).order_by('sort_order', 'name')[:2]
                )
            # fallback: produtos com "molho" no nome
            return list(
                StoreProduct.objects.filter(
                    store=self.store,
                    is_active=True,
                    name__icontains='molho',
                ).order_by('sort_order', 'name')[:2]
            )
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao buscar molhos: %s', exc)
            return []

    def _show_sauce_upsell(self, items: List[Dict]) -> HandlerResult:
        """Mostra upsell de molho extra ou retorna None se não houver produtos."""
        sauces = self._get_sauce_products()
        if not sauces:
            return None
        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar itens antes do upsell molho: %s', exc)
        buttons = [
            {'id': f'sauce_{s.id}', 'title': s.name[:20]}
            for s in sauces[:2]
        ]
        buttons.append({'id': 'skip_sauce', 'title': '✅ Não, obrigado'})
        return HandlerResult.buttons(
            body="🥫 *Quer adicionar um molho extra?*\n\nUm molho especial faz toda diferença! 😋",
            buttons=buttons,
        )

    def _handle_sauce_upsell(self, reply_id: str) -> HandlerResult:
        """Adiciona molho ao carrinho e prossegue para entrega."""
        sauce_id = reply_id[len('sauce_'):]
        try:
            sauce = StoreProduct.objects.get(id=sauce_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return self._handle_skip_sauce()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao buscar molho %s: %s', sauce_id, exc)
            return self._handle_skip_sauce()
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
            items.append({'product_id': str(sauce.id), 'quantity': 1})
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao adicionar molho: %s', exc)
            items = [{'product_id': str(sauce.id), 'quantity': 1}]
        return self._prepend_body(
            self._ask_delivery_method(items),
            f"✅ *{sauce.name}* adicionado ao seu pedido!",
        )

    @staticmethod
    def _prepend_body(result: HandlerResult, text: str) -> HandlerResult:
        """Antepõe uma confirmação ao corpo da próxima mensagem do fluxo."""
        if result.interactive_data and result.interactive_data.get('body'):
            result.interactive_data['body'] = f"{text}\n\n{result.interactive_data['body']}"
        elif result.response_text and result.response_text not in (
            'BUTTONS_SENT', 'LIST_SENT', 'PRODUCT_LIST_SENT',
        ):
            result.response_text = f"{text}\n\n{result.response_text}"
        return result

    def _handle_skip_sauce(self) -> HandlerResult:
        """Pula molho e vai direto para entrega."""
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

        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar itens do repeat: %s', exc)

        # Verifica se algum item NÃO é bebida para disparar upsell de bebida
        has_non_drink = any(
            not _is_drink_product(StoreProduct.objects.filter(id=it['product_id']).first())
            for it in items
            if StoreProduct.objects.filter(id=it['product_id']).exists()
        )
        if has_non_drink:
            drinks = self._get_drink_products()
            if drinks:
                buttons = [{'id': f'drink_{d.id}', 'title': d.name[:20]} for d in drinks[:2]]
                buttons.append({'id': 'skip_upsell', 'title': '✅ Continuar sem bebida'})
                return HandlerResult.buttons(
                    body=f"🔁 *Pedido repetido!*\n\nQuer adicionar uma bebida gelada? 🥤",
                    buttons=buttons,
                )

        sauce_upsell = self._show_sauce_upsell(items)
        return sauce_upsell if sauce_upsell else self._ask_delivery_method(items)
