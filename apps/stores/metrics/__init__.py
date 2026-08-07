"""Núcleo de métricas — a fonte de verdade única sobre faturamento.

Toda tela, relatório e export que fale de DINHEIRO importa daqui. Nenhuma view
deve conter `Sum('total')`, `payment_status='paid'` ou cálculo de início de dia:
se precisar de um número novo, o número nasce aqui.

    from apps.stores import metrics

    janela = metrics.hoje()
    total = metrics.totais(loja, janela)['receita']
    grafico = metrics.serie_completa(loja, metrics.ultimos_dias(30))

Três responsabilidades, três módulos:

- `definicoes`  o que conta como receita, e por qual data
- `janelas`     que intervalo é esse, sempre no fuso da loja
- `series`      como isso se distribui no tempo e entre produtos

Por que existe: seis arquivos calculavam faturamento por conta própria e
davam respostas diferentes para o mesmo dia. O card da home chegou a mostrar
mais que o dobro da receita real, e depois das 21h mostrava quase zero. O
histórico completo está em `docs/superpowers/specs/2026-08-06-nucleo-de-metricas-design.md`.
"""
from .definicoes import (
    FLAG_PEDIDO_TESTE,
    STATUS_SEM_RECEITA,
    apenas_receita,
    eh_pedido_de_teste,
    eixo_de_receita,
    itens_de_receita,
    marcar_como_teste,
    pedidos_de_receita,
)
from .janelas import (
    Janela,
    agora_local,
    de_datas,
    hoje,
    hoje_local,
    inicio_do_dia,
    janela_anterior,
    mes_corrente,
    ontem,
    ultimos_dias,
)
from .series import (
    comparar_periodo,
    contagem_operacional,
    serie_completa,
    serie_temporal,
    top_produtos,
    totais,
)

__all__ = [
    # definições
    'FLAG_PEDIDO_TESTE',
    'STATUS_SEM_RECEITA',
    'apenas_receita',
    'eh_pedido_de_teste',
    'eixo_de_receita',
    'itens_de_receita',
    'marcar_como_teste',
    'pedidos_de_receita',
    # janelas
    'Janela',
    'agora_local',
    'de_datas',
    'hoje',
    'hoje_local',
    'inicio_do_dia',
    'janela_anterior',
    'mes_corrente',
    'ontem',
    'ultimos_dias',
    # séries
    'comparar_periodo',
    'contagem_operacional',
    'serie_completa',
    'serie_temporal',
    'top_produtos',
    'totais',
]
