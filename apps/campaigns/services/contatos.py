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
    """Telefone em E.164 sem '+', COMO A GENTE O CONHECE.

    Usa `telefone_para_envio_e164` e não `normalize_phone_number` porque as
    duas deixaram de ser a mesma coisa em 05/09: a de identidade acrescenta o
    nono dígito para colapsar `556391124171` (wa_id) com `5563991124171`
    (checkout) e parar a duplicação de cadastro.

    Para ENVIAR, mexer no número é risco de outra natureza — identidade errada
    é relatório torto, número de envio errado é a mensagem não chegando. Aqui
    só o DDI é garantido.
    """
    from apps.core.utils import telefone_para_envio_e164
    return telefone_para_envio_e164(_so_digitos(telefone))


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


def coletar_por_loja(store_ids) -> Dict[str, dict]:
    """Todos os contatos das lojas, deduplicados pela chave do telefone.

    Pedido e conversa são as duas fontes que existem de verdade: quem comprou
    e quem falou com a loja. A mescla usa `mesclar_contato`, a mesma do
    caminho antigo — chave única, nome do melhor registro.

    Existe para o construtor de público não reimplementar a coleta que a
    `SystemContactsView` faz inline. (Ela ainda não usa esta função: o caminho
    dela tem filtro por conta de WhatsApp e mais fontes; adotar é o próximo
    passo, com teste de caracterização antes.)
    """
    from django.db.models import Max

    from apps.conversations.models import Conversation
    from apps.stores.models import StoreOrder

    contatos: Dict[str, dict] = {}

    pedidos = (
        StoreOrder.objects
        .filter(store_id__in=list(store_ids))
        .exclude(customer_phone='')
        .values('customer_phone', 'customer_name')
        .annotate(ultimo=Max('created_at'))
        .order_by('-ultimo')[:5000]
    )
    for pedido in pedidos:
        mesclar_contato(contatos, pedido['customer_phone'], pedido['customer_name'], 'order')

    conversas = (
        Conversation.objects
        .filter(account__stores__id__in=list(store_ids))
        .exclude(phone_number='')
        .values('phone_number', 'contact_name')
        .annotate(ultimo=Max('updated_at'))
        .order_by('-ultimo')[:5000]
    )
    for conversa in conversas:
        mesclar_contato(contatos, conversa['phone_number'], conversa['contact_name'], 'conversation')

    return contatos
