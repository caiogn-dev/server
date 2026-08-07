"""Que intervalo de tempo é esse — sempre no fuso da loja.

Janela de tempo é conceito de métrica, não utilitário genérico. Ficava
espalhada como `timezone.now().replace(hour=0, ...)` em sete lugares, e essa
linha está errada: `now()` devolve UTC, então a meia-noite resultante é 00:00
UTC — 21:00 de Brasília do dia ANTERIOR.

Efeito real no painel (06/ago/2026): todo dia às 21h o dia "virava" em UTC e o
card "Receita hoje" descartava o faturamento das 00h às 21h — justamente o pico
do delivery. Antes das 21h o erro era o oposto: colava as vendas do fim da
noite anterior no dia de hoje.

Nenhuma janela nasce de `timezone.now()` cru: `localtime()` primeiro, sempre.
Assim o bug fica impossível de reintroduzir por construção.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class Janela:
    """Intervalo fechado de dias, no fuso da loja.

    `inicio` e `fim` são DATAS, não instantes: métrica de faturamento se fala
    em dias ("hoje", "últimos 30 dias"), e trabalhar com datas elimina a classe
    inteira de erro de fuso na fronteira do dia.
    """
    inicio: date
    fim: date
    rotulo: str = ''

    @property
    def dias(self) -> int:
        """Quantidade de dias que a janela cobre (inclusive nas duas pontas)."""
        return (self.fim - self.inicio).days + 1

    def __str__(self) -> str:
        return self.rotulo or f'{self.inicio} a {self.fim}'


def agora_local() -> datetime:
    """O instante atual no fuso do projeto. Use isto, nunca `timezone.now()`."""
    return timezone.localtime(timezone.now())


def hoje_local() -> date:
    """A data de hoje no fuso da loja."""
    return agora_local().date()


def inicio_do_dia(dia: date = None) -> datetime:
    """Instante em que o dia começou, no fuso da loja.

    Substitui o `timezone.now().replace(hour=0, ...)` que estava espalhado.
    """
    dia = dia or hoje_local()
    return timezone.make_aware(
        datetime(dia.year, dia.month, dia.day),
        timezone.get_current_timezone(),
    )


def hoje() -> Janela:
    d = hoje_local()
    return Janela(inicio=d, fim=d, rotulo='hoje')


def ontem() -> Janela:
    d = hoje_local() - timedelta(days=1)
    return Janela(inicio=d, fim=d, rotulo='ontem')


def ultimos_dias(n: int) -> Janela:
    """Os últimos `n` dias, incluindo hoje.

    `ultimos_dias(7)` = hoje e os 6 anteriores. Contar 7 dias para trás A PARTIR
    de hoje daria 8 dias no total — erro clássico em comparativo de semana.
    """
    if n < 1:
        raise ValueError('a janela precisa de pelo menos 1 dia')
    fim = hoje_local()
    return Janela(inicio=fim - timedelta(days=n - 1), fim=fim, rotulo=f'últimos {n} dias')


def mes_corrente() -> Janela:
    fim = hoje_local()
    return Janela(inicio=fim.replace(day=1), fim=fim, rotulo='mês corrente')


def janela_anterior(janela: Janela) -> Janela:
    """A janela imediatamente anterior, do mesmo tamanho.

    Para comparativo honesto: "últimos 7 dias" contra "os 7 dias antes desses",
    e não contra um período de tamanho diferente.
    """
    dias = janela.dias
    fim = janela.inicio - timedelta(days=1)
    return Janela(
        inicio=fim - timedelta(days=dias - 1),
        fim=fim,
        rotulo=f'{dias} dias anteriores',
    )


def de_datas(inicio, fim, rotulo: str = '') -> Janela:
    """Janela a partir de datas cruas (query params, filtros do painel)."""
    if isinstance(inicio, datetime):
        inicio = timezone.localtime(inicio).date() if timezone.is_aware(inicio) else inicio.date()
    if isinstance(fim, datetime):
        fim = timezone.localtime(fim).date() if timezone.is_aware(fim) else fim.date()
    if inicio > fim:
        inicio, fim = fim, inicio
    return Janela(inicio=inicio, fim=fim, rotulo=rotulo)
