"""Os vigias que existem, como o painel os mostra. Uma lista só para API e tela."""

CATALOGO = (
    {'tipo': 'resumo', 'nome': 'Resumo do dia', 'icone': 'sunrise', 'quando': 'Toda manhã',
     'exemplo': 'Ontem: 18 pedidos, R$ 1.020,00 — 12% acima da média das últimas 4 quintas. '
                'Mais vendido: Queridinha (7).'},
    {'tipo': 'sem_pedido', 'nome': 'Nenhum pedido até o almoço', 'icone': 'bell-off', 'quando': 'Só se acontecer',
     'exemplo': 'Até 12:30 nenhum pedido hoje. Nas últimas 4 quintas, a essa hora já eram 5 em média.'},
    {'tipo': 'sabor_em_queda', 'nome': 'Sabor em queda', 'icone': 'trending-down', 'quando': 'Só se acontecer',
     'exemplo': 'Almôndega Premium: 3 vendidas nos últimos 5 dias abertos; o normal seria ~9 (−67%).'},
    {'tipo': 'fiel_sumiu', 'nome': 'Cliente frequente sumiu', 'icone': 'user-x', 'quando': 'Uma vez por semana',
     'exemplo': '2 clientes que pediam com frequência sumiram: Raquel (pedia a cada 7 dias, há 19 sem pedir).'},
    {'tipo': 'margem_baixa', 'nome': 'Margem baixa', 'icone': 'percent', 'quando': 'Uma vez por semana',
     'exemplo': 'Magnífico Camarão: margem de 28% na semana (custo R$ 25,00 para preço médio R$ 34,90).'},
    {'tipo': 'sem_custo', 'nome': 'Sabor sem custo', 'icone': 'circle-dollar-sign', 'quando': 'Uma vez por semana',
     'exemplo': '2 itens vendidos na semana sem custo cadastrado (19% da receita): Tilápia, Almôndega.'},
)

TIPOS = frozenset(item['tipo'] for item in CATALOGO)
