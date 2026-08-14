"""O que a loja REALMENTE sabe sobre um produto — e o que ela não sabe.

Regra do dono: o bot não pode falar sobre uma receita que ele não sabe, nem
sobre ingrediente que não tem cadastrado.

Numa loja de comida isso não é preciosismo. Medido no catálogo real, 7 dos 41
produtos ativos da Cê Saladas estão com a descrição VAZIA — "Combo Camarão" e
"suco 1" entre eles. Perguntado "o que vem no Combo Camarão?", um modelo
responde com fluência "camarão, alface, tomate e molho especial", e o cliente
recebe outra coisa. Se a invenção incluir um alérgeno que a pessoa evita, o
custo não é uma reclamação.

Por isso este módulo devolve **só o cadastrado** e diz explicitamente quando não
sabe. `texto_seguro` existe para ser a ÚNICA porta pela qual uma resposta sobre
composição sai: ele não tem como inventar porque não tem de onde tirar.

⚠️ Silêncio sobre alérgeno é pior que silêncio sobre ingrediente. "Tem glúten?"
respondido com "não" sem base é risco de saúde — a ficha nunca afirma ausência,
só encaminha para quem pode confirmar.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Ficha:
    nome: str = ''
    composicao: str = ''
    sabe_composicao: bool = False
    alergenicos: List[str] = field(default_factory=list)
    sabe_alergenicos: bool = False


def ficha(produto) -> Ficha:
    """Lê o cadastro. Não interpreta, não resume, não completa."""
    if produto is None:
        return Ficha()

    descricao = (getattr(produto, 'description', '') or '').strip()
    alergenicos = _alergenicos(produto)

    return Ficha(
        nome=getattr(produto, 'name', '') or '',
        # Literal. Reescrever o que o lojista escreveu é o primeiro passo para
        # inventar: uma "melhoria" de texto vira ingrediente que não existe.
        composicao=descricao,
        sabe_composicao=bool(descricao),
        alergenicos=alergenicos,
        sabe_alergenicos=bool(alergenicos),
    )


def _alergenicos(produto) -> List[str]:
    """Só o que está declarado. Lista vazia significa 'não declarado', nunca
    'não contém' — a diferença entre as duas é a que importa."""
    attrs = getattr(produto, 'attributes', None) or {}
    if not isinstance(attrs, dict):
        return []
    bruto = attrs.get('alergenicos') or attrs.get('allergens') or []
    if isinstance(bruto, str):
        bruto = [bruto]
    return [str(x).strip() for x in bruto if str(x).strip()]


_PERGUNTA_DE_ALERGIA = (
    'gluten', 'glúten', 'lactose', 'leite', 'amendoim', 'castanha', 'nozes',
    'soja', 'ovo', 'peixe', 'camarao', 'camarão', 'frutos do mar', 'alergia',
    'alergico', 'alérgico', 'celiaco', 'celíaco', 'intolerancia', 'intolerância',
)


def texto_seguro(produto, pergunta: str = '') -> str:
    """Resposta sobre composição que não tem como inventar.

    Devolve o cadastrado, ou admite que não sabe. Nunca preenche a lacuna.
    """
    f = ficha(produto)
    alvo = (pergunta or '').lower()
    sobre_alergia = any(p in alvo for p in _PERGUNTA_DE_ALERGIA)

    if not f.nome:
        return (
            'Não encontrei esse item no nosso cardápio. '
            'Quer ver o que temos hoje?'
        )

    if sobre_alergia and not f.sabe_alergenicos:
        # Jamais responder "não contém". Sem declaração cadastrada, a única
        # resposta honesta é encaminhar — e é por isso que este ramo vem antes
        # de mostrar a composição: descrição não é laudo de alérgeno.
        return (
            f'Sobre alérgenos no *{f.nome}* eu não tenho a informação '
            'confirmada aqui, e nesse assunto eu prefiro não chutar. '
            'Vou confirmar com a cozinha e te retorno.'
        )

    if not f.sabe_composicao:
        return (
            f'A composição do *{f.nome}* não está detalhada aqui comigo — '
            'não tenho como te dizer sem confirmar. '
            'Já pergunto pra equipe e te falo.'
        )

    resposta = f'*{f.nome}*\n{f.composicao}'
    if f.sabe_alergenicos:
        resposta += '\n\n⚠️ Contém: ' + ', '.join(f.alergenicos)
    return resposta
