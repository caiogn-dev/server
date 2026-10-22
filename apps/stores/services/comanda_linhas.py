"""Comanda montada no servidor: payload do pedido + layout da loja → linhas.

22/10, dono: o desenho da comanda morava no print agent (Node) e toda mudança
exigia atualizar o PC de cada loja à mão. Agora o desenho mora aqui. As linhas
são a fonte única do papel (`comanda_escpos.bytes_da_comanda`) e da prévia do
painel — o que a loja vê na tela é o que sai na impressora.

Contrato: docs/comanda-no-servidor.md (§1 layout, §2 linhas).
"""
from __future__ import annotations

import copy
import logging
import re
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

BLOCOS = (
    'cabecalho', 'numero', 'pagamento', 'cliente', 'endereco', 'avisos',
    'itens', 'totais', 'observacao', 'mensagem', 'codigo_barras',
)
# "mensagem" nasce desligado: texto livre vazio não deve gastar papel.
_DESLIGADOS_DE_FABRICA = {'mensagem'}
SEPARADORES = ('tracejado', 'linha', 'espaco')
COLUNAS = (48, 32)
VIAS = (1, 2)
MENSAGEM_MAX = 200

_PADRAO = {
    'versao': 1,
    'blocos': [{'id': b, 'ligado': b not in _DESLIGADOS_DE_FABRICA} for b in BLOCOS],
    'separador': 'tracejado',
    'colunas': 48,
    'vias': 1,
    'itens_grandes': False,
    'precos_nos_itens': True,
    'mensagem': '',
}


class LayoutInvalido(ValueError):
    pass


def layout_padrao() -> dict:
    return copy.deepcopy(_PADRAO)


def _inteiro_em(dados: dict, chave: str, permitidos: tuple) -> int:
    valor = dados[chave]
    if isinstance(valor, bool):
        raise LayoutInvalido(f'{chave} inválido')
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        raise LayoutInvalido(f'{chave} inválido') from None
    if valor not in permitidos:
        raise LayoutInvalido(f'{chave} precisa ser um de {permitidos}')
    return valor


def validar_layout(layout) -> dict:
    """Layout normalizado. Bloco desconhecido some; bloco faltando entra no
    fim desligado — layout salvo antes de um bloco novo continua válido."""
    if not isinstance(layout, dict):
        raise LayoutInvalido('layout precisa ser um objeto')
    saida = layout_padrao()

    if 'blocos' in layout:
        blocos = layout['blocos']
        if not isinstance(blocos, list):
            raise LayoutInvalido('blocos precisa ser uma lista')
        vistos: list[dict] = []
        for bloco in blocos:
            if not isinstance(bloco, dict) or bloco.get('id') not in BLOCOS:
                continue
            if any(v['id'] == bloco['id'] for v in vistos):
                continue
            vistos.append({'id': bloco['id'], 'ligado': bool(bloco.get('ligado', True))})
        ids = {v['id'] for v in vistos}
        vistos.extend({'id': b, 'ligado': False} for b in BLOCOS if b not in ids)
        saida['blocos'] = vistos

    if 'separador' in layout:
        if layout['separador'] not in SEPARADORES:
            raise LayoutInvalido(f'separador precisa ser um de {SEPARADORES}')
        saida['separador'] = layout['separador']
    if 'colunas' in layout:
        saida['colunas'] = _inteiro_em(layout, 'colunas', COLUNAS)
    if 'vias' in layout:
        saida['vias'] = _inteiro_em(layout, 'vias', VIAS)
    for chave in ('itens_grandes', 'precos_nos_itens'):
        if chave in layout:
            saida[chave] = bool(layout[chave])
    if 'mensagem' in layout:
        mensagem = str(layout['mensagem'] or '').strip()
        if len(mensagem) > MENSAGEM_MAX:
            raise LayoutInvalido(f'mensagem passa de {MENSAGEM_MAX} caracteres')
        saida['mensagem'] = mensagem
    return saida


def layout_da_cozinha(layout: dict) -> dict:
    """Cozinha não vê dinheiro: sem preço nos itens, sem totais, sem pagamento,
    uma via. Espelho de `layoutDaCozinha` no painel (src/utils/comandaHtml.ts)."""
    return {
        **layout,
        'vias': 1,
        'precos_nos_itens': False,
        'blocos': [
            {**b, 'ligado': False} if b['id'] in ('totais', 'pagamento') else b
            for b in layout['blocos']
        ],
    }


def layout_da_loja(store) -> dict:
    """O salvo em `metadata['comanda']`, ou o padrão. Layout corrompido não
    pode deixar a cozinha sem comanda: cai no padrão e registra."""
    salvo = (getattr(store, 'metadata', None) or {}).get('comanda')
    if not salvo:
        return layout_padrao()
    try:
        return validar_layout(salvo)
    except LayoutInvalido as exc:
        logger.warning('Layout de comanda inválido na loja %s: %s', getattr(store, 'pk', '?'), exc)
        return layout_padrao()


# ── Papel: quebra, colunas, estilos ───────────────────────────────────────────

def _dinheiro(valor) -> str:
    try:
        numero = Decimal(str(valor if valor not in (None, '') else 0))
    except (InvalidOperation, ValueError):
        numero = Decimal('0')
    return f'R$ {numero:.2f}'.replace('.', ',')


def _dec(valor) -> Decimal:
    try:
        return Decimal(str(valor if valor not in (None, '') else 0))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _quebra(texto: str, largura: int) -> list[str]:
    """Quebra por palavra; palavra maior que a linha é cortada à força."""
    linhas: list[str] = []
    atual = ''
    for palavra in str(texto or '').split():
        while len(palavra) > largura:
            if atual:
                linhas.append(atual)
                atual = ''
            linhas.append(palavra[:largura])
            palavra = palavra[largura:]
        if not palavra:
            continue
        if atual and len(atual) + 1 + len(palavra) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f'{atual} {palavra}' if atual else palavra
    if atual:
        linhas.append(atual)
    return linhas


def _linha(texto='', *, alinhar='esquerda', negrito=False, altura_dupla=False,
           largura_dupla=False, invertido=False, tipo='texto') -> dict:
    return {
        'texto': texto, 'alinhar': alinhar, 'negrito': negrito,
        'altura_dupla': altura_dupla, 'largura_dupla': largura_dupla,
        'invertido': invertido, 'tipo': tipo,
    }


class _Papel:
    def __init__(self, colunas: int):
        self.colunas = colunas

    def largura(self, largura_dupla=False) -> int:
        # Largura dupla: cada caractere ocupa duas colunas.
        return self.colunas // 2 if largura_dupla else self.colunas

    def texto(self, texto, *, recuo=0, **estilo) -> list[dict]:
        largura = self.largura(estilo.get('largura_dupla', False))
        prefixo = ' ' * recuo
        return [_linha(prefixo + parte, **estilo) for parte in _quebra(texto, largura - recuo)]

    def faixa(self, texto, **estilo) -> list[dict]:
        """Faixa invertida de ponta a ponta: o invertido pinta os espaços,
        então o texto já vem preenchido até a borda."""
        largura = self.largura(estilo.get('largura_dupla', False))
        estilo = {'negrito': True, **estilo, 'invertido': True}
        return [_linha(parte.center(largura), **{**estilo, 'alinhar': 'centro'})
                for parte in _quebra(texto, largura)]

    def duas_colunas(self, esquerda, direita, **estilo) -> dict:
        largura = self.largura(estilo.get('largura_dupla', False))
        esquerda, direita = str(esquerda or ''), str(direita or '')
        cabe = largura - len(direita) - 1
        if len(esquerda) > cabe:
            esquerda = esquerda[:max(cabe - 1, 0)] + '.'
        espaco = max(1, largura - len(esquerda) - len(direita))
        return _linha(esquerda + ' ' * espaco + direita, **estilo)

    def separador(self, tipo: str) -> list[dict]:
        if tipo == 'espaco':
            return [_linha('', tipo='espaco')]
        if tipo == 'linha':
            return [_linha('─' * self.colunas, tipo='separador')]
        return [_linha(('- ' * (self.colunas // 2))[:self.colunas].rstrip(), tipo='separador')]


# ── Rótulos ───────────────────────────────────────────────────────────────────

_FORMAS = {
    'pix': 'PIX', 'credit_card': 'Cartão de crédito', 'debit_card': 'Cartão de débito',
    'cash': 'Dinheiro', 'card': 'Cartão', 'mercadopago': 'Mercado Pago',
    'card_on_delivery': 'Cartão na entrega', 'voucher': 'Vale', 'voucher_link': 'Vale (link)',
    'sem_cobranca': 'Sem cobrança',
}
_SITUACAO = {'failed': 'PAGAMENTO FALHOU', 'refunded': 'REEMBOLSADO'}
_CANAIS = {
    'whatsapp': 'WhatsApp', 'instagram': 'Instagram', 'pdv': 'PDV', 'balcao': 'balcão',
    'web': 'site', 'site': 'site', 'storefront': 'site', 'payment_link': 'link de pagamento',
}
_AVISO_MAQUININHA = 'LEVAR MAQUININHA'


def _hora_local(iso: str, formato: str) -> str:
    momento = parse_datetime(str(iso or ''))
    if momento is None:
        return ''
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento)
    return timezone.localtime(momento).strftime(formato)


def _numero_curto(numero: str) -> str:
    """Últimos 4 dígitos: é o que se grita na bancada ("cinco cinco nove zero")."""
    digitos = re.sub(r'\D', '', numero or '')
    return '#' + (digitos[-4:] if digitos else (numero or '')[-4:])


def _modo(order: dict) -> str:
    # Três modos, não dois: 'digital' (cobrança por link) não é entrega.
    modo = order.get('delivery_method') or 'delivery'
    return {'delivery': 'ENTREGA', 'pickup': 'RETIRADA'}.get(modo, 'PAGTO POR LINK')


def _agendamento(texto: str) -> str:
    partes = str(texto or '').split()
    if partes and re.fullmatch(r'\d{4}-\d{2}-\d{2}', partes[0]):
        ano, mes, dia = partes[0].split('-')
        partes[0] = f'{dia}/{mes}'
    return ' '.join(partes)


def _descontos(totals: dict, cupom: str) -> list[tuple[str, str]]:
    """Uma linha por origem do desconto, com o código do cupom garantido —
    mesma regra do `descontosComCupom` do agent."""
    lista = totals.get('descontos') if isinstance(totals.get('descontos'), list) else []
    if lista:
        pares = [
            (f"Fidelidade: {d['item']}" if d.get('tipo') == 'fidelidade' and d.get('item')
             else str(d.get('rotulo') or 'Desconto'), f"- {_dinheiro(d.get('valor'))}")
            for d in lista if isinstance(d, dict)
        ]
    elif _dec(totals.get('discount')) > 0:
        pares = [('Desconto', f"- {_dinheiro(totals.get('discount'))}")]
    else:
        pares = []
    cupom = str(cupom or '').strip()
    if not cupom or any(cupom in esquerda for esquerda, _ in pares):
        return pares
    if len(pares) == 1 and pares[0][0] == 'Desconto':
        return [(f'Cupom {cupom}', pares[0][1])]
    return [*pares, (f'Cupom {cupom}', '')]


def _e_remocao(texto: str) -> bool:
    return bool(re.match(r'^\s*(sem|remover|tirar)\b', texto, re.IGNORECASE))


# ── Blocos ────────────────────────────────────────────────────────────────────

def _bloco_cabecalho(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    loja = payload.get('store') or {}
    linhas = []
    logo = loja.get('logo_escpos')
    if isinstance(logo, dict) and logo.get('data') and logo.get('width') and logo.get('height'):
        # Selo da loja: com quatro lojas na mesma impressora, separa as comandas.
        # A prévia pode ignorar; o ESC/POS despeja o bitmap (GS v 0).
        linhas.append({**_linha('', alinhar='centro', tipo='logo'), 'logo': logo})
    linhas += p.texto(str(loja.get('name') or 'LOJA').upper(), alinhar='centro', negrito=True)
    return linhas


def _bloco_numero(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    order = payload.get('order') or {}
    numero = str(order.get('order_number') or '')
    curto, modo = _numero_curto(numero), _modo(order)
    grande = {'negrito': True, 'altura_dupla': True, 'largura_dupla': True}
    if len(curto) + 1 + len(modo) <= p.largura(True):
        linhas = [p.duas_colunas(curto, modo, **grande)]
    else:
        linhas = [*p.texto(curto, alinhar='centro', **grande), *p.texto(modo, alinhar='centro', **grande)]
    if numero:
        linhas += p.texto(f'Pedido {numero}', alinhar='centro')
    canal = _CANAIS.get(order.get('source') or '', '')
    contexto = '  '.join(filter(None, [
        _hora_local(order.get('created_at'), '%d/%m/%Y %H:%M'),
        f'via {canal}' if canal else '',
    ]))
    if contexto:
        linhas += p.texto(contexto, alinhar='centro')
    return linhas


def _bloco_pagamento(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    order = payload.get('order') or {}
    totals = payload.get('totals') or {}
    metodo = order.get('payment_method') or ''
    forma = _FORMAS.get(metodo, metodo.upper())
    total = _dec(totals.get('total'))
    linhas: list[dict] = []

    if order.get('payment_status') == 'paid':
        linhas += p.texto(' · '.join(filter(None, ['PAGO', forma])), alinhar='centro', negrito=True, altura_dupla=True)
    elif total <= 0 or metodo == 'sem_cobranca':
        linhas += p.texto('SEM COBRANCA', alinhar='centro', negrito=True, altura_dupla=True)
    else:
        # O grito vem antes de tudo: quem entrega precisa saber que vai cobrar.
        largura = p.largura()
        cobrar = p.duas_colunas(' COBRAR', f'{_dinheiro(total)} ', negrito=True, altura_dupla=True, invertido=True)
        cobrar['texto'] = cobrar['texto'].ljust(largura)
        linhas.append(cobrar)
        if metodo == 'card_on_delivery':
            forma = f'{forma} - levar maquininha'
        if forma:
            linhas += p.texto(forma, alinhar='centro', negrito=True)
        situacao = _SITUACAO.get(order.get('payment_status') or '')
        if situacao:
            linhas += p.texto(situacao, alinhar='centro', negrito=True)

    # Troco: None = ninguém perguntou; 0 = cliente disse que não precisa.
    troco_para = order.get('change_for')
    if troco_para not in (None, ''):
        if _dec(troco_para) == 0:
            linhas += p.texto('SEM TROCO', alinhar='centro', negrito=True)
        else:
            levar = order.get('change_due')
            levar = _dec(levar) if levar not in (None, '') else max(Decimal('0'), _dec(troco_para) - total)
            linhas += p.texto(f'Troco para {_dinheiro(troco_para)}', alinhar='centro', negrito=True)
            linhas += p.texto(f'LEVAR {_dinheiro(levar)}', alinhar='centro', negrito=True, altura_dupla=True)
    return linhas


def _bloco_cliente(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    cliente = payload.get('customer') or {}
    nome = str(cliente.get('name') or '').strip().upper()
    try:
        pedidos = int(cliente.get('pedidos'))
    except (TypeError, ValueError):
        pedidos = 0
    estilo = {'negrito': True, 'altura_dupla': True}
    linhas: list[dict] = []
    etiqueta = f'{pedidos}º pedido' if pedidos >= 2 else ''
    if nome and etiqueta and len(nome) + 1 + len(etiqueta) <= p.largura():
        linhas.append(p.duas_colunas(nome, etiqueta, **estilo))
    else:
        if nome:
            linhas += p.texto(nome, **estilo)
        if etiqueta:
            linhas += p.texto(etiqueta, alinhar='direita', negrito=True)
    if pedidos == 1:
        # Cliente novo: a loja quer caprichar, então salta aos olhos.
        linhas += p.faixa('1º PEDIDO · CLIENTE NOVO')
    if cliente.get('phone'):
        linhas += p.texto(str(cliente['phone']))
    return linhas


def _bloco_endereco(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    order = payload.get('order') or {}
    if (order.get('delivery_method') or 'delivery') != 'delivery':
        return []
    linhas: list[dict] = []
    for i, parte in enumerate(payload.get('address_lines') or []):
        # A 2ª linha é complemento - bairro/quadra: é o que o entregador procura.
        if i == 1:
            linhas += p.texto(str(parte), negrito=True, altura_dupla=True)
        else:
            linhas += p.texto(str(parte))
    if order.get('delivery_notes'):
        linhas += p.texto(f"Ref: {order['delivery_notes']}")
    return linhas


def _bloco_avisos(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    order = payload.get('order') or {}
    linhas: list[dict] = []
    agendado = _agendamento(order.get('scheduled_for') or '')
    if agendado:
        linhas += p.faixa(f'AGENDADO {agendado}')
    aviso = payload.get('address_warning') or []
    if aviso:
        linhas += p.faixa('!! CONFERIR ENDERECO !!')
        for parte in aviso[1:]:
            linhas += p.texto(str(parte), alinhar='centro', negrito=True)
    notas = str(order.get('internal_notes') or '').strip()
    pagamento_ligado = any(b['id'] == 'pagamento' and b['ligado'] for b in layout['blocos'])
    if pagamento_ligado and notas.startswith(_AVISO_MAQUININHA):
        # O bloco de pagamento já diz "levar maquininha"; sem ele, o aviso fica.
        notas = notas.split(' | ', 1)[1] if ' | ' in notas else ''
    if notas:
        linhas += p.faixa('!! ATENCAO DA LOJA !!')
        linhas += p.texto(notas, alinhar='centro', negrito=True)
    return linhas


def _bloco_itens(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    itens = payload.get('items') or []
    if not itens:
        return []
    preparo = payload.get('template') == 'prep_ticket'
    unidades = sum(int(i.get('qty') or 1) for i in itens)
    linhas = p.texto(f"{unidades} {'ITEM' if unidades == 1 else 'ITENS'}", alinhar='centro', negrito=True)
    largura = p.largura()
    for n, item in enumerate(itens):
        if n:
            linhas.append(_linha('', tipo='espaco'))
        cabeca = f"{item.get('qty') or 1} x "
        preco = _dinheiro(item.get('subtotal')) if layout['precos_nos_itens'] else ''
        estilo = {'negrito': True, 'altura_dupla': layout['itens_grandes']}
        partes = _quebra(str(item.get('name') or ''), largura - len(cabeca) - (len(preco) + 1 if preco else 0))
        primeira = cabeca + (partes[0] if partes else '')
        linhas.append(p.duas_colunas(primeira, preco, **estilo) if preco else _linha(primeira, **estilo))
        for resto in partes[1:]:
            linhas.append(_linha(' ' * len(cabeca) + resto, **estilo))

        if preparo:
            for prep in item.get('prep') or []:
                linhas += p.texto(str(prep), recuo=4, negrito=str(prep).startswith('>>'))
        for detalhe in item.get('details') or []:
            detalhe = '[COMBO]' if detalhe == 'COMBO' else str(detalhe)
            if _e_remocao(detalhe):
                # Remoção é o que mais volta para a cozinha: invertida.
                linhas += [_linha(f' {t} ', invertido=True, negrito=True) for t in _quebra(detalhe, largura - 2)]
            else:
                linhas += p.texto(detalhe, recuo=4)
        if item.get('notes'):
            texto = f"OBS: {str(item['notes']).upper()}"
            linhas += [_linha(f' {t} ', invertido=True, negrito=True) for t in _quebra(texto, largura - 2)]
    return linhas


def _bloco_totais(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    totals = payload.get('totals') or {}
    order = payload.get('order') or {}
    linhas = [p.duas_colunas('Subtotal', _dinheiro(totals.get('subtotal')))]
    if _dec(totals.get('delivery_fee')) > 0:
        linhas.append(p.duas_colunas('Entrega', _dinheiro(totals.get('delivery_fee'))))
    if _dec(totals.get('voucher_fee')) > 0:
        # Sem a linha, itens + entrega não batem com o TOTAL e o caixa acha que errou.
        linhas.append(p.duas_colunas('Acrescimo vale', _dinheiro(totals.get('voucher_fee'))))
    for esquerda, direita in _descontos(totals, order.get('coupon_code')):
        linhas.append(p.duas_colunas(esquerda, direita))
    linhas.append(p.duas_colunas('TOTAL', _dinheiro(totals.get('total')), negrito=True, altura_dupla=True))
    return linhas


def _bloco_observacao(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    notas = str((payload.get('order') or {}).get('customer_notes') or '').strip()
    if not notas:
        return []
    return [*p.texto('OBSERVACAO DO CLIENTE', alinhar='centro', negrito=True),
            *p.texto(notas, alinhar='centro', negrito=True)]


def _bloco_mensagem(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    return p.texto(layout.get('mensagem') or '', alinhar='centro')


def _bloco_codigo_barras(p: _Papel, payload: dict, layout: dict) -> list[dict]:
    numero = str((payload.get('order') or {}).get('order_number') or '')
    # CODE128 B só leva ASCII imprimível; 22 é o que cabe em 80 mm.
    codigo = re.sub(r'[^\x20-\x7e]', '', numero)[:22]
    if not codigo:
        return []
    return [_linha(codigo, alinhar='centro', tipo='codigo_barras'), *p.texto(numero, alinhar='centro')]


_BLOCOS = {
    'cabecalho': _bloco_cabecalho, 'numero': _bloco_numero, 'pagamento': _bloco_pagamento,
    'cliente': _bloco_cliente, 'endereco': _bloco_endereco, 'avisos': _bloco_avisos,
    'itens': _bloco_itens, 'totais': _bloco_totais, 'observacao': _bloco_observacao,
    'mensagem': _bloco_mensagem, 'codigo_barras': _bloco_codigo_barras,
}


def linhas_da_comanda(payload: dict, layout: dict) -> list[dict]:
    """Payload de `build_order_print_payload` + layout validado → linhas."""
    p = _Papel(layout['colunas'])
    blocos = [
        _BLOCOS[b['id']](p, payload, layout)
        for b in layout['blocos'] if b['ligado'] and b['id'] in _BLOCOS
    ]
    linhas: list[dict] = []
    for bloco in filter(None, blocos):
        if linhas:
            linhas += p.separador(layout['separador'])
        linhas += bloco

    loja = (payload.get('store') or {}).get('name') or ''
    hora = _hora_local(payload.get('generated_at'), '%H:%M:%S') or timezone.localtime().strftime('%H:%M:%S')
    linhas.append(_linha('', tipo='espaco'))
    linhas += p.texto(' · '.join(filter(None, [f'Impresso {hora}', loja])), alinhar='centro')
    linhas.append(_linha('', tipo='corte'))
    return linhas


def pedido_de_exemplo(store=None) -> dict:
    """Pedido fictício para a prévia de loja sem pedido nenhum. Mostra o
    máximo de blocos de uma vez: cobrança, cupom, remoção, observação."""
    loja = {
        'name': getattr(store, 'name', None) or 'Sua Loja',
        'phone': getattr(store, 'phone', '') or '',
        'logo_escpos': None,
    }
    agora = timezone.now().isoformat()
    return {
        'template': 'kitchen_ticket',
        'generated_at': agora,
        'store': loja,
        'order': {
            'order_number': 'EX-2610221234', 'created_at': agora, 'scheduled_for': '',
            'delivery_method': 'delivery', 'payment_method': 'card_on_delivery',
            'payment_status': 'pending', 'source': 'whatsapp', 'coupon_code': 'BEMVINDO10',
            'customer_notes': 'Tocar o interfone, por favor.', 'internal_notes': '',
            'delivery_notes': '', 'change_for': None, 'change_due': None,
        },
        'customer': {'name': 'Ana Paula Souza', 'phone': '(63) 98888-1234', 'pedidos': 3},
        'address_lines': ['Rua das Palmeiras, nº 145', 'Apto 302 - Plano Diretor Sul', 'Palmas / TO'],
        'address_warning': [],
        'items': [
            {'type': 'item', 'qty': 1, 'name': 'Salada Caesar Grande', 'unit_price': '42.90',
             'subtotal': '42.90', 'details': ['Proteína: Frango grelhado', 'Sem cebola'],
             'ingredients': [], 'prep': [], 'notes': ''},
            {'type': 'item', 'qty': 2, 'name': 'Suco de Laranja 500ml', 'unit_price': '12.00',
             'subtotal': '24.00', 'details': [], 'ingredients': [], 'prep': [], 'notes': ''},
        ],
        'totals': {
            'subtotal': '66.90', 'discount': '6.69', 'delivery_fee': '8.00', 'voucher_fee': '0.00',
            'total': '68.21',
            'descontos': [{'tipo': 'cupom', 'rotulo': 'Cupom BEMVINDO10', 'valor': '6.69', 'codigo': 'BEMVINDO10'}],
        },
    }
