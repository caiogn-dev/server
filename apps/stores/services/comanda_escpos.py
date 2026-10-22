"""Linhas da comanda → bytes ESC/POS (contrato §2).

Mesmos comandos que `pastita-print-agent/src/escpos.js` usava: o papel sai
igual em qualquer Epson/Elgin que já imprimia, e o agente só despeja os bytes.
"""
from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)

ESC, GS, LF = 0x1B, 0x1D, b'\n'

INICIO = bytes([ESC, 0x40])
CODEPAGE_PC850 = bytes([ESC, 0x74, 0x02])  # cobre todos os acentos pt-BR
_ALINHAR = {'esquerda': 0, 'centro': 1, 'direita': 2}
CORTE = bytes([GS, 0x56, 66, 0])  # avança e corta (GS V 66 0)


def _texto(texto: str) -> bytes:
    return str(texto or '').encode('cp850', errors='replace')


def _alinhar(alinhar: str) -> bytes:
    return bytes([ESC, 0x61, _ALINHAR.get(alinhar, 0)])


def _logo(logo: dict) -> bytes:
    """Bitmap 1 bit já pronto (print_service.build_store_logo_escpos)."""
    try:
        largura, altura = int(logo['width']), int(logo['height'])
        dados = base64.b64decode(logo['data'])
    except (KeyError, TypeError, ValueError):
        return b''
    por_linha = (largura + 7) // 8
    # Bitmap truncado imprime lixo por metros de fita: melhor não imprimir.
    if len(dados) != por_linha * altura:
        return b''
    return (_alinhar('centro')
            + bytes([GS, 0x76, 0x30, 0x00, por_linha & 0xFF, (por_linha >> 8) & 0xFF,
                     altura & 0xFF, (altura >> 8) & 0xFF])
            + dados + LF)


def _codigo_barras(texto: str) -> bytes:
    valor = ''.join(c for c in str(texto or '') if 0x20 <= ord(c) <= 0x7E)[:22]
    if not valor:
        return b''
    dados = ('{B' + valor).encode('ascii')
    return (_alinhar('centro')
            + bytes([GS, 0x68, 80])    # altura 80 dots
            + bytes([GS, 0x77, 2])     # largura do módulo
            + bytes([GS, 0x48, 0])     # HRI off: ligada imprime o '{B' junto
            + bytes([GS, 0x6B, 0x49, len(dados)]) + dados + LF)


def _linha_de_texto(linha: dict) -> bytes:
    tamanho = (0x10 if linha.get('largura_dupla') else 0) | (0x01 if linha.get('altura_dupla') else 0)
    saida = _alinhar(linha.get('alinhar') or 'esquerda')
    if linha.get('negrito'):
        saida += bytes([ESC, 0x45, 1])
    if tamanho:
        saida += bytes([GS, 0x21, tamanho])
    if linha.get('invertido'):
        saida += bytes([GS, 0x42, 1])
    saida += _texto(linha.get('texto')) + LF
    # Desliga tudo na própria linha: um estilo vazado pinta o resto da comanda.
    if linha.get('invertido'):
        saida += bytes([GS, 0x42, 0])
    if tamanho:
        saida += bytes([GS, 0x21, 0])
    if linha.get('negrito'):
        saida += bytes([ESC, 0x45, 0])
    return saida


def bytes_da_comanda(linhas: list[dict], colunas: int) -> bytes:
    """Uma via. `colunas` já está embutida no texto das linhas; fica na
    assinatura do contrato para quem quiser conferir largura."""
    saida = bytearray(INICIO + CODEPAGE_PC850)
    for linha in linhas:
        tipo = linha.get('tipo') or 'texto'
        if tipo == 'espaco':
            saida += LF
        elif tipo == 'corte':
            saida += LF * 3 + CORTE
        elif tipo == 'codigo_barras':
            saida += _codigo_barras(linha.get('texto'))
        elif tipo == 'logo':
            saida += _logo(linha.get('logo') or {})
        else:  # texto, separador
            saida += _linha_de_texto(linha)
    return bytes(saida)


def escpos_b64_da_comanda(payload: dict, layout: dict) -> str:
    """Base64 de todas as vias, pronto para `payload['escpos_b64']`."""
    from apps.stores.services.comanda_linhas import linhas_da_comanda

    via = bytes_da_comanda(linhas_da_comanda(payload, layout), layout['colunas'])
    return base64.b64encode(via * layout['vias']).decode('ascii')
