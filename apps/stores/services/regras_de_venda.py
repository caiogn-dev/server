"""
Regras de venda do produto: quando vende, como sai e quanto por pedido.

Tirado do admin do Prefiro, onde o lojista marca "almoço só das 11h às 15h",
"feijoada só sábado", "bolo inteiro só retirada" e "mínimo 10 salgados".
Sem isto o dono desativava o item à mão todo dia e esquecia de reativar.

Formato em `StoreProduct.regras_de_venda` (tudo opcional; {} = sem regra):
    {
        'dias': [0, 1, 2, 3, 4],      # weekday() do Python; vazio = todo dia
        'de': '11:00', 'ate': '15:00',  # janela do dia; os dois ou nenhum
        'so_retirada': True,
        'minimo': 10, 'maximo': 50,    # unidades do item por pedido
    }

A vitrine recebe as regras e desenha o aviso (o catálogo dela é cacheado, não
pode esconder por horário). Quem DECIDE é o servidor: `disponiveis()` para o
bot, `erros_do_carrinho()` para o checkout.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from django.db.models import Q

HORA = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
DIAS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']


class RegraInvalida(ValueError):
    pass


def normalizar(dados) -> dict:
    """Valida o que o painel mandou e devolve só as chaves com efeito."""
    if not dados:
        return {}
    if not isinstance(dados, dict):
        raise RegraInvalida('Regras de venda em formato inválido.')
    limpo: dict = {}

    dias = dados.get('dias') or []
    if not isinstance(dias, list) or any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in dias):
        raise RegraInvalida('Dias da semana inválidos.')
    if dias and len(set(dias)) < 7:
        limpo['dias'] = sorted(set(dias))

    de, ate = (dados.get('de') or '').strip(), (dados.get('ate') or '').strip()
    if de or ate:
        if not (HORA.match(de) and HORA.match(ate)):
            raise RegraInvalida('Use horário no formato 11:00, com início e fim.')
        if de == ate:
            raise RegraInvalida('O horário de início e o de fim são iguais.')
        if de > ate:
            raise RegraInvalida('A janela de venda não pode virar a meia-noite.')
        limpo['de'], limpo['ate'] = de, ate

    if dados.get('so_retirada') is True:
        limpo['so_retirada'] = True

    minimo, maximo = dados.get('minimo'), dados.get('maximo')
    for nome, v in (('mínima', minimo), ('máxima', maximo)):
        if v not in (None, '') and (not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > 999):
            raise RegraInvalida(f'Quantidade {nome} deve ser um número de 1 a 999.')
    if minimo and minimo > 1:
        limpo['minimo'] = minimo
    if maximo:
        limpo['maximo'] = maximo
    if minimo and maximo and minimo > maximo:
        raise RegraInvalida('A quantidade mínima não pode passar da máxima.')
    return limpo


def vende_agora(regras: dict | None, agora: datetime) -> bool:
    regras = regras or {}
    dias = regras.get('dias')
    if dias and agora.weekday() not in dias:
        return False
    de, ate = regras.get('de'), regras.get('ate')
    if de and ate:
        hhmm = agora.strftime('%H:%M')
        return de <= hhmm < ate
    return True


def filtro_vende_agora(agora: datetime) -> Q:
    """`vende_agora` em SQL (jsonb), para `StoreProduct.disponiveis()`.

    Horário guardado como 'HH:MM' compara certo como texto — por isso o
    formato é validado com zero à esquerda.
    """
    hhmm = agora.strftime('%H:%M')
    no_dia = (
        Q(regras_de_venda__dias__isnull=True)
        | Q(regras_de_venda__dias=[])
        | Q(regras_de_venda__dias__contains=[agora.weekday()])
    )
    na_hora = Q(regras_de_venda__de__isnull=True) | Q(
        regras_de_venda__de__lte=hhmm, regras_de_venda__ate__gt=hhmm,
    )
    return no_dia & na_hora


def quando_vende(regras: dict | None) -> str:
    """'sábado e domingo, das 11:00 às 15:00' — para a mensagem de recusa."""
    regras = regras or {}
    partes = []
    dias = regras.get('dias')
    if dias:
        nomes = [DIAS[d] for d in dias]
        partes.append(nomes[0] if len(nomes) == 1 else ', '.join(nomes[:-1]) + ' e ' + nomes[-1])
    if regras.get('de'):
        partes.append(f"das {regras['de']} às {regras['ate']}")
    return ', '.join(partes)


def erros_do_carrinho(itens: Iterable[tuple], metodo: str, agora: datetime) -> list[str]:
    """`itens` = (produto, quantidade). Uma frase por problema, para o cliente."""
    erros: list[str] = []
    for produto, quantidade in itens:
        regras = getattr(produto, 'regras_de_venda', None) or {}
        if not regras:
            continue
        nome = produto.name
        if not vende_agora(regras, agora):
            erros.append(f'{nome} só é vendido {quando_vende(regras)}.')
        if regras.get('so_retirada') and metodo == 'delivery':
            erros.append(f'{nome} é só para retirada na loja.')
        if regras.get('minimo') and quantidade < regras['minimo']:
            erros.append(f"{nome}: o mínimo é {regras['minimo']} unidades.")
        if regras.get('maximo') and quantidade > regras['maximo']:
            erros.append(f"{nome}: o máximo é {regras['maximo']} unidades por pedido.")
    return erros
