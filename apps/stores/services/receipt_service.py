"""
Receipt PDF generation service using ReportLab.

Generates a clean A4 receipt for a StoreOrder that can be:
- Downloaded by the customer/staff
- Attached to a WhatsApp message
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.formats import date_format

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from apps.stores.models import StoreOrder


# ---------------------------------------------------------------------------
# Colour palette (matches pastita brand)
# ---------------------------------------------------------------------------
PRIMARY = (0.55, 0.18, 0.18)      # marsala
DARK    = (0.15, 0.15, 0.15)
GREY    = (0.45, 0.45, 0.45)
LIGHT   = (0.95, 0.95, 0.95)
WHITE   = (1, 1, 1)
GREEN   = (0.13, 0.55, 0.13)


def _fmt_brl(value) -> str:
    try:
        return f"R$ {Decimal(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def generate_order_receipt_pdf(order: "StoreOrder") -> bytes:
    """
    Return raw PDF bytes for *order*.

    Raises ImportError if reportlab is not installed.
    Raises any other exception on render failure (caller should catch).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 4 * cm  # usable width

    def style(name, **kw):
        s = ParagraphStyle(name, parent=styles["Normal"], **kw)
        return s

    s_title   = style("title",   fontSize=18, textColor=colors.Color(*PRIMARY), leading=22, alignment=TA_CENTER, spaceAfter=4)
    s_sub     = style("sub",     fontSize=9,  textColor=colors.Color(*GREY),    leading=12, alignment=TA_CENTER)
    s_section = style("section", fontSize=10, textColor=colors.Color(*PRIMARY), leading=14, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
    s_body    = style("body",    fontSize=9,  textColor=colors.Color(*DARK),    leading=13)
    s_right   = style("right",   fontSize=9,  textColor=colors.Color(*DARK),    leading=13, alignment=TA_RIGHT)
    s_bold    = style("bold",    fontSize=9,  textColor=colors.Color(*DARK),    leading=13, fontName="Helvetica-Bold")
    s_total   = style("total",   fontSize=11, textColor=colors.Color(*PRIMARY), leading=16, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    s_footer  = style("footer",  fontSize=8,  textColor=colors.Color(*GREY),    leading=11, alignment=TA_CENTER)

    store = order.store
    items = list(order.items.select_related("product").all())
    combo_items = list(order.combo_items.all())
    issued_at = timezone.localtime(order.created_at)

    story = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    story.append(Paragraph(store.name, s_title))
    if getattr(store, "phone", None):
        story.append(Paragraph(store.phone, s_sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width=W, thickness=1.5, color=colors.Color(*PRIMARY)))
    story.append(Spacer(1, 6))

    # ------------------------------------------------------------------
    # Order meta
    # ------------------------------------------------------------------
    meta_data = [
        ["Pedido #", order.order_number, "Data", issued_at.strftime("%d/%m/%Y %H:%M")],
        ["Status", order.get_status_display(), "Pagamento", order.get_payment_status_display()],
    ]
    meta_table = Table(meta_data, colWidths=[2.5 * cm, W / 2 - 2.5 * cm, 2.5 * cm, W / 2 - 2.5 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (0, -1), colors.Color(*PRIMARY)),
        ("TEXTCOLOR",   (2, 0), (2, -1), colors.Color(*PRIMARY)),
        ("TEXTCOLOR",   (1, 0), (1, -1), colors.Color(*DARK)),
        ("TEXTCOLOR",   (3, 0), (3, -1), colors.Color(*DARK)),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Customer info
    # ------------------------------------------------------------------
    story.append(Paragraph("Cliente", s_section))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.Color(*LIGHT)))
    story.append(Spacer(1, 4))

    cust_rows = [
        ["Nome", order.customer_name or "-"],
        ["Telefone", order.customer_phone or "-"],
        ["E-mail", order.customer_email or "-"],
    ]
    if order.delivery_method == "delivery" and order.delivery_address:
        addr = order.delivery_address
        addr_str = ", ".join(filter(None, [
            addr.get("street", ""), addr.get("number", ""),
            addr.get("complement", ""), addr.get("neighborhood", ""),
            addr.get("city", ""), addr.get("state", ""),
        ]))
        cust_rows.append(["Endereço", addr_str or "-"])

    cust_table = Table(cust_rows, colWidths=[2.8 * cm, W - 2.8 * cm])
    cust_table.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (0, -1), colors.Color(*GREY)),
        ("TEXTCOLOR",   (1, 0), (1, -1), colors.Color(*DARK)),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(cust_table)
    story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    story.append(Paragraph("Itens do Pedido", s_section))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.Color(*LIGHT)))
    story.append(Spacer(1, 4))

    item_rows = [["Descrição", "Qtd", "Unitário", "Total"]]

    for item in items:
        name = item.product_name or (item.product.name if item.product else "-")
        if item.variant_name:
            name += f"\n({item.variant_name})"
        if item.notes:
            name += f"\nObs: {item.notes}"
        item_rows.append([
            name,
            str(item.quantity),
            _fmt_brl(item.unit_price),
            _fmt_brl(item.unit_price * item.quantity),
        ])

    for ci in combo_items:
        name = ci.combo_name or "-"
        if ci.notes:
            name += f"\nObs: {ci.notes}"
        item_rows.append([
            name,
            str(ci.quantity),
            _fmt_brl(ci.unit_price),
            _fmt_brl(ci.unit_price * ci.quantity),
        ])

    col_w = [W - 7 * cm, 1.5 * cm, 2.5 * cm, 3 * cm]
    items_table = Table(item_rows, colWidths=col_w, repeatRows=1)
    items_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",  (0, 0), (-1, 0), colors.Color(*PRIMARY)),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        # Data rows
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR",   (0, 1), (-1, -1), colors.Color(*DARK)),
        ("ALIGN",       (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",       (0, 0), (0, -1), "LEFT"),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(*LIGHT)]),
        ("LINEBELOW",   (0, 0), (-1, 0), 0.5, colors.Color(*PRIMARY)),
        ("LINEBELOW",   (0, -1), (-1, -1), 0.5, colors.Color(*LIGHT)),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    totals = []
    if order.subtotal != order.total:
        totals.append(["Subtotal", _fmt_brl(order.subtotal)])
    if order.discount and order.discount > 0:
        discount_label = f"Desconto ({order.coupon_code})" if order.coupon_code else "Desconto"
        totals.append([discount_label, f"- {_fmt_brl(order.discount)}"])
    if order.delivery_fee and order.delivery_fee > 0:
        totals.append(["Taxa de entrega", _fmt_brl(order.delivery_fee)])
    if order.tax and order.tax > 0:
        totals.append(["Impostos", _fmt_brl(order.tax)])

    for row in totals:
        tot_table = Table([row], colWidths=[W - 3.5 * cm, 3.5 * cm])
        tot_table.setStyle(TableStyle([
            ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",   (0, 0), (-1, -1), colors.Color(*GREY)),
            ("ALIGN",       (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING",  (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(tot_table)

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=W, thickness=1, color=colors.Color(*PRIMARY)))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"TOTAL &nbsp;&nbsp; {_fmt_brl(order.total)}", s_total))
    story.append(Spacer(1, 4))

    # Payment method
    if order.payment_method:
        story.append(Paragraph(f"Forma de pagamento: {order.payment_method}", s_right))
    story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    if order.customer_notes:
        story.append(Paragraph("Observações", s_section))
        story.append(Paragraph(order.customer_notes, s_body))
        story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.Color(*LIGHT)))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Recibo gerado em {issued_at.strftime('%d/%m/%Y %H:%M')} — {store.name}", s_footer))

    doc.build(story)
    return buf.getvalue()
