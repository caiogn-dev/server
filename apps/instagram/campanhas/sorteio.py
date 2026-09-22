"""Sorteia ganhadores entre quem entrou valendo.

Atenção do dono: sorteio com prêmio no Brasil precisa de autorização (Lei
5.768/71). Sem autorização, a promoção tem de ser de mérito — concurso
cultural — ou cupom para todo mundo que participou.
"""
import secrets
from typing import List

from django.utils import timezone


def elegiveis(campanha):
    return campanha.participacoes.filter(aceita=True, ganhador=False)


def sortear(campanha, quantidade: int = 1) -> List:
    """Escolhe `quantidade` participações, marca como ganhadoras e devolve.

    Quem já ganhou não volta ao pote: a loja pode sortear em rodadas.
    """
    pote = list(elegiveis(campanha))
    if not pote:
        return []

    escolhidos = []
    for _ in range(min(quantidade, len(pote))):
        escolhidos.append(pote.pop(secrets.randbelow(len(pote))))

    agora = timezone.now()
    for p in escolhidos:
        p.ganhador = True
        p.sorteado_em = agora
        p.save(update_fields=['ganhador', 'sorteado_em'])
    return escolhidos
