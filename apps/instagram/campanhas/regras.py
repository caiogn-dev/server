"""As regras da campanha, sem banco e sem rede.

Cliente escreve "Eu Querô!!!" e "eu quero" — a palavra-chave não pode depender
de acento nem de caixa, senão a loja recebe reclamação de quem comentou certo.
"""
import re
import unicodedata

SEM_PALAVRA = 'sem_palavra'
POUCOS_AMIGOS = 'poucos_amigos'
NAO_SEGUE = 'nao_segue'
JA_PARTICIPOU = 'ja_participou'

MOTIVOS = {
    SEM_PALAVRA: 'não escreveu a palavra da promoção',
    POUCOS_AMIGOS: 'marcou menos amigos do que a regra pede',
    NAO_SEGUE: 'ainda não segue a loja',
    JA_PARTICIPOU: 'já tinha participado com outro comentário',
}

_MARCACAO = re.compile(r'@([A-Za-z0-9._]{1,30})')


def _simples(texto: str) -> str:
    sem_acento = unicodedata.normalize('NFKD', texto or '')
    sem_acento = ''.join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', sem_acento).strip().lower()


def tem_a_palavra(texto: str, palavra: str) -> bool:
    """Campanha sem palavra-chave aceita qualquer comentário."""
    if not palavra:
        return True
    return _simples(palavra) in _simples(texto)


def contar_marcacoes(texto: str, propria: str = '') -> int:
    """@amigos distintos, sem contar a própria loja nem repetição."""
    marcados = {m.lower() for m in _MARCACAO.findall(texto or '')}
    marcados.discard((propria or '').lower().lstrip('@'))
    return len(marcados)
