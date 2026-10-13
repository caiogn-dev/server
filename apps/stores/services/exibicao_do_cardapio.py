"""Exibição do cardápio — como o produto aparece na vitrine, decidido pelo dono.

Guardado em `store.metadata['exibicao']` e gravado SÓ por aqui (mesmo motivo
dos informativos: o painel mandava o metadata inteiro e uma tela apagava a
outra). Sem configuração, a vitrine recebe PADRAO — que reproduz o que já
estava no ar, então nada muda para quem não mexeu.
"""
from django.db import transaction

CHAVE = 'exibicao'

PADRAO = {
    # 0 = automático (o cartão corta pelo tamanho, como antes).
    'descricao_limite': 0,
    # 'padrao' = o que o template já faz (topo; Elegant à direita).
    'foto_posicao': 'padrao',
    'foto_encaixe': 'cortar',
    'foto_proporcao': 'padrao',
    'mostrar_estoque_baixo': True,
    'mostrar_esgotados': True,
    # Vazio = o texto de sempre da tela de pedido concluído.
    'agradecimento_titulo': '',
    'agradecimento_subtitulo': '',
}

ESCOLHAS = {
    'foto_posicao': ('padrao', 'topo', 'esquerda', 'direita'),
    'foto_encaixe': ('cortar', 'inteira'),
    'foto_proporcao': ('padrao', 'quadrada', 'retangular', 'paisagem'),
}
LIMITE_DESCRICAO_MAX = 500
TEXTOS_MAX = {'agradecimento_titulo': 60, 'agradecimento_subtitulo': 160}
BOOLEANOS = ('mostrar_estoque_baixo', 'mostrar_esgotados')


class ExibicaoInvalida(ValueError):
    pass


def _validar_campo(campo, valor):
    if campo in ESCOLHAS:
        if valor not in ESCOLHAS[campo]:
            raise ExibicaoInvalida(f'"{campo}" aceita: {", ".join(ESCOLHAS[campo])}.')
        return valor
    if campo == 'descricao_limite':
        if isinstance(valor, bool):
            raise ExibicaoInvalida('Limite da descrição precisa ser um número.')
        try:
            n = int(valor)
        except (TypeError, ValueError):
            raise ExibicaoInvalida('Limite da descrição precisa ser um número.')
        if not 0 <= n <= LIMITE_DESCRICAO_MAX:
            raise ExibicaoInvalida(f'Limite da descrição entre 0 e {LIMITE_DESCRICAO_MAX} caracteres.')
        return n
    if campo in BOOLEANOS:
        if not isinstance(valor, bool):
            raise ExibicaoInvalida(f'"{campo}" é ligado ou desligado.')
        return valor
    if campo in TEXTOS_MAX:
        texto = str(valor or '').strip()
        if len(texto) > TEXTOS_MAX[campo]:
            raise ExibicaoInvalida(f'Texto com no máximo {TEXTOS_MAX[campo]} caracteres.')
        return texto
    raise KeyError(campo)


def ler(loja) -> dict:
    salvo = (loja.metadata or {}).get(CHAVE) or {}
    return {campo: salvo.get(campo, padrao) for campo, padrao in PADRAO.items()}


def salvar(loja, dados: dict) -> dict:
    """Valida tudo antes de gravar; campo desconhecido é ignorado."""
    novos = {campo: _validar_campo(campo, valor) for campo, valor in (dados or {}).items() if campo in PADRAO}
    with transaction.atomic():
        fresca = type(loja).objects.select_for_update().get(pk=loja.pk)
        meta = dict(fresca.metadata or {})
        meta[CHAVE] = {**(meta.get(CHAVE) or {}), **novos}
        fresca.metadata = meta
        fresca.save(update_fields=['metadata', 'updated_at'])
    return ler(fresca)
