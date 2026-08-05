"""
Planilhas que o dono abre no Excel e entende sem precisar formatar nada.

O export era CSV cru: sem tipo, sem moeda, número com ponto decimal que o Excel
pt-BR lê como texto, e a primeira linha rolando junto com os dados. Aqui a
planilha sai pronta — cabeçalho fixo, filtro, moeda em R$, coluna dimensionada e
linha de totais.

Uso:
    colunas = [
        Coluna('Pedido', 'numero'),
        Coluna('Data', 'data', tipo='data'),
        Coluna('Total', 'total', tipo='dinheiro', somar=True),
    ]
    return resposta_xlsx(linhas, colunas, 'pedidos.xlsx', titulo='Pedidos')
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

from django.http import HttpResponse

# Formatos numéricos do Excel. O ponto-e-vírgula separa positivo;negativo.
FORMATO_DINHEIRO = 'R$ #,##0.00'
FORMATO_INTEIRO = '#,##0'
FORMATO_DECIMAL = '#,##0.00'
FORMATO_PERCENTUAL = '0.0%'
FORMATO_DATA = 'dd/mm/yyyy'
FORMATO_DATA_HORA = 'dd/mm/yyyy hh:mm'

_LARGURA_MIN = 10
_LARGURA_MAX = 60

CONTENT_TYPE_XLSX = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


@dataclass
class Coluna:
    """Uma coluna da planilha.

    `origem` é o nome da chave no dict da linha, ou um callable que recebe a
    linha inteira — útil quando o valor é derivado (ex.: juntar itens do pedido).
    `somar=True` faz a coluna entrar na linha de totais do rodapé.
    """

    titulo: str
    origem: Any  # str (chave) ou Callable[[dict], Any]
    tipo: str = 'texto'  # texto | dinheiro | inteiro | decimal | percentual | data | data_hora
    somar: bool = False
    largura: Optional[int] = None

    def valor(self, linha: dict) -> Any:
        if callable(self.origem):
            return self.origem(linha)
        return linha.get(self.origem)


_FORMATO_POR_TIPO = {
    'dinheiro': FORMATO_DINHEIRO,
    'inteiro': FORMATO_INTEIRO,
    'decimal': FORMATO_DECIMAL,
    'percentual': FORMATO_PERCENTUAL,
    'data': FORMATO_DATA,
    'data_hora': FORMATO_DATA_HORA,
}

_TIPOS_NUMERICOS = {'dinheiro', 'inteiro', 'decimal', 'percentual'}


def _normaliza(valor: Any, tipo: str) -> Any:
    """Converte para um tipo que o Excel entende como número/data, não texto."""
    if valor is None:
        return 0 if tipo in _TIPOS_NUMERICOS else ''
    if tipo in _TIPOS_NUMERICOS:
        if isinstance(valor, Decimal):
            return float(valor)
        if isinstance(valor, (int, float)):
            return valor
        try:
            return float(valor)
        except (TypeError, ValueError):
            return 0
    if tipo in ('data', 'data_hora'):
        if isinstance(valor, datetime):
            # openpyxl não serializa datetime com tzinfo.
            return valor.replace(tzinfo=None) if valor.tzinfo else valor
        if isinstance(valor, date):
            return valor
        return str(valor)
    return '' if valor is None else str(valor)


def monta_planilha(
    linhas: Iterable[dict],
    colunas: list[Coluna],
    titulo: str = 'Dados',
    subtitulo: str = '',
):
    """Monta o Workbook. Separado da resposta HTTP para poder ser testado."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31] or 'Dados'  # limite do Excel

    linha_atual = 1
    if subtitulo:
        ws.cell(row=1, column=1, value=subtitulo).font = Font(size=10, italic=True, color='666666')
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(colunas), 1))
        linha_atual = 3

    linha_cabecalho = linha_atual
    fundo = PatternFill('solid', start_color='1F1A15')  # carvão da marca
    fonte_cabecalho = Font(bold=True, color='C9A24B', size=11)  # dourado
    borda_fina = Side(style='thin', color='D9D9D9')

    for i, col in enumerate(colunas, start=1):
        c = ws.cell(row=linha_cabecalho, column=i, value=col.titulo)
        c.fill = fundo
        c.font = fonte_cabecalho
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    larguras = [len(c.titulo) + 4 for c in colunas]
    totais = {i: 0.0 for i, c in enumerate(colunas, start=1) if c.somar}

    r = linha_cabecalho
    for linha in linhas:
        r += 1
        for i, col in enumerate(colunas, start=1):
            bruto = _normaliza(col.valor(linha), col.tipo)
            celula = ws.cell(row=r, column=i, value=bruto)
            fmt = _FORMATO_POR_TIPO.get(col.tipo)
            if fmt:
                celula.number_format = fmt
            celula.border = Border(bottom=borda_fina)
            if col.somar and isinstance(bruto, (int, float)):
                totais[i] += bruto
            largura_valor = len(str(bruto)) + 4 if bruto is not None else 0
            if largura_valor > larguras[i - 1]:
                larguras[i - 1] = largura_valor

    ultima_linha_dados = r
    tem_dados = ultima_linha_dados > linha_cabecalho

    # Rodapé de totais — o número que o dono procura primeiro.
    if tem_dados and totais:
        r += 1
        rotulo = ws.cell(row=r, column=1, value='TOTAL')
        rotulo.font = Font(bold=True)
        for i, col in enumerate(colunas, start=1):
            if i in totais:
                c = ws.cell(row=r, column=i, value=totais[i])
                c.font = Font(bold=True)
                fmt = _FORMATO_POR_TIPO.get(col.tipo)
                if fmt:
                    c.number_format = fmt

    for i, col in enumerate(colunas, start=1):
        largura = col.largura or min(max(larguras[i - 1], _LARGURA_MIN), _LARGURA_MAX)
        ws.column_dimensions[get_column_letter(i)].width = largura

    # Cabeçalho fixo ao rolar + filtro por coluna. É o que transforma um dump
    # numa planilha utilizável de verdade.
    ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=1)
    if tem_dados:
        ws.auto_filter.ref = (
            f'A{linha_cabecalho}:'
            f'{get_column_letter(len(colunas))}{ultima_linha_dados}'
        )
    ws.sheet_view.showGridLines = False
    return wb


def resposta_xlsx(
    linhas: Iterable[dict],
    colunas: list[Coluna],
    nome_arquivo: str,
    titulo: str = 'Dados',
    subtitulo: str = '',
    abas_extras: Optional[list[tuple[str, Iterable[dict], list[Coluna]]]] = None,
) -> HttpResponse:
    """Workbook pronto como download. `abas_extras` acrescenta outras planilhas."""
    import io

    wb = monta_planilha(linhas, colunas, titulo=titulo, subtitulo=subtitulo)

    if abas_extras:
        for nome_aba, linhas_extra, colunas_extra in abas_extras:
            _acrescenta_aba(wb, nome_aba, linhas_extra, colunas_extra)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resposta = HttpResponse(buffer.read(), content_type=CONTENT_TYPE_XLSX)
    resposta['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    return resposta


def _acrescenta_aba(wb, nome: str, linhas: Iterable[dict], colunas: list[Coluna]) -> None:
    """Copia uma aba montada por monta_planilha para o workbook destino."""
    origem = monta_planilha(linhas, colunas, titulo=nome).active
    destino = wb.create_sheet(title=nome[:31])
    for linha in origem.iter_rows():
        for celula in linha:
            nova = destino.cell(row=celula.row, column=celula.column, value=celula.value)
            if celula.has_style:
                nova.number_format = celula.number_format
                nova.font = celula.font.copy()
                nova.fill = celula.fill.copy()
                nova.alignment = celula.alignment.copy()
    for chave, dim in origem.column_dimensions.items():
        destino.column_dimensions[chave].width = dim.width
    destino.freeze_panes = origem.freeze_panes
    destino.sheet_view.showGridLines = False
