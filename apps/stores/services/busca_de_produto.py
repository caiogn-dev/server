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


def _nomes(objeto) -> list:
    """Nome + apelidos, já normalizados.

    Apelido é o nome que o cliente usa ("filé especial"), gravado pelo dono na
    tela "ensinar" do painel em `metadata['apelidos']`. Vale como nome.
    Leitura defensiva: o campo `metadata` do StoreProduct chega por outra
    branch (migração 0089), e apelido que não é texto é ignorado.
    """
    apelidos = (getattr(objeto, 'metadata', None) or {}).get('apelidos') or []
    return [n for n in (normalizar(x) for x in [objeto.name, *apelidos] if isinstance(x, str)) if n]


def _casa_objeto(alvo: str, objeto) -> bool:
    return any(_casa(alvo, nome) for nome in _nomes(objeto))


def casar_produto(store, texto: str):
    """Produto ativo desta loja cujo nome (ou apelido) aparece no texto."""
    from apps.stores.models import StoreProduct

    alvo = normalizar(texto)
    if not alvo:
        return None
    candidatos = [p for p in StoreProduct.disponiveis(store) if _casa_objeto(alvo, p)]
    return _melhor(candidatos, alvo, lambda p: p.name)


def casar_combo(store, texto: str):
    from apps.stores.models import StoreCombo

    alvo = normalizar(texto)
    if not alvo:
        return None
    candidatos = [
        c for c in StoreCombo.objects.filter(store=store, is_active=True) if _casa_objeto(alvo, c)
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


def distancia(a: str, b: str) -> int:
    """Levenshtein: letras a inserir, apagar ou trocar para ir de `a` a `b`."""
    anterior = list(range(len(b) + 1))
    for i, letra_a in enumerate(a, 1):
        atual = [i]
        for j, letra_b in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (letra_a != letra_b)))
        anterior = atual
    return anterior[-1]


def _peso_da_palavra(do_cliente: str, do_nome: str) -> int:
    """2 = mesma palavra (ou plural); 1 = erro de digitação; 0 = outra palavra.

    "espesial" é "especial" digitado torto — 30 dias de prod: 160 mensagens
    em `unknown` e 12 pedidos pelo WhatsApp. A régua é curta de propósito:
    palavra de até 3 letras só casa exata ("mel" não vira "gel"), e a
    tolerância é 1 letra — 2 só quando as duas têm 7 ou mais.
    """
    if _raiz(do_cliente) == _raiz(do_nome):
        return 2
    menor = min(len(do_cliente), len(do_nome))
    if menor < 4:
        return 0
    return 1 if distancia(do_cliente, do_nome) <= (2 if menor >= 7 else 1) else 0


def _palavras(texto: str) -> list:
    """Palavra de uma letra ou duas não casa nada — "de", "e", "ml" fariam meio
    catálogo casar com qualquer frase."""
    return [p for p in texto.split() if len(p) > 2]


def _casa(alvo: str, nome: str) -> bool:
    """O texto contém o nome, o nome contém o texto, ou uma palavra casa.

    As duas direções importam: "Suco de laranja 400ml" (o cliente copiou o nome
    inteiro) e "quero salada" (o cliente disse uma palavra que está no nome).
    """
    if not alvo or not nome:
        return False
    if nome in alvo or alvo in nome:
        return True
    return any(_peso_da_palavra(a, n) for n in _palavras(nome) for a in _palavras(alvo))


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


#: Verbos de acréscimo: "acrescenta cenoura" é recado pra cozinha, não item.
_ACRESCIMOS = ('acrescenta', 'acrescentar', 'adiciona', 'adicionar', 'coloca', 'colocar',
               'capricha', 'caprichar', 'com mais', 'extra ', 'a mais')

# Um trecho negado vai do marcador até a próxima vírgula / " e " / ponto.
_TRECHO_NEGADO = re.compile(
    r'\b(sem|tirar|retirar|tira|nao quero|nada de|menos|exceto|fora|nao coloca|nao ponha)\s+'
    r'(?P<alvo>[^,.;!?\n]+?)(?=\s+\b(?:e|ou|se|mas|porem|por favor|pfv)\b|[,.;!?\n]|$)',
)


def separar_negacoes(texto: str) -> tuple[str, list[str]]:
    """Divide a frase em (o que PEDE, [trechos que TIRAM]).

    25/09, Cê Saladas: "Vou querer uma espécie filé de frango, sem tomate
    cereja e sem cebola roxa, se poder acrescentar cenoura ralada" virou
    1x Cebola roxa — o item negado entrou e a salada de R$ 39,99 ficou de
    fora. Quem casa produto com texto tem que olhar só a parte que pede;
    a parte que tira é observação.

    Devolve os dois lados com a grafia do cliente: os negados viram nota e o
    que sobra vai ao casamento (que normaliza sozinho).
    """
    bruto = str(texto or '')
    if not bruto.strip():
        return '', []
    # Trabalha sobre a versão sem acento para casar "não", mas recorta do
    # texto original para a nota sair como o cliente escreveu.
    plano = unicodedata.normalize('NFD', bruto).encode('ascii', 'ignore').decode()
    negados, pedido, cursor = [], [], 0
    for m in _TRECHO_NEGADO.finditer(plano.lower()):
        pedido.append(bruto[cursor:m.start()])
        negados.append(bruto[m.start():m.end()].strip(' ,'))
        cursor = m.end()
    pedido.append(bruto[cursor:])
    sobra = re.sub(r'\s+', ' ', ' '.join(pedido)).strip(' ,')
    return sobra, negados


def trechos_de_acrescimo(texto: str) -> list[str]:
    """"acrescenta cenoura ralada", "capricha no molho": recado, não item."""
    plano = normalizar(texto)
    achados = []
    for frase in re.split(r'[,.;!?\n]', str(texto or '')):
        if any(v in normalizar(frase) for v in _ACRESCIMOS):
            achados.append(frase.strip(' ,'))
    return achados if plano else []


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
    if tem_negacao(texto):
        return []
    return [o for o, _ in candidatos_pontuados(store, texto)[:limite]]


def candidatos_pontuados(store, texto: str) -> list:
    """[(produto ou combo, pontos)] do melhor ao pior — os pontos decidem empate.

    Quem precisa saber se há UM vencedor claro (a leitura do pedido digitado)
    olha os pontos: empatou no topo, pergunta ao cliente. Não filtra negação —
    quem chama já separou o que o cliente tira do que ele pede.
    """
    from apps.stores.models import StoreCombo, StoreProduct

    alvo = normalizar(texto)
    if not store or not alvo:
        return []
    # Produtos E combos. Varrer só StoreProduct fazia "Quero salada" voltar
    # vazio na Cê Saladas, onde salada é vendida por combo — e a mensagem caía
    # em observação de novo, que é o bug que este módulo existe para matar.
    pontuados = [
        (o, max(_pontos(alvo, nome) for nome in _nomes(o)))
        for o in [
            # disponiveis() e não is_active: o painel escreve em `status`, e
            # filtrar pelo campo errado oferecia produto que o dono desativou.
            *StoreProduct.disponiveis(store),
            *StoreCombo.objects.filter(store=store, is_active=True),
        ]
        if _casa_objeto(alvo, o)
    ]
    # Ganha quem casa MAIS palavras da frase, não quem tem o nome mais curto.
    # "quero 2 combos de 5 saladas" devolvia "Combo Salmão" — qualquer "Combo X"
    # vencia "COMBO 5 SALADAS", que casa duas palavras.
    pontuados.sort(key=lambda par: (-par[1], len(par[0].name)))
    return pontuados


def _pontos(alvo: str, nome: str) -> int:
    """Nome idêntico > nome inteiro dentro da frase > palavras casadas.

    Palavra exata vale 2 e digitada torta vale 1: com "Molho" e "Milho" no
    cardápio, "quero molho" tem vencedor claro em vez de empate.
    """
    if nome == alvo:
        return 1000
    do_cliente = _palavras(alvo)
    casadas = sum(
        max((_peso_da_palavra(a, n) for a in do_cliente), default=0)
        for n in dict.fromkeys(_raiz(p) for p in _palavras(nome))
    )
    return casadas + (100 if nome in alvo else 0)


# Avisos de que o dinheiro já saiu da mão do cliente.
#
# Precisam ser reconhecidos ANTES de qualquer passo que trate texto livre como
# observação do pedido. Em 31/08 a Dênia voltou do Checkout Pro com o texto que
# a página de sucesso pré-preenche no wa.me e o bot anotou a confirmação de
# pagamento como recado pra cozinha, pedindo pagamento de novo a quem já tinha
# pagado — e depois mandando um segundo link de cobrança.
_AVISOS_DE_PAGAMENTO = (
    'ja paguei', 'ja pagei', 'paguei', 'ja foi pago', 'foi pago', 'ta pago',
    'esta pago', 'pagamento efetuado', 'pagamento feito', 'pagamento realizado',
    'acabei de pagar', 'acabei de fazer o pagamento', 'comprovante',
    'ja fiz o pix', 'fiz o pix', 'ja transferi', 'efetuei o pagamento',
    'gostaria de confirmar meu pedido', 'gostaria de confirmar',
    'acabei de fazer um pedido',
)


def parece_aviso_de_pagamento(texto) -> bool:
    """O cliente está dizendo que pagou — não deixando recado pra cozinha.

    Reconhece tanto o texto que o Mercado Pago devolve pelo botão de voltar
    quanto o que a pessoa escreve sozinha ("já foi pago", "segue o comprovante").

    Deliberadamente NÃO casa "pagar na entrega" nem "pago na maquininha": aquilo
    é escolha de forma de pagamento e tem outro caminho. Aqui só entra quem
    afirma que o dinheiro JÁ saiu.
    """
    alvo = normalizar(texto)
    if not alvo:
        return False
    return any(frase in alvo for frase in _AVISOS_DE_PAGAMENTO)
