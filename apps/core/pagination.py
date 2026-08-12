"""
Paginação que respeita o `page_size` que o cliente pede.

O padrão do DRF (`PageNumberPagination` sem `page_size_query_param`) **ignora
em silêncio** o parâmetro. O painel pede `page_size=500` em ~30 lugares —
produtos para imprimir etiqueta, ingredientes para montar receita, clientes,
pedidos — e sempre recebeu 20, sem erro nenhum. O sintoma que apareceu foi
"só tem 1 ingrediente da TACO e 19 da POF": eram os 20 primeiros em ordem
alfabética, filtrados no navegador como se fossem a base inteira.

Silêncio é o problema: uma lista truncada parece uma lista completa e curta.

O teto existe porque `page_size` vem da URL: sem ele, `?page_size=999999`
transforma qualquer listagem em varredura de tabela.
"""
from rest_framework.pagination import PageNumberPagination


class PaginacaoPadrao(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    # Maior pedido legítimo do painel hoje é 500 (produtos e ingredientes).
    max_page_size = 500
