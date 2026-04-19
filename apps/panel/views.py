"""
Pastita Panel — Django-rendered admin panel with multi-tenant support.

Served at /panel/ on backend.pastita.com.br
Authentication: Django session (wraps the existing Token auth)
Multi-tenant: store selected per session → request.session['panel_store_id']
"""
import json
import logging
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from apps.stores.models import Store, StoreOrder, StoreProduct, StoreCustomer
from apps.conversations.models import Conversation
from .decorators import panel_login_required, store_required

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_accessible_stores(user: User):
    """Return all stores the user can manage."""
    if user.is_superuser or user.is_staff:
        return Store.objects.filter(is_active=True).order_by('name')
    return Store.objects.filter(
        Q(owner=user) | Q(staff=user), is_active=True
    ).distinct().order_by('name')


def _get_selected_store(request) -> Store | None:
    store_id = request.session.get('panel_store_id')
    if not store_id:
        return None
    try:
        stores = _get_accessible_stores(request.user)
        return stores.get(id=store_id)
    except Store.DoesNotExist:
        request.session.pop('panel_store_id', None)
        return None


def _panel_context(request) -> dict:
    """Base context injected into every panel template."""
    store = _get_selected_store(request)
    pending_count = 0
    if store:
        try:
            pending_count = StoreOrder.objects.filter(
                store=store, status='pending'
            ).count()
        except Exception:
            pass
    return {
        'current_store': store,
        'user': request.user,
        'pending_orders_count': pending_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
def panel_login(request):
    if request.user.is_authenticated:
        return redirect('panel:stores')

    error = None
    if request.method == 'POST':
        identifier = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        # Try by email, then username
        user_obj = User.objects.filter(email__iexact=identifier).first() \
                   or User.objects.filter(username__iexact=identifier).first()

        user = authenticate(request, username=user_obj.username if user_obj else '', password=password)
        if user and user.is_active:
            login(request, user)
            return redirect(request.GET.get('next') or 'panel:stores')
        error = 'E-mail ou senha inválidos.'

    return render(request, 'panel/login.html', {'error': error})


@panel_login_required
def panel_logout(request):
    logout(request)
    return redirect('panel:login')


# ─────────────────────────────────────────────────────────────────────────────
# Store selector (multi-tenant entry point)
# ─────────────────────────────────────────────────────────────────────────────

@panel_login_required
def store_select(request):
    stores = _get_accessible_stores(request.user)

    if request.method == 'POST':
        store_id = request.POST.get('store_id')
        if store_id and stores.filter(id=store_id).exists():
            request.session['panel_store_id'] = store_id
            return redirect('panel:dashboard')

    # Auto-select if only one store
    if stores.count() == 1:
        request.session['panel_store_id'] = str(stores.first().id)
        return redirect('panel:dashboard')

    return render(request, 'panel/stores.html', {
        'stores': stores,
        **_panel_context(request),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def dashboard(request):
    store = _get_selected_store(request)
    today = timezone.now().date()

    # Orders today
    orders_today = StoreOrder.objects.filter(
        store=store, created_at__date=today
    ).aggregate(
        count=Count('id'),
        revenue=Sum('total'),
    )

    # Order status breakdown
    order_statuses = list(
        StoreOrder.objects.filter(store=store)
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )

    # Active conversations (via store's WhatsApp account)
    try:
        wa_account = store.get_whatsapp_account()
        if wa_account:
            active_conversations = Conversation.objects.filter(account=wa_account, status='open').count()
            pending_conversations = Conversation.objects.filter(account=wa_account, status='pending').count()
        else:
            active_conversations = 0
            pending_conversations = 0
    except Exception:
        active_conversations = 0
        pending_conversations = 0

    # Recent orders
    recent_orders = StoreOrder.objects.filter(store=store).order_by('-created_at')[:8]

    ctx = {
        'orders_today': orders_today['count'] or 0,
        'revenue_today': orders_today['revenue'] or Decimal('0'),
        'active_conversations': active_conversations,
        'pending_conversations': pending_conversations,
        'order_statuses': order_statuses,
        'recent_orders': recent_orders,
        **_panel_context(request),
    }
    return render(request, 'panel/dashboard.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def orders_list(request):
    store = _get_selected_store(request)
    qs = StoreOrder.objects.filter(store=store).order_by('-created_at')

    # Filters
    status = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    payment_status = request.GET.get('payment_status', '')

    if status:
        qs = qs.filter(status=status)
    if payment_status:
        qs = qs.filter(payment_status=payment_status)
    if search:
        qs = qs.filter(
            Q(order_number__icontains=search)
            | Q(customer_name__icontains=search)
            | Q(customer_email__icontains=search)
            | Q(customer_phone__icontains=search)
        )

    # Pagination
    page = max(1, int(request.GET.get('page', 1)))
    page_size = 25
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    orders = qs[(page - 1) * page_size: page * page_size]

    ctx = {
        'orders': orders,
        'total': total,
        'page': page,
        'total_pages': total_pages,
        'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        'status_filter': status,
        'payment_status_filter': payment_status,
        'search': search,
        'order_statuses': StoreOrder.OrderStatus.choices,
        **_panel_context(request),
    }
    return render(request, 'panel/orders/list.html', ctx)


@store_required
def order_detail(request, order_id):
    store = _get_selected_store(request)
    order = get_object_or_404(StoreOrder, id=order_id, store=store)

    # PATCH: update status via POST
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status and new_status in dict(StoreOrder.OrderStatus.choices):
            old_status = order.status
            try:
                order.update_status(new_status, notify=True)
                logger.info(f"Panel: Order {order.order_number} status {old_status}→{new_status} by {request.user}")
            except Exception as e:
                logger.error(f"Panel: Failed to update order {order.order_number} status: {e}")
            return redirect('panel:order_detail', order_id=order_id)

    items = order.items.select_related('product').all() if hasattr(order, 'items') else []

    # Pipeline steps for the visual stepper (val, label, icon)
    pipeline_steps = [
        ('pending',          'Pendente',  '⏳'),
        ('confirmed',        'Confirmado','✅'),
        ('preparing',        'Preparo',   '🍳'),
        ('out_for_delivery', 'Entrega',   '🛵'),
        ('delivered',        'Entregue',  '📦'),
    ]
    step_order = [v for v, _, _ in pipeline_steps]
    current_idx = step_order.index(order.status) if order.status in step_order else -1
    completed_steps = set(step_order[:current_idx])

    ctx = {
        'order': order,
        'items': items,
        'order_statuses': StoreOrder.OrderStatus.choices,
        'pipeline_steps': pipeline_steps,
        'completed_steps': completed_steps,
        **_panel_context(request),
    }
    return render(request, 'panel/orders/detail.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Conversations
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def conversations_list(request):
    store = _get_selected_store(request)

    # Filter conversations through the store's WhatsApp account
    try:
        wa_account = store.get_whatsapp_account()
        if wa_account:
            qs = Conversation.objects.filter(account=wa_account).order_by('-last_message_at', '-created_at')
        else:
            qs = Conversation.objects.none()
    except Exception:
        qs = Conversation.objects.none()

    status = request.GET.get('status', 'open')
    search = request.GET.get('q', '').strip()

    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(phone_number__icontains=search)
            | Q(contact_name__icontains=search)
        )

    page = max(1, int(request.GET.get('page', 1)))
    page_size = 30
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    conversations = qs[(page - 1) * page_size: page * page_size]

    STATUS_CHOICES = [
        ('', 'Todos'),
        ('open', 'Abertas'),
        ('pending', 'Pendentes'),
        ('resolved', 'Resolvidas'),
        ('closed', 'Fechadas'),
    ]

    ctx = {
        'conversations': conversations,
        'total': total,
        'page': page,
        'total_pages': total_pages,
        'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        'status_filter': status,
        'search': search,
        'status_choices': STATUS_CHOICES,
        **_panel_context(request),
    }
    return render(request, 'panel/conversations/list.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def products_list(request):
    store = _get_selected_store(request)
    qs = StoreProduct.objects.filter(store=store).order_by('name')

    search = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    active_only = request.GET.get('active', '') == '1'

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if category:
        qs = qs.filter(categories__id=category)
    if active_only:
        qs = qs.filter(is_active=True)

    # Categories for filter
    from apps.stores.models import StoreCategory
    categories = StoreCategory.objects.filter(store=store, is_active=True).order_by('name')

    page = max(1, int(request.GET.get('page', 1)))
    page_size = 30
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    products = qs[(page - 1) * page_size: page * page_size]

    ctx = {
        'products': products,
        'categories': categories,
        'total': total,
        'page': page,
        'total_pages': total_pages,
        'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        'search': search,
        'category_filter': category,
        'active_only': active_only,
        **_panel_context(request),
    }
    return render(request, 'panel/products/list.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def customers_list(request):
    store = _get_selected_store(request)
    qs = StoreCustomer.objects.filter(store=store).order_by('-created_at')

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    page = max(1, int(request.GET.get('page', 1)))
    page_size = 30
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    customers = qs[(page - 1) * page_size: page * page_size]

    ctx = {
        'customers': customers,
        'total': total,
        'page': page,
        'total_pages': total_pages,
        'page_range': range(max(1, page - 2), min(total_pages + 1, page + 3)),
        'search': search,
        **_panel_context(request),
    }
    return render(request, 'panel/customers/list.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

@store_required
def store_settings(request):
    store = _get_selected_store(request)
    saved = False

    if request.method == 'POST':
        # Basic store settings update
        store.name = request.POST.get('name', store.name).strip() or store.name
        store.email = request.POST.get('email', store.email).strip()
        store.phone = request.POST.get('phone', store.phone).strip()
        store.address = request.POST.get('address', store.address).strip()
        store.city = request.POST.get('city', store.city).strip()
        store.state = request.POST.get('state', store.state).strip()
        store.delivery_enabled = request.POST.get('delivery_enabled') == 'on'
        store.pickup_enabled = request.POST.get('pickup_enabled') == 'on'
        try:
            store.min_order_value = Decimal(request.POST.get('min_order_value', str(store.min_order_value)))
            store.default_delivery_fee = Decimal(request.POST.get('default_delivery_fee', str(store.default_delivery_fee)))
        except Exception:
            pass

        # WhatsApp message templates
        if not isinstance(store.metadata, dict):
            store.metadata = {}
        store.metadata['whatsapp_messages'] = {
            'confirmed':        request.POST.get('msg_confirmed', '').strip(),
            'preparing':        request.POST.get('msg_preparing', '').strip(),
            'out_for_delivery': request.POST.get('msg_out_for_delivery', '').strip(),
            'delivered':        request.POST.get('msg_delivered', '').strip(),
        }
        store.save()
        saved = True

    # Load current message templates (with defaults shown as placeholders)
    wa_msgs = store.metadata.get('whatsapp_messages', {}) if isinstance(store.metadata, dict) else {}

    ctx = {
        'store': store,
        'saved': saved,
        'wa_msgs': wa_msgs,
        **_panel_context(request),
    }
    return render(request, 'panel/settings.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# API helpers (JSON endpoints for AJAX)
# ─────────────────────────────────────────────────────────────────────────────

@panel_login_required
def api_switch_store(request):
    """AJAX: switch the active store."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        store_id = data.get('store_id')
    except (json.JSONDecodeError, TypeError):
        store_id = request.POST.get('store_id')

    stores = _get_accessible_stores(request.user)
    if store_id and stores.filter(id=store_id).exists():
        request.session['panel_store_id'] = store_id
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Store not found'}, status=404)
