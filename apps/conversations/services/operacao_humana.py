"""O que o atendente precisa saber ao abrir uma conversa em modo humano.

Por que caiu para humano (motivo), há quanto tempo o cliente espera, o que o
bot já tinha colhido (carrinho, endereço, observação) e quem é o cliente.
Antes (26/09) o atendente relia a conversa inteira para descobrir o que a
sessão do bot já sabia, e o motivo era "Synced from conversation mode switch"
para quase tudo.

Tudo aqui é LEITURA: nada cria sessão, perfil ou pedido. `SessionManager`
não serve — `get_or_create_session` cria sessão e mexe em
`last_activity_at`, e abrir o painel não pode mudar o estado do bot.
"""
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

GENERICO = 'Synced from conversation mode switch'

TEXTOS = {
    'pediu_atendente': 'Cliente pediu atendente',
    'bot_nao_entendeu': 'O bot não entendeu o cliente',
    'eco_do_celular': 'Respondido pelo WhatsApp do celular',
    'atendente_assumiu': 'Um atendente assumiu a conversa',
    'outro': 'Passou para atendimento humano',
}

#: Motivo gravado ao ASSUMIR pelo painel (POST .../assumir/).
MOTIVO_ASSUMIU = TEXTOS['atendente_assumiu']


def normalizar(texto: str) -> str:
    """minúsculas, sem acento, sem pontuação, espaços colapsados."""
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    texto = re.sub(r'[^\w\s]', ' ', texto.lower())
    return ' '.join(texto.split())


def normalizar_mantendo_acento(texto: str) -> str:
    """Para GRAVAR (apelido, gatilho): minúsculo e sem pontuação, mas legível."""
    texto = re.sub(r'[^\w\s]', ' ', str(texto or '').lower())
    return ' '.join(texto.split())


def _codigo_pelo_texto(texto: str):
    t = normalizar(texto)
    if not t or t == normalizar(GENERICO):
        return None
    if 'celular' in t or 'eco' in t.split() or 'app business' in t:
        return 'eco_do_celular'
    if 'assumiu' in t or 'painel' in t:
        return 'atendente_assumiu'
    if ('ia nao conseguiu' in t or 'nao entend' in t or 'catalogo' in t
            or 'falha' in t or 'fallback' in t):
        return 'bot_nao_entendeu'
    if 'pediu' in t or 'atendente' in t or 'human handoff' in t or 'human_handoff' in t:
        return 'pediu_atendente'
    return 'outro'


def _inferir_do_generico(conversa, desde, feito_por_id):
    """O texto genérico não diz nada: o que aconteceu em volta da passagem diz.

    O botão "Atendente" do bot e o `_forcar_atendimento_humano` antigo
    passavam para humano sem motivo. A intenção registrada na mesma hora
    (IntentLog) e o eco do celular (mensagem de saída que veio do app, com o
    payload do webhook em `content`) contam a história.
    """
    if feito_por_id:
        return 'atendente_assumiu'
    if desde is None:
        return 'outro'
    from apps.automation.models import IntentLog
    from apps.whatsapp.models import Message

    intencoes = list(
        IntentLog.objects.filter(
            conversation=conversa,
            created_at__gte=desde - timedelta(minutes=3),
            created_at__lte=desde + timedelta(minutes=2),
        ).values_list('intent_type', 'metadata')
    )
    if any(tipo == 'human_handoff' for tipo, _ in intencoes):
        return 'pediu_atendente'
    if any(tipo in ('unknown', 'fallback') or (meta or {}).get('source') == 'fallback'
           for tipo, meta in intencoes):
        return 'bot_nao_entendeu'
    eco = Message.objects.filter(
        conversation=conversa, direction='outbound',
        created_at__gte=desde - timedelta(minutes=2),
        created_at__lte=desde + timedelta(minutes=1),
    ).filter(Q(content__has_key='from') | Q(content__has_key='to')).exclude(
        # `contains`, não `metadata__automatico=True`: no Postgres o exclude
        # por chave de JSON também derruba as linhas SEM a chave.
        metadata__contains={'automatico': True},
    )
    if eco.exists():
        return 'eco_do_celular'
    return 'outro'


def motivo(conversa) -> dict:
    """{codigo, texto, desde} da passagem MAIS RECENTE para humano.

    "Assumir" uma conversa que já era humana grava log humano→humano; esse
    não conta — senão assumir apagaria o motivo original (pediu atendente).
    """
    from apps.handover.models import HandoverLog

    log = (
        HandoverLog.objects.filter(conversation=conversa, to_status='human')
        .exclude(from_status='human')
        .order_by('-created_at')
        .first()
    )
    handover = getattr(conversa, 'handover', None) if _tem_handover(conversa) else None
    if log is not None:
        texto_cru, desde, feito_por = log.reason or '', log.created_at, log.performed_by_id
    elif handover is not None:
        texto_cru, desde, feito_por = handover.transfer_reason or '', handover.last_transfer_at, None
    else:
        texto_cru, desde, feito_por = '', None, None

    codigo = _codigo_pelo_texto(texto_cru) or _inferir_do_generico(conversa, desde, feito_por)
    texto = TEXTOS[codigo]
    if codigo == 'outro' and texto_cru and normalizar(texto_cru) != normalizar(GENERICO):
        texto = texto_cru
    return {'codigo': codigo, 'texto': texto, 'desde': desde.isoformat() if desde else None}


def _tem_handover(conversa) -> bool:
    try:
        return getattr(conversa, 'handover', None) is not None
    except Exception:  # RelatedObjectDoesNotExist
        return False


def esta_esperando(conversa) -> bool:
    escreveu = conversa.last_customer_message_at
    if not escreveu:
        return False
    respondemos = conversa.last_agent_message_at
    return respondemos is None or escreveu > respondemos


def esperando_desde(conversa):
    """Primeira mensagem do cliente ainda sem resposta — não a última.

    Quem mandou "oi" há 40 min e "alguém?" há 1 min espera há 40.
    """
    if not esta_esperando(conversa):
        return None
    from apps.whatsapp.models import Message

    mensagens = Message.objects.filter(conversation=conversa, direction='inbound')
    if conversa.last_agent_message_at:
        mensagens = mensagens.filter(created_at__gt=conversa.last_agent_message_at)
    primeira = mensagens.order_by('created_at').values_list('created_at', flat=True).first()
    return primeira or conversa.last_customer_message_at


def segundos_desde(marco, agora=None) -> int:
    if not marco:
        return 0
    return max(0, int(((agora or timezone.now()) - marco).total_seconds()))


def _loja(conversa):
    from apps.automation.services.context_service import AutomationContextService

    try:
        return AutomationContextService.resolve(conversation=conversa)
    except Exception:
        return None


def _dinheiro(valor):
    if valor in (None, ''):
        return None
    try:
        return str(Decimal(str(valor)).quantize(Decimal('0.01')))
    except (InvalidOperation, ValueError):
        return None


def _sessao(contexto, telefone):
    from apps.automation.models import CustomerSession
    from apps.core.utils import phone_variants

    if contexto is None or not (contexto.store or contexto.profile):
        return None
    variantes = [telefone, *phone_variants(telefone)]
    digitos = re.sub(r'\D', '', telefone or '')
    if digitos:
        variantes += [digitos, f'+{digitos}']
    escopo = Q(company__store=contexto.store) if contexto.store else Q(company=contexto.profile)
    return (
        CustomerSession.objects.filter(escopo, phone_number__in=list(dict.fromkeys(variantes)))
        .filter(status__in=['active', 'cart_created', 'checkout', 'payment_pending'])
        .order_by('-last_activity_at', '-created_at')
        .first()
    )


def _itens(pendentes, loja) -> list:
    from apps.stores.models import StoreCombo, StoreProduct

    ids_produto = [i.get('product_id') for i in pendentes if i.get('product_id')]
    ids_combo = [i.get('combo_id') for i in pendentes if i.get('combo_id')]
    produtos = {
        str(p.id): p for p in StoreProduct.objects.filter(id__in=ids_produto, **({'store': loja} if loja else {}))
    } if ids_produto else {}
    combos = {
        str(c.id): c for c in StoreCombo.objects.filter(id__in=ids_combo, **({'store': loja} if loja else {}))
    } if ids_combo else {}
    itens = []
    for item in pendentes:
        coisa = produtos.get(str(item.get('product_id'))) or combos.get(str(item.get('combo_id')))
        preco = item.get('unit_price') if item.get('unit_price') not in (None, '') else getattr(coisa, 'price', None)
        itens.append({
            'nome': item.get('name') or getattr(coisa, 'name', None) or 'Item',
            'quantidade': int(item.get('quantity') or 1),
            'preco': _dinheiro(preco),
        })
    return itens


def carrinho(conversa, contexto=None) -> dict:
    vazio = {'passo': 'nenhum', 'itens': [], 'endereco': None, 'taxa': None, 'notas': '', 'entrega': None}
    sessao = _sessao(contexto, conversa.phone_number)
    if sessao is None:
        return vazio
    dados = sessao.cart_data or {}
    if dados.get('waiting_for_address'):
        passo = 'endereco'
    elif dados.get('waiting_for_notes'):
        passo = 'observacao'
    elif sessao.status in ('checkout', 'payment_pending'):
        passo = 'pagamento'
    else:
        passo = 'nenhum'
    return {
        'passo': passo,
        'itens': _itens(dados.get('pending_items') or [], getattr(contexto, 'store', None)),
        'endereco': dados.get('delivery_address') or None,
        'taxa': _dinheiro(dados.get('delivery_fee_calculated')),
        'notas': dados.get('customer_notes') or '',
        'entrega': dados.get('pending_delivery_method') or None,
    }


def nome_do_cliente(conversa) -> str:
    nome = (conversa.contact_name or '').strip() or (getattr(conversa, 'anno_unified_name', '') or '').strip()
    if not nome:
        from apps.users.models import UnifiedUser

        nome = (
            UnifiedUser.objects.filter(phone_number=conversa.phone_number)
            .values_list('name', flat=True).first() or ''
        ).strip()
    return nome or conversa.phone_number


def cliente(conversa, contexto=None) -> dict:
    from django.db.models import Count, Max

    from apps.core.utils import phone_variants
    from apps.stores.models import StoreOrder

    loja = getattr(contexto, 'store', None)
    pedidos, ultimo = 0, None
    if loja is not None:
        agregado = StoreOrder.objects.filter(
            store=loja, customer_phone__in=[conversa.phone_number, *phone_variants(conversa.phone_number)],
        ).aggregate(n=Count('id'), ultimo=Max('created_at'))
        pedidos, ultimo = agregado['n'] or 0, agregado['ultimo']
    return {
        'nome': nome_do_cliente(conversa),
        'telefone': conversa.phone_number,
        'pedidos': pedidos,
        'ultimo_pedido': ultimo.isoformat() if ultimo else None,
    }


def contexto_do_bot(conversa, agora=None) -> dict:
    agora = agora or timezone.now()
    contexto = _loja(conversa)
    desde = esperando_desde(conversa)
    return {
        'modo': conversa.mode,
        'motivo': motivo(conversa),
        'esperando_ha_segundos': segundos_desde(desde, agora),
        'ultima_msg_cliente': conversa.last_customer_message_at.isoformat() if conversa.last_customer_message_at else None,
        'ultima_msg_atendente': conversa.last_agent_message_at.isoformat() if conversa.last_agent_message_at else None,
        'carrinho': carrinho(conversa, contexto),
        'cliente': cliente(conversa, contexto),
    }


def atendente(conversa):
    agente = conversa.assigned_agent
    if agente is None:
        return None
    return {'id': agente.id, 'nome': (agente.get_full_name() or agente.username).strip()}
