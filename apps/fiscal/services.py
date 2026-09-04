"""Emissão de NFC-e a partir de um StoreOrder."""
import logging
import re
from decimal import Decimal

from .documents import classificar
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


def documento_do_consumidor(order) -> str:
    """CPF/CNPJ que vai na nota, em ordem de precedência.

    `cpf_nota` é o informado na hora da emissão (PDV/painel) e ganha do resto.
    Sem ele, vale o CPF que o próprio cliente digitou no campo opcional do
    checkout: quem preenche ali já está pedindo CPF na nota.
    """
    metadata = order.metadata or {}
    explicito = metadata.get('cpf_nota')
    if explicito:
        return str(explicito)
    return str((metadata.get('customer') or {}).get('cpf') or '')


def _cnpj_emitente(config: dict) -> str:
    cnpj = _digits(config.get('cnpj', ''))
    if not cnpj:
        raise FiscalNotConfigured('CNPJ ausente na config fiscal da loja')
    return cnpj


def _itens(order, config: dict, cfop: str) -> list[dict]:
    itens = []
    # Usa cache de prefetch quando disponível (chamado do viewset que faz
    # prefetch_related('items__product')). Para chamadas sem prefetch (Celery,
    # emissão direta), select_related evita 1 query por item.
    _cache = getattr(order, '_prefetched_objects_cache', {})
    _items_qs = order.items.all() if 'items' in _cache else order.items.select_related('product').all()
    for idx, item in enumerate(_items_qs, start=1):
        product = item.product
        ncm = ''
        if product is not None:
            ncm = str((product.attributes or {}).get('ncm') or '')
        itens.append({
            'numero_item': idx,
            'codigo_produto': (product.sku if product else '') or str(idx),
            'descricao': item.product_name,
            'quantidade_comercial': float(item.quantity),
            'quantidade_tributavel': float(item.quantity),
            'cfop': cfop,
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
    return itens


def _formas_pagamento(order) -> list[dict]:
    payment_map = {
        'cash': '01', 'credit_card': '03', 'debit_card': '04', 'pix': '17',
    }
    return [{
        'forma_pagamento': payment_map.get(order.payment_method or '', '99'),
        'valor_pagamento': float(order.total),
    }]


def _aplicar_desconto_e_frete(payload: dict, order) -> None:
    """Sem isto a soma dos itens não bate com `formas_pagamento` e a SEFAZ
    rejeita a nota (531/610). Vale para os dois modelos."""
    if order.discount and Decimal(order.discount) > 0:
        payload['valor_desconto'] = float(order.discount)
    if order.delivery_fee and Decimal(order.delivery_fee) > 0:
        payload['frete'] = float(order.delivery_fee)
        payload['modalidade_frete'] = 0  # por conta do emitente


def build_nfce_payload(order, config: dict) -> dict:
    """Monta o JSON de NFC-e (modelo 65) no formato Focus NFe (que espelha os
    campos SEFAZ, então o provider sefaz reaproveita o mesmo payload)."""
    payload = {
        'cnpj_emitente': _cnpj_emitente(config),
        'data_emissao': order.created_at.isoformat(),
        'indicador_inscricao_estadual_destinatario': '9',
        'modalidade_frete': 9,
        'local_destino': 1,
        'presenca_comprador': 1,
        'natureza_operacao': 'VENDA AO CONSUMIDOR',
        'itens': _itens(order, config, config.get('cfop_padrao') or DEFAULT_CFOP),
        'formas_pagamento': _formas_pagamento(order),
    }
    _aplicar_desconto_e_frete(payload, order)

    # NFC-e aceita consumidor não identificado; com cliente vinculado vai o nome
    if order.customer_name and order.customer_name != 'Cliente Balcão':
        payload['nome_destinatario'] = order.customer_name

    # CPF/CNPJ na nota é opcional — mas se for errado a SEFAZ recusa tudo.
    # Documento que não fecha o dígito é descartado em silêncio aqui: melhor
    # nota sem CPF do que venda sem nota. Quem digita recebe o aviso antes,
    # na API (ver emit_nfce) e no checkout.
    tipo, numero = classificar(documento_do_consumidor(order))
    if tipo:
        payload[f'{tipo}_destinatario'] = numero
    elif numero:
        logger.warning(
            'NFC-e pedido %s: documento do consumidor inválido, emitindo sem identificação',
            order.id,
        )

    return payload


# NF-e interestadual muda o CFOP: 5102 dentro do estado, 6102 para fora.
CFOP_INTERESTADUAL = '6102'

# O que a SEFAZ exige do destinatário numa NF-e, e o nome que o operador
# reconhece — a mensagem de erro tem que dizer o que ir buscar.
CAMPOS_ENDERECO = (
    ('street', 'rua'),
    ('number', 'número'),
    ('neighborhood', 'bairro'),
    ('city', 'cidade'),
    ('state', 'estado'),
    ('zip_code', 'CEP'),
)


def build_nfe_payload(order, config: dict) -> dict:
    """Monta o JSON de NF-e (modelo 55) — venda a empresa.

    Diferente da NFC-e, aqui não existe "consumidor não identificado": sem
    documento e endereço completos a nota não existe. Falhar aqui, com a lista
    do que falta, é melhor do que traduzir código de rejeição da SEFAZ depois.
    """
    cnpj = _cnpj_emitente(config)

    tipo, numero = classificar(documento_do_consumidor(order))
    if not tipo:
        raise FiscalNotConfigured(
            'NF-e exige o CPF ou CNPJ do destinatário — informe o documento antes de emitir.'
        )

    endereco = order.delivery_address or {}
    faltando = [rotulo for chave, rotulo in CAMPOS_ENDERECO if not str(endereco.get(chave) or '').strip()]
    if faltando:
        raise FiscalNotConfigured(
            'NF-e exige o endereço completo do destinatário. '
            f'Faltando: {", ".join(faltando)}.'
        )

    uf_destino = str(endereco['state']).strip().upper()
    uf_emitente = str(config.get('uf') or '').strip().upper()
    interestadual = bool(uf_emitente) and uf_destino != uf_emitente
    cfop = CFOP_INTERESTADUAL if interestadual else (config.get('cfop_padrao') or DEFAULT_CFOP)

    inscricao = _digits(str((order.metadata or {}).get('ie_nota') or ''))

    payload = {
        'cnpj_emitente': cnpj,
        'data_emissao': order.created_at.isoformat(),
        'natureza_operacao': 'VENDA DE MERCADORIA',
        'tipo_documento': 1,          # saída
        'finalidade_emissao': 1,      # normal
        'consumidor_final': 1,
        'presenca_comprador': 9,      # operação não presencial
        'modalidade_frete': 9,
        'local_destino': 2 if interestadual else 1,
        'itens': _itens(order, config, cfop),
        'formas_pagamento': _formas_pagamento(order),
        f'{tipo}_destinatario': numero,
        'nome_destinatario': order.customer_name,
        'logradouro_destinatario': str(endereco['street']).strip(),
        'numero_destinatario': str(endereco['number']).strip(),
        'bairro_destinatario': str(endereco['neighborhood']).strip(),
        'municipio_destinatario': str(endereco['city']).strip(),
        'uf_destinatario': uf_destino,
        'cep_destinatario': _digits(str(endereco['zip_code'])),
        # 1 = contribuinte com IE; 9 = não contribuinte. Mandar 1 sem IE é
        # rejeição certa, então o indicador segue o dado que existe.
        'indicador_inscricao_estadual_destinatario': '1' if inscricao else '9',
    }
    if inscricao:
        payload['inscricao_estadual_destinatario'] = inscricao
    if str(endereco.get('complement') or '').strip():
        payload['complemento_destinatario'] = str(endereco['complement']).strip()
    if order.customer_phone:
        payload['telefone_destinatario'] = _digits(order.customer_phone)

    _aplicar_desconto_e_frete(payload, order)
    return payload


def construir_payload(order, config: dict, modelo: str) -> dict:
    """Despacho por modelo. Resolve o construtor pelo nome no momento da
    chamada (e não num dicionário montado no import) — assim o payload
    continua substituível em teste."""
    if modelo == FiscalDocument.Modelo.NFE:
        return build_nfe_payload(order, config)
    return build_nfce_payload(order, config)


def _provider_for(store):
    config = get_fiscal_config(store)
    provider_key = config.get('provider') or FiscalDocument.Provider.FOCUS
    provider_cls = PROVIDERS.get(provider_key)
    if provider_cls is None:
        raise FiscalNotConfigured(f'Provider fiscal desconhecido: {provider_key}')
    return provider_cls(config), provider_key


def _aplicar_resultado(doc: FiscalDocument, result) -> FiscalDocument:
    doc.status = result.status
    doc.chave_acesso = result.chave_acesso or doc.chave_acesso
    doc.numero = result.numero or doc.numero
    doc.serie = result.serie or doc.serie
    doc.qrcode_url = result.qrcode_url or doc.qrcode_url
    doc.danfe_url = result.danfe_url or doc.danfe_url
    doc.xml_url = result.xml_url or doc.xml_url
    doc.error_message = result.error_message
    doc.response = result.raw
    doc.save()
    return doc


def refresh_fiscal_document(doc: FiscalDocument) -> FiscalDocument:
    """Sincroniza com o provedor uma nota que ficou em processamento.

    Nota já autorizada ou cancelada é estado final — não gasta chamada.
    """
    if doc.status != FiscalDocument.Status.PENDING:
        return doc

    provider, _ = _provider_for(doc.store)
    consult = getattr(provider, 'consult', None)
    if consult is None:
        return doc
    try:
        result = consult(ref=doc.ref, modelo=doc.modelo)
    except Exception:
        logger.exception('Falha ao consultar documento fiscal %s', doc.ref)
        return doc
    return _aplicar_resultado(doc, result)


# A SEFAZ só aceita cancelamento em até 30 minutos da autorização.
JANELA_CANCELAMENTO_MIN = 30
JUSTIFICATIVA_MIN = 15


def cancel_nfce(doc: FiscalDocument, justificativa: str) -> FiscalDocument:
    """Cancela a nota. Erros de regra viram ValueError (viram 400 na API) —
    o operador precisa saber o que fazer, não ver 'erro interno'."""
    from django.utils import timezone

    if doc.status != FiscalDocument.Status.AUTHORIZED:
        raise ValueError('Só é possível cancelar uma nota autorizada.')

    justificativa = (justificativa or '').strip()
    if len(justificativa) < JUSTIFICATIVA_MIN:
        raise ValueError(
            f'A justificativa do cancelamento precisa de pelo menos {JUSTIFICATIVA_MIN} caracteres.'
        )

    idade = (timezone.now() - doc.created_at).total_seconds() / 60
    if idade > JANELA_CANCELAMENTO_MIN:
        raise ValueError(
            f'Prazo de cancelamento esgotado (limite de {JANELA_CANCELAMENTO_MIN} minutos da '
            'autorização). Para desfazer a venda, emita uma nota de devolução.'
        )

    provider, _ = _provider_for(doc.store)
    cancelar = provider.cancel_nfe if doc.modelo == FiscalDocument.Modelo.NFE else provider.cancel_nfce
    result = cancelar(ref=doc.ref, justificativa=justificativa)
    return _aplicar_resultado(doc, result)


# Prefixo da ref idempotente por modelo: a mesma venda pode ter NFC-e e NF-e,
# e são documentos diferentes — a ref não pode colidir.
REF_POR_MODELO = {
    FiscalDocument.Modelo.NFCE: 'nfce',
    FiscalDocument.Modelo.NFE: 'nfe',
}


def emit_nfce_for_order(order, modelo: str = FiscalDocument.Modelo.NFCE) -> FiscalDocument:
    """Emite (ou devolve a já emitida) a nota do pedido no modelo pedido.

    A idempotência é POR MODELO: NFC-e e NF-e do mesmo pedido são documentos
    distintos, e devolver uma no lugar da outra seria entregar o cupom errado.
    """
    if modelo not in REF_POR_MODELO:
        raise FiscalNotConfigured(f'Modelo de nota desconhecido: {modelo}')

    existing = FiscalDocument.objects.filter(
        order=order,
        modelo=modelo,
        status__in=[FiscalDocument.Status.AUTHORIZED, FiscalDocument.Status.PENDING],
    ).first()
    if existing:
        return existing

    config = get_fiscal_config(order.store)
    provider, provider_key = _provider_for(order.store)
    if not config:
        raise FiscalNotConfigured(
            'Loja sem config fiscal. '
            'Configure provider, CNPJ e token nas configurações fiscais da loja antes de emitir.'
        )
    if not config.get('habilitado'):
        raise FiscalNotConfigured(
            'Emissão de nota fiscal desligada nesta loja. '
            'Ative em Configurações da loja → Nota fiscal.'
        )

    # Monta ANTES de gravar: dado faltando (endereço do destinatário na NF-e,
    # CNPJ do emitente) levanta aqui, e nota que nunca saiu não pode deixar
    # linha no banco.
    payload = construir_payload(order, config, modelo)

    doc = FiscalDocument.objects.create(
        store=order.store,
        order=order,
        provider=provider_key,
        modelo=modelo,
        ref=f'{REF_POR_MODELO[modelo]}-{order.id}',
        serie=str(config.get('serie', '1')),
    )

    emitir = provider.emit_nfe if modelo == FiscalDocument.Modelo.NFE else provider.emit_nfce
    try:
        result = emitir(ref=doc.ref, payload=payload)
    except FiscalNotConfigured:
        doc.delete()
        raise
    except Exception:  # provedor fora do ar etc. — registra e devolve
        logger.exception('Falha ao emitir nota do pedido %s', order.id)
        doc.status = FiscalDocument.Status.ERROR
        doc.error_message = 'Falha de comunicação com o provedor fiscal. Tente novamente.'
        doc.save(update_fields=['status', 'error_message', 'updated_at'])
        return doc

    return _aplicar_resultado(doc, result)
