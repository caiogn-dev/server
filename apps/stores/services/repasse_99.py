"""Extrato de repasse da 99Food → pedido a pedido, e o agregado do canal.

O aviso `orderNew` da 99 não diz quanto a loja recebe (até 06/11/2026). O
número certo é o do extrato de repasse do 99store: por pedido, a venda (preço
de cardápio) e o recebido. Este módulo lê esse extrato (CSV), acha cada pedido
e grava em `metadata['99food']['financeiro']`:

    recebido        o valor do extrato
    comissao_taxas  venda − recebido (custo do canal)

Gabarito: extrato da Cê de 06/11 — 6 pedidos, venda 258,76, recebido 158,42.

Uso: `manage.py importar_extrato_99 arquivo.csv --loja <slug> [--data AAAA-MM-DD] [--dry-run]`.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.stores.services import pedidos_da_99 as p99

ZERO = Decimal('0.00')


@dataclass
class LinhaExtrato:
    numero_da_linha: int
    pedido: str           # "#5" vira "5"; order_id longo fica inteiro
    data: date | None
    venda: Decimal | None
    recebido: Decimal


# ── Leitura ───────────────────────────────────────────────────────────────

def _sem_acento(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texto or '') if unicodedata.category(c) != 'Mn').lower()


def _coluna(cabecalho: str):
    nome = _sem_acento(cabecalho)
    if any(t in nome for t in ('receb', 'repasse', 'liquido')):
        return 'recebido'
    if any(t in nome for t in ('venda', 'bruto')):
        return 'venda'
    if any(t in nome for t in ('data', 'hora')):
        return 'data'
    if any(t in nome for t in ('pedido', 'numero', 'order', 'id')):
        return 'pedido'
    return None


def _dinheiro(texto) -> Decimal | None:
    bruto = re.sub(r'[^\d,.\-]', '', str(texto or ''))
    if not bruto:
        return None
    if ',' in bruto:
        bruto = bruto.replace('.', '').replace(',', '.')
    try:
        return Decimal(bruto).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def _data(texto) -> date | None:
    texto = str(texto or '').strip()
    for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _separador(primeira_linha: str) -> str:
    for sep in (';', '\t'):
        if sep in primeira_linha:
            return sep
    return ','


def ler_extrato(texto: str, data_padrao: date | None = None) -> list[LinhaExtrato]:
    """CSV do extrato (`;`, `,` ou tab) → linhas. Cabeçalho decide as colunas:
    pedido (#N do dia ou order_id), data (opcional), venda (opcional), recebido."""
    texto = (texto or '').lstrip('﻿')
    primeira = texto.splitlines()[0] if texto.strip() else ''
    leitor = csv.reader(io.StringIO(texto), delimiter=_separador(primeira))
    cabecalho = next(leitor, None) or []
    colunas = {}
    for i, nome in enumerate(cabecalho):
        tipo = _coluna(nome)
        if tipo and tipo not in colunas:
            colunas[tipo] = i
    if 'pedido' not in colunas or 'recebido' not in colunas:
        raise ValueError('O extrato precisa das colunas "pedido" e "recebido".')

    linhas = []
    for n, campos in enumerate(leitor, start=2):
        if not any(c.strip() for c in campos):
            continue

        def campo(tipo):
            i = colunas.get(tipo)
            return campos[i] if i is not None and i < len(campos) else ''

        pedido = re.sub(r'\D', '', campo('pedido'))
        recebido = _dinheiro(campo('recebido'))
        if not pedido or recebido is None:
            continue
        linhas.append(LinhaExtrato(
            numero_da_linha=n,
            pedido=pedido,
            data=_data(campo('data')) or data_padrao,
            venda=_dinheiro(campo('venda')),
            recebido=recebido,
        ))
    return linhas


# ── Texto copiado do 99store ──────────────────────────────────────────────
# O dono copia a lista de pedidos da tela do 99store e cola. Cada pedido vem
# num bloco: "#6" / "06 de nov. 11:18" / "R$44,99" (venda) / "R$29,05"
# (recebido) / "Concluído".

_MESES = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
          'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}
_NUMERO = re.compile(r'^#\s*(\d+)$')
_DIA = re.compile(r'^(\d{1,2})\s+de\s+([a-z]{3})')
_VALOR = re.compile(r'^-?\s*r\$\s*-?[\d.]+,\d{2}$')


def parece_colado(texto: str) -> bool:
    return any(_NUMERO.match(l.strip()) for l in (texto or '').splitlines())


def ler_texto_colado(texto: str, ano: int | None = None, hoje: date | None = None) -> list[LinhaExtrato]:
    """Blocos copiados do 99store → linhas. Sem ano no texto: o mais recente
    que não cai no futuro (dezembro lido em janeiro é do ano anterior)."""
    hoje = hoje or date.today()
    partes = []
    for bruta in (texto or '').splitlines():
        partes.extend(p.strip() for p in re.split(r'\t| / ', bruta) if p.strip())

    blocos, atual = [], None
    for n, parte in enumerate(partes, start=1):
        numero = _NUMERO.match(parte)
        if numero:
            atual = {'n': n, 'pedido': numero.group(1), 'data': None, 'valores': []}
            blocos.append(atual)
            continue
        if atual is None:
            continue
        minusculo = _sem_acento(parte)
        dia = _DIA.match(minusculo)
        if dia and atual['data'] is None and dia.group(2) in _MESES:
            mes, d = _MESES[dia.group(2)], int(dia.group(1))
            a = ano or (hoje.year if (mes, d) <= (hoje.month, hoje.day) else hoje.year - 1)
            try:
                atual['data'] = date(a, mes, d)
            except ValueError:
                pass
        elif _VALOR.match(minusculo):
            atual['valores'].append(_dinheiro(parte))

    linhas = []
    for b in blocos:
        if not b['valores']:
            continue
        venda, recebido = (b['valores'][0], b['valores'][1]) if len(b['valores']) >= 2 else (None, b['valores'][0])
        linhas.append(LinhaExtrato(numero_da_linha=b['n'], pedido=b['pedido'], data=b['data'],
                                   venda=venda, recebido=recebido))
    return linhas


def ler_planilha(conteudo: bytes, data_padrao: date | None = None) -> list[LinhaExtrato]:
    """Planilha .xlsx (1ª aba, 1ª linha = cabeçalho) → linhas, pelo mesmo leitor do CSV."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # zip/xml inválido: arquivo não é planilha
        raise ValueError('Não consegui abrir a planilha.') from exc
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=';')
    for linha in wb.worksheets[0].iter_rows(values_only=True):
        celulas = []
        for valor in linha:
            if valor is None:
                celulas.append('')
            elif isinstance(valor, float):
                celulas.append(f'{valor:.2f}')
            else:
                celulas.append(str(valor))
        escritor.writerow(celulas)
    return ler_extrato(saida.getvalue(), data_padrao=data_padrao)


def ler_qualquer(texto: str, data_padrao: date | None = None, hoje: date | None = None) -> list[LinhaExtrato]:
    """CSV com cabeçalho ou texto colado do 99store, o que vier."""
    if parece_colado(texto):
        return ler_texto_colado(texto, ano=data_padrao.year if data_padrao else None, hoje=hoje)
    return ler_extrato(texto, data_padrao=data_padrao)


# ── Conciliação ───────────────────────────────────────────────────────────

def _achar_pedido(store, linha: LinhaExtrato):
    from apps.stores.models import StoreOrder

    if len(linha.pedido) > 6:  # order_id de 64 bits
        return p99.pedido_da_99(store, linha.pedido)
    if linha.data is None:
        return None
    # "#5" é o número do DIA na 99: precisa da data para não pegar o #5 de ontem.
    candidatos = list(StoreOrder.objects.filter(
        store=store, source=p99.PROVEDOR, created_at__date=linha.data,
        **{f'metadata__{p99.PROVEDOR}__numero': int(linha.pedido)},
    )[:2])
    return candidatos[0] if len(candidatos) == 1 else None


def _financeiro(pedido) -> dict:
    fin = p99.dados_99(pedido).get('financeiro')
    return dict(fin) if isinstance(fin, dict) else p99.financeiro_do_preco({})


def conciliar(store, linhas: list[LinhaExtrato], gravar: bool = True, fonte: str = 'extrato') -> dict:
    """Grava recebido e comissão de cada pedido do extrato. Reimportar não muda nada.

    `fonte`: 'extrato' (CSV/planilha/texto do 99store) ou 'api' (API financeira)."""
    conciliados, sem_pedido, divergentes = [], [], []
    for linha in linhas:
        pedido = _achar_pedido(store, linha)
        if pedido is None:
            sem_pedido.append(linha)
            continue
        fin = _financeiro(pedido)
        venda = Decimal(fin['venda_cardapio']) if fin.get('venda_cardapio') else linha.venda
        if linha.venda is not None and venda is not None and linha.venda != venda:
            divergentes.append((linha, pedido, venda))
        novo = dict(fin)
        if venda is not None and not fin.get('venda_cardapio'):
            novo['venda_cardapio'] = str(venda)
        novo['recebido'] = str(linha.recebido)
        novo['comissao_taxas'] = str(venda - linha.recebido) if venda is not None else None
        novo['fonte_recebido'] = fonte
        if linha.venda is not None:
            novo['venda_extrato'] = str(linha.venda)
        conciliados.append((linha, pedido))
        if gravar and novo != fin:
            p99._registrar(pedido, financeiro=novo)
    return {'conciliados': conciliados, 'sem_pedido': sem_pedido, 'divergentes': divergentes}


# ── Agregado ──────────────────────────────────────────────────────────────

def resumo_de_pedidos(queryset) -> dict:
    """Venda, desconto da 99, desconto da loja, comissão e recebido de pedidos da 99.

    `queryset` já vem com a regra de receita aplicada (pago, não cancelado,
    não teste). Comissão e recebido somam só os pedidos já conciliados —
    `conciliados` diz quantos são, para a tela não comparar alhos com bugalhos.
    """
    resumo = {
        'pedidos': 0, 'conciliados': 0, 'venda': ZERO, 'desconto_plataforma': ZERO,
        'desconto_loja': ZERO, 'comissao_taxas': ZERO, 'recebido': ZERO,
    }
    campos = ('subtotal', 'discount', 'platform_discount', 'metadata')
    for pedido in queryset.filter(source=p99.PROVEDOR).only(*campos):
        fin = p99.dados_99(pedido).get('financeiro') or {}
        resumo['pedidos'] += 1
        resumo['venda'] += Decimal(fin['venda_cardapio']) if fin.get('venda_cardapio') else pedido.subtotal
        resumo['desconto_plataforma'] += pedido.platform_discount or ZERO
        resumo['desconto_loja'] += (pedido.discount or ZERO) - (pedido.platform_discount or ZERO)
        if fin.get('recebido') is not None:
            resumo['conciliados'] += 1
            resumo['recebido'] += Decimal(fin['recebido'])
            if fin.get('comissao_taxas') is not None:
                resumo['comissao_taxas'] += Decimal(fin['comissao_taxas'])
    return resumo


def resumo_do_periodo(loja, inicio: date, fim: date, incluir_teste: bool = False) -> dict:
    from apps.stores.metrics import pedidos_de_receita
    return resumo_de_pedidos(pedidos_de_receita(loja=loja, inicio=inicio, fim=fim, incluir_teste=incluir_teste))
