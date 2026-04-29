"""
Services for automatic print job generation and agent orchestration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.stores.models import StoreOrder, StorePrintAgent, StorePrintJob

logger = logging.getLogger(__name__)


def _money(value: Decimal | int | float | str | None) -> str:
    number = Decimal(str(value or 0))
    return f"{number:.2f}"


def _extract_address_lines(order: StoreOrder) -> list[str]:
    if order.delivery_method == StoreOrder.DeliveryMethod.PICKUP:
        return ['PEDIDO PARA RETIRADA']

    address = order.delivery_address or {}
    if not isinstance(address, dict):
        return [str(address)]

    line1 = ', '.join(filter(None, [
        address.get('rua') or address.get('street'),
        f"nº {address.get('numero') or address.get('number')}" if address.get('numero') or address.get('number') else '',
    ]))
    line2 = ' - '.join(filter(None, [
        address.get('complemento') or address.get('complement'),
        address.get('bairro') or address.get('neighborhood'),
    ]))
    line3 = ' / '.join(filter(None, [
        address.get('cidade') or address.get('city'),
        address.get('estado') or address.get('state'),
        address.get('cep') or address.get('zip_code'),
    ]))

    fallback = address.get('raw_address') or address.get('address')
    return [line for line in [line1, line2, line3, fallback] if line]


def _ingredient_lines(ingredients: Iterable[dict]) -> list[str]:
    lines: list[str] = []
    for ingredient in ingredients:
        if not isinstance(ingredient, dict):
            continue
        name = str(ingredient.get('name') or '').strip()
        if not name:
            continue
        role = str(ingredient.get('role') or '').strip()
        price = Decimal(str(ingredient.get('price') or 0))
        prefix = f"{role}: " if role else ''
        suffix = f" (+R$ {_money(price)})" if price > 0 else ''
        lines.append(f"{prefix}{name}{suffix}")
    return lines


def build_order_print_payload(order: StoreOrder, *, template: str = StorePrintJob.Template.KITCHEN_TICKET) -> dict:
    items = []
    for item in order.items.all():
        options = item.options if isinstance(item.options, dict) else {}
        details = []
        if item.variant_name:
            details.append(item.variant_name)
        details.extend(_ingredient_lines(options.get('ingredients') or []))
        items.append({
            'type': 'item',
            'qty': item.quantity,
            'name': item.product_name,
            'unit_price': _money(item.unit_price),
            'subtotal': _money(item.subtotal),
            'details': details,
            'notes': item.notes or '',
        })

    for combo in order.combo_items.all():
        customizations = combo.customizations if isinstance(combo.customizations, dict) else {}
        items.append({
            'type': 'combo',
            'qty': combo.quantity,
            'name': combo.combo_name,
            'unit_price': _money(combo.unit_price),
            'subtotal': _money(combo.subtotal),
            'details': ['COMBO', *_ingredient_lines(customizations.get('ingredients') or [])],
            'notes': combo.notes or '',
        })

    scheduled_for = ' '.join(filter(None, [
        order.scheduled_date.isoformat() if order.scheduled_date else '',
        order.scheduled_time or '',
    ])).strip()

    return {
        'template': template,
        'generated_at': timezone.now().isoformat(),
        'store': {
            'id': str(order.store_id),
            'name': order.store.name,
            'slug': order.store.slug,
            'phone': order.store.phone or order.store.whatsapp_number or '',
            'address': order.store.address or '',
            'city': order.store.city or '',
            'state': order.store.state or '',
        },
        'order': {
            'id': str(order.id),
            'order_number': order.order_number,
            'created_at': order.created_at.isoformat(),
            'scheduled_for': scheduled_for,
            'delivery_method': order.delivery_method,
            'payment_method': order.payment_method or '',
            'payment_status': order.payment_status,
            'status': order.status,
            'coupon_code': order.coupon_code or '',
            'customer_notes': order.customer_notes or '',
            'internal_notes': order.internal_notes or '',
            'delivery_notes': order.delivery_notes or '',
        },
        'customer': {
            'name': order.customer_name,
            'phone': order.customer_phone,
            'email': order.customer_email,
        },
        'address_lines': _extract_address_lines(order),
        'items': items,
        'totals': {
            'subtotal': _money(order.subtotal),
            'discount': _money(order.discount),
            'delivery_fee': _money(order.delivery_fee),
            'total': _money(order.total),
        },
    }


@dataclass(slots=True)
class PrintJobResult:
    job: StorePrintJob
    created: bool


def enqueue_order_print_job(
    order: StoreOrder,
    *,
    station: str = 'kitchen',
    template: str = StorePrintJob.Template.KITCHEN_TICKET,
    source: str = StorePrintJob.Source.ORDER_CREATED,
    dedupe: bool = True,
    requested_by: str = '',
) -> PrintJobResult:
    payload = build_order_print_payload(order, template=template)
    dedupe_key = ''
    if dedupe:
        dedupe_key = f"order:{order.id}:station:{station}:template:{template}:source:{source}"

    defaults = {
        'store': order.store,
        'order': order,
        'station': station,
        'template': template,
        'source': source,
        'payload': payload,
        'title': f"{order.store.name} #{order.order_number}",
        'max_attempts': 3,
        'metadata': {'requested_by': requested_by} if requested_by else {},
    }

    try:
        with transaction.atomic():
            job, created = StorePrintJob.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults=defaults,
            ) if dedupe_key else (StorePrintJob.objects.create(**defaults), True)
    except IntegrityError:
        job = StorePrintJob.objects.get(dedupe_key=dedupe_key)
        created = False

    return PrintJobResult(job=job, created=created)


def claim_next_print_job(agent: StorePrintAgent) -> StorePrintJob | None:
    with transaction.atomic():
        job = (
            StorePrintJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                store=agent.store,
                station=agent.station,
                status=StorePrintJob.JobStatus.PENDING,
                available_at__lte=timezone.now(),
            )
            .order_by('created_at')
            .first()
        )
        if not job:
            return None

        job.claim(agent)
        return job


def complete_print_job(job: StorePrintJob, *, printer_name: str = '', metadata: dict | None = None) -> StorePrintJob:
    job.complete(printer_name=printer_name, metadata=metadata)
    return job


def fail_print_job(
    job: StorePrintJob,
    *,
    error_message: str,
    retryable: bool = True,
    retry_delay_seconds: int = 15,
) -> StorePrintJob:
    job.fail(
        error_message=error_message,
        retryable=retryable,
        retry_delay_seconds=retry_delay_seconds,
    )
    return job
