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
MODELOS = ('validade', 'nutricao-qr', 'produto', 'nutricao')
TIPOS = ('texto', 'qr', 'barras', 'linha', 'caixa', 'tabela')
CAMPOS = ('name', 'manip', 'val', 'price', 'description', 'barcode', 'publicUrl', 'coluna', 'ingredients', 'allergens')
ALINHAMENTOS = ('esquerda', 'centro', 'direita')
MODOS_DE_MIDIA = ('gap', 'continuo', 'auto')
# Liberation (SIL OFL), vendorizada em apps/stores/fonts: métricas de Arial/Arial Narrow/Times/Courier.
FONTES = {
    'sans': ('LiberationSans-Regular.ttf', 'LiberationSans-Bold.ttf'),
    'estreita': ('LiberationSansNarrow-Regular.ttf', 'LiberationSansNarrow-Bold.ttf'),
    'serif': ('LiberationSerif-Regular.ttf', 'LiberationSerif-Bold.ttf'),
    'mono': ('LiberationMono-Regular.ttf', 'LiberationMono-Bold.ttf'),
}
AJUSTES = ('quebrar', 'encolher')
DIR_FONTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts')


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


_PADRAO['nutricao'] = {
    'versao': 1,
    'etiqueta': {'largura': 100, 'altura': 80},
    'papel': {'largura': 100, 'colunas': 1, 'espaco': 0},
    'elementos': [
        _texto('nome', 3, 2, 76, 6, '{name}', 3.2, negrito=True, linhas=1),
        {'id': 'tabela', 'tipo': 'tabela', 'x': 3, 'y': 8.5, 'w': 60, 'h': 62},
        _texto('ingredientes', 65, 8.5, 32, 30, 'INGREDIENTES: {ingredients}', 1.7, linhas=12),
        _texto('alergenicos', 65, 40, 32, 10, '{allergens}', 1.8, negrito=True, linhas=4),
        {'id': 'qr', 'tipo': 'qr', 'x': 79, 'y': 58, 'w': 18, 'h': 18, 'campo': 'publicUrl'},
        _texto('rodape', 3, 72, 60, 6, 'Escaneie o QR para a tabela completa e a lista de alergênicos.', 1.5, linhas=2),
    ],
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
    # Margens medidas no rolo. Com margem esquerda informada a 1ª coluna começa
    # nela (nada de centralizar) e a largura do rolo é a soma das partes.
    m_esq = papel.get('margem_esquerda', papel.get('margem'))
    m_esq = None if m_esq in (None, '') else _num(m_esq, 'papel.margem_esquerda', 0, 200)
    m_dir = papel.get('margem_direita')
    m_dir = None if m_dir in (None, '') else _num(m_dir, 'papel.margem_direita', 0, 200)
    vao_linhas = papel.get('vao_linhas')
    vao_linhas = None if vao_linhas in (None, '') else _num(vao_linhas, 'papel.vao_linhas', 0, 100)
    if m_esq is not None and m_dir is not None:
        soma = m_esq + bloco + m_dir
        papel_w = _num(papel.get('largura', soma), 'papel.largura', 5, 400)
        if abs(papel_w - soma) > 0.05:
            raise LayoutInvalido(f'rolo de {papel_w} mm não fecha: {m_esq} + {bloco} + {m_dir} = {soma} mm')
    else:
        papel_w = _num(papel.get('largura', bloco), 'papel.largura', 5, 400)
    if papel_w + 0.01 < bloco:
        raise LayoutInvalido(f'papel de {papel_w} mm não cabe {colunas} coluna(s) de {largura} mm')
    margem = m_esq
    # Rolo com vão entre linhas (gap, o normal em etiqueta picotada) / contínuo /
    # auto = não mexe no que está na impressora. Em contínuo a impressora avança
    # ^LL por etiqueta, então ^LL precisa ser o PASSO (altura + vão de linha).
    modo_midia = papel.get('modo_midia', 'gap') or 'gap'
    if modo_midia not in MODOS_DE_MIDIA:
        raise LayoutInvalido(f'papel.modo_midia desconhecido: {modo_midia}')
    passo = papel.get('passo')
    passo = None if passo in (None, '') else _num(passo, 'papel.passo', altura, 400)

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
            fonte = e.get('fonte', 'sans') or 'sans'
            if fonte not in FONTES:
                raise LayoutInvalido(f'elemento {i}: fonte desconhecida')
            n['fonte'] = fonte
            ajuste = e.get('ajuste', 'quebrar') or 'quebrar'
            if ajuste not in AJUSTES:
                raise LayoutInvalido(f'elemento {i}: ajuste desconhecido')
            n['ajuste'] = ajuste
        elif n['tipo'] in ('qr', 'barras'):
            campo = e.get('campo') or ('publicUrl' if n['tipo'] == 'qr' else 'barcode')
            if campo not in CAMPOS:
                raise LayoutInvalido(f'elemento {i}: campo desconhecido')
            n['campo'] = campo
        elif n['tipo'] == 'caixa':
            n['espessura'] = _num(e.get('espessura', 0.3), f'elemento {i}.espessura', 0.1, 10)
        elif n['tipo'] == 'tabela':
            fonte = e.get('fonte', 'sans') or 'sans'
            if fonte not in FONTES:
                raise LayoutInvalido(f'elemento {i}: fonte desconhecida')
            n['fonte'] = fonte
        saida.append(n)
    return {
        'versao': 1,
        'etiqueta': {'largura': largura, 'altura': altura},
        'papel': {'largura': papel_w, 'colunas': colunas, 'espaco': espaco, 'margem': margem,
                  'margem_esquerda': m_esq, 'margem_direita': m_dir, 'vao_linhas': vao_linhas,
                  'modo_midia': modo_midia, 'passo': passo},
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


@lru_cache(maxsize=256)
def _fonte(px: int, negrito: bool, familia: str = 'sans'):
    arquivo = FONTES.get(familia, FONTES['sans'])[1 if negrito else 0]
    try:
        return ImageFont.truetype(os.path.join(DIR_FONTES, arquivo), max(4, px))
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
    familia = e.get('fonte', 'sans')
    fonte = _fonte(px, e['negrito'], familia)
    x0, y0, w, h = mm(e['x']), mm(e['y']), mm(e['w']), mm(e['h'])
    if e.get('ajuste') == 'encolher':
        # Uma linha só: diminui a letra até caber na largura (mínimo 4 px).
        while px > 4 and fonte.getlength(conteudo) > w:
            px -= 1
            fonte = _fonte(px, e['negrito'], familia)
        linhas = [conteudo]
    else:
        linhas = _quebrar(conteudo, fonte, w, e['linhas'])
    passo = int(round(px * 1.12))
    y = y0
    for linha in linhas:
        if y + passo > y0 + h + 2:  # não invade o elemento de baixo
            break
        lw = fonte.getlength(linha)
        x = x0 if e['alinhar'] == 'esquerda' else (x0 + (w - lw) / 2 if e['alinhar'] == 'centro' else x0 + w - lw)
        draw.text((x, y), linha, font=fonte, fill=0)
        y += passo


# ---------------------------------------------------------------- tabela nutricional (IN 75/2020)

_LINHAS_ANVISA = [
    # (chave, rótulo, unidade, VD, recuo)
    ('energy_kcal', 'Valor energético (kcal)', 'kcal', 2000, 0),
    ('carbohydrates_g', 'Carboidratos (g)', 'g', 300, 0),
    ('total_sugars_g', 'Açúcares totais (g)', 'g', None, 1),
    ('added_sugars_g', 'Açúcares adicionados (g)', 'g', 50, 2),
    ('protein_g', 'Proteínas (g)', 'g', 50, 0),
    ('total_fat_g', 'Gorduras totais (g)', 'g', 65, 0),
    ('saturated_fat_g', 'Gorduras saturadas (g)', 'g', 20, 1),
    ('trans_fat_g', 'Gorduras trans (g)', 'g', None, 1),
    ('fiber_g', 'Fibras alimentares (g)', 'g', 25, 0),
    ('sodium_mg', 'Sódio (mg)', 'mg', 2000, 0),
]


def _fmt(v, unidade):
    if v is None or v == '':
        return '-'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '-'
    if unidade == 'mg' or unidade == 'kcal':
        return f'{int(round(f))}'
    return f'{f:.1f}'.rstrip('0').rstrip('.').replace('.', ',')


def linhas_da_tabela(et: dict) -> list:
    """[(rótulo, por 100 g, por porção, %VD, recuo)] com travessão onde não há valor."""
    per100 = et.get('per100g') or {}
    porcao = et.get('perServing') or {}
    try:
        fator = float(et.get('servingG', 100)) / 100.0
    except (TypeError, ValueError):
        fator = 1.0
    saida = []
    for chave, rotulo, unidade, vd, recuo in _LINHAS_ANVISA:
        base = per100.get(chave)
        na_porcao = porcao.get(chave)
        if na_porcao is None and base not in (None, ''):
            try:
                na_porcao = float(base) * fator
            except (TypeError, ValueError):
                na_porcao = None
        pct = '-'
        if vd and na_porcao not in (None, ''):
            try:
                pct = str(int(round(float(na_porcao) / vd * 100)))
            except (TypeError, ValueError):
                pct = '-'
        saida.append((rotulo, _fmt(base, unidade), _fmt(na_porcao, unidade), pct, recuo))
    return saida


def cabecalho_da_tabela(et: dict) -> tuple:
    porcoes = et.get('servingsPerContainer')
    porcoes_txt = _fmt(porcoes, 'g') if porcoes not in (None, '') else '-'
    porcao = f"{_fmt(et.get('servingG', 100), 'g')} g"
    if et.get('householdMeasure'):
        porcao += f" ({et['householdMeasure']})"
    return (f'Porções por embalagem: {porcoes_txt}', f'Porção: {porcao}')


def _desenhar_tabela(draw, e, dados):
    """Tabela no padrão da ANVISA dentro da caixa (x, y, w, h em mm): moldura,
    título, porções, barra grossa, cabeçalho de colunas, 10 linhas, rodapé."""
    x0, y0, w, h = mm(e['x']), mm(e['y']), mm(e['w']), mm(e['h'])
    familia = e.get('fonte', 'sans')
    draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=0, width=max(2, mm(0.4)))
    pad = mm(1.2)
    # alturas proporcionais à caixa: título 11%, porções 14%, cabeçalho 9%, rodapé 8%, resto = 10 linhas
    y = y0 + pad
    h_titulo = int(h * 0.11); h_porc = int(h * 0.14); h_cab = int(h * 0.09); h_rod = int(h * 0.08)
    h_linhas = h - 2 * pad - h_titulo - h_porc - h_cab - h_rod
    h_linha = h_linhas // len(_LINHAS_ANVISA)
    def texto(tx, ty, s, px, negrito=False, alinhar='L', largura=None):
        f = _fonte(px, negrito, familia)
        lw = f.getlength(s)
        if alinhar == 'C' and largura:
            tx = tx + (largura - lw) / 2
        elif alinhar == 'R' and largura:
            tx = tx + largura - lw
        draw.text((tx, ty), s, font=f, fill=0)
    # título
    px_t = max(6, int(h_titulo * 0.62))
    texto(x0 + pad, y + (h_titulo - px_t) // 2, 'INFORMAÇÃO NUTRICIONAL', px_t, True, 'C', w - 2 * pad)
    y += h_titulo
    draw.rectangle([x0 + pad, y, x0 + w - pad, y + 1], fill=0)
    # porções
    l1, l2 = cabecalho_da_tabela(dados)
    px_p = max(5, int(h_porc * 0.36))
    texto(x0 + pad, y + 2, l1, px_p, False)
    texto(x0 + pad, y + 2 + int(px_p * 1.25), l2, px_p, False)
    y += h_porc
    draw.rectangle([x0 + pad, y, x0 + w - pad, y + max(3, mm(0.8))], fill=0)   # barra grossa
    y += max(3, mm(0.8)) + 1
    # colunas
    c_val = int((w - 2 * pad) * 0.16)
    x_c3 = x0 + w - pad - c_val; x_c2 = x_c3 - c_val; x_c1 = x_c2 - c_val
    px_c = max(5, int(h_cab * 0.55))
    texto(x_c1, y + (h_cab - px_c) // 2, '100 g', px_c, True, 'C', c_val)
    texto(x_c2, y + (h_cab - px_c) // 2, f"{_fmt(dados.get('servingG', 100), 'g')} g", px_c, True, 'C', c_val)
    texto(x_c3, y + (h_cab - px_c) // 2, '%VD*', px_c, True, 'C', c_val)
    y += h_cab
    px_l = max(5, int(h_linha * 0.55))
    for rotulo, v100, vporc, pct, recuo in linhas_da_tabela(dados):
        draw.rectangle([x0 + pad, y, x0 + w - pad, y], fill=0)   # linha fina
        ty = y + (h_linha - px_l) // 2
        texto(x0 + pad + recuo * mm(1.5), ty, rotulo, px_l)
        for xx, v in ((x_c1, v100), (x_c2, vporc), (x_c3, pct)):
            draw.rectangle([xx, y, xx, y + h_linha], fill=0)     # divisória vertical
            texto(xx, ty, v, px_l, False, 'C', c_val)
        y += h_linha
    draw.rectangle([x0 + pad, y, x0 + w - pad, y], fill=0)
    px_r = max(4, int(h_rod * 0.45))
    texto(x0 + pad, y + (h_rod - px_r) // 2, '*Percentual de valores diários fornecidos pela porção.', px_r)


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
        elif e['tipo'] == 'tabela':
            _desenhar_tabela(draw, e, dados or {})
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
    papel = lay['papel']
    modo = papel.get('modo_midia', 'gap')
    mn = {'gap': '^MNY', 'continuo': '^MNN'}.get(modo, '')
    altura = lay['etiqueta']['altura']
    if modo == 'continuo':
        if papel.get('passo'):
            altura = papel['passo']
        elif papel.get('vao_linhas') is not None:
            altura = altura + papel['vao_linhas']
    return f"^XA^CI28{mn}^PW{mm(papel['largura'])}^LL{mm(altura)}^LH0,0^LS{ls}^LT{lt}^MD{md}"


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
