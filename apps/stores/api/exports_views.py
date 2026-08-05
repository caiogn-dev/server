"""
Downloads do painel: planilhas, relatórios e o cardápio em PDF.

Convenção: todo endpoint aceita `?fmt=csv|xlsx`. O CSV continua sendo o padrão — quem já tem rotina montada em cima dele não quebra; o
Excel é opção, não substituição.

O gate de tenant vem de BaseExportView: loja obrigatória, e acesso negado a loja
existente vira 404 (info-hiding).
"""
import csv
import io
from decimal import Decimal

from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework.response import Response

from ..services.exports.planilha import Coluna, resposta_xlsx
from ..services.exports.relatorios import (
    faturamento_por_dia,
    faturamento_por_entrega,
    faturamento_por_pagamento,
    resumo_faturamento,
    vendas_por_item,
)
from .export_views import BaseExportView

FORMATOS_PLANILHA = ('csv', 'xlsx')


def _formato(request) -> str:
    """csv (padrão) ou xlsx. Valor inválido cai no padrão, não em 400.

    Lê `fmt` e NÃO `format`: este último é reservado pelo DRF para content
    negotiation. Com `?format=csv` o DRF procura um renderer chamado "csv", não
    encontra e levanta Http404 ANTES de a view rodar — o endpoint respondia 404
    sem nunca ter sido executado.
    """
    pedido = (request.query_params.get('fmt') or 'csv').strip().lower()
    return pedido if pedido in FORMATOS_PLANILHA else 'csv'


def _incluir_teste(request) -> bool:
    """Por padrão pedido de teste do dono fica FORA de qualquer relatório."""
    return (request.query_params.get('include_test') or '').lower() in ('1', 'true', 'yes')


def _resposta_csv(linhas, colunas, nome_arquivo):
    """CSV com BOM e ponto-e-vírgula — o que o Excel pt-BR abre sem assistente.

    Sem o BOM, acento sai quebrado; com vírgula como separador, o Excel em
    português joga a linha inteira numa coluna só.
    """
    buffer = io.StringIO()
    buffer.write('﻿')
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow([c.titulo for c in colunas])
    for linha in linhas:
        writer.writerow([_valor_csv(c, linha) for c in colunas])
    resposta = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    resposta['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    return resposta


def _valor_csv(coluna: Coluna, linha: dict):
    valor = coluna.valor(linha)
    if valor is None:
        return ''
    if isinstance(valor, Decimal):
        # Vírgula decimal: o Excel pt-BR lê "12.50" como texto, não número.
        return f'{valor:.2f}'.replace('.', ',')
    if coluna.tipo in ('data', 'data_hora') and hasattr(valor, 'strftime'):
        fmt = '%d/%m/%Y %H:%M' if coluna.tipo == 'data_hora' else '%d/%m/%Y'
        return valor.strftime(fmt)
    if coluna.tipo == 'percentual' and isinstance(valor, (int, float)):
        return f'{valor * 100:.1f}'.replace('.', ',')
    return valor


def _entrega(linhas, colunas, base_nome, formato, titulo, subtitulo='', abas_extras=None):
    if formato == 'xlsx':
        return resposta_xlsx(
            linhas, colunas, f'{base_nome}.xlsx',
            titulo=titulo, subtitulo=subtitulo, abas_extras=abas_extras,
        )
    return _resposta_csv(linhas, colunas, f'{base_nome}.csv')


class VendasPorItemExportView(BaseExportView):
    """O que cada produto vendeu no período, do maior faturamento para o menor.

    Responde uma pergunta que o export de pedidos não responde: dá para somar
    pedidos, mas não dá para ver que 6 itens fazem 80% do caixa. A coluna de
    acumulado (curva ABC) mostra exatamente onde está esse corte.
    """

    def get(self, request):
        loja = self.get_store(request)
        if not loja:
            return Response({'error': 'Store parameter required'}, status=400)

        inicio, fim = self.get_date_range(request)
        linhas = vendas_por_item(loja, inicio, fim, incluir_teste=_incluir_teste(request))

        colunas = [
            Coluna('Produto', 'produto', largura=42),
            Coluna('Qtd vendida', 'quantidade', tipo='inteiro', somar=True),
            Coluna('Pedidos', 'pedidos', tipo='inteiro', somar=True),
            Coluna('Receita', 'receita', tipo='dinheiro', somar=True),
            Coluna('Preço médio', 'preco_medio', tipo='dinheiro'),
            Coluna('% da receita', 'part_receita', tipo='percentual'),
            Coluna('% acumulado', 'acumulado', tipo='percentual'),
        ]
        return _entrega(
            linhas, colunas,
            f'vendas-por-item_{slugify(loja.name)}_{inicio}_{fim}',
            _formato(request),
            titulo='Vendas por item',
            subtitulo=f'{loja.name} · {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} · '
                      f'exclui cancelados, estornados e pedidos de teste',
        )


class FaturamentoExportView(BaseExportView):
    """Faturamento por dia, com quebras por pagamento e por modalidade.

    Em xlsx vai em três abas; em csv sai a série diária (um CSV não comporta
    três tabelas sem virar sopa).
    """

    def get(self, request):
        loja = self.get_store(request)
        if not loja:
            return Response({'error': 'Store parameter required'}, status=400)

        inicio, fim = self.get_date_range(request)
        incluir_teste = _incluir_teste(request)
        formato = _formato(request)

        dias = faturamento_por_dia(loja, inicio, fim, incluir_teste)
        resumo = resumo_faturamento(loja, inicio, fim, incluir_teste)

        colunas_dia = [
            Coluna('Data', 'dia', tipo='data'),
            Coluna('Pedidos', 'pedidos', tipo='inteiro', somar=True),
            Coluna('Receita', 'receita', tipo='dinheiro', somar=True),
            Coluna('Ticket médio', 'ticket_medio', tipo='dinheiro'),
            Coluna('Taxa de entrega', 'entrega', tipo='dinheiro', somar=True),
            Coluna('Descontos', 'desconto', tipo='dinheiro', somar=True),
        ]

        subtitulo = (
            f'{loja.name} · {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} · '
            f'{resumo["pedidos"]} pedidos · média diária '
            f'R$ {resumo["media_diaria"]:.2f} · exclui cancelados e testes'
        )

        abas = None
        if formato == 'xlsx':
            abas = [
                (
                    'Por pagamento',
                    faturamento_por_pagamento(loja, inicio, fim, incluir_teste),
                    [
                        Coluna('Meio de pagamento', 'metodo', largura=26),
                        Coluna('Pedidos', 'pedidos', tipo='inteiro', somar=True),
                        Coluna('Receita', 'receita', tipo='dinheiro', somar=True),
                        Coluna('Participação', 'participacao', tipo='percentual'),
                    ],
                ),
                (
                    'Por modalidade',
                    faturamento_por_entrega(loja, inicio, fim, incluir_teste),
                    [
                        Coluna('Modalidade', 'modalidade', largura=26),
                        Coluna('Pedidos', 'pedidos', tipo='inteiro', somar=True),
                        Coluna('Receita', 'receita', tipo='dinheiro', somar=True),
                        Coluna('Taxa de entrega', 'taxa_entrega', tipo='dinheiro', somar=True),
                    ],
                ),
            ]

        return _entrega(
            dias, colunas_dia,
            f'faturamento_{slugify(loja.name)}_{inicio}_{fim}',
            formato,
            titulo='Faturamento',
            subtitulo=subtitulo,
            abas_extras=abas,
        )


class CardapioPdfView(BaseExportView):
    """Cardápio da loja em PDF — para imprimir ou mandar no WhatsApp.

    Sai sempre do catálogo real, então não envelhece como um PDF feito à mão.
    """

    def get(self, request):
        loja = self.get_store(request)
        if not loja:
            return Response({'error': 'Store parameter required'}, status=400)

        from ..models import StoreProduct
        from ..services.exports.cardapio_pdf import gera_cardapio_pdf

        produtos = (
            StoreProduct.objects
            .filter(store=loja, status=StoreProduct.ProductStatus.ACTIVE)
            .select_related('category')
            .order_by('category__sort_order', 'category__name', 'sort_order', 'name')
        )
        # Fora de estoque não vai para o cardápio impresso: o cliente pede e a
        # loja tem que negar no balcão. `allow_backorder` continua entrando.
        if (request.query_params.get('include_out_of_stock') or '').lower() not in ('1', 'true'):
            produtos = [p for p in produtos if p.is_in_stock]

        agrupado: list[tuple[str, list]] = []
        atual = None
        for produto in produtos:
            nome_cat = produto.category.name if produto.category else 'Outros'
            if atual is None or atual[0] != nome_cat:
                atual = (nome_cat, [])
                agrupado.append(atual)
            atual[1].append(produto)

        buffer = io.BytesIO()
        gera_cardapio_pdf(loja, agrupado, buffer)
        buffer.seek(0)

        resposta = HttpResponse(buffer.read(), content_type='application/pdf')
        # inline: abre no navegador (o dono confere antes de mandar para alguém)
        resposta['Content-Disposition'] = (
            f'inline; filename="cardapio-{slugify(loja.name)}.pdf"'
        )
        return resposta
