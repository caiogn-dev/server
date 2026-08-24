"""Deduplicação da lista de contatos do sistema.

A mesma pessoa chega por origens diferentes (conversa, pedido, inscrição,
sessão do bot) e cada origem grava o telefone do seu jeito. Deduplicar pela
string crua fazia o painel prometer uma base grande que não existe: a Cê
Saladas exibia ~292 "clientes" com só 58 telefones distintos tendo pedido.

São DUAS divergências empilhadas:

    pedido    '63984289103'    -> sem DDI, com o nono dígito
    conversa  '556384289103'   -> com DDI, SEM o nono dígito (wa_id antigo)

Por isso a chave colapsa o nono dígito, do mesmo jeito que `phone_variants`
faz nos lookups. E o telefone EXPOSTO prefere o wa_id de uma conversa real:
é o único formato com entrega comprovada naquele número.
"""
from typing import Dict

from apps.core.utils import normalize_phone_number

# Quem comprou vale mais que quem só conversou: no empate, a origem mais forte
# é a que fica, porque é ela que diz se vale a pena gastar mensagem com a pessoa.
PRIORIDADE_DE_ORIGEM = {
    'conversation': 1,
    'session': 2,
    'subscriber': 3,
    'order': 4,
}

# Origem cujo telefone é um wa_id devolvido pela própria Meta.
ORIGEM_COM_WA_ID = 'conversation'


def _so_digitos(telefone) -> str:
    return ''.join(filter(str.isdigit, str(telefone or '')))


def chave_do_telefone(telefone) -> str:
    """Forma canônica para comparar telefones: DDI 55 e nono dígito removido.

    Não serve para enviar mensagem — é só a identidade da pessoa. Use
    `contato['phone']` para o envio.
    """
    digitos = normalize_phone_number(_so_digitos(telefone))
    if not digitos:
        return ''

    if digitos.startswith('55'):
        local = digitos[2:]
        if len(local) == 11 and local[2] == '9':
            return '55' + local[:2] + local[3:]
    return digitos


def telefone_para_envio(telefone) -> str:
    """Telefone em E.164 sem '+', preservando o nono dígito quando existe."""
    return normalize_phone_number(_so_digitos(telefone))


def mesclar_contato(contatos: Dict[str, dict], telefone, nome, origem) -> None:
    """Insere ou funde o contato em `contatos`, chaveado pela forma canônica."""
    chave = chave_do_telefone(telefone)
    if not chave:
        return

    nome = (nome or '').strip()
    existente = contatos.get(chave)

    if existente is None:
        contatos[chave] = {
            'phone': telefone_para_envio(telefone),
            'name': nome,
            'source': origem,
            'tem_wa_id': origem == ORIGEM_COM_WA_ID,
        }
        return

    if not existente['name'] and nome:
        existente['name'] = nome

    # wa_id da Meta vence qualquer outro formato para o envio.
    if origem == ORIGEM_COM_WA_ID and not existente['tem_wa_id']:
        existente['phone'] = telefone_para_envio(telefone)
        existente['tem_wa_id'] = True

    if PRIORIDADE_DE_ORIGEM.get(origem, 0) > PRIORIDADE_DE_ORIGEM.get(existente['source'], 0):
        existente['source'] = origem


def contatos_para_resposta(contatos: Dict[str, dict], limite: int) -> list:
    """Lista pronta para a API — sem o campo interno de controle."""
    return [
        {'phone': c['phone'], 'name': c['name'], 'source': c['source']}
        for c in list(contatos.values())[:limite]
    ]
