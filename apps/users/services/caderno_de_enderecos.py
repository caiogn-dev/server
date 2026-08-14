"""O caderno de endereços do cliente — preenchido pelo ato de pedir.

Existe porque o PDV mostrava cliente conhecido SEM endereço, enquanto o bot
achava o endereço sem dificuldade. Não era bug de tela: eram duas fontes
diferentes. O bot lê o `delivery_address` do último pedido; o PDV lê
`UserAddress`, e `UserAddress` só nascia quando o cliente mandava um pin no
WhatsApp — está escrito no docstring do próprio model.

Medido na Cê Saladas em 14/ago: 45 clientes com pedido de entrega, 7 com
endereço salvo. 38 chegavam vazios no PDV.

A correção é fazer o caderno ser preenchido por quem pede, não por quem manda
pin. Assim as duas telas voltam a ler a mesma coisa.

⚠️ `delivery_address` é JSONField LIVRE, e em produção tem cinco formatos
diferentes ao mesmo tempo — inclusive 18 pedidos que são só
`{"address": "<texto>"}`. Qualquer coisa aqui que assuma um formato só descarta
endereço de verdade em silêncio.
"""
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

#: Chaves que já apareceram carregando o logradouro, em ordem de preferência.
#: `address` e `raw_address` são os formatos sem estrutura — vêm por último
#: porque são o pior dado, mas entram: descartá-los perderia 18 endereços reais.
_CHAVES_DE_RUA = ('street', 'address', 'raw_address', 'formatted_address', 'label')


def _texto(valor) -> str:
    if valor is None:
        return ''
    return str(valor).strip()


#: `state` tem max_length=2, mas o dado real traz "Tocantins" por extenso.
#: Truncar daria "To" — um estado que não existe. Mapear é a única saída que
#: não inventa dado.
_UF = {
    'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM',
    'bahia': 'BA', 'ceara': 'CE', 'distrito federal': 'DF',
    'espirito santo': 'ES', 'goias': 'GO', 'maranhao': 'MA',
    'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG',
    'para': 'PA', 'paraiba': 'PB', 'parana': 'PR', 'pernambuco': 'PE',
    'piaui': 'PI', 'rio de janeiro': 'RJ', 'rio grande do norte': 'RN',
    'rio grande do sul': 'RS', 'rondonia': 'RO', 'roraima': 'RR',
    'santa catarina': 'SC', 'sao paulo': 'SP', 'sergipe': 'SE',
    'tocantins': 'TO',
}


def _uf(valor: str) -> str:
    """Devolve a sigla. String vazia quando não reconhece — melhor vazio que errado."""
    texto = _texto(valor)
    if len(texto) == 2:
        return texto.upper()
    import unicodedata

    chave = ''.join(
        c for c in unicodedata.normalize('NFD', texto.lower())
        if unicodedata.category(c) != 'Mn'
    )
    return _UF.get(chave, '')


def _numero(valor):
    """lat/lng chegam como float, str e None conforme a origem do pedido."""
    if valor in (None, ''):
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalizar(bruto, *, loja=None) -> dict:
    """Achata qualquer um dos formatos de `delivery_address` num só.

    Devolve `{}` quando não há logradouro algum — retirada na loja cai aqui, e
    retirada não deve criar endereço.
    """
    if not isinstance(bruto, dict):
        # Já veio string, None e lista neste campo. Nada a aproveitar, mas
        # também não é motivo para derrubar o salvamento do pedido.
        return {}

    rua = ''
    for chave in _CHAVES_DE_RUA:
        rua = _texto(bruto.get(chave))
        if rua:
            break
    if not rua:
        return {}

    # `city`/`state` são obrigatórios no model. O formato de texto livre não
    # traz nenhum dos dois, então a loja serve de padrão: um endereço com a
    # cidade da loja é aproveitável, um sem cidade não é.
    cidade = _texto(bruto.get('city')) or _texto(getattr(loja, 'city', ''))
    estado = _uf(bruto.get('state')) or _uf(getattr(loja, 'state', ''))

    return {
        'street': rua[:255],
        'number': _texto(bruto.get('number'))[:20],
        'neighborhood': _texto(bruto.get('neighborhood'))[:100],
        'complement': _texto(bruto.get('complement'))[:255],
        'city': cidade[:100],
        'state': estado,
        'zip_code': _texto(bruto.get('zip_code') or bruto.get('cep'))[:10],
        'lat': _numero(bruto.get('lat')),
        'lng': _numero(bruto.get('lng')),
    }


def _mesma_porta(dados: dict) -> dict:
    """Chave de identidade do endereço, para não duplicar.

    Rua + número + cidade. O signal roda em TODO save do pedido, incluindo cada
    mudança de status — sem isto, um pedido que passa por recebido → preparando
    → saiu → entregue criaria quatro endereços iguais.
    """
    return {
        'street__iexact': dados['street'],
        'number': dados['number'],
        'city__iexact': dados['city'],
    }


def guardar_endereco_do_pedido(order):
    """Salva o endereço do pedido no caderno do cliente. Idempotente.

    Nunca levanta: isto roda no `post_save` de `StoreOrder`, e endereço é
    acessório — a venda é o principal. Mesma regra do `acquire_lock` e do
    agendamento de avaliação.
    """
    try:
        return _guardar(order)
    except Exception as exc:  # pragma: no cover - rede de segurança
        logger.warning(
            'Não consegui salvar o endereço do pedido %s: %s',
            getattr(order, 'id', '?'), exc,
        )
        return None


def _guardar(order):
    from apps.users.models import UnifiedUser, UserAddress

    telefone = (getattr(order, 'customer_phone', '') or '').strip()
    if not telefone:
        return None

    dados = normalizar(getattr(order, 'delivery_address', None), loja=order.store)
    if not dados:
        return None

    # Mesma resolução de telefone que o signal de estatísticas já usa — o
    # cadastro guarda o número em mais de um formato.
    from apps.users.signals import _phone_candidates

    cliente = UnifiedUser.objects.filter(
        phone_number__in=_phone_candidates(telefone),
    ).first()
    if cliente is None:
        # Pedido de balcão de quem nunca se cadastrou. Normal.
        return None

    existente = UserAddress.objects.filter(
        unified_user=cliente, tenant=order.store, **_mesma_porta(dados),
    ).first()
    if existente is not None:
        # Coordenada pode ter chegado depois (o primeiro pedido às vezes vem
        # sem pin). Completar o que falta vale; sobrescrever o que já existe não.
        faltando = {
            campo: dados[campo]
            for campo in ('lat', 'lng', 'zip_code', 'neighborhood', 'complement')
            if dados[campo] and not getattr(existente, campo)
        }
        if faltando:
            for campo, valor in faltando.items():
                setattr(existente, campo, valor)
            existente.save(update_fields=list(faltando))
        return existente

    return UserAddress.objects.create(
        unified_user=cliente,
        tenant=order.store,
        label=dados['neighborhood'] or 'Entrega',
        **dados,
    )
