import logging
from typing import Any, Dict, List

from django.core.cache import cache

from apps.stores.models import StoreProduct

from .base import HandlerResult, IntentHandler
from .catalog import MenuRequestHandler
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

        if reply_id == 'view_cart':
            return self._handle_view_cart()

        if reply_id == 'edit_cart':
            return self._handle_edit_cart()

        if reply_id.startswith('remove_'):
            return self._handle_remove_item(reply_id[len('remove_'):])

        if reply_id == 'clear_cart':
            return self._handle_clear_cart()

        if reply_id == 'use_saved_address':
            return self._handle_use_saved_address()

        if reply_id == 'new_address':
            return self._handle_new_address()

        if reply_id == 'change_details':
            return self._handle_change_details()

        if reply_id.startswith('sched_'):
            return self._handle_schedule_slot(reply_id[len('sched_'):])

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

        if reply_id.startswith('upsell_'):
            return self._handle_generic_upsell(reply_id[len('upsell_'):])

        # Compat: ids antigos de upsell (bebida/molho) em conversas em andamento
        if reply_id.startswith('drink_'):
            return self._handle_generic_upsell(reply_id[len('drink_'):])

        if reply_id.startswith('sauce_'):
            return self._handle_generic_upsell(reply_id[len('sauce_'):])

        if reply_id in ('skip_upsell', 'skip_sauce'):
            return self._handle_skip_upsell()

        logger.warning('[InteractiveReplyHandler] Unhandled reply_id=%s', reply_id)
        return HandlerResult.buttons(
            body=f"Você selecionou: {reply_title or reply_id}\n\nComo posso ajudar?",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
            ],
        )

    _ASK_ADDRESS_TEXT = (
        "📍 *Qual é o seu endereço de entrega?*\n\n"
        "Você pode:\n\n"
        "📌 *Compartilhar sua localização* — toque no clipe 📎 e escolha *Localização* (mais rápido e preciso!)\n\n"
        "✍️ *Ou digitar o endereço*, por exemplo:\n"
        "_Quadra 304 Sul, Alameda 2, Lote 5_\n"
        "_ARSE 72, Rua 4, Casa 3_"
    )

    def _ask_address(self, session_manager) -> HandlerResult:
        try:
            session_manager.save_pending_delivery_method('delivery')
            session_manager.set_waiting_for_address(True)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar estado de endereço: %s', exc)
        return HandlerResult.text(self._ASK_ADDRESS_TEXT)

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
            # Cliente recorrente: endereço já validado nesta sessão → oferece reusar
            try:
                addr = session_manager.get_delivery_address_info()
            except Exception:
                addr = {}
            if addr.get('address') and addr.get('fee') is not None:
                try:
                    session_manager.save_pending_delivery_method('delivery')
                except Exception:
                    pass
                fee = float(addr['fee'] or 0)
                fee_fmt = f"R$ {fee:.2f}".replace('.', ',') if fee > 0 else "Grátis 🎉"
                return HandlerResult.buttons(
                    body=(
                        f"📍 *Entregar no mesmo endereço?*\n\n"
                        f"{addr['address']}\n"
                        f"🛵 Taxa: {fee_fmt}"
                    ),
                    buttons=[
                        {'id': 'use_saved_address', 'title': '✅ Usar este'},
                        {'id': 'new_address', 'title': '✍️ Novo endereço'},
                    ],
                )
            return self._ask_address(session_manager)
        logger.info('[InteractiveReplyHandler] Pickup — mostrando resumo e pedindo observações')
        try:
            session_manager.save_pending_delivery_method('pickup')
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar pickup: %s', exc)
        return self._show_order_summary_and_ask_notes(delivery_method='pickup')

    def _handle_use_saved_address(self) -> HandlerResult:
        session_manager = self._get_session_manager()
        try:
            addr = session_manager.get_delivery_address_info()
        except Exception:
            addr = {}
        if not (addr.get('address') and addr.get('fee') is not None):
            return self._ask_address(session_manager)
        try:
            session_manager.set_waiting_for_address(False)
        except Exception:
            pass
        return self._show_order_summary_and_ask_notes(
            delivery_method='delivery',
            delivery_address=addr['address'],
            delivery_fee=float(addr['fee'] or 0),
            distance_km=addr.get('distance_km'),
            duration_minutes=addr.get('duration_minutes'),
        )

    def _handle_new_address(self) -> HandlerResult:
        return self._ask_address(self._get_session_manager())

    def _handle_view_cart(self) -> HandlerResult:
        try:
            items = self._get_session_manager().get_pending_order_items() or []
        except Exception:
            items = []
        if not items:
            return HandlerResult.buttons(
                body="🛒 Seu carrinho está vazio.\n\nQue tal dar uma olhada no cardápio? 😊",
                buttons=[{'id': 'view_menu', 'title': '📋 Ver Cardápio'}],
            )
        return self._cart_summary_result(items)

    def _handle_edit_cart(self) -> HandlerResult:
        try:
            items = self._get_session_manager().get_pending_order_items() or []
        except Exception:
            items = []
        if not items:
            return self._handle_view_cart()
        products = {
            str(p.id): p
            for p in StoreProduct.objects.filter(id__in=[i['product_id'] for i in items])
        }
        qty_rows, remove_rows = [], []
        for it in items[:4]:  # lista do WhatsApp: máx 10 linhas no total
            p = products.get(str(it['product_id']))
            if not p:
                continue
            qty = int(it.get('quantity', 1))
            qty_rows.append({
                'id': f'qty_{p.id}', 'title': f'✏️ {p.name}'[:24],
                'description': f'Alterar quantidade (hoje: {qty})',
            })
            remove_rows.append({
                'id': f'remove_{p.id}', 'title': f'❌ {p.name}'[:24],
                'description': 'Remover do carrinho',
            })
        sections = [
            {'title': 'Alterar quantidade', 'rows': qty_rows},
            {'title': 'Remover', 'rows': remove_rows + [
                {'id': 'clear_cart', 'title': '🗑️ Esvaziar carrinho',
                 'description': 'Remove todos os itens'},
            ]},
        ]
        return HandlerResult.list_message(
            body="✏️ *O que você quer ajustar no carrinho?*",
            button="Editar carrinho",
            sections=sections,
        )

    def _handle_remove_item(self, product_id: str) -> HandlerResult:
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
        except Exception:
            return HandlerResult.text("Erro ao acessar o carrinho. Tente novamente.")
        items = [i for i in items if str(i.get('product_id')) != str(product_id)]
        try:
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar remoção: %s', exc)
        if not items:
            return HandlerResult.buttons(
                body="🗑️ Item removido — seu carrinho ficou vazio.\n\nQuer recomeçar?",
                buttons=[{'id': 'view_menu', 'title': '📋 Ver Cardápio'}],
            )
        return self._cart_summary_result(items)

    def _handle_clear_cart(self) -> HandlerResult:
        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_order_items([])
            session_manager.clear_pending_order_items()
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao esvaziar carrinho: %s', exc)
        self._reset_upsell_progress()
        return HandlerResult.buttons(
            body="🗑️ *Carrinho esvaziado!*\n\nQuando quiser, é só escolher de novo. 😊",
            buttons=[{'id': 'view_menu', 'title': '📋 Ver Cardápio'}],
        )

    # ── Agendamento (loja fechada aceita pedido AGENDADO, nunca bloqueia) ────

    def _store_is_open(self) -> bool:
        try:
            return bool(self.store.is_open()) if self.store else True
        except Exception:
            return True

    def _next_open_slots(self, max_slots: int = 8) -> List[Dict[str, str]]:
        """Próximos horários de abertura pelo operating_hours da loja."""
        from datetime import datetime as _dt, timedelta
        from django.utils import timezone as _tz
        if not self.store or not getattr(self.store, 'operating_hours', None):
            return []
        now = _tz.localtime()
        weekday_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_labels = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        slots = []
        for offset in range(7):
            day = (now + timedelta(days=offset)).date()
            hours = self.store.operating_hours.get(weekday_names[day.weekday()])
            if not hours:
                continue
            try:
                open_t = _dt.strptime(hours.get('open') or hours.get('start') or '00:00', '%H:%M').time()
                close_t = _dt.strptime(hours.get('close') or hours.get('end') or '23:59', '%H:%M').time()
            except (ValueError, TypeError):
                continue
            cursor = _dt.combine(day, open_t)
            end = _dt.combine(day, close_t)
            while cursor < end and len(slots) < max_slots:
                aware = _tz.make_aware(cursor) if _tz.is_naive(cursor) else cursor
                if aware > now + timedelta(minutes=30):
                    if offset == 0:
                        label = f"Hoje {cursor.strftime('%H:%M')}"
                    elif offset == 1:
                        label = f"Amanhã {cursor.strftime('%H:%M')}"
                    else:
                        label = f"{day_labels[day.weekday()]} {day.strftime('%d/%m')} {cursor.strftime('%H:%M')}"
                    slots.append({
                        'id': f"sched_{day.isoformat()}_{cursor.strftime('%H:%M')}",
                        'title': label[:24],
                        'description': 'Agendar para este horário',
                    })
                cursor += timedelta(hours=1)
            if len(slots) >= max_slots:
                break
        return slots

    def _offer_scheduling(self, items: List[Dict]) -> HandlerResult:
        slots = self._next_open_slots()
        if not slots:
            # Sem horários configurados p/ agendar — segue o fluxo normal
            self._reset_upsell_progress()
            return self._show_next_upsell(items)
        store_name = getattr(self.store, 'name', 'A loja')
        return HandlerResult.list_message(
            body=(
                f"😴 *{store_name} está fechada agora* — mas seu pedido não se perde!\n\n"
                f"📅 *Escolha quando quer receber* e deixamos tudo agendado:"
            ),
            button="📅 Agendar pedido",
            sections=[{'title': 'Próximos horários', 'rows': slots}],
        )

    def _handle_schedule_slot(self, slot: str) -> HandlerResult:
        try:
            date_str, time_str = slot.rsplit('_', 1)
            from datetime import date as _date
            _date.fromisoformat(date_str)  # valida formato
        except (ValueError, TypeError):
            return HandlerResult.text("❌ Horário inválido. Tente novamente.")
        try:
            session_manager = self._get_session_manager()
            session_manager.save_scheduling(date_str, time_str)
            items = session_manager.get_pending_order_items() or []
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao salvar agendamento: %s', exc)
            return HandlerResult.text("❌ Erro ao agendar. Tente novamente.")
        if not items:
            return HandlerResult.text(
                "📅 Agendado! Agora escolha os itens — digite *cardápio* para ver as opções."
            )
        from datetime import date as _date
        d = _date.fromisoformat(date_str)
        confirm = f"📅 *Agendado para {d.strftime('%d/%m')} às {time_str}!*"
        self._reset_upsell_progress()
        return self._show_next_upsell(items, confirm=confirm)

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
            return HandlerResult.text(session_data['pix_code'])

        if not items:
            if lock_key:
                cache.delete(lock_key)
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )
        # Loja fechada sem agendamento: oferece agendar antes de cobrar
        if not self._store_is_open():
            try:
                has_schedule = bool(session_manager and session_manager.get_scheduling()['date'])
            except Exception:
                has_schedule = True
            if not has_schedule:
                if lock_key:
                    cache.delete(lock_key)
                return self._offer_scheduling(items)
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
            {'id': 'edit_cart', 'title': '✏️ Editar carrinho'},
            {'id': 'checkout_now', 'title': '✅ Fechar pedido'},
        ]
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

    # Palavras-chave de categorias "complemento" que disparam upsell.
    # Dinâmico por loja: só oferece o que EXISTE no cardápio dela; o lojista
    # pode fixar as categorias via settings['bot_upsell_categories'].
    UPSELL_CATEGORY_KEYWORDS = [
        'bebida', 'molho', 'acompanhamento', 'sobremesa', 'adicional',
        'extra', 'complemento', 'porção', 'porcao',
    ]
    MAX_UPSELL_STAGES = 2

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
        # Loja fechada: aceita o pedido, mas AGENDADO (nunca bloqueia)
        if not self._store_is_open():
            try:
                if not session_manager.get_scheduling()['date']:
                    return self._offer_scheduling(items)
            except Exception:
                pass
        self._reset_upsell_progress()
        return self._show_next_upsell(items)

    def _get_upsell_stages(self, items: List[Dict]) -> List:
        """[(categoria, produtos)] das categorias-complemento DO CARDÁPIO DA LOJA.

        Pula categorias já representadas no carrinho. Nada de bebida/molho
        hardcoded: se a loja não tem categoria-complemento, não há upsell.
        """
        if not self.store:
            return []
        try:
            from apps.stores.models import StoreCategory
            configured = [
                str(c).lower()
                for c in ((getattr(self.company, 'settings', None) or {}).get('bot_upsell_categories') or [])
            ]
            categories = list(StoreCategory.objects.filter(store=self.store, is_active=True))

            def is_upsell_category(cat) -> bool:
                name = (cat.name or '').lower()
                if configured:
                    return any(c in name for c in configured)
                return any(k in name for k in self.UPSELL_CATEGORY_KEYWORDS)

            upsell_cats = [c for c in categories if is_upsell_category(c)]
            if not upsell_cats:
                return []
            cart_ids = [i['product_id'] for i in items]
            cart_cat_ids = {
                str(cid)
                for cid in StoreProduct.objects.filter(id__in=cart_ids).values_list('category_id', flat=True)
                if cid
            }
            stages = []
            for cat in upsell_cats:
                if str(cat.id) in cart_cat_ids:
                    continue
                products = list(
                    StoreProduct.objects.filter(
                        store=self.store, is_active=True, category=cat,
                    ).order_by('sort_order', 'name')[:2]
                )
                if products:
                    stages.append((cat, products))
            # Conversão > upsell: heurística faz UMA pergunta só; duas etapas
            # apenas quando o lojista configurou as categorias de propósito.
            max_stages = self.MAX_UPSELL_STAGES if configured else 1
            return stages[:max_stages]
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao montar upsell: %s', exc)
            return []

    def _upsell_offered(self) -> set:
        try:
            session = self._get_session_manager().get_or_create_session()
            return set((session.cart_data or {}).get('upsell_offered') or [])
        except Exception:
            return set()

    def _mark_upsell_offered(self, category_id: str) -> None:
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            data = dict(session.cart_data or {})
            offered = list(data.get('upsell_offered') or [])
            if category_id not in offered:
                offered.append(category_id)
            data['upsell_offered'] = offered
            session.cart_data = data
            session.save(update_fields=['cart_data'])
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao marcar upsell: %s', exc)

    def _reset_upsell_progress(self) -> None:
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            data = dict(session.cart_data or {})
            if data.pop('upsell_offered', None) is not None:
                session.cart_data = data
                session.save(update_fields=['cart_data'])
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao resetar upsell: %s', exc)

    def _show_next_upsell(self, items: List[Dict], confirm: str = None) -> HandlerResult:
        """Mostra a próxima etapa de upsell pendente, ou segue para a entrega."""
        offered = self._upsell_offered()
        for cat, products in self._get_upsell_stages(items):
            if str(cat.id) in offered:
                continue
            self._mark_upsell_offered(str(cat.id))
            try:
                session_manager = self._get_session_manager()
                session_manager.save_pending_order_items(items)
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao salvar itens antes do upsell: %s', exc)
            buttons = [{'id': f'upsell_{p.id}', 'title': p.name[:20]} for p in products]
            buttons.append({'id': 'skip_upsell', 'title': '✅ Não, obrigado'})
            result = HandlerResult.buttons(
                body=f"✨ *Que tal adicionar de {cat.name}?*\n\nCombina com o seu pedido 😊",
                buttons=buttons,
            )
            return self._prepend_body(result, confirm) if confirm else result
        result = self._ask_delivery_or_express(items)
        return self._prepend_body(result, confirm) if confirm else result

    def _ask_delivery_or_express(self, items: List[Dict]) -> HandlerResult:
        """Checkout expresso: endereço já validado na sessão → pagamento direto.

        Colapsa entrega + endereço + observações em UMA mensagem com botões
        PIX/Cartão/Alterar. Sem endereço salvo, segue o fluxo normal.
        """
        try:
            session_manager = self._get_session_manager()
            addr = session_manager.get_delivery_address_info()
        except Exception:
            return self._ask_delivery_method(items)
        delivery_ok = getattr(self.store, 'delivery_enabled', True) if self.store else True
        if not (delivery_ok and addr.get('address') and addr.get('fee') is not None):
            return self._ask_delivery_method(items)
        try:
            session_manager.save_pending_order_items(items)
            session_manager.save_pending_delivery_method('delivery')
            session_manager.set_waiting_for_address(False)
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro no checkout expresso: %s', exc)
        return self._show_order_summary_and_ask_notes(
            delivery_method='delivery',
            delivery_address=addr['address'],
            delivery_fee=float(addr['fee'] or 0),
            distance_km=addr.get('distance_km'),
            duration_minutes=addr.get('duration_minutes'),
            include_change_button=True,
        )

    def _handle_change_details(self) -> HandlerResult:
        try:
            items = self._get_session_manager().get_pending_order_items() or []
        except Exception:
            items = []
        if not items:
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\nDigite *cardápio* para ver as opções."
            )
        return self._ask_delivery_method(items)

    def _handle_generic_upsell(self, product_id: str) -> HandlerResult:
        """Adiciona o item de upsell escolhido e mostra a próxima etapa."""
        try:
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return self._handle_skip_upsell()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao buscar upsell %s: %s', product_id, exc)
            return self._handle_skip_upsell()
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items() or []
            for it in items:
                if str(it.get('product_id')) == str(product.id):
                    it['quantity'] = int(it.get('quantity', 1)) + 1
                    break
            else:
                items.append({'product_id': str(product.id), 'quantity': 1})
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao adicionar upsell: %s', exc)
            items = [{'product_id': str(product.id), 'quantity': 1}]
        return self._show_next_upsell(items, confirm=f"✅ *{product.name}* adicionado ao seu pedido!")

    def _handle_skip_upsell(self) -> HandlerResult:
        """Pula a etapa atual e mostra a próxima (ou segue para entrega)."""
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
        return self._show_next_upsell(items)

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

        self._reset_upsell_progress()
        return self._show_next_upsell(items, confirm="🔁 *Pedido repetido!*")
