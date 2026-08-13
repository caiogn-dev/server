"""Casar um texto livre com um produto ou combo do catálogo da loja.

Fonte única. O mesmo casamento já existia dentro de
`apps/agents/services/langchain_service.py` como método privado da classe, e
qualquer outro lugar que precisasse dele teria de escrever a sua própria versão
— que é exatamente como o bypass do modo humano e o remetente de e-mail
divergiram nesta mesma semana.

Empate resolve pelo nome mais curto: "Molho" ganha de "Molho Especial da Casa"
quando o cliente escreve "molho".
"""
import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculo, sem acento e sem pontuação — só para comparar."""
    texto = unicodedata.normalize('NFD', str(texto or ''))
    texto = texto.encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9 ]+', ' ', texto.lower()).strip()


def _melhor(candidatos, alvo, nome_de):
    if not candidatos:
        return None
    return sorted(
        candidatos,
        key=lambda o: (normalizar(nome_de(o)) != alvo, len(nome_de(o))),
    )[0]


def casar_produto(store, texto: str):
    """Produto ativo desta loja cujo nome aparece no texto (ou vice-versa)."""
    from apps.stores.models import StoreProduct

    alvo = normalizar(texto)
    if not alvo:
        return None
    candidatos = [
        p for p in StoreProduct.objects.filter(store=store, is_active=True)
        if _casa(alvo, normalizar(p.name))
    ]
    return _melhor(candidatos, alvo, lambda p: p.name)


def casar_combo(store, texto: str):
    from apps.stores.models import StoreCombo

    alvo = normalizar(texto)
    if not alvo:
        return None
    candidatos = [
        c for c in StoreCombo.objects.filter(store=store, is_active=True)
        if _casa(alvo, normalizar(c.name))
    ]
    return _melhor(candidatos, alvo, lambda c: c.name)


def _casa(alvo: str, nome: str) -> bool:
    """O texto contém o nome, ou o nome contém o texto.

    As duas direções importam: "Suco de laranja 400ml" (o cliente copiou o nome
    inteiro) e "quero salada" (o cliente disse uma palavra que está no nome).

    Palavra de uma letra ou duas não casa nada — "de", "e", "ml" fariam meio
    catálogo casar com qualquer frase.
    """
    if not alvo or not nome:
        return False
    if nome in alvo or alvo in nome:
        return True
    palavras_do_nome = {p for p in nome.split() if len(p) > 2}
    palavras_do_alvo = {p for p in alvo.split() if len(p) > 2}
    return bool(palavras_do_nome & palavras_do_alvo)


#: Marcas de negação. Quem escreve "sem cebola" está TIRANDO, não pedindo.
#:
#: Sem isto o casamento vira uma armadilha em loja que vende ingrediente avulso:
#: a Cê Saladas tem "Cebola roxa" no catálogo, então "sem cebola" — o exemplo
#: que o próprio bot dá ao pedir observação — casaria com produto e deixaria de
#: ser anotado.
_NEGACOES = (
    'sem ', 'tirar', 'retirar', 'tira ', 'nao quero', 'não quero',
    'nada de', 'menos ', 'exceto', 'fora ', 'nao coloca', 'não coloca',
    'nao ponha', 'sem o ', 'sem a ',
)


def tem_negacao(texto: str) -> bool:
    alvo = normalizar(texto)
    return any(n.strip() in f' {alvo} ' for n in _NEGACOES)


def parece_pedido_de_produto(store, texto: str):
    """Devolve o produto/combo quando o texto NOMEIA algo do catálogo.

    Existe por causa da conversa da Yeda (13/ago): no estado de observação, ela
    escreveu "Quero salada" e o bot respondeu "✅ Anotado: Quero salada",
    fechando um pedido de R$ 20 quando o real era R$ 100. Pedir produto não é
    observação.
    """
    if not store or not (texto or '').strip():
        return None
    if tem_negacao(texto):
        return None
    return casar_produto(store, texto) or casar_combo(store, texto)
