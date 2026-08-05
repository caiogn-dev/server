"""
Cardápio em PDF com a cara da loja.

Serve para dois usos concretos: imprimir para o balcão/mesa e mandar o arquivo no
WhatsApp para quem pede "manda o cardápio". Hoje o dono resolve isso com print de
tela ou com um PDF feito à mão no Canva que envelhece assim que muda um preço —
aqui sai sempre do catálogo real.

Usa reportlab (já instalado) em vez de HTML→PDF: sem dependência de sistema
(weasyprint precisa de cairo/pango) e o layout é previsível na impressão.
"""
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

MARGEM = 16 * mm
ALTURA_BANNER = 34 * mm      # faixa da marca com a logo, no topo de toda página
MARGEM_MOLDURA = 9 * mm      # onde a borda decorativa é desenhada
_CINZA_TEXTO = colors.HexColor('#333333')
_CINZA_CLARO = colors.HexColor('#777777')


def _cor(valor: str, padrao: str) -> colors.Color:
    """Hex da loja → cor do reportlab, tolerando valor inválido/vazio."""
    try:
        v = (valor or '').strip()
        if not v.startswith('#') or len(v) not in (4, 7):
            return colors.HexColor(padrao)
        return colors.HexColor(v)
    except Exception:
        return colors.HexColor(padrao)


def _dinheiro(valor) -> str:
    """R$ no padrão brasileiro — reportlab não formata locale sozinho."""
    v = Decimal(str(valor or 0))
    inteiro, _, centavos = f'{v:.2f}'.partition('.')
    milhar = ''
    while len(inteiro) > 3:
        milhar = '.' + inteiro[-3:] + milhar
        inteiro = inteiro[:-3]
    return f'R$ {inteiro}{milhar},{centavos}'


def _limpa(texto: str) -> str:
    """Escapa o que quebraria a mini-marcação do reportlab.

    A descrição do produto é escrita pelo dono no painel e pode conter `<`, `&`
    ou markdown do editor. Sem escapar, um `<` derruba a geração inteira.
    """
    if not texto:
        return ''
    return (
        str(texto)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .strip()
    )


def _estilos(cor_marca):
    base = getSampleStyleSheet()
    return {
        'titulo_loja': ParagraphStyle(
            'tituloLoja', parent=base['Title'], fontSize=26, leading=30,
            textColor=cor_marca, spaceAfter=2,
        ),
        'subtitulo': ParagraphStyle(
            'subtitulo', parent=base['Normal'], fontSize=10, leading=14,
            textColor=_CINZA_CLARO, alignment=TA_CENTER, spaceAfter=2,
        ),
        'categoria': ParagraphStyle(
            'categoria', parent=base['Heading2'], fontSize=14, leading=18,
            textColor=cor_marca, spaceBefore=10, spaceAfter=4,
        ),
        'produto': ParagraphStyle(
            'produto', parent=base['Normal'], fontSize=11, leading=14,
            textColor=_CINZA_TEXTO,
        ),
        'descricao': ParagraphStyle(
            'descricao', parent=base['Normal'], fontSize=8.5, leading=11,
            textColor=_CINZA_CLARO,
        ),
        'preco': ParagraphStyle(
            'preco', parent=base['Normal'], fontSize=11, leading=14,
            textColor=_CINZA_TEXTO, alignment=2,  # direita
        ),
    }


def _logo_reader(loja):
    """A logo da loja pronta para o reportlab, ou None.

    Lê pelo storage (pode ser S3/local) e nunca deixa um arquivo faltando ou
    corrompido derrubar a geração — sem logo o cardápio ainda sai.
    """
    if not getattr(loja, 'logo', None):
        return None
    try:
        from reportlab.lib.utils import ImageReader
        import io as _io

        with loja.logo.open('rb') as f:
            dados = f.read()
        return ImageReader(_io.BytesIO(dados))
    except Exception:
        return None


def _desenha_banner(canvas, loja, cor_marca, cor_apoio, logo):
    """Banner do topo: faixa nas cores da loja com a logo centralizada."""
    largura, altura = A4
    topo = altura
    base_banner = altura - ALTURA_BANNER

    # Faixa principal na cor da marca.
    canvas.setFillColor(cor_marca)
    canvas.rect(0, base_banner, largura, ALTURA_BANNER, stroke=0, fill=1)

    # Faixa fina na cor secundária, embaixo — dá acabamento sem custar leitura.
    canvas.setFillColor(cor_apoio)
    canvas.rect(0, base_banner - 2.5 * mm, largura, 2.5 * mm, stroke=0, fill=1)

    if logo is not None:
        try:
            lw, lh = logo.getSize()
            altura_max = ALTURA_BANNER - 12 * mm
            largura_max = 62 * mm
            escala = min(largura_max / lw, altura_max / lh)
            w, h = lw * escala, lh * escala
            canvas.drawImage(
                logo,
                (largura - w) / 2,
                base_banner + (ALTURA_BANNER - h) / 2,
                width=w, height=h,
                mask='auto',           # respeita PNG transparente
                preserveAspectRatio=True,
            )
            return True
        except Exception:
            pass
    return False


def _cabecalho_rodape(loja, cor_marca, cor_apoio, logo):
    """Banner + moldura da marca + paginação, em toda página."""
    def desenha(canvas, doc):
        canvas.saveState()
        largura, altura = A4

        _desenha_banner(canvas, loja, cor_marca, cor_apoio, logo)

        # Moldura fina na cor da marca em volta do conteúdo. Duas linhas (uma
        # mais clara por dentro) dão o acabamento de cardápio impresso sem
        # pesar na tinta.
        canvas.setStrokeColor(cor_marca)
        canvas.setLineWidth(1.2)
        canvas.rect(
            MARGEM_MOLDURA,
            MARGEM_MOLDURA,
            largura - 2 * MARGEM_MOLDURA,
            altura - ALTURA_BANNER - MARGEM_MOLDURA - 4 * mm,
        )
        canvas.setStrokeColor(cor_apoio)
        canvas.setLineWidth(0.4)
        canvas.rect(
            MARGEM_MOLDURA + 1.6 * mm,
            MARGEM_MOLDURA + 1.6 * mm,
            largura - 2 * (MARGEM_MOLDURA + 1.6 * mm),
            altura - ALTURA_BANNER - MARGEM_MOLDURA - 4 * mm - 3.2 * mm,
        )

        canvas.setFillColor(_CINZA_CLARO)
        canvas.setFont('Helvetica', 7.5)
        canvas.drawCentredString(
            largura / 2, MARGEM_MOLDURA - 5 * mm,
            f'{loja.name} · página {doc.page}',
        )
        canvas.restoreState()
    return desenha


def _linha_produto(produto, estilos, largura_util):
    """Nome + descrição à esquerda, preço à direita, alinhados numa tabela."""
    nome = _limpa(produto.name)
    descricao = _limpa(produto.description)[:180]

    esquerda = [Paragraph(f'<b>{nome}</b>', estilos['produto'])]
    if descricao:
        esquerda.append(Paragraph(descricao, estilos['descricao']))

    preco_txt = _dinheiro(produto.price)
    # Produto com variação tem preço "a partir de" — dizer isso evita reclamação
    # no balcão de quem leu o menor preço e esperava pagar aquilo.
    if getattr(produto, 'has_variants', False):
        preco_txt = f'a partir de<br/>{preco_txt}'

    tabela = Table(
        [[esquerda, Paragraph(preco_txt, estilos['preco'])]],
        colWidths=[largura_util * 0.76, largura_util * 0.24],
    )
    tabela.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#EEEEEE')),
    ]))
    return tabela


def gera_cardapio_pdf(loja, categorias_com_produtos, buffer):
    """Escreve o PDF no buffer.

    `categorias_com_produtos` é uma lista de (nome_categoria, [produtos]) já
    ordenada — a view decide a ordem e o que entra (ativo, em estoque etc.).
    """
    cor_marca = _cor(loja.primary_color, '#C9A24B')
    cor_apoio = _cor(loja.secondary_color, '#8C6D3F')
    estilos = _estilos(cor_marca)
    logo = _logo_reader(loja)

    # topMargin abre espaço para o banner (desenhado por fora do fluxo, em toda
    # página); as laterais respeitam a moldura.
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM,
        topMargin=ALTURA_BANNER + 8 * mm,
        bottomMargin=MARGEM + 4 * mm,
        title=f'Cardápio · {loja.name}', author=loja.name,
    )
    largura_util = A4[0] - 2 * MARGEM

    fluxo = []
    # Com logo no banner, repetir o nome em corpo 26 seria redundante — o nome
    # vira legenda discreta. Sem logo, ele assume o papel de identificação.
    if logo is None:
        fluxo.append(Paragraph(_limpa(loja.name), estilos['titulo_loja']))

    contato = ' · '.join(filter(None, [
        _limpa(loja.phone),
        _limpa(loja.city),
    ]))
    if contato:
        fluxo.append(Paragraph(contato, estilos['subtitulo']))
    if loja.description:
        fluxo.append(Paragraph(_limpa(loja.description)[:200], estilos['subtitulo']))
    fluxo.append(Spacer(1, 5 * mm))

    if not categorias_com_produtos:
        fluxo.append(Paragraph(
            'Nenhum produto disponível no momento.', estilos['descricao']))

    for nome_categoria, produtos in categorias_com_produtos:
        if not produtos:
            continue
        bloco = [Paragraph(_limpa(nome_categoria) or 'Outros', estilos['categoria'])]
        # KeepTogether no título + primeiro item evita categoria órfã no pé da
        # página (título numa folha e produtos na seguinte).
        bloco.append(_linha_produto(produtos[0], estilos, largura_util))
        fluxo.append(KeepTogether(bloco))
        for produto in produtos[1:]:
            fluxo.append(_linha_produto(produto, estilos, largura_util))

    desenha = _cabecalho_rodape(loja, cor_marca, cor_apoio, logo)
    doc.build(fluxo, onFirstPage=desenha, onLaterPages=desenha)
    return buffer
