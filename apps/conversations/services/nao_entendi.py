"""O que o bot não entendeu — e o dono ensinando.

`IntentLog` grava toda mensagem desde 23/09; as de intenção `unknown` e as
que caíram no `fallback` são exatamente onde o bot está falhando com cliente
de verdade. Aqui elas viram lista (deduplicada: "Tem coca zero?" e "tem coca
zero" são a mesma dúvida) e cada linha pode ser resolvida:

- `produto`: o texto vira apelido do produto (`StoreProduct.metadata['apelidos']`);
- `resposta`: o texto vira gatilho de uma resposta pronta da loja (`AutoMessage`);
- `ignorar`: some da lista.

Resolvida, a dúvida sai da lista (marca em `IntentLog.metadata`).
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .operacao_humana import normalizar, normalizar_mantendo_acento

TIPOS = ('unknown', 'fallback')
ACOES = ('produto', 'resposta', 'ignorar')
LIMITE_DE_LINHAS = 3000


class PedidoInvalido(Exception):
    """400 — corpo sem o que a ação precisa."""


class NaoEncontrado(Exception):
    """404 — produto que não é da loja."""


def _logs_das_lojas(lojas_ids):
    from apps.automation.models import IntentLog

    return (
        IntentLog.objects.filter(
            Q(company__store_id__in=lojas_ids) | Q(company__account__stores__id__in=lojas_ids)
        )
        .filter(Q(intent_type__in=TIPOS) | Q(metadata__source='fallback'))
        # `contains`: exclude por chave de JSON derrubaria as linhas sem a chave.
        .exclude(metadata__contains={'ignorado': True})
        .exclude(metadata__has_key='ensinado')
    )


def listar(lojas_ids, dias=7) -> list:
    try:
        dias = max(1, min(int(dias or 7), 90))
    except (TypeError, ValueError):
        dias = 7
    desde = timezone.now() - timedelta(days=dias)
    linhas = (
        _logs_das_lojas(lojas_ids)
        .filter(created_at__gte=desde)
        .order_by('-created_at')
        .distinct()
        .values('id', 'conversation_id', 'phone_number', 'message_text', 'created_at', 'response_text')
        [:LIMITE_DE_LINHAS]
    )
    grupos = {}
    for linha in linhas:
        chave = normalizar(linha['message_text'])
        if not chave:
            continue
        if chave in grupos:
            grupos[chave]['vezes'] += 1
            continue
        grupos[chave] = {
            'id': str(linha['id']),
            'conversa_id': str(linha['conversation_id']) if linha['conversation_id'] else None,
            'telefone': linha['phone_number'],
            'texto': normalizar_mantendo_acento(linha['message_text']),
            'quando': linha['created_at'].isoformat(),
            'resposta_do_bot': linha['response_text'] or '',
            'vezes': 1,
        }
    return list(grupos.values())  # dict preserva a ordem: mais recente primeiro


def _marcar(loja, texto, marca: dict) -> int:
    from apps.automation.models import IntentLog

    alvo = normalizar(texto)
    ids = [
        pk for pk, msg in _logs_das_lojas([loja.id]).distinct().values_list('id', 'message_text')
        if normalizar(msg) == alvo
    ]
    marcadas = 0
    for log in IntentLog.objects.filter(id__in=ids):
        log.metadata = {**(log.metadata or {}), **marca}
        log.save(update_fields=['metadata'])
        marcadas += 1
    return marcadas


def _apelido(loja, texto, produto_id):
    from django.core.exceptions import ValidationError

    from apps.stores.models import StoreProduct

    try:
        produto = StoreProduct.objects.filter(store=loja, id=produto_id).first()
    except (ValueError, ValidationError):
        produto = None
    if produto is None:
        raise NaoEncontrado('Produto não encontrado nesta loja.')
    apelido = normalizar_mantendo_acento(texto)
    dados = dict(produto.metadata or {})
    apelidos = list(dados.get('apelidos') or [])
    if apelido not in apelidos:
        apelidos.append(apelido)
    dados['apelidos'] = apelidos
    produto.metadata = dados
    produto.save(update_fields=['metadata', 'updated_at'])
    return {'produto_id': str(produto.id), 'apelidos': apelidos}


def _resposta(loja, texto, resposta):
    from apps.automation.models import AutoMessage, CompanyProfile

    perfil = CompanyProfile.objects.filter(store=loja).first() or loja.get_automation_profile()
    gatilho = normalizar_mantendo_acento(texto)
    existente = next(
        (
            m for m in AutoMessage.objects.filter(company=perfil, conditions__origem='nao_entendi')
            if normalizar(' '.join((m.conditions or {}).get('gatilhos') or [])) == normalizar(gatilho)
        ),
        None,
    )
    if existente is None:
        existente = AutoMessage(
            company=perfil,
            event_type=AutoMessage.EventType.CUSTOM,
            name=f'Resposta ensinada: {gatilho}'[:255],
            conditions={'origem': 'nao_entendi', 'tipo': 'palavra_chave', 'gatilhos': [gatilho]},
        )
    existente.message_text = resposta
    existente.is_active = True
    existente.save()
    return {'auto_message_id': str(existente.id), 'gatilho': gatilho}


def ensinar(loja, dados: dict, usuario=None) -> dict:
    texto = (dados.get('texto') or '').strip()
    acao = dados.get('acao')
    if not normalizar(texto):
        raise PedidoInvalido('Informe o texto.')
    if acao not in ACOES:
        raise PedidoInvalido(f'acao deve ser uma de {", ".join(ACOES)}.')

    resultado = {'acao': acao, 'texto': normalizar_mantendo_acento(texto)}
    if acao == 'produto':
        if not dados.get('produto_id'):
            raise PedidoInvalido('Informe produto_id.')
        resultado.update(_apelido(loja, texto, dados['produto_id']))
        marca = {'ensinado': 'produto'}
    elif acao == 'resposta':
        resposta = (dados.get('resposta') or '').strip()
        if not resposta:
            raise PedidoInvalido('Informe a resposta.')
        resultado.update(_resposta(loja, texto, resposta))
        marca = {'ensinado': 'resposta'}
    else:
        marca = {'ignorado': True}

    if usuario is not None:
        marca['resolvido_por'] = usuario.id
    marca['resolvido_em'] = timezone.now().isoformat()
    resultado['marcadas'] = _marcar(loja, texto, marca)
    return resultado
