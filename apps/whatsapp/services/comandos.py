"""Atalhos "/" do inbox: agir no pedido sem sair da conversa.

Nasceu de uma conta de tempo. Em 13/ago o bot montou um pedido errado para a
Yeda, e consertar custou à dona **5 minutos e uma troca de tela**: cancelar o
pedido no painel, refazer o valor, copiar um link do Mercado Pago e colar no
chat — com a cliente esperando do outro lado.

Este módulo é só o INTERPRETADOR. Ele lê o texto e diz o que a pessoa quis
fazer; quem executa é a camada de ação, e quem confirma é a tela. A separação é
a mesma da triagem, e pela mesma razão: interpretar é barato e testável, agir é
irreversível.

O perigo específico desta superfície não é o comando dar errado — é o comando
não ser reconhecido e **virar mensagem enviada ao cliente**. A dona digita
`/pixx`, o sistema não entende, e a cliente recebe "/pixx". Por isso
`enviar_ao_cliente` é False até para o desconhecido: qualquer texto que comece
com barra é tentativa de comando, nunca conversa.
"""
import difflib
import re
from dataclasses import dataclass
from typing import Optional

#: Catálogo. `descricao` não é enfeite: é o que a paleta do painel mostra, e sem
#: ela o atalho vira adivinhação.
COMANDOS = {
    'pedido': {
        'descricao': 'Mostra o resumo do pedido atual do cliente',
        'confirmar': False,
    },
    'pix': {
        'descricao': 'Gera e envia o PIX do pedido atual',
        'confirmar': False,
    },
    'status': {
        'descricao': 'Mostra em que etapa o pedido está',
        'confirmar': False,
    },
    'entregue': {
        'descricao': 'Marca o pedido como entregue e avisa o cliente',
        'confirmar': True,
    },
    'cancelar': {
        'descricao': 'Cancela o pedido atual',
        'confirmar': True,
    },
    'cupom': {
        'descricao': 'Aplica um cupom ao pedido — /cupom CODIGO',
        'confirmar': False,
    },
    'nota': {
        'descricao': 'Anota um recado interno na conversa — /nota texto',
        'confirmar': False,
    },
    'bot': {
        'descricao': 'Liga ou desliga o bot nesta conversa — /bot on | off',
        'confirmar': False,
    },
}


@dataclass
class Comando:
    nome: str
    argumento: str = ''
    conhecido: bool = True
    precisa_confirmar: bool = False
    sugestao: Optional[str] = None
    #: Sempre False. Comando é instrução para o sistema, nunca texto para o
    #: cliente — nem quando o sistema não entendeu.
    enviar_ao_cliente: bool = False


def interpretar(texto: str) -> Optional[Comando]:
    """Devolve o comando, ou None quando a mensagem é conversa normal.

    Só conta barra no INÍCIO. "5/5 estrelas" e "meio/meio" são texto de gente e
    não podem virar comando — o operador digita no mesmo campo em que fala com o
    cliente.
    """
    if not texto:
        return None
    limpo = texto.strip()
    if not limpo.startswith('/'):
        return None

    corpo = limpo[1:].strip()
    if not corpo:
        return None

    partes = re.split(r'\s+', corpo, maxsplit=1)
    nome = partes[0].lower()
    argumento = partes[1].strip() if len(partes) > 1 else ''

    meta = COMANDOS.get(nome)
    if meta is None:
        return Comando(
            nome=nome,
            argumento=argumento,
            conhecido=False,
            sugestao=_parecido(nome),
        )

    return Comando(
        nome=nome,
        argumento=argumento,
        precisa_confirmar=bool(meta['confirmar']),
    )


def _parecido(nome: str) -> Optional[str]:
    """O comando mais próximo, quando existe um.

    Erro de digitação é o caso comum de quem usa atalho com pressa. Sugerir sem
    executar deixa a correção a um toque, sem risco de agir pelo palpite.
    """
    achados = difflib.get_close_matches(nome, COMANDOS.keys(), n=1, cutoff=0.6)
    return achados[0] if achados else None
