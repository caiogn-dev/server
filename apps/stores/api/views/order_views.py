"""
Order management API views.
"""
import logging
import uuid as uuid_module
from decimal import Decimal, InvalidOperation
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q, Sum, Count, Func, F, Value, CharField
from django.utils import timezone
from apps.stores.metrics import inicio_do_dia
from datetime import timedelta

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreCustomer, StoreProduct
from apps.stores.services.realtime_service import broadcast_order_event
from apps.stores.services.order_service import OrderService
from apps.stores.services.print_service import enqueue_order_print_job
from apps.core.permissions import StoreQuerysetMixin, user_can_access_store
from ..serializers import (
    StoreOrderSerializer, StoreOrderCreateSerializer, StoreOrderUpdateSerializer,
    StoreCustomerSerializer, StorePrintJobSerializer, StoreOrderAdjustSerializer,
)
from .base import IsStoreOwnerOrStaff, filter_by_store

logger = logging.getLogger(__name__)


class StoreOperationsPagination(PageNumberPagination):
    page_size = 500
    page_size_query_param = 'page_size'
    max_page_size = 500


class StoreOrderViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing store orders."""

    queryset = StoreOrder.objects.all()
    pagination_class = StoreOperationsPagination
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def initialize_request(self, request, *args, **kwargs):
        """Override to resolve store slug to UUID if needed."""
        # Resolve store_pk from slug to UUID if necessary
        store_pk = self.kwargs.get('store_pk')
        if store_pk:
            try:
                uuid_module.UUID(str(store_pk))
            except (ValueError, AttributeError):
                # It's a slug, resolve to UUID
                from apps.stores.models import Store
                try:
                    store = Store.objects.get(slug=store_pk)
                    self.kwargs['store_pk'] = str(store.id)
                except Store.DoesNotExist:
                    pass
        return super().initialize_request(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        # Fase 3 — anti-N+1: soma das cobranças 'completed' por pedido numa
        # única query. O model lê `amount_paid_agg` na property amount_paid.
        from django.db.models import DecimalField as _DecimalField
        from django.db.models.functions import Coalesce
        qs = qs.annotate(
            amount_paid_agg=Coalesce(
                Sum('payments__amount', filter=Q(payments__status='completed')),
                Decimal('0.00'),
                output_field=_DecimalField(max_digits=10, decimal_places=2),
            )
        )
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')

        if store_param:
            try:
                uuid_module.UUID(store_param)
                qs = qs.filter(store_id=store_param)
            except (ValueError, AttributeError):
                qs = qs.filter(store__slug=store_param)

        # Filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(order_number__icontains=search) |
                Q(customer_name__icontains=search) |
                Q(customer_email__icontains=search) |
                Q(customer_phone__icontains=search)
            )

        qs = self._filtrar_periodo(qs)

        # Canal de origem (site, whatsapp, pdv). O dono quer saber de onde vem
        # a venda antes de decidir onde investir.
        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)

        payment_method = self.request.query_params.get('payment_method')
        if payment_method:
            qs = qs.filter(payment_method=payment_method)

        customer = self.request.query_params.get('customer')
        if customer:
            import re
            digits = re.sub(r'\D', '', customer)
            if digits:
                # O telefone do cadastro (phone/whatsapp) e o customer_phone gravado
                # no checkout divergem em formato (+55, espaços, parênteses, traço);
                # igualdade exata zerava o histórico. Compara só dígitos casando pelo
                # sufixo nacional (DDD+número, 11 díg.), tolerando DDI 55 ausente/extra.
                suffix = digits[-11:] if len(digits) >= 11 else digits
                qs = qs.annotate(
                    _phone_digits=Func(
                        F('customer_phone'),
                        Value(r'[^0-9]'), Value(''), Value('g'),
                        function='regexp_replace',
                        output_field=CharField(),
                    )
                ).filter(_phone_digits__endswith=suffix)
            else:
                qs = qs.filter(customer_phone=customer)

        # Optimize querysets by action (different needs for list vs. retrieve)
        if self.action in ['retrieve']:
            # Detail view: include all related data
            qs = qs.select_related(
                'store',
                'customer',
            ).prefetch_related(
                'items__product',
                # combo_items é serializado (get_combo_items) — sem prefetch dava
                # 1 query por pedido (N+1).
                'combo_items__combo',
                'combo_items__order_item',
            )
        else:
            # List view: minimal related data
            qs = qs.select_related(
                'store',
                'customer',
            ).prefetch_related(
                'items__product',
                'combo_items__combo',
                'combo_items__order_item',
            )

        return qs.order_by('-created_at')
    
    def _filtrar_periodo(self, qs):
        """Recorta a lista pelo período pedido, no FUSO DA LOJA.

        `created_at__date` sobre UTC empurra tudo que foi vendido depois das
        21h para o dia seguinte — e 21h é o pico do delivery. Foi esse bug no
        card "Receita hoje" em 06/ago. `__date` do Django converte para o fuso
        ativo (TIME_ZONE), então a comparação é feita no dia local.

        Data inválida IGNORA o filtro em vez de estourar: o valor vem de URL
        colada e de campo de texto, e um 500 apaga a tela inteira, enquanto a
        lista completa é um resultado que o operador consegue corrigir.
        """
        from datetime import date as _date

        def _ler(nome):
            bruto = self.request.query_params.get(nome)
            if not bruto:
                return None
            try:
                return _date.fromisoformat(bruto[:10])
            except (ValueError, TypeError):
                logger.info('Período ignorado em %s: valor inválido %r', nome, bruto)
                return None

        inicio = _ler('date_from')
        fim = _ler('date_to')

        if inicio and fim:
            # `range` inclui as duas pontas: quem pede "até hoje" quer as
            # vendas de hoje, não até a meia-noite de ontem.
            return qs.filter(created_at__date__range=(inicio, fim))
        if inicio:
            return qs.filter(created_at__date__gte=inicio)
        if fim:
            return qs.filter(created_at__date__lte=fim)
        return qs

    @action(detail=False, methods=['get'])
    def resumo(self, request):
        """Totais do MESMO recorte que a lista está mostrando.

        A aritmética mora no núcleo (`apps.stores.metrics`): seis arquivos já
        calcularam faturamento por conta própria e deram respostas diferentes
        para o mesmo dia. Aqui a view só escolhe o recorte e formata.
        """
        from apps.stores import metrics

        qs = self.filter_queryset(self.get_queryset())
        resumo = metrics.resumo_de_lista(qs)
        ticket = resumo['ticket_medio']

        return Response({
            'pedidos': resumo['pedidos'],
            'cancelados': resumo['cancelados'],
            'pedidos_faturados': resumo['pedidos_faturados'],
            'faturamento': f"{resumo['receita']:.2f}",
            'ticket_medio': f'{ticket:.2f}' if ticket is not None else None,
            'por_pagamento': [
                {**linha, 'total': f"{linha['total']:.2f}"}
                for linha in metrics.quebra_de_lista(qs, 'payment_method')
            ],
            'por_canal': [
                {**linha, 'total': f"{linha['total']:.2f}"}
                for linha in metrics.quebra_de_lista(qs, 'source')
            ],
            # A régua junto do número: sem isto ninguém sabe por que o
            # faturamento é menor que a soma visível das linhas.
            'definicoes': {
                'faturamento': 'soma dos pedidos pagos, sem cancelados e sem pedidos de teste',
                'ticket_medio': 'faturamento ÷ pedidos que faturaram',
                'periodo': 'pela data de entrada do pedido, no fuso da loja',
            },
        })

    def get_serializer_class(self):
        if self.action == 'create':
            return StoreOrderCreateSerializer
        if self.action in ['update', 'partial_update']:
            return StoreOrderUpdateSerializer
        return StoreOrderSerializer

    def create(self, request, *args, **kwargs):
        """Create an order and return the full order contract used by the dashboard."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning('[ORDER_CREATE_ERROR] Validation failed: %s', serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        order = serializer.save()
        # serializer.save() direto pulava o perform_create() — pedido novo
        # nascia sem broadcast e o painel só via no refresh manual
        self._notify_order_update(order, 'order.created')

        # PDV: gerar o pagamento na criação (o checkout do storefront faz isso;
        # esta rota administrativa não fazia — pedido nascia sem link/QR PIX)
        payment_error = None
        if order.payment_method == 'pix' and not order.pix_code:
            from apps.stores.services.checkout_service import CheckoutService
            try:
                result = CheckoutService.create_payment(order, payment_method='pix')
                if not result.get('success'):
                    payment_error = result.get('error') or 'Falha ao gerar pagamento PIX'
                order.refresh_from_db()
            except Exception as exc:
                logger.warning('[ORDER_CREATE] Falha ao gerar PIX do pedido %s: %s', order.id, exc)
                payment_error = str(exc)

        data = StoreOrderSerializer(order).data
        if payment_error:
            data['payment_error'] = payment_error
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        order = serializer.save()
        self._notify_order_update(order, 'order.created')

    def update(self, request, *args, **kwargs):
        return self._update_with_full_response(request, partial=False, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self._update_with_full_response(request, partial=True, *args, **kwargs)

    def _update_with_full_response(self, request, partial=False, *args, **kwargs):
        """Run DRF update validation but always return the full order payload."""
        instance = self.get_object()
        previous_status = instance.status
        previous_payment_status = instance.payment_status

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()

        if (
            previous_payment_status != instance.payment_status
            and instance.payment_status == StoreOrder.PaymentStatus.PAID
            and not instance.paid_at
        ):
            metadata = instance.metadata if isinstance(instance.metadata, dict) else {}
            metadata['manual_payment'] = {
                'source': 'dashboard',
                'user_id': str(request.user.id) if request.user and request.user.is_authenticated else '',
                'marked_at': timezone.now().isoformat(),
            }
            instance.payment_status = StoreOrder.PaymentStatus.PAID
            instance.paid_at = timezone.now()
            instance.metadata = metadata
            instance.save(update_fields=['paid_at', 'metadata', 'updated_at'])
            instance.refresh_from_db()

        if previous_payment_status != instance.payment_status and instance.payment_status == StoreOrder.PaymentStatus.PAID:
            self._notify_order_update(instance, 'order.paid')
        elif previous_status != instance.status or previous_payment_status != instance.payment_status:
            self._notify_order_update(instance, 'order.updated')

        return Response(StoreOrderSerializer(instance).data)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status."""
        order = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'error': 'status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_statuses = [s[0] for s in StoreOrder.OrderStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Bloqueia avanço de pedidos PIX não pagos — previne entregas sem confirmação de pagamento
        _paid_required = {'confirmed', 'preparing', 'ready', 'out_for_delivery', 'delivered', 'completed'}
        if (
            new_status in _paid_required
            and order.payment_method == 'pix'
            and order.payment_status not in ('paid', 'completed')
        ):
            return Response(
                {
                    'error': 'Pagamento PIX não confirmado. Confirme o recebimento do pagamento antes de avançar o pedido.',
                    'code': 'payment_not_confirmed',
                    'payment_status': order.payment_status,
                    'payment_method': order.payment_method,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use OrderService for proper status update with notifications
        order_service = OrderService()
        result = order_service.update_status(
            order,
            new_status,
            notify_customer=True
        )
        
        if not result.get('success'):
            return Response(
                result,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Refresh order to get all updated fields
        order.refresh_from_db()
        
        # Notify via WebSocket
        self._notify_order_update(order, 'order.updated')
        
        return Response(StoreOrderSerializer(order).data)
    
    _ADJUST_BLOCKED = {'cancelled', 'refunded', 'failed'}

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None, **kwargs):
        """Edita desconto/acréscimo/taxa de entrega e itens de um pedido,
        recalculando o total no backend. Corpo parcial."""
        order = self.get_object()
        if order.status in self._ADJUST_BLOCKED:
            return Response(
                {'error': f'Pedido em status "{order.status}" não pode ser editado.',
                 'code': 'order_not_editable'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = StoreOrderAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            order = StoreOrder.objects.select_for_update().get(pk=order.pk)

            item_ops = data.get('item_ops', [])
            for op in item_ops:
                kind = op['op']
                if kind == 'add':
                    product = StoreProduct.objects.filter(
                        id=op['product_id'], store=order.store,
                        status=StoreProduct.ProductStatus.ACTIVE,
                    ).first()
                    if not product:
                        raise DRFValidationError(
                            {'error': 'Produto não encontrado ou inativo.',
                             'code': 'product_not_found'})
                    qty = op['quantity']
                    unit_price = product.price or Decimal('0.00')
                    StoreOrderItem.objects.create(
                        order=order, product=product, variant=None,
                        product_name=product.name, variant_name='', sku=product.sku,
                        unit_price=unit_price, quantity=qty,
                        subtotal=unit_price * qty, options={}, notes='',
                    )
                elif kind == 'update':
                    item = order.items.filter(id=op['item_id']).first()
                    if not item:
                        raise DRFValidationError(
                            {'error': 'Item não pertence a este pedido.',
                             'code': 'item_not_found'})
                    item.quantity = op['quantity']
                    item.subtotal = item.unit_price * item.quantity
                    item.save(update_fields=['quantity', 'subtotal'])
                elif kind == 'remove':
                    item = order.items.filter(id=op['item_id']).first()
                    if not item:
                        raise DRFValidationError(
                            {'error': 'Item não pertence a este pedido.',
                             'code': 'item_not_found'})
                    item.delete()

            if not order.items.exists():
                raise DRFValidationError(
                    {'error': 'O pedido precisa manter pelo menos um item.',
                     'code': 'order_empty'})

            if 'discount' in data:
                order.discount = data['discount']
            if 'discount_reason' in data:
                order.manual_discount_reason = data['discount_reason']
            if 'surcharge_value' in data:
                order.surcharge_value = data['surcharge_value']
            if 'surcharge_reason' in data:
                order.surcharge_reason = data['surcharge_reason']
            if 'delivery_fee' in data:
                order.delivery_fee = data['delivery_fee']

            # Guard: desconto não pode tornar o total negativo
            from decimal import Decimal as _D
            subtotal = sum((i.subtotal for i in order.items.all()), _D('0.00'))
            prospective = (subtotal - (order.discount or _D('0.00'))
                           + (order.tax or _D('0.00')) + (order.delivery_fee or _D('0.00'))
                           + (order.surcharge_value or _D('0.00')))
            if prospective < _D('0.00'):
                raise DRFValidationError(
                    {'error': 'Desconto deixa o total negativo.', 'code': 'total_negative'}
                )

            order.save(update_fields=[
                'discount', 'manual_discount_reason', 'surcharge_value',
                'surcharge_reason', 'delivery_fee', 'updated_at',
            ])
            order.recalculate_totals(save=True)

        order.refresh_from_db()
        self._notify_order_update(order, 'order.updated')
        return Response(StoreOrderSerializer(order).data)

    def _notify_order_update(self, order, event_type='order.updated'):
        """Send WebSocket notification for order updates.

        Disparado via on_commit p/ rodar após o commit e fora do caminho do
        response. Fora de um bloco atomic o callback executa imediatamente,
        mantendo o comportamento idêntico (uma vez por evento de pedido).
        """
        transaction.on_commit(
            lambda: broadcast_order_event(order, event_type=event_type)
        )

    @action(detail=True, methods=['post'], url_path='add_tracking')
    def add_tracking(self, request, pk=None):
        """Attach tracking details and mark order as shipped."""
        order = self.get_object()
        order.tracking_code = request.data.get('tracking_code', order.tracking_code or '')
        order.tracking_url = request.data.get('tracking_url', order.tracking_url or '')
        order.carrier = request.data.get('carrier', order.carrier or '')

        if order.status not in ['shipped', 'out_for_delivery', 'delivered', 'completed']:
            order.status = 'shipped'
            if not order.shipped_at:
                order.shipped_at = timezone.now()

        order.save(update_fields=[
            'tracking_code', 'tracking_url', 'carrier',
            'status', 'shipped_at', 'updated_at'
        ])

        self._notify_order_update(order, 'order.shipped')
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='add_note')
    def add_note(self, request, pk=None):
        """Append note to internal or customer notes."""
        order = self.get_object()
        note = (request.data.get('note') or '').strip()
        is_internal = request.data.get('is_internal', True)

        if not note:
            return Response(
                {'error': 'note is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_field = 'internal_notes' if is_internal else 'customer_notes'
        existing = getattr(order, target_field) or ''
        combined = f"{existing}\n{note}".strip() if existing else note
        setattr(order, target_field, combined)
        order.save(update_fields=[target_field, 'updated_at'])

        self._notify_order_update(order, 'order.updated')
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='reprint-kitchen-ticket')
    def reprint_kitchen_ticket(self, request, pk=None):
        """Queue a manual kitchen ticket reprint for the order."""
        order = self.get_object()
        result = enqueue_order_print_job(
            order,
            station='kitchen',
            template='kitchen_ticket',
            source='manual_reprint',
            dedupe=False,
            requested_by=request.user.email or request.user.username,
        )
        return Response(StorePrintJobSerializer(result.job).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Return a lightweight timeline for the order."""
        order = self.get_object()
        events = [
            {
                'id': f'{order.id}-created',
                'order_id': str(order.id),
                'event_type': 'created',
                'description': f'Pedido criado com status {order.status}',
                'created_at': order.created_at.isoformat(),
            }
        ]

        if order.paid_at:
            events.append({
                'id': f'{order.id}-paid',
                'order_id': str(order.id),
                'event_type': 'payment_paid',
                'description': 'Pagamento confirmado',
                'created_at': order.paid_at.isoformat(),
            })
        if order.shipped_at:
            events.append({
                'id': f'{order.id}-shipped',
                'order_id': str(order.id),
                'event_type': 'shipped',
                'description': 'Pedido enviado',
                'created_at': order.shipped_at.isoformat(),
            })
        if order.delivered_at:
            events.append({
                'id': f'{order.id}-delivered',
                'order_id': str(order.id),
                'event_type': 'delivered',
                'description': 'Pedido entregue',
                'created_at': order.delivered_at.isoformat(),
            })
        if order.cancelled_at:
            events.append({
                'id': f'{order.id}-cancelled',
                'order_id': str(order.id),
                'event_type': 'cancelled',
                'description': 'Pedido cancelado',
                'created_at': order.cancelled_at.isoformat(),
            })

        events.sort(key=lambda event: event['created_at'], reverse=True)
        return Response(events)
    
    @staticmethod
    def _pix_expired(order) -> bool:
        """True se o pedido é PIX e o código já expirou (não deve ser confirmado)."""
        return bool(
            order.payment_method == 'pix'
            and order.pix_expires_at
            and order.pix_expires_at < timezone.now()
        )

    @action(detail=True, methods=['post'])
    def update_payment_status(self, request, pk=None):
        """Update order payment status."""
        order = self.get_object()
        new_status = request.data.get('payment_status')

        if not new_status:
            return Response(
                {'error': 'payment_status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_statuses = [s[0] for s in StoreOrder.PaymentStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        paid = StoreOrder.PaymentStatus.PAID
        # Trava a linha sob transação: evita confirmação dupla concorrente (race).
        with transaction.atomic():
            order = StoreOrder.objects.select_for_update().get(pk=order.pk)

            # PIX expirado não pode ser confirmado manualmente.
            if new_status == paid and order.payment_status != paid and self._pix_expired(order):
                return Response(
                    {'error': 'PIX expirado — gere uma nova cobrança antes de confirmar o pagamento.',
                     'code': 'pix_expired'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            update_fields = ['payment_status', 'updated_at']
            order.payment_status = new_status
            # paid_at só no 1º pagamento confirmado — não sobrescreve o original.
            if new_status == paid and not order.paid_at:
                order.paid_at = timezone.now()
                update_fields.append('paid_at')
            order.save(update_fields=update_fields)

        # Fidelidade: pagamento confirmado pelo painel também credita (mesma
        # regra do webhook/status; idempotente por pedido).
        if new_status == paid:
            self._credit_loyalty(order)

        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None, **kwargs):
        """Mark order as paid (convenience endpoint)."""
        order = self.get_object()
        paid = StoreOrder.PaymentStatus.PAID

        # Trava a linha sob transação: evita confirmação dupla concorrente (race).
        with transaction.atomic():
            order = StoreOrder.objects.select_for_update().get(pk=order.pk)

            # PIX expirado não pode ser confirmado manualmente.
            if order.payment_status != paid and self._pix_expired(order):
                return Response(
                    {'error': 'PIX expirado — gere uma nova cobrança antes de confirmar o pagamento.',
                     'code': 'pix_expired'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            update_fields = ['payment_status', 'updated_at']
            order.payment_status = paid
            # paid_at só no 1º pagamento confirmado — não sobrescreve o original.
            if not order.paid_at:
                order.paid_at = timezone.now()
                update_fields.append('paid_at')
            order.save(update_fields=update_fields)

        logger.info(f"Order {order.order_number} marked as paid")

        self._credit_loyalty(order)

        # Notify via WebSocket
        self._notify_order_update(order, 'order.paid')

        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='recalcular-fidelidade')
    def recalcular_fidelidade(self, request, pk=None, **kwargs):
        """Recalcula os selos deste pedido pelas regras atuais da loja.

        Existe porque o crédito é uma fotografia tirada na entrega: quando a
        loja corrige `loyalty_units` depois da venda, o pedido antigo fica
        congelado no valor errado e não havia caminho no painel pra ajustar.
        """
        from apps.stores.services.loyalty_service import LoyaltyService

        order = self.get_object()
        resultado = LoyaltyService.recalculate_order_credit(order)
        return Response(resultado)

    @staticmethod
    def _credit_loyalty(order):
        try:
            from apps.stores.services.loyalty_service import LoyaltyService
            LoyaltyService.credit_order(order)
        except Exception:
            logger.warning('Falha ao creditar fidelidade do pedido %s', order.id, exc_info=True)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None, **kwargs):
        """Cancel an order."""
        order = self.get_object()
        reason = request.data.get('reason', '')

        order_service = OrderService()
        result = order_service.cancel_order(
            order,
            reason=reason,
            restore_stock=True,
            notify_customer=True,
        )

        if not result.get('success'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        order.refresh_from_db()
        self._notify_order_update(order, 'order.cancelled')
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'], url_path='emit_nfce')
    def emit_nfce(self, request, pk=None, **kwargs):
        """Emite a NFC-e do pedido via provider fiscal configurado na loja."""
        from apps.fiscal.providers.base import FiscalNotConfigured
        from apps.fiscal.services import emit_nfce_for_order

        order = self.get_object()
        try:
            doc = emit_nfce_for_order(order)
        except FiscalNotConfigured as exc:
            logger.warning('emit_nfce: config inválida pedido=%s loja=%s: %s',
                           order.id, order.store_id, exc)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': str(doc.id),
            'status': doc.status,
            'provider': doc.provider,
            'chave_acesso': doc.chave_acesso,
            'numero': doc.numero,
            'serie': doc.serie,
            'qrcode_url': doc.qrcode_url,
            'danfe_url': doc.danfe_url,
            'error_message': doc.error_message,
        }, status=status.HTTP_201_CREATED if doc.status == 'authorized' else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='generate_payment')
    def generate_payment(self, request, pk=None, **kwargs):
        """Generate a real PIX/card payment link for an admin-created order."""
        from apps.stores.services.checkout_service import CheckoutService

        order = self.get_object()
        payment_method = request.data.get('payment_method', order.payment_method or 'pix')
        payment_data = request.data.get('payment_data', {})

        # Bloqueia cobrança em pedidos encerrados (não há o que receber).
        _BLOCKED = {
            StoreOrder.OrderStatus.CANCELLED,
            StoreOrder.OrderStatus.REFUNDED,
            StoreOrder.OrderStatus.FAILED,
        }
        if order.status in _BLOCKED:
            return Response(
                {'error': f'Não é possível gerar cobrança para pedido {order.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valor da cobrança: explícito (usuário escolhe) ou default = amount_due.
        raw_amount = request.data.get('amount')
        if raw_amount is not None and raw_amount != '':
            try:
                amount = Decimal(str(raw_amount)).quantize(Decimal('0.01'))
            except (InvalidOperation, ValueError, TypeError):
                return Response({'error': 'Valor inválido.'}, status=status.HTTP_400_BAD_REQUEST)
            if amount <= Decimal('0.00'):
                return Response({'error': 'O valor deve ser maior que zero.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            amount = order.amount_due
            if amount <= Decimal('0.00'):
                return Response(
                    {'error': 'Pedido já está integralmente pago. Informe um valor para cobrar a mais.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = CheckoutService.create_payment(order, payment_method, payment_data, amount=amount)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Payment generation failed for order %s', order.id)
            return Response({'error': 'Erro ao gerar pagamento'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Erro ao gerar pagamento')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.refresh_from_db()
        self._notify_order_update(order, 'order.updated')

        return Response({'payment': result, 'order': StoreOrderSerializer(order).data})

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics. Optimized to use single aggregation query."""
        from django.db.models import Count, Sum, Case, When, Q, F

        store_id = request.query_params.get('store')
        # Use fresh queryset without prefetch for aggregation (incompatible with .values())
        # IDOR: sempre escopar às lojas do usuário ANTES de qualquer filtro por
        # param. Sem isto, `?store=<loja-alheia>` vazava a receita da concorrente
        # e a ausência de `store` agregava os números de TODAS as lojas.
        store_ids = self._get_user_store_ids()  # None => superuser (sem restrição)
        queryset = StoreOrder.objects.all()
        if store_ids is not None:
            queryset = queryset.filter(store_id__in=store_ids)

        if store_id:
            # Aceita slug OU UUID (antes só UUID → slug dava 500 no painel).
            queryset, _ = filter_by_store(queryset, store_id)

        now = timezone.now()
        today = inicio_do_dia()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Faturamento vem do núcleo (apps/stores/metrics/). As CONTAGENS
        # continuam sobre o queryset cru — a lista de pedidos precisa mostrar
        # o cancelado, o faturamento não.
        #
        # Este endpoint pode agregar VÁRIAS lojas (sem `?store` ele cobre todas
        # as do usuário), então usa a forma por queryset em vez de por loja.
        from apps.stores import metrics

        hoje = metrics.hoje()
        semana = metrics.ultimos_dias(8)

        def _receita(janela=None):
            qs = metrics.pedidos_de_receita(
                queryset=queryset,
                inicio=janela.inicio if janela else None,
                fim=janela.fim if janela else None,
            )
            return qs.aggregate(t=Sum('total'))['t'] or 0

        def _comparar(janela, rotulo):
            """Variação contra o período anterior.

            `variacao_pct` vem None quando o anterior foi ZERO: 0% lê como
            "estável", e sair de R$ 0 para R$ 500 não é estabilidade.
            """
            anterior = metrics.janela_anterior(janela)
            atual_v = Decimal(str(_receita(janela)))
            ant_v = Decimal(str(_receita(anterior)))
            delta = atual_v - ant_v
            pct = (delta / ant_v * 100) if ant_v else None
            return {
                'atual': float(atual_v),
                'anterior': float(ant_v),
                'delta': float(delta),
                'variacao_pct': round(float(pct), 1) if pct is not None else None,
                'rotulo': f'vs {rotulo}',
            }

        # Single aggregation query combines all counts
        agg = queryset.aggregate(
            # Total counts by period.
            # 'count_total' (não 'total') p/ não colidir com o FIELD 'total' usado
            # nos Sum('total') abaixo — o alias 'total' fazia o Django tratar o
            # campo como agregado ("'total' is an aggregate") e estourava 500.
            count_total=Count('id'),
            today=Count(Case(When(created_at__gte=today, then=1))),
            this_week=Count(Case(When(created_at__gte=week_ago, then=1))),
            this_month=Count(Case(When(created_at__gte=month_ago, then=1))),

            # Receita sai daqui: era agrupada por `created_at`, um eixo
            # diferente do resto do painel. Ver `_receita()` acima.
            # metrics-ok: valor PENDENTE — explicitamente o que ainda nao e
            # receita. O card do painel mostra isso como "a receber".
            revenue_pending=Sum('total', filter=Q(payment_status='pending')),

            # Counts por payment_status (o painel de pagamentos precisa do
            # nº exato de pagos/pendentes — by_status é STATUS do pedido, não
            # do pagamento; um pedido pode estar 'pago' mas ainda 'confirmed').
            # metrics-ok: CONTAGEM de pagamentos, nao soma de dinheiro.
            paid_count=Count('id', filter=Q(payment_status='paid')),
            pending_count=Count('id', filter=Q(payment_status='pending')),

            # By-status counts
            **{
                f'status_{status}': Count(Case(When(status=status, then=1)))
                for status, _ in StoreOrder.OrderStatus.choices
            }
        )

        # Build response from single aggregation
        stats = {
            'total': agg['count_total'],
            'today': agg['today'],
            'this_week': agg['this_week'],
            'this_month': agg['this_month'],
            'by_status': {
                status: agg.get(f'status_{status}', 0)
                for status, _ in StoreOrder.OrderStatus.choices
            },
            'by_payment_status': {
                'paid': agg['paid_count'],
                'pending': agg['pending_count'],
            },
            'revenue': {
                'total': _receita(),
                'today': _receita(hoje),
                'week': _receita(semana),
                'pending': agg['revenue_pending'] or 0,
            },
            # Comparativo com o período anterior, do mesmo tamanho. Número
            # sozinho não informa: R$ 137 pode ser um dia bom ou metade do
            # normal, e quem olha o card não tem como saber.
            'comparativo': {
                'today': _comparar(hoje, 'ontem'),
                'week': _comparar(semana, 'semana anterior'),
            }
        }

        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        """Get orders by customer phone number."""
        phone = request.query_params.get('phone')
        store_id = request.query_params.get('store')
        
        if not phone:
            return Response(
                {'error': 'phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(customer_phone=phone)
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        return Response(StoreOrderSerializer(queryset[:20], many=True).data)


def _anotar_crm(qs):
    """Gasto, pedidos e última compra REAIS, por subquery.

    Vem dos pedidos e não de `total_spent`/`total_orders`: os contadores são
    gravados por signal e divergem — 12 dos 78 clientes da Cê Saladas tinham
    valor errado em 07/ago.

    Subquery correlacionada e não `annotate(Sum(...))` com join: o join
    multiplicaria as linhas de endereço já trazidas pelo prefetch e somaria o
    mesmo pedido várias vezes. Continua sendo UMA query para a lista inteira.
    """
    from django.db.models import OuterRef, Subquery
    from apps.stores.metrics import eixo_de_receita, pedidos_de_receita

    # `customer` é a FK do pedido para auth.User; `StoreCustomer.user` é o
    # mesmo User visto do lado do perfil da loja.
    do_cliente = pedidos_de_receita().filter(
        store=OuterRef('store_id'), customer=OuterRef('user_id'),
    )

    return qs.annotate(
        _gasto_real=Subquery(
            do_cliente.values('customer').annotate(t=Sum('total')).values('t')[:1]
        ),
        _pedidos_reais=Subquery(
            do_cliente.values('customer').annotate(n=Count('id')).values('n')[:1]
        ),
        _ultima_compra=Subquery(
            do_cliente.annotate(_quando=eixo_de_receita())
            .order_by('-_quando')
            .values('_quando')[:1]
        ),
    )


class StoreCustomerViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing store customers."""

    queryset = StoreCustomer.objects.all()
    pagination_class = StoreOperationsPagination
    serializer_class = StoreCustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if store_param:
            qs, _ = filter_by_store(qs, store_param)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(phone__icontains=search) |
                Q(whatsapp__icontains=search)
            )
        # prefetch_related('address_list'): get_default_address() e o campo
        # 'addresses' do serializer eram lidos por linha → N+1 em
        # store_customer_addresses. Com o prefetch, é 1 query p/ todos os endereços.
        qs = qs.select_related('user', 'store').prefetch_related('address_list')
        return _anotar_crm(qs)

    def perform_create(self, serializer):
        """Injeta a store no create garantindo isolamento por tenant.

        I-1: Na rota flat (?store=<slug>), IsStoreOwnerOrStaff não pode checar
        o store_pk (não existe no kwargs), então verificamos aqui explicitamente
        se o usuário tem acesso à loja resolvida antes de salvar.
        M-3: A branch sem store foi removida — sem store resolvida é 400/403,
        nunca um save silencioso storeless.
        """
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if not store_param:
            raise DRFValidationError({'store': 'Parâmetro store é obrigatório.'})

        try:
            uuid_module.UUID(str(store_param))
            store = Store.objects.filter(pk=store_param).first()
        except (ValueError, AttributeError):
            store = Store.objects.filter(slug=store_param).first()

        if store is None:
            raise DRFValidationError({'store': 'Loja não encontrada.'})

        # I-1: verificar acesso ao store resolvido (cobre a rota flat sem store_pk)
        if not self.request.user.is_superuser and not user_can_access_store(self.request.user, store):
            raise PermissionDenied('Você não tem permissão para criar clientes nesta loja.')

        serializer.save(store=store)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """KPIs agregados dos clientes no escopo da loja (1 query).

        Evita que o painel baixe centenas de clientes só para calcular
        contadores no JS. O escopo reusa o get_queryset do viewset
        (StoreQuerysetMixin + ?store=), garantindo isolamento por tenant.
        """
        agg = self.get_queryset().aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            with_orders=Count('id', filter=Q(total_orders__gt=0)),
            total_revenue=Sum('total_spent'),
        )
        revenue = agg['total_revenue'] or Decimal('0.00')
        return Response({
            'total': agg['total'],
            'active': agg['active'],
            'with_orders': agg['with_orders'],
            'total_revenue': f"{revenue:.2f}",
            'segmentos': self._segmentos(),
        })

    # Réguas dos segmentos, em dias sem comprar.
    #
    # 30 dias porque o ciclo de recompra de delivery é semanal a quinzenal:
    # um mês sem aparecer já é sinal. 45 porque, passado isso, quem some
    # raramente volta sozinho — vira campanha, não lembrete.
    DIAS_ATIVO = 30
    DIAS_RISCO = 45

    def _segmentos(self):
        """Quantos clientes em cada estágio, com a régua declarada.

        "2.386 clientes cadastrados" não é acionável; "106 em risco, 30 a 45
        dias sem comprar" é — dá para disparar campanha hoje à tarde.

        A RÉGUA VAI JUNTO. "Em risco" sem o corte é opinião nossa disfarçada de
        dado: quem lê não tem como julgar se concorda, nem como explicar o
        número para outra pessoa.
        """
        from apps.stores.metrics import hoje_local

        hoje = hoje_local()
        corte_ativo = hoje - timedelta(days=self.DIAS_ATIVO)
        corte_risco = hoje - timedelta(days=self.DIAS_RISCO)

        qs = self.get_queryset()
        agg = qs.aggregate(
            ativos=Count('id', filter=Q(_ultima_compra__date__gte=corte_ativo)),
            em_risco=Count('id', filter=Q(
                _ultima_compra__date__lt=corte_ativo,
                _ultima_compra__date__gte=corte_risco,
            )),
            inativos=Count('id', filter=Q(_ultima_compra__date__lt=corte_risco)),
            # Cadastro sem compra é LEAD, não cliente perdido. Somar os dois
            # inflaria "inativos" e mandaria campanha de reativação para quem
            # nunca ativou.
            sem_compra=Count('id', filter=Q(_ultima_compra__isnull=True)),
        )
        return {
            **agg,
            'reguas': {
                'ativos': f'comprou nos últimos {self.DIAS_ATIVO} dias',
                'em_risco': f'{self.DIAS_ATIVO} a {self.DIAS_RISCO} dias sem comprar',
                'inativos': f'mais de {self.DIAS_RISCO} dias sem comprar',
                'sem_compra': 'cadastrado, nunca comprou',
            },
        }

    @action(detail=True, methods=['post'])
    def update_stats(self, request, pk=None):
        """Recalculate customer statistics."""
        customer = self.get_object()
        customer.update_stats()
        return Response(StoreCustomerSerializer(customer).data)
