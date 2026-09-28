"""Etiqueta desenhada: layout em milímetros → bitmap → ZPL (^GFA).

Por que não ^A0/^FB direto: a Zebra ZD220 e a Elgin L42 PRO (emulação ZPL)
desenham as fontes nativas com métricas diferentes, então a mesma etiqueta
"cabe" numa e estoura na outra, e o painel nunca conseguia mostrar o que ia
sair. Aqui o desenho é feito UMA vez, em pixels (203 dpi = 8 por mm), e as
duas impressoras recebem o mesmo bitmap. A prévia do painel é este bitmap.

QR e código de barras continuam nativos (^BQ / ^BE / ^BC): a impressora
gera com módulo exato, e a prévia mostra um marcador no mesmo lugar e tamanho.

Calibração (deslocamento em mm e escurecimento) é da IMPRESSORA — vai em
^LS/^LT/^MD, guardada no agent — e nunca no layout: o desenho é o mesmo em
qualquer máquina; o que muda é onde cada rolo está preso.
"""
from __future__ import annotations

import copy
import io
import math
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

DPMM = 8  # 203 dpi
MODELOS = ('validade', 'nutricao-qr', 'produto')
TIPOS = ('texto', 'qr', 'barras', 'linha', 'caixa')
CAMPOS = ('name', 'manip', 'val', 'price', 'description', 'barcode', 'publicUrl', 'coluna')
ALINHAMENTOS = ('esquerda', 'centro', 'direita')


class LayoutInvalido(ValueError):
    pass


def mm(v) -> int:
    return int(round(float(v) * DPMM))


# ------------------------------------------------------------------ layouts padrão

def _texto(id_, x, y, w, h, texto, tamanho, *, negrito=False, linhas=1, alinhar='esquerda'):
    return {'id': id_, 'tipo': 'texto', 'x': x, 'y': y, 'w': w, 'h': h, 'texto': texto,
            'tamanho': tamanho, 'negrito': negrito, 'linhas': linhas, 'alinhar': alinhar}


_PADRAO = {
    # Igual ao rolo de 3 que a Cê Saladas usa na Elgin (33 × 22, vão 2, papel 107).
    'validade': {
        'versao': 1,
        'etiqueta': {'largura': 33, 'altura': 22},
        'papel': {'largura': 107, 'colunas': 3, 'espaco': 2},
        'elementos': [
            _texto('nome', 1.6, 1.4, 29.8, 9.5, '{name}', 2.6, negrito=True, linhas=3),
            _texto('manip', 1.6, 14.6, 29.8, 2.8, 'Manip.: {manip}', 2.1),
            _texto('val', 1.6, 17.6, 29.8, 3.4, 'Val.: {val}', 2.8, negrito=True),
        ],
    },
    'nutricao-qr': {
        'versao': 1,
        'etiqueta': {'largura': 30, 'altura': 22},
        'papel': {'largura': 100, 'colunas': 3, 'espaco': 3},
        'elementos': [
            _texto('nome', 1.2, 1.2, 11, 9, '{name}', 2.2, negrito=True, linhas=3),
            _texto('dica', 1.2, 13, 11, 8, 'Escaneie para ver a informação nutricional', 1.5, linhas=4),
            {'id': 'qr', 'tipo': 'qr', 'x': 12.5, 'y': 3, 'w': 16, 'h': 16, 'campo': 'publicUrl'},
        ],
    },
    'produto': {
        'versao': 1,
        'etiqueta': {'largura': 100, 'altura': 80},
        'papel': {'largura': 100, 'colunas': 1, 'espaco': 0},
        'elementos': [
            _texto('nome', 3, 3, 94, 10, '{name}', 3.8, negrito=True, linhas=2),
            _texto('preco', 3, 14, 94, 7, '{price}', 5.5, negrito=True),
            {'id': 'barras', 'tipo': 'barras', 'x': 3, 'y': 23, 'w': 94, 'h': 50, 'campo': 'barcode'},
        ],
    },
}


def layout_padrao(modelo: str) -> dict:
    if modelo not in _PADRAO:
        raise LayoutInvalido(f'Modelo sem layout desenhável: {modelo}')
    return copy.deepcopy(_PADRAO[modelo])


# ------------------------------------------------------------------ validação

def _num(v, nome, minimo, maximo):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise LayoutInvalido(f'{nome} precisa ser número')
    if not math.isfinite(f) or f < minimo or f > maximo:
        raise LayoutInvalido(f'{nome} fora da faixa {minimo}–{maximo}')
    return f


def validar_layout(layout) -> dict:
    """Devolve uma cópia normalizada (números como float) ou levanta LayoutInvalido."""
    if not isinstance(layout, dict):
        raise LayoutInvalido('layout precisa ser um objeto')
    et = layout.get('etiqueta') or {}
    papel = layout.get('papel') or {}
    largura = _num(et.get('largura'), 'etiqueta.largura', 5, 300)
    altura = _num(et.get('altura'), 'etiqueta.altura', 5, 300)
    colunas = int(_num(papel.get('colunas', 1), 'papel.colunas', 1, 12))
    espaco = _num(papel.get('espaco', 0), 'papel.espaco', 0, 50)
    bloco = colunas * largura + (colunas - 1) * espaco
    papel_w = _num(papel.get('largura', bloco), 'papel.largura', 5, 400)
    if papel_w + 0.01 < bloco:
        raise LayoutInvalido(f'papel de {papel_w} mm não cabe {colunas} coluna(s) de {largura} mm')
    margem = papel.get('margem')
    margem = None if margem in (None, '') else _num(margem, 'papel.margem', 0, 200)

    elementos = layout.get('elementos')
    if not isinstance(elementos, list) or len(elementos) > 60:
        raise LayoutInvalido('elementos precisa ser uma lista de até 60 itens')
    saida = []
    for i, e in enumerate(elementos):
        if not isinstance(e, dict) or e.get('tipo') not in TIPOS:
            raise LayoutInvalido(f'elemento {i}: tipo desconhecido')
        n = {
            'id': str(e.get('id') or f'e{i}')[:40],
            'tipo': e['tipo'],
            'x': _num(e.get('x', 0), f'elemento {i}.x', -50, 400),
            'y': _num(e.get('y', 0), f'elemento {i}.y', -50, 400),
            'w': _num(e.get('w', 1), f'elemento {i}.w', 0.1, 400),
            'h': _num(e.get('h', 1), f'elemento {i}.h', 0.1, 400),
        }
        if n['tipo'] == 'texto':
            n['texto'] = str(e.get('texto') or '')[:200]
            n['tamanho'] = _num(e.get('tamanho', 2.5), f'elemento {i}.tamanho', 0.8, 60)
            n['negrito'] = bool(e.get('negrito', False))
            n['linhas'] = int(_num(e.get('linhas', 1), f'elemento {i}.linhas', 1, 20))
            al = e.get('alinhar', 'esquerda')
            n['alinhar'] = al if al in ALINHAMENTOS else 'esquerda'
        elif n['tipo'] in ('qr', 'barras'):
            campo = e.get('campo') or ('publicUrl' if n['tipo'] == 'qr' else 'barcode')
            if campo not in CAMPOS:
                raise LayoutInvalido(f'elemento {i}: campo desconhecido')
            n['campo'] = campo
        elif n['tipo'] == 'caixa':
            n['espessura'] = _num(e.get('espessura', 0.3), f'elemento {i}.espessura', 0.1, 10)
        saida.append(n)
    return {
        'versao': 1,
        'etiqueta': {'largura': largura, 'altura': altura},
        'papel': {'largura': papel_w, 'colunas': colunas, 'espaco': espaco, 'margem': margem},
        'elementos': saida,
    }


def _geometria(layout):
    lay = validar_layout(layout)
    et, papel = lay['etiqueta'], lay['papel']
    bloco = papel['colunas'] * et['largura'] + (papel['colunas'] - 1) * papel['espaco']
    margem = papel['margem'] if papel['margem'] is not None else max(0.0, (papel['largura'] - bloco) / 2)
    return lay, margem


# ------------------------------------------------------------------ texto

def preencher(texto: str, dados: dict) -> str:
    """'Val.: {val}' + {'val': '30/09'} → 'Val.: 30/09'. Campo desconhecido vira vazio."""
    class _Vazio(dict):
        def __missing__(self, k):
            return ''
    try:
        return str(texto).format_map(_Vazio({k: ('' if v is None else v) for k, v in (dados or {}).items()}))
    except (ValueError, IndexError):
        return str(texto)


@lru_cache(maxsize=64)
def _fonte(px: int, negrito: bool):
    """Bitstream Vera (Latin-1 completo: ç ã é) vem com o reportlab da imagem."""
    try:
        import reportlab
        base = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
        return ImageFont.truetype(os.path.join(base, 'VeraBd.ttf' if negrito else 'Vera.ttf'), max(4, px))
    except Exception:  # noqa: BLE001 — sem a fonte, ainda imprime (feio, mas imprime)
        return ImageFont.load_default()


def _quebrar(texto, fonte, largura_px, max_linhas):
    linhas = []
    for paragrafo in str(texto).split('\n'):
        atual = ''
        for palavra in paragrafo.split(' '):
            tentativa = palavra if not atual else f'{atual} {palavra}'
            if fonte.getlength(tentativa) <= largura_px or not atual:
                atual = tentativa
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return linhas[:max_linhas]


def _desenhar_texto(draw, e, dados):
    conteudo = preencher(e['texto'], dados).strip()
    if not conteudo:
        return
    px = int(round(e['tamanho'] * DPMM * 0.92))
    fonte = _fonte(px, e['negrito'])
    x0, y0, w, h = mm(e['x']), mm(e['y']), mm(e['w']), mm(e['h'])
    passo = int(round(px * 1.12))
    y = y0
    for linha in _quebrar(conteudo, fonte, w, e['linhas']):
        if y + passo > y0 + h + 2:  # não invade o elemento de baixo
            break
        lw = fonte.getlength(linha)
        x = x0 if e['alinhar'] == 'esquerda' else (x0 + (w - lw) / 2 if e['alinhar'] == 'centro' else x0 + w - lw)
        draw.text((x, y), linha, font=fonte, fill=0)
        y += passo


def _marcador_qr(draw, e):
    """Prévia: quadro com os 3 olhos do QR, no lugar e tamanho do real."""
    x, y, lado = mm(e['x']), mm(e['y']), mm(min(e['w'], e['h']))
    draw.rectangle([x, y, x + lado - 1, y + lado - 1], outline=0, width=2)
    olho = max(6, lado // 7)
    for ox, oy in ((x, y), (x + lado - olho, y), (x, y + lado - olho)):
        draw.rectangle([ox, oy, ox + olho - 1, oy + olho - 1], outline=0, width=2)
        draw.rectangle([ox + 3, oy + 3, ox + olho - 4, oy + olho - 4], fill=0)


def _marcador_barras(draw, e):
    x, y, w, h = mm(e['x']), mm(e['y']), mm(e['w']), mm(e['h'])
    cx = x
    i = 0
    while cx < x + w:
        largura = 2 + (i % 3)
        if i % 2 == 0:
            draw.rectangle([cx, y, cx + largura - 1, y + h - 1], fill=0)
        cx += largura + 1
        i += 1


def _desenhar_etiqueta(lay, dados, elementos, marcadores):
    et = lay['etiqueta']
    img = Image.new('1', (mm(et['largura']), mm(et['altura'])), 1)
    draw = ImageDraw.Draw(img)
    for e in elementos:
        if e['tipo'] == 'texto':
            _desenhar_texto(draw, e, dados)
        elif e['tipo'] == 'linha':
            draw.rectangle([mm(e['x']), mm(e['y']), mm(e['x'] + e['w']) - 1, max(mm(e['y']), mm(e['y'] + e['h']) - 1)], fill=0)
        elif e['tipo'] == 'caixa':
            draw.rectangle([mm(e['x']), mm(e['y']), mm(e['x'] + e['w']) - 1, mm(e['y'] + e['h']) - 1],
                           outline=0, width=max(1, mm(e['espessura'])))
        elif marcadores and e['tipo'] == 'qr' and (dados or {}).get(e['campo']):
            _marcador_qr(draw, e)
        elif marcadores and e['tipo'] == 'barras' and (dados or {}).get(e['campo']):
            _marcador_barras(draw, e)
    return img


def _origem_x(lay, margem, coluna) -> float:
    return margem + coluna * (lay['etiqueta']['largura'] + lay['papel']['espaco'])


def render_bitmap(layout, etiquetas, *, elementos=None, marcadores=False) -> Image.Image:
    """Uma linha física do rolo (todas as colunas) em modo '1' (1 = branco)."""
    lay, margem = _geometria(layout)
    elementos = lay['elementos'] if elementos is None else elementos
    colunas = lay['papel']['colunas']
    dados = list(etiquetas or [])[:colunas]
    if not dados and elementos is not lay['elementos']:
        dados = [{'coluna': i + 1} for i in range(colunas)]
    papel = Image.new('1', (mm(lay['papel']['largura']), mm(lay['etiqueta']['altura'])), 1)
    for col, et in enumerate(dados):
        papel.paste(_desenhar_etiqueta(lay, dict(et, coluna=col + 1), elementos, marcadores),
                    (mm(_origem_x(lay, margem, col)), 0))
    return papel


def _tem_tinta(img, x0, y0, x1, y1) -> bool:
    caixa = img.crop((mm(x0), mm(y0), mm(x1), mm(y1)))
    return ImageOps.invert(caixa.convert("L")).getbbox() is not None


# ------------------------------------------------------------------ ZPL

def _zpl_seguro(v) -> str:
    return str(v if v is not None else '').replace('^', '-').replace('~', '-')


def _cabecalho(lay, calibracao) -> str:
    cal = calibracao or {}
    ls = mm(cal.get('desloc_x', 0) or 0)
    lt = max(-120, min(120, mm(cal.get('desloc_y', 0) or 0)))
    md = max(0, min(30, int(cal.get('escuro', 10) or 10)))
    return f"^XA^CI28^PW{mm(lay['papel']['largura'])}^LL{mm(lay['etiqueta']['altura'])}^LH0,0^LS{ls}^LT{lt}^MD{md}"


def _gfa(img: Image.Image) -> str:
    preto = ImageOps.invert(img.convert('L')).convert('1')  # bit 1 = tinta
    dados = preto.tobytes()
    bpr = math.ceil(img.width / 8)
    total = bpr * img.height
    return f'^FO0,0^GFA,{total},{total},{bpr},{dados.hex().upper()}^FS'


def _modulos_qr(n: int) -> int:
    """Módulos de um QR nível Q (o do ^FDQA) em modo byte, pelo tamanho do texto."""
    for cap, mods in ((11, 21), (20, 25), (32, 29), (46, 33), (60, 37), (74, 41), (86, 45), (108, 49),
                      (130, 53), (151, 57), (177, 61), (203, 65), (241, 69), (258, 73)):
        if n <= cap:
            return mods
    return 77


def _nativos(lay, margem, col, e, dados) -> str:
    valor = _zpl_seguro((dados or {}).get(e['campo']) or '').strip()
    if not valor:
        return ''
    x = mm(_origem_x(lay, margem, col) + e['x']); y = mm(e['y'])
    if e['tipo'] == 'qr':
        lado = mm(min(e['w'], e['h']))
        escala = max(2, min(10, lado // _modulos_qr(len(valor))))
        return f'^FO{x},{y}^BQN,2,{escala}^FDQA,{valor}^FS'
    h = mm(e['h']); w = mm(e['w'])
    if len(valor) == 13 and valor.isdigit():
        modulo = max(1, min(4, w // 113))  # EAN-13 = 95 módulos + texto
        largura_real = modulo * 95
        return f'^FO{x + max(0, (w - largura_real) // 2)},{y}^BY{modulo}^BEN,{max(20, h - 24)},Y,N^FD{valor}^FS'
    return f'^FO{x},{y}^BY2^BCN,{max(20, h - 24)},Y,N,N^FD{valor}^FS'


def render_zpl(layout, etiquetas, calibracao=None) -> str:
    lay, margem = _geometria(layout)
    colunas = lay['papel']['colunas']
    etiquetas = [e for e in (etiquetas or []) if isinstance(e, dict)]
    saida = []
    for i in range(0, len(etiquetas), colunas):
        linha = etiquetas[i:i + colunas]
        partes = [_cabecalho(lay, calibracao), _gfa(render_bitmap(lay, linha))]
        for col, et in enumerate(linha):
            for e in lay['elementos']:
                if e['tipo'] in ('qr', 'barras'):
                    partes.append(_nativos(lay, margem, col, e, et))
        partes.append('^XZ')
        saida.append(''.join(partes))
    return '\n'.join(saida)


# ------------------------------------------------------------------ calibração

def elementos_da_grade(layout) -> list:
    """Moldura da etiqueta + régua em mm nas bordas de cima e da esquerda.

    Quem lê a etiqueta impressa vê onde o "0" caiu em relação à borda real
    (ou em que traço a borda real cortou a régua) e digita o deslocamento.
    """
    lay = validar_layout(layout)
    w, h = lay['etiqueta']['largura'], lay['etiqueta']['altura']
    els = [{'id': 'moldura', 'tipo': 'caixa', 'x': 0, 'y': 0, 'w': w, 'h': h, 'espessura': 0.25}]
    for i in range(0, int(w) + 1):
        alto = 2.5 if i % 10 == 0 else (1.6 if i % 5 == 0 else 0.9)
        els.append({'id': f'tx{i}', 'tipo': 'linha', 'x': i, 'y': 0, 'w': 0.25, 'h': alto})
        if i % 10 == 0 and i > 0 and i + 3 <= w:
            els.append(_texto(f'nx{i}', i + 0.4, 0.3, 4, 2, str(i), 1.4))
    for j in range(0, int(h) + 1):
        longo = 2.5 if j % 10 == 0 else (1.6 if j % 5 == 0 else 0.9)
        els.append({'id': f'ty{j}', 'tipo': 'linha', 'x': 0, 'y': j, 'w': longo, 'h': 0.25})
        if j % 10 == 0 and j > 0 and j + 2 <= h:
            els.append(_texto(f'ny{j}', 0.5, j + 0.3, 4, 2, str(j), 1.4))
    els.append({'id': 'centro-h', 'tipo': 'linha', 'x': w / 2 - 3, 'y': h / 2, 'w': 6, 'h': 0.25})
    els.append({'id': 'centro-v', 'tipo': 'linha', 'x': w / 2, 'y': h / 2 - 3, 'w': 0.25, 'h': 6})
    els.append(_texto('col', 4, h / 2 + 1, w - 8, 3, 'Coluna {coluna}', 1.8, negrito=True, alinhar='centro'))
    return els


def grade_de_calibracao(layout, calibracao=None) -> str:
    lay, _ = _geometria(layout)
    return ''.join([_cabecalho(lay, calibracao), _gfa(render_bitmap(lay, [], elementos=elementos_da_grade(lay))), '^XZ'])


def preview_png(layout, etiquetas, *, grade=False) -> bytes:
    lay, margem = _geometria(layout)
    if grade:
        img = render_bitmap(lay, [], elementos=elementos_da_grade(lay))
    else:
        img = render_bitmap(lay, etiquetas, marcadores=True)
    cinza = img.convert('L')
    draw = ImageDraw.Draw(cinza)
    et = lay['etiqueta']
    for col in range(lay['papel']['colunas']):
        x = mm(_origem_x(lay, margem, col))
        draw.rectangle([x, 0, x + mm(et['largura']) - 1, mm(et['altura']) - 1], outline=170)
    buf = io.BytesIO()
    cinza.save(buf, format='PNG', optimize=True)
    return buf.getvalue()
