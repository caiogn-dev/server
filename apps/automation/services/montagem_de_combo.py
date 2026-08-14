"""Montar um combo pelo WhatsApp: escolher os sabores antes de fechar.

Pedido pelo dono em 13/ago: "montar pedidos com COMBOS (deve selecionar os
sabores)". Nunca existiu — e o buraco era maior do que parecia: o
`ProductMentionHandler` procura só em `StoreProduct`, então **combo não existia
para o bot**. Medido na Cê Saladas em 14/ago, "combo 5 saladas" — o item de
R$ 239,98, o mais caro da loja — recebia "😕 Não encontrei no cardápio".

Estrutura real da loja: o combo tem um grupo (`ComboProductGroup`) com
`min_selections == max_selections == N` e N opções de sabor
(`ComboProductGroupProductOption`). "COMBO 5 SALADAS" = escolher 5 entre 7.

Duas regras que vêm do dinheiro, não de estilo:

- **Nunca fechar um combo incompleto.** Faltando sabor, o pedido vai para a
  cozinha sem dizer o que fazer. Contar é obrigação deste módulo.
- **Nunca escolher pelo cliente.** Completar "faltam 2" com os dois primeiros
  da lista entrega salada que ninguém pediu. Faltou, pergunta.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Opcao:
    """Um sabor disponível dentro do grupo."""
    id: str
    nome: str


@dataclass
class Grupo:
    """A escolha que o combo exige. `minimo == maximo` é o caso da Cê Saladas."""
    titulo: str
    minimo: int
    maximo: int
    opcoes: List[Opcao] = field(default_factory=list)
    permite_repetir: bool = True


@dataclass
class Escolha:
    """O que o cliente escolheu, e o que ainda falta."""
    selecionados: List[Opcao] = field(default_factory=list)
    nao_reconhecidos: List[str] = field(default_factory=list)

    @property
    def quantidade(self) -> int:
        return len(self.selecionados)


def _sem_acento(texto: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto or '').lower())
        if unicodedata.category(c) != 'Mn'
    )


def grupos_do_combo(combo) -> List[Grupo]:
    """Lê os grupos de escolha do combo. Lista vazia quando não exige escolha."""
    from apps.stores.models.combo_group import (
        ComboProductGroup, ComboProductGroupProductOption,
    )

    grupos = []
    for g in ComboProductGroup.objects.filter(combo=combo).order_by('id'):
        opcoes = [
            Opcao(id=str(o.product_id), nome=o.product.name)
            for o in ComboProductGroupProductOption.objects
            .filter(group=g).select_related('product')
            if o.product_id
        ]
        if not opcoes:
            continue
        grupos.append(Grupo(
            titulo=g.title or 'Escolha suas opções',
            minimo=g.min_selections,
            maximo=g.max_selections,
            opcoes=opcoes,
            permite_repetir=bool(g.allow_duplicate_variants),
        ))
    return grupos


def texto_das_opcoes(grupo: Grupo) -> str:
    """A pergunta que vai para o cliente, numerada.

    Numerada porque digitar "1, 3, 5" no WhatsApp é muito mais provável de dar
    certo do que escrever "Magnífico Camarão" sem errar o acento.
    """
    linhas = [f'{i}. {o.nome}' for i, o in enumerate(grupo.opcoes, start=1)]
    if grupo.minimo == grupo.maximo:
        quantos = f'Escolha *{grupo.minimo}*'
    else:
        quantos = f'Escolha de *{grupo.minimo}* a *{grupo.maximo}*'
    return (
        f'{grupo.titulo}\n\n'
        + '\n'.join(linhas)
        + f'\n\n{quantos} — pode mandar os números (ex.: 1, 3, 5) '
          'ou os nomes. Pode repetir se quiser. 😊'
    )


#: "2 de frango", "3x camarão", "2 camarão". O número vem antes do nome.
_QUANTIDADE = re.compile(r'(\d+)\s*(?:x|de|do|da)?\s+([a-z].*)')


def interpretar(texto: str, grupo: Grupo) -> Escolha:
    """Traduz a resposta do cliente em opções concretas.

    Aceita, porque as três formas aparecem de verdade:
      "1, 3, 5"                  → por número
      "frango, camarão, salmão"  → por nome
      "2 de frango e 3 camarão"  → por quantidade + nome

    O que não reconhece vai para `nao_reconhecidos` em vez de sumir: o cliente
    precisa saber que a palavra dele não entrou, senão o combo fecha faltando
    item e ninguém entende por quê.
    """
    escolha = Escolha()
    bruto = _sem_acento(texto)
    if not bruto.strip():
        return escolha

    # Separadores: vírgula, "e", quebra de linha, "+".
    pedacos = [p.strip() for p in re.split(r'[,\n+]|\be\b', bruto) if p.strip()]

    # "1 2 3 4 5" — números separados só por espaço. Só vale quando o pedaço é
    # SÓ dígitos: "2 frango" continua sendo quantidade + nome, não dois índices.
    expandidos = []
    for pedaco in pedacos:
        if re.fullmatch(r'\d+(\s+\d+)+', pedaco):
            expandidos.extend(pedaco.split())
        else:
            expandidos.append(pedaco)
    pedacos = expandidos

    for pedaco in pedacos:
        quantidade, alvo = 1, pedaco

        achado = _QUANTIDADE.match(pedaco)
        if achado:
            quantidade = int(achado.group(1))
            alvo = achado.group(2).strip()

        opcao = _casar(alvo, grupo)

        # Número solto ("1", "3") só é índice quando não casou como nome — há
        # loja com produto chamado "5 saladas", e aí o 5 é o nome, não a posição.
        if opcao is None and alvo.isdigit():
            indice = int(alvo) - 1
            if 0 <= indice < len(grupo.opcoes):
                opcao, quantidade = grupo.opcoes[indice], 1

        if opcao is None:
            escolha.nao_reconhecidos.append(pedaco)
            continue

        escolha.selecionados.extend([opcao] * max(1, quantidade))

    return escolha


def _casar(alvo: str, grupo: Grupo) -> Optional[Opcao]:
    """Casa por palavra inteira contida no nome da opção.

    Palavra inteira, e não substring, pela mesma razão que 'sem' casava dentro
    de 'sempre': casar pedaço de palavra escolhe o sabor errado calado.
    """
    alvo = alvo.strip()
    if not alvo:
        return None

    for o in grupo.opcoes:
        if _sem_acento(o.nome) == alvo:
            return o

    palavras_do_alvo = set(re.findall(r'\w+', alvo))
    if not palavras_do_alvo:
        return None

    melhor, melhor_peso = None, 0
    for o in grupo.opcoes:
        palavras = set(re.findall(r'\w+', _sem_acento(o.nome)))
        peso = len(palavras & palavras_do_alvo)
        if peso > melhor_peso:
            melhor, melhor_peso = o, peso
    return melhor


def faltam(escolha: Escolha, grupo: Grupo) -> int:
    """Quantas escolhas ainda faltam. Negativo significa que passou do limite."""
    if escolha.quantidade < grupo.minimo:
        return grupo.minimo - escolha.quantidade
    if escolha.quantidade > grupo.maximo:
        return grupo.maximo - escolha.quantidade
    return 0


def resumo(escolha: Escolha) -> str:
    """"2x Tilápia Suprema, 3x Magnífico Camarão" — o que vai para a cozinha."""
    contagem: dict = {}
    for o in escolha.selecionados:
        contagem[o.nome] = contagem.get(o.nome, 0) + 1
    return ', '.join(
        f'{n}x {nome}' if n > 1 else nome for nome, n in contagem.items()
    )


# ── A conversa ────────────────────────────────────────────────────────────
#
# O estado é um dicionário simples, guardado no `context` da sessão. Ele mora
# aqui e não no handler porque a montagem acontece em dois turnos — a pergunta
# num, a resposta no outro — e regra de negócio partida entre dois arquivos foi
# o que produziu as duas máquinas de estado divergentes de 12/ago.

CHAVE = 'combo_em_montagem'


def iniciar(combo, grupos: List[Grupo]) -> tuple:
    """Devolve (texto para o cliente, estado a guardar).

    Estado `None` significa que o combo não exige escolha e pode ir direto para
    o carrinho.
    """
    if not grupos:
        return '', None

    grupo = grupos[0]
    texto = (
        f'🥗 *{combo.name}* — R$ {combo.price}\n\n'
        + texto_das_opcoes(grupo)
    )
    return texto, {
        'combo_id': str(combo.id),
        'combo_nome': combo.name,
        'escolhidos': [],
    }


def responder(estado: dict, texto: str, grupo: Grupo) -> tuple:
    """Processa a resposta do cliente.

    Devolve (texto, novo_estado). `novo_estado is None` significa que a
    montagem terminou — o chamador então adiciona ao carrinho.
    """
    escolha = Escolha(
        selecionados=[Opcao(**o) for o in (estado.get('escolhidos') or [])],
    )
    nova = interpretar(texto, grupo)
    escolha.selecionados.extend(nova.selecionados)

    aviso = ''
    if nova.nao_reconhecidos:
        # Sumir com a palavra do cliente fecha o combo faltando item e ninguém
        # entende por quê.
        nao = ', '.join(f'"{n}"' for n in nova.nao_reconhecidos)
        aviso = f'Não achei {nao} no cardápio. '

    sobra = faltam(escolha, grupo)

    if sobra > 0:
        estado['escolhidos'] = [vars(o) for o in escolha.selecionados]
        ja = f'Até agora: {resumo(escolha)}.\n\n' if escolha.selecionados else ''
        return (
            f'{aviso}{ja}Faltam *{sobra}* — quais?',
            estado,
        )

    if sobra < 0:
        # Passou do limite. NÃO cortar sozinho: escolher quais tirar é decisão
        # do cliente, e cortar calado entrega salada que ele não pediu.
        excedente = -sobra
        return (
            f'{aviso}Você escolheu {escolha.quantidade} e o combo é de '
            f'*{grupo.maximo}*. Tira {excedente}? Me manda a lista de novo. 😊',
            {**estado, 'escolhidos': []},
        )

    return (
        f'{aviso}Fechado! ✅ *{estado["combo_nome"]}* com: {resumo(escolha)}.',
        None,
    )
