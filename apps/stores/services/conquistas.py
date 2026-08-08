"""Conquistas e metas de faturamento.

A DECISÃO QUE DEFINE ESTE MÓDULO: marco é DERIVADO, nunca armazenado.

Uma conquista não é um registro — é um fato sobre o histórico. "R$ 10 mil
faturados" aconteceu no dia em que a receita acumulada cruzou dez mil, e isso
se calcula a partir dos pedidos.

Guardar numa tabela parece mais simples e é pior. Pedido cancelado depois de
pago, reembolso, restauração de backup: qualquer um muda o acumulado, e a
conquista gravada passa a mentir. É exatamente o defeito de
`StoreCustomer.total_spent`, onde 12 de 78 clientes tinham valor errado por
contador denormalizado que ninguém reconcilia.

Derivando, a conquista some sozinha se o faturamento que a sustentava sumiu.

O custo é uma varredura dos pedidos da loja por consulta. Aceitável: são
milhares de linhas, não milhões, e a página é aberta por vontade, não a cada
carregamento do painel.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Sum
from django.utils import timezone

from ..metrics import (
    de_datas,
    eixo_de_receita,
    hoje_local,
    mes_corrente,
    pedidos_de_receita,
    totais,
)

ZERO = Decimal('0')

# Escala de marcos.
#
# Cresce em passos que o dono reconhece — mil, cinco mil, dez mil — e não em
# múltiplos matemáticos. Marco existe para ser comemorado; "R$ 32.768" não
# comemora ninguém.
#
# Os saltos aumentam junto com o negócio: quem fatura 500 mil não celebra mais
# de dez em dez mil, senão a conquista vira ruído mensal.
MARCOS = [
    Decimal(v) for v in (
        1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 150_000, 200_000,
        250_000, 300_000, 400_000, 500_000, 750_000,
        1_000_000, 1_500_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000,
    )
]

# Crescimento padrão da meta anual automática.
CRESCIMENTO_META_ANUAL_PCT = 20

# Janela usada para estimar o ritmo. 30 dias absorve a variação de fim de
# semana sem carregar um mês ruim de três meses atrás.
DIAS_DE_RITMO = 30


def _rotulo(valor: Decimal) -> str:
    """R$ 10 mil, R$ 1,5 milhão — como o dono fala, não como o banco grava."""
    if valor >= 1_000_000:
        n = valor / Decimal('1000000')
        txt = f'{n:.1f}'.replace('.0', '').replace('.', ',')
        return f'R$ {txt} {"milhão" if n == 1 else "milhões"}'
    n = valor / Decimal('1000')
    txt = f'{n:.0f}'
    return f'R$ {txt} mil'


def _pedidos_ordenados(loja):
    """Pedidos que contam como receita, do mais antigo para o mais novo."""
    return (
        pedidos_de_receita(loja)
        .annotate(_quando=eixo_de_receita())
        .order_by('_quando')
        .values_list('_quando', 'total')
    )


def conquistas_alcancadas(loja) -> list:
    """Marcos já batidos, do mais recente para o mais antigo.

    A ordem importa: a lista é uma linha do tempo lida de cima para baixo, e o
    que acabou de acontecer vem primeiro. Ordem crescente enterraria a
    conquista nova sob dez antigas.
    """
    linhas = list(_pedidos_ordenados(loja))
    if not linhas:
        return []

    alcancadas = []
    acumulado = ZERO
    proximo = 0

    primeiro_quando, primeiro_total = linhas[0]
    alcancadas.append({
        'chave': 'primeira_venda',
        'titulo': 'Primeira venda',
        'descricao': 'Sua loja registrou a primeira venda no canal próprio.',
        'valor': None,
        'alcancado_em': primeiro_quando.astimezone().date(),
        'faturamento_no_marco': Decimal(primeiro_total or 0),
    })

    for quando, total in linhas:
        acumulado += Decimal(total or 0)
        # `while` e não `if`: um pedido grande pode cruzar dois marcos de uma
        # vez, e pular um deixaria buraco na linha do tempo.
        while proximo < len(MARCOS) and acumulado >= MARCOS[proximo]:
            marco = MARCOS[proximo]
            alcancadas.append({
                'chave': f'faturamento_{int(marco)}',
                'titulo': f'{_rotulo(marco)} faturados',
                'descricao': f'Faturamento acumulado de {_rotulo(marco)} no canal próprio.',
                'valor': marco,
                'alcancado_em': quando.astimezone().date(),
                'faturamento_no_marco': acumulado,
            })
            proximo += 1

    alcancadas.reverse()
    return alcancadas


def _ritmo_diario(loja) -> Decimal:
    """Receita média por dia nos últimos 30 dias."""
    fim = hoje_local()
    janela = de_datas(fim - timedelta(days=DIAS_DE_RITMO - 1), fim)
    receita = totais(loja, janela)['receita']
    return (receita / Decimal(DIAS_DE_RITMO)) if receita > 0 else ZERO


def proxima_conquista(loja) -> Optional[dict]:
    """O próximo marco, quanto falta e em quanto tempo — se der para estimar."""
    acumulado = pedidos_de_receita(loja).aggregate(t=Sum('total'))['t'] or ZERO

    if acumulado <= 0:
        # "Sua primeira venda" é objetivo melhor que "R$ 1.000" para quem ainda
        # não vendeu: o segundo parece inalcançável e desliga em vez de puxar.
        return {
            'chave': 'primeira_venda',
            'titulo': 'Primeira venda',
            'descricao': 'O primeiro pedido pago da sua loja.',
            'valor': None,
            'acumulado': ZERO,
            'falta': None,
            'progresso_pct': 0,
            'dias_estimados': None,
            'prazo_estimado': None,
        }

    marco = next((m for m in MARCOS if m > acumulado), None)
    if marco is None:
        # Acima do último marco da escala: "não há próximo" é a resposta certa.
        # Inventar um seria prometer conquista que ninguém desenhou.
        return None

    anterior = next((m for m in reversed(MARCOS) if m <= acumulado), ZERO)
    falta = marco - acumulado
    faixa = marco - anterior
    progresso = float((acumulado - anterior) / faixa * 100) if faixa > 0 else 0.0

    ritmo = _ritmo_diario(loja)
    if ritmo > 0:
        dias = int((falta / ritmo).to_integral_value(rounding='ROUND_CEILING'))
        prazo = hoje_local() + timedelta(days=dias)
    else:
        # Loja parada: dividir por zero daria infinito, e data chutada é pior
        # que nenhuma — o dono planeja em cima dela.
        dias, prazo = None, None

    return {
        'chave': f'faturamento_{int(marco)}',
        'titulo': f'{_rotulo(marco)} faturados',
        'descricao': f'Próximo marco: {_rotulo(marco)} acumulados.',
        'valor': marco,
        'acumulado': acumulado,
        'falta': falta,
        'progresso_pct': round(progresso, 1),
        'dias_estimados': dias,
        'prazo_estimado': prazo,
    }


def _variacao(atual: Decimal, anterior: Decimal) -> Optional[float]:
    """Percentual de variação, ou None quando não há base.

    Sair de zero não é "+100%": é uma conta que não existe. Mostrar número ali
    dá uma precisão que o dado não tem — o mesmo cuidado que já está no
    comparativo dos KPIs.
    """
    if anterior <= 0:
        return None
    return round(float((atual - anterior) / anterior * 100), 1)


def resumo_de_metas(loja) -> dict:
    """Faturamento do mês e do ano, crescimento e a meta anual automática."""
    hoje = hoje_local()

    mes = totais(loja, mes_corrente())['receita']
    primeiro_do_mes = hoje.replace(day=1)
    fim_mes_passado = primeiro_do_mes - timedelta(days=1)
    mes_passado = totais(
        loja, de_datas(fim_mes_passado.replace(day=1), fim_mes_passado)
    )['receita']

    ano = totais(loja, de_datas(hoje.replace(month=1, day=1), hoje))['receita']
    ano_passado = totais(
        loja,
        de_datas(
            hoje.replace(year=hoje.year - 1, month=1, day=1),
            hoje.replace(year=hoje.year - 1, month=12, day=31),
        ),
    )['receita']

    # Meta anual automática: ano anterior + 20%. Sem ano anterior não há base
    # para uma meta honesta, e a tela diz isso em vez de inventar um alvo.
    alvo = (
        (ano_passado * (100 + CRESCIMENTO_META_ANUAL_PCT) / 100).quantize(Decimal('0.01'))
        if ano_passado > 0
        else None
    )

    return {
        'mes_atual': mes,
        'mes_anterior': mes_passado,
        'crescimento_mensal_pct': _variacao(mes, mes_passado),
        'ano_atual': ano,
        'ano_anterior': ano_passado,
        'crescimento_anual_pct': _variacao(ano, ano_passado),
        'meta_anual': {
            'ano': hoje.year,
            'alvo': alvo,
            'realizado': ano,
            'base': ano_passado,
            'crescimento_pct': CRESCIMENTO_META_ANUAL_PCT,
            'progresso_pct': (
                round(float(ano / alvo * 100), 1) if alvo and alvo > 0 else None
            ),
            'falta': (alvo - ano) if alvo and alvo > ano else None,
        },
    }


def painel_de_conquistas(loja) -> dict:
    """Tudo que a página precisa, numa chamada."""
    return {
        'resumo': resumo_de_metas(loja),
        'proxima': proxima_conquista(loja),
        'conquistas': conquistas_alcancadas(loja),
    }
