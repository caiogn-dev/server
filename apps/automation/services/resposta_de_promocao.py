"""Resposta fixa para "tem promoção?", usada quando a IA não responde.

06/10: "qual a promoção do dia?", "Hoje tem promoção de quê?" e "Terça tem
promoção de salada?" receberam "Como posso te ajudar? 👇" — a promoção só
existia no contexto da IA, e a IA estava fora (503). O dado mora no banco.
"""
import re
import unicodedata
from datetime import timedelta
from typing import Optional

from apps.campaigns.services.promo_do_dia import DIAS_PT, fuso, ofertas

_PERGUNTA = re.compile(r'\b(promo\w*|oferta\w*|desconto\w*)\b')
_DIAS = {
    'segunda': 0, 'terca': 1, 'quarta': 2, 'quinta': 3, 'sexta': 4, 'sabado': 5, 'domingo': 6,
}


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize('NFD', (texto or '').lower())
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn')


def _dia_pedido(texto: str, hoje: int) -> tuple:
    """(weekday, rótulo) do dia que o cliente perguntou; hoje quando não diz."""
    if 'amanha' in texto:
        dia = (hoje + 1) % 7
        return dia, f'Amanhã ({DIAS_PT[dia].lower()})'
    for nome, numero in _DIAS.items():
        if re.search(rf'\b{nome}\b', texto):
            return numero, ('Hoje' if numero == hoje else DIAS_PT[numero].capitalize())
    return hoje, f'Hoje ({DIAS_PT[hoje].lower()})'


def responder_promocao(store, mensagem: str, agora) -> Optional[str]:
    """Texto com as promoções do dia perguntado; None se a mensagem não é sobre promoção."""
    texto = _sem_acento(mensagem)
    if not _PERGUNTA.search(texto):
        return None

    from apps.agents.services.contexto_da_loja import link_do_cardapio

    hoje = agora.astimezone(fuso(store)).weekday()
    dia, rotulo = _dia_pedido(texto, hoje)
    itens = ofertas(store, dia)
    if itens:
        linhas = "\n".join(f"• {o['nome']} — de ~{o['de']}~ por *{o['preco']}*" for o in itens)
        return f"🔥 *{rotulo}:*\n{linhas}\n\nPeça pelo cardápio: {link_do_cardapio(store)}"

    outros = []
    for d in range(7):
        if d == dia:
            continue
        do_dia = ofertas(store, d)
        if do_dia:
            outros.append(f"• {DIAS_PT[d].capitalize()}: " + ", ".join(f"{o['nome']} {o['preco']}" for o in do_dia))
    if not outros:
        return "No momento não temos promoção cadastrada. 🙂 Quer ver o cardápio?"
    return (
        f"{rotulo} não tem promoção do dia. 😕\n\nNos outros dias:\n"
        + "\n".join(outros)
    )
