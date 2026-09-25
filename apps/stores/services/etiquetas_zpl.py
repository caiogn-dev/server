"""Etiquetas em ZPL para a Zebra (ZD220, 203 dpi = 8 pontos por mm).

O painel já monta os dados da etiqueta (é o mesmo objeto que alimenta a
impressão pelo navegador em `labelPrint.ts`). Aqui esse objeto vira ZPL para
sair pelo print agent, em qualquer PC, sem o painel aberto na frente da Zebra.

Três modelos:
  - validade: rolo de N colunas (config igual ao do navegador)
  - nutricao: tabela completa 100 × 80 mm com QR
  - nutricao-qr: 30 × 22 mm, só nome + QR para a tabela pública
"""
from __future__ import annotations

DPMM = 8  # 203 dpi

LINHAS_NUTRICIONAIS = [
    ('energy_kcal', 'Valor energético', 'kcal', 2000),
    ('carbohydrates_g', 'Carboidratos', 'g', 300),
    ('total_sugars_g', 'Açúcares totais', 'g', None),
    ('added_sugars_g', 'Açúcares adicionados', 'g', 50),
    ('protein_g', 'Proteínas', 'g', 50),
    ('total_fat_g', 'Gorduras totais', 'g', 65),
    ('saturated_fat_g', 'Gorduras saturadas', 'g', 20),
    ('trans_fat_g', 'Gorduras trans', 'g', 2),
    ('fiber_g', 'Fibra alimentar', 'g', 25),
    ('sodium_mg', 'Sódio', 'mg', 2000),
]

MODELOS = ('produto', 'validade', 'nutricao', 'nutricao-qr')


def mm(v) -> int:
    return int(round(float(v) * DPMM))


def texto(v) -> str:
    """`^` e `~` são comandos no ZPL: um nome de produto com eles quebraria o
    rótulo (ou o resto do lote). Viram hífen."""
    return str(v if v is not None else '').replace('^', '-').replace('~', '-')


def numero(v, unidade: str) -> str:
    if v is None or v == '':
        return '-'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '-'
    if unidade == 'mg':
        return f'{int(round(f))}'
    s = f'{f:.1f}'.rstrip('0').rstrip('.')
    return s.replace('.', ',')


def _cabecalho(largura_mm, altura_mm) -> str:
    return f'^XA^CI28^PW{mm(largura_mm)}^LL{mm(altura_mm)}^LH0,0^MD10'


def _campo(x, y, fonte, conteudo, *, largura=None, linhas=1, alinhar='L', reverso=False) -> str:
    bloco = f'^FB{largura},{linhas},0,{alinhar}' if largura else ''
    return f'^FO{x},{y}^A0N,{fonte},{fonte}{bloco}{"^FR" if reverso else ""}^FD{texto(conteudo)}^FS'


def _qr(x, y, url, escala) -> str:
    return f'^FO{x},{y}^BQN,2,{escala}^FDQA,{texto(url)}^FS'


# ---------------------------------------------------------------- validade

def _validade(etiquetas, cfg) -> str:
    cols = max(1, int(cfg.get('cols', 1)))
    label_w = float(cfg.get('labelW', 33))
    label_h = float(cfg.get('labelH', 22))
    gap = float(cfg.get('gap', 2))
    paper_w = float(cfg.get('paperW', cols * label_w + (cols - 1) * gap))
    off_x = float(cfg.get('offsetX', 0))
    off_y = float(cfg.get('offsetY', 0))
    bloco = cols * label_w + (cols - 1) * gap
    margem = max(0.0, (paper_w - bloco) / 2)

    saida = []
    for i in range(0, len(etiquetas), cols):
        linha = etiquetas[i:i + cols]
        partes = [_cabecalho(paper_w, label_h)]
        for col, et in enumerate(linha):
            x = mm(margem + off_x + col * (label_w + gap)) + mm(1.6)
            y = mm(off_y) + mm(1.4)
            largura = mm(label_w - 3.2)
            partes.append(_campo(x, y, 20, et.get('name', ''), largura=largura, linhas=3))
            partes.append(_campo(x, mm(off_y + label_h) - mm(7.2), 17, f"Manip.: {et.get('manip', '')}", largura=largura))
            partes.append(_campo(x, mm(off_y + label_h) - mm(4.4), 22, f"Val.: {et.get('val', '')}", largura=largura))
        partes.append('^XZ')
        saida.append(''.join(partes))
    return '\n'.join(saida)


# ---------------------------------------------------------------- produto (código de barras)

def _e_ean13(codigo: str) -> bool:
    return len(codigo) == 13 and codigo.isdigit()


def _produto(etiquetas, cfg) -> str:
    w = float(cfg.get('width', 100)); h = float(cfg.get('height', 80))
    paper_w = max(float(cfg.get('paperW', w)), w)
    rotate = bool(cfg.get('rotate', False))
    off_x = float(cfg.get('offsetX', 0)); off_y = float(cfg.get('offsetY', 0))
    borda = str(cfg.get('border', 'none'))
    mostrar_preco = bool(cfg.get('showPrice', True))
    mostrar_desc = bool(cfg.get('showDesc', True))
    margem = (paper_w - w) / 2

    saida = []
    for et in etiquetas:
        # Girado: o rolo é estreito e a etiqueta é impressa "deitada". Trocamos
        # largura por altura e viramos os campos com ^FWR.
        p = [_cabecalho(h if rotate else paper_w, w if rotate else h)]
        if rotate:
            p.append('^FWR')
        x0 = mm(margem + off_x) + mm(3)
        y = mm(off_y) + mm(3)
        largura = mm(w - 6)
        if borda in ('solid', 'dashed'):
            p.append(f'^FO{mm(margem + off_x)},{mm(off_y)}^GB{mm(w)},{mm(h)},2^FS')
        p.append(_campo(x0, y, 30, et.get('name', ''), largura=largura, linhas=2)); y += 66
        if mostrar_desc and et.get('description'):
            p.append(_campo(x0, y, 16, et['description'], largura=largura, linhas=3)); y += 3 * 18 + 4
        if mostrar_preco and et.get('price'):
            p.append(_campo(x0, y, 40, et['price'], largura=largura)); y += 46
        codigo = texto(et.get('barcode') or '').strip()
        if codigo:
            altura_barra = max(40, mm(h) - y - mm(3) - 24)
            if _e_ean13(codigo):
                p.append(f'^FO{x0 + (largura - 380) // 2},{y}^BY3^BEN,{altura_barra},Y,N^FD{codigo}^FS')
            else:
                p.append(f'^FO{x0},{y}^BY2^BCN,{altura_barra},Y,N,N^FD{codigo}^FS')
        p.append('^XZ')
        saida.append(''.join(p))
    return '\n'.join(saida)


# ---------------------------------------------------------------- nutrição 100 × 80

def _nutricao(etiquetas) -> str:
    W, H = 100, 80
    x0 = mm(4)
    largura = mm(W - 8)
    saida = []
    for et in etiquetas:
        p = [_cabecalho(W, H)]
        y = mm(3)
        selos = [s for s in (et.get('frontOfPack') or []) if s]
        if selos:
            x = x0
            for selo in selos:
                w = 12 * len(str(selo)) + 16
                p.append(f'^FO{x},{y}^GB{w},30,30^FS')
                p.append(_campo(x + 8, y + 6, 18, selo, reverso=True))
                x += w + mm(2)
            y += 30 + mm(1)
        p.append(_campo(x0, y, 30, et.get('name', ''), largura=largura))
        y += 36
        p.append(f'^FO{x0},{y}^GB{largura},8,8^FS'); y += 12
        p.append(_campo(x0, y, 32, 'INFORMAÇÃO NUTRICIONAL', largura=largura)); y += 36
        p.append(f'^FO{x0},{y}^GB{largura},3,3^FS'); y += 7
        porcao = f"{numero(et.get('servingG', 100), 'g')} g"
        medida = et.get('householdMeasure')
        if medida:
            porcao += f' ({medida})'
        p.append(_campo(x0, y, 18, f'Porções por embalagem: -  |  Porção: {porcao}', largura=largura)); y += 22
        p.append(f'^FO{x0},{y}^GB{largura},2,2^FS'); y += 6

        c_nome, c1, c2, c3 = x0, x0 + mm(48), x0 + mm(63), x0 + mm(78)
        col_w = mm(14)
        cab = (_campo(c1, y, 16, '100 g', largura=col_w, alinhar='R')
               + _campo(c2, y, 16, f"{numero(et.get('servingG', 100), 'g')} g", largura=col_w, alinhar='R')
               + _campo(c3, y, 16, '%VD*', largura=col_w, alinhar='R'))
        p.append(cab); y += 20
        per100 = et.get('per100g') or {}
        porcao_g = et.get('perServing')
        try:
            fator = float(et.get('servingG', 100)) / 100.0
        except (TypeError, ValueError):
            fator = 1.0
        for chave, nome, unidade, vd in LINHAS_NUTRICIONAIS:
            base = per100.get(chave)
            if porcao_g is not None:
                na_porcao = porcao_g.get(chave)
            else:
                na_porcao = None if base is None else float(base) * fator
            pct = None
            if vd and na_porcao not in (None, ''):
                try:
                    pct = int(round(float(na_porcao) / vd * 100))
                except (TypeError, ValueError):
                    pct = None
            linha = (_campo(c_nome, y, 17, f'{nome} ({unidade})')
                     + _campo(c1, y, 17, numero(base, unidade), largura=col_w, alinhar='R')
                     + _campo(c2, y, 17, numero(na_porcao, unidade), largura=col_w, alinhar='R')
                     + _campo(c3, y, 17, '-' if pct is None else str(pct), largura=col_w, alinhar='R')
                     + f'^FO{x0},{y + 20}^GB{largura},1,1^FS')
            p.append(linha); y += 22
        p.append(_campo(x0, y + 2, 14, '*Percentual de valores diários fornecidos pela porção.', largura=largura)); y += 20

        qr_x = x0 + largura - mm(14)
        texto_largura = largura - mm(16)
        if et.get('ingredients'):
            p.append(_campo(x0, y, 15, f"INGREDIENTES: {et['ingredients']}", largura=texto_largura, linhas=3)); y += 3 * 17
        if et.get('allergens'):
            p.append(_campo(x0, y, 16, str(et['allergens']).upper(), largura=texto_largura, linhas=2)); y += 2 * 18
        if et.get('publicUrl'):
            p.append(_qr(qr_x, mm(H) - mm(4) - mm(14), et['publicUrl'], 4))
        p.append('^XZ')
        saida.append(''.join(p))
    return '\n'.join(saida)


# ---------------------------------------------------------------- QR 30 × 22

def _nutricao_qr(etiquetas) -> str:
    W, H = 30, 22
    saida = []
    for et in etiquetas:
        p = [_cabecalho(W, H)]
        p.append(_campo(mm(1.2), mm(1.2), 16, et.get('name', ''), largura=mm(13.5), linhas=3))
        p.append(_campo(mm(1.2), mm(12), 11, 'Escaneie para consultar a informação nutricional', largura=mm(13.5), linhas=4))
        if et.get('publicUrl'):
            p.append(_qr(mm(15.5), mm(3), et['publicUrl'], 3))
        p.append('^XZ')
        saida.append(''.join(p))
    return '\n'.join(saida)


def render_etiquetas(modelo: str, etiquetas: list, config: dict | None) -> str:
    cfg = config or {}
    etiquetas = [e for e in (etiquetas or []) if isinstance(e, dict)]
    if modelo == 'produto':
        return _produto(etiquetas, cfg)
    if modelo == 'validade':
        return _validade(etiquetas, cfg)
    if modelo == 'nutricao':
        return _nutricao(etiquetas)
    if modelo == 'nutricao-qr':
        return _nutricao_qr(etiquetas)
    raise ValueError(f'Modelo de etiqueta desconhecido: {modelo}')
