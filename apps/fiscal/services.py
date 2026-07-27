"""Emissão de NFC-e a partir de um StoreOrder."""
import logging
import re
from decimal import Decimal

from .models import FiscalDocument
from .providers.base import FiscalNotConfigured, FiscalProvider
from .providers.focus import FocusProvider
from .providers.sefaz import SefazProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type[FiscalProvider]] = {
    FiscalDocument.Provider.FOCUS: FocusProvider,
    FiscalDocument.Provider.SEFAZ: SefazProvider,
}

# Defaults food service: NCM genérico de preparações alimentícias e
# CFOP de venda presencial no estado
DEFAULT_NCM = '21069090'
DEFAULT_CFOP = '5102'


def get_fiscal_config(store) -> dict:
    cfg = (store.metadata or {}).get('fiscal') or {}
    if not isinstance(cfg, dict):
        return {}
    return cfg


def _digits(value: str) -> str:
    return re.sub(r'\D', '', value or '')


def build_nfce_payload(order, config: dict) -> dict:
    """Monta o JSON de NFC-e no formato Focus NFe (que espelha os campos SEFAZ,
    então o provider sefaz reaproveita o mesmo payload como fonte)."""
    cnpj = _digits(config.get('cnpj', ''))
    if not cnpj:
        raise FiscalNotConfigured('CNPJ ausente na config fiscal da loja')

    items = []
    for idx, item in enumerate(order.items.all(), start=1):
        product = item.product
        ncm = ''
        if product is not None:
            ncm = str((product.attributes or {}).get('ncm') or '')
        items.append({
            'numero_item': idx,
            'codigo_produto': (product.sku if product else '') or str(idx),
            'descricao': item.product_name,
            'quantidade_comercial': float(item.quantity),
            'quantidade_tributavel': float(item.quantity),
            'cfop': config.get('cfop_padrao', DEFAULT_CFOP),
            'valor_unitario_comercial': float(item.unit_price),
            'valor_unitario_tributavel': float(item.unit_price),
            'unidade_comercial': 'un',
            'unidade_tributavel': 'un',
            'codigo_ncm': ncm or config.get('ncm_padrao', DEFAULT_NCM),
            # Simples Nacional: CSOSN 102 (sem permissão de crédito)
            'icms_situacao_tributaria': config.get('csosn', '102'),
            'icms_origem': 0,
            'valor_bruto': float(item.subtotal),
        })

    payment_map = {
        'cash': '01', 'credit_card': '03', 'debit_card': '04', 'pix': '17',
    }
    forma_pagamento = payment_map.get(order.payment_method or '', '99')

    payload = {
        'cnpj_emitente': cnpj,
        'data_emissao': order.created_at.isoformat(),
        'indicador_inscricao_estadual_destinatario': '9',
        'modalidade_frete': 9,
        'local_destino': 1,
        'presenca_comprador': 1,
        'natureza_operacao': 'VENDA AO CONSUMIDOR',
        'itens': items,
        'formas_pagamento': [{
            'forma_pagamento': forma_pagamento,
            'valor_pagamento': float(order.total),
        }],
    }
    if order.discount and Decimal(order.discount) > 0:
        payload['valor_desconto'] = float(order.discount)

    # NFC-e aceita consumidor não identificado; com cliente vinculado vai o nome
    if order.customer_name and order.customer_name != 'Cliente Balcão':
        payload['nome_destinatario'] = order.customer_name

    return payload


def emit_nfce_for_order(order) -> FiscalDocument:
    """Emite (ou retorna a já autorizada) NFC-e do pedido."""
    existing = FiscalDocument.objects.filter(
        order=order,
        status__in=[FiscalDocument.Status.AUTHORIZED, FiscalDocument.Status.PENDING],
    ).first()
    if existing:
        return existing

    config = get_fiscal_config(order.store)
    provider_key = config.get('provider') or FiscalDocument.Provider.FOCUS
    provider_cls = PROVIDERS.get(provider_key)
    if provider_cls is None:
        raise FiscalNotConfigured(f'Provider fiscal desconhecido: {provider_key}')
    if not config:
        raise FiscalNotConfigured(
            'Loja sem config fiscal. '
            'Configure provider, CNPJ e token nas configurações fiscais da loja antes de emitir.'
        )

    doc = FiscalDocument.objects.create(
        store=order.store,
        order=order,
        provider=provider_key,
        ref=f'nfce-{order.id}',
        serie=str(config.get('serie', '1')),
    )

    payload = build_nfce_payload(order, config)
    try:
        result = provider_cls(config).emit_nfce(ref=doc.ref, payload=payload)
    except FiscalNotConfigured:
        doc.delete()
        raise
    except Exception:  # provedor fora do ar etc. — registra e devolve
        logger.exception('Falha ao emitir NFC-e do pedido %s', order.id)
        doc.status = FiscalDocument.Status.ERROR
        doc.error_message = 'Falha de comunicação com o provedor fiscal. Tente novamente.'
        doc.save(update_fields=['status', 'error_message', 'updated_at'])
        return doc

    doc.status = result.status
    doc.chave_acesso = result.chave_acesso
    doc.numero = result.numero
    doc.serie = result.serie or doc.serie
    doc.qrcode_url = result.qrcode_url
    doc.danfe_url = result.danfe_url
    doc.xml_url = result.xml_url
    doc.error_message = result.error_message
    doc.response = result.raw
    doc.save()
    return doc
