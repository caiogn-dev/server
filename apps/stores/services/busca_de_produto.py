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
        p for p in StoreProduct.disponiveis(store)
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


def _raiz(palavra: str) -> str:
    """Plural cru do português: 'batatas' e 'batata' têm que casar.

    Não é stemmer de verdade e nem tenta ser — 'ões'/'ães' ficam de fora. Existe
    porque "Batatas" não achava "Batata rústica" e virava silêncio.
    """
    if len(palavra) > 3 and palavra.endswith('s'):
        return palavra[:-1]
    return palavra


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
    palavras_do_nome = {_raiz(p) for p in nome.split() if len(p) > 2}
    palavras_do_alvo = {_raiz(p) for p in alvo.split() if len(p) > 2}
    return bool(palavras_do_nome & palavras_do_alvo)


#: Aberturas de pergunta. Interrogativa que cita produto é DÚVIDA, não pedido.
#:
#: Na avaliação com 4 personas (13/ago) foram 3 erros em 20, todos deste tipo:
#: "voces so tem salada?", "qual a diferenca do combo 5 pro 8?" e — o pior —
#: "o molho vem junto?", que faria o bot ADICIONAR molho ao carrinho em vez de
#: explicar que ele é vendido à parte.
#:
#: Cliente no WhatsApp quase nunca digita "?", então a lista de aberturas vale
#: tanto quanto o ponto de interrogação.
_PERGUNTAS = (
    'qual', 'quais', 'quanto', 'quantos', 'quantas', 'como', 'quando', 'onde',
    'por que', 'porque', 'pq', 'o que', 'oq', 'tem ', 'teria', 'voces tem',
    'voce tem', 'da pra', 'de pra', 'sera que', 'qnt', 'quanta',
)


def eh_pergunta(texto: str) -> bool:
    """True quando a frase pergunta em vez de pedir."""
    bruto = str(texto or '').strip()
    if bruto.endswith('?'):
        return True
    alvo = normalizar(bruto)
    return any(alvo.startswith(p.strip()) or f' {p.strip()} ' in f' {alvo} '
               for p in _PERGUNTAS)


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
    """Compara PALAVRA inteira, nunca substring.

    A primeira versão fazia `n.strip() in f' {alvo} '`, o que transformava
    'sem ' em 'sem' e casava dentro de "sempre", "semana", "sementes". "quero o
    de sempre" — frase de cliente habitual — era lida como negação e nunca
    virava item.
    """
    alvo = f' {normalizar(texto)} '
    return any(f' {n.strip()} ' in alvo for n in _NEGACOES)


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


def candidatos_de_produto(store, texto: str, limite: int = 4) -> list:
    """TODOS os produtos que a frase pode estar nomeando, do melhor ao pior.

    `casar_produto` devolve um só, e para "quero salada" numa loja com várias
    saladas isso é um chute. Chute vira item errado no carrinho — foi assim que
    o pedido da Yeda saiu R$ 20 em vez de R$ 100. Devolvendo a lista, quem fala
    com o cliente pode perguntar "qual delas?" em vez de adivinhar.
    """
    from apps.stores.models import StoreProduct

    alvo = normalizar(texto)
    if not store or not alvo or tem_negacao(texto):
        return []
    # Produtos E combos. Varrer só StoreProduct fazia "Quero salada" voltar
    # vazio na Cê Saladas, onde salada é vendida por combo — e a mensagem caía
    # em observação de novo, que é o bug que este módulo existe para matar.
    from apps.stores.models import StoreCombo

    candidatos = [
        o for o in [
            # disponiveis() e não is_active: o painel escreve em `status`, e
            # filtrar pelo campo errado oferecia produto que o dono desativou.
            *StoreProduct.disponiveis(store),
            *StoreCombo.objects.filter(store=store, is_active=True),
        ]
        if _casa(alvo, normalizar(o.name))
    ]
    # Ganha quem casa MAIS palavras da frase, não quem tem o nome mais curto.
    # "quero 2 combos de 5 saladas" devolvia "Combo Salmão" — qualquer "Combo X"
    # vencia "COMBO 5 SALADAS", que casa duas palavras.
    def _peso(o):
        nome = normalizar(o.name)
        casadas = len({_raiz(p) for p in nome.split() if len(p) > 2}
                      & {_raiz(p) for p in alvo.split() if len(p) > 2})
        return (nome != alvo, -casadas, len(o.name))

    candidatos.sort(key=_peso)
    return candidatos[:limite]
