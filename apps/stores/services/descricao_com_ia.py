""""Melhorar com IA" na descrição do produto (do admin do Prefiro).

Usa a mesma escada de modelos NVIDIA do painel (`ai_insights._llm_text`): se
um modelo morre, o próximo responde; se todos caem, o lojista recebe o motivo
e o texto dele fica como estava. A sugestão NUNCA é gravada aqui — volta para
o formulário, e quem salva é o dono, depois de ler.
"""
from __future__ import annotations

LIMITE_DESCRICAO = 400
LIMITE_CURTA = 120

PROMPT = """Você escreve descrições de cardápio de delivery em português do Brasil.
Reescreva a descrição do produto abaixo. Regras:
- Tom direto e adulto, de comida de verdade. Sem exagero, sem emoji, sem ponto de exclamação.
- NÃO invente ingrediente, peso, porção ou benefício que não esteja nos dados.
- "descricao": até {limite} caracteres, diz o que vem no prato.
- "descricao_curta": até {limite_curta} caracteres, uma frase para o card.
Responda SÓ com JSON: {{"descricao": "...", "descricao_curta": "..."}}

Produto: {nome}
Categoria: {categoria}
Descrição atual: {descricao}"""


class SemSugestao(RuntimeError):
    """Não deu para sugerir. A mensagem vai para o lojista."""


class IaForaDoAr(SemSugestao):
    """Nenhum modelo da escada respondeu (503, não erro do lojista)."""


def _corta(texto: str, limite: int) -> str:
    texto = ' '.join(str(texto or '').split())
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(' ', 1)[0].rstrip(' ,.;:') + '…'


def melhorar_descricao(nome: str, descricao: str = '', categoria: str = '') -> dict:
    from apps.stores.services.ai_insights import LLMIndisponivel, _json_do_modelo, _llm_text

    nome = (nome or '').strip()
    if not nome:
        raise SemSugestao('Dê um nome ao produto antes.')
    prompt = PROMPT.format(
        limite=LIMITE_DESCRICAO, limite_curta=LIMITE_CURTA,
        nome=nome[:120], categoria=(categoria or '—')[:80], descricao=(descricao or '—')[:1500],
    )
    try:
        dados = _json_do_modelo(_llm_text(prompt))
    except LLMIndisponivel as exc:
        raise IaForaDoAr('A IA não respondeu agora. Tente de novo em instantes.') from exc
    if not isinstance(dados, dict) or not str(dados.get('descricao') or '').strip():
        raise IaForaDoAr('A IA não devolveu uma descrição. Tente de novo.')
    return {
        'descricao': _corta(dados['descricao'], LIMITE_DESCRICAO),
        'descricao_curta': _corta(dados.get('descricao_curta') or '', LIMITE_CURTA),
    }


__all__ = ['IaForaDoAr', 'SemSugestao', 'melhorar_descricao']
