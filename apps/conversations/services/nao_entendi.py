"""O que o bot não entendeu — e o dono ensinando.

`IntentLog` grava toda mensagem desde 23/09; as de intenção `unknown` e as
que caíram no `fallback` são exatamente onde o bot está falhando com cliente
de verdade. Aqui elas viram lista (deduplicada: "Tem coca zero?" e "tem coca
zero" são a mesma dúvida) e cada linha pode ser resolvida:

- `produto`: o texto vira apelido do produto (`StoreProduct.metadata['apelidos']`);
- `resposta`: pergunta + resposta viram conhecimento da IA (`AgentKnowledgeEntry`
  manual, injetado no prompt). Até 28/09 gravava uma `AutoMessage` com
  `gatilhos` que nenhum código lia — o dono ensinava e nada mudava;
- `regra`: a resposta vira um FATO da loja (`Store.metadata['bot_fatos']`);
- `ignorar`: some da lista.

A lista mostra só FALHA DE VERDADE por padrão (`todas=1` desliga o filtro):
`intent=unknown` é o regex antes da IA, e a IA acerta a maioria desses.

Resolvida, a dúvida sai da lista (marca em `IntentLog.metadata`).
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .operacao_humana import normalizar, normalizar_mantendo_acento

TIPOS = ('unknown', 'fallback')
ACOES = ('produto', 'resposta', 'regra', 'ignorar')
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


import re

# O que o bot respondeu quando falhou. Medido em 28/09 nas duas lojas.
_RESPOSTA_DE_FALHA = re.compile(
    r'(?i)(probleminha|pode repetir|não entendi|nao entendi|não consegui|nao consegui|travou'
    r'|não encontrei|nao encontrei|como posso te ajudar\?|tente novamente|erro ao )'
)
# A saudação genérica que a IA dá quando não sabe o que fazer com o texto.
_RESPOSTA_GENERICA = re.compile(r'(?i)(que bom que (você )?entrou em contato|o que você gostaria de saber)')
_ENTRADA_E_SAUDACAO = re.compile(r'(?i)^\s*(oi+|ol[aá]+|bom dia+|boa tarde+|boa noite+|e a[ií]|opa+|hey+|hello+)\b')
_SEM_LETRA = re.compile(r'^[^a-zA-Zà-ÿÀ-Ý]*$')
_EMAIL_OU_LINK = re.compile(r'(?i)(@|https?://|www\.|\.com\b|\.br\b|goo\.gl|maps\.app)')


def falha_de_verdade(texto: str, resposta: str) -> bool:
    """A IA falhou com ESTA mensagem, ou só o regex não a reconheceu?

    Telefone, e-mail e link não têm o que ensinar. Resposta boa a pergunta
    boa não é falha. Saudação genérica a algo que não é saudação, é.
    """
    texto = (texto or '').strip()
    resposta = (resposta or '').strip()
    if not texto or _SEM_LETRA.match(texto) or _EMAIL_OU_LINK.search(texto):
        return False
    if not resposta or _RESPOSTA_DE_FALHA.search(resposta):
        return True
    if _RESPOSTA_GENERICA.search(resposta) and not _ENTRADA_E_SAUDACAO.match(texto):
        return True
    return False


def listar(lojas_ids, dias=7, todas=False) -> list:
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
        if not todas and not falha_de_verdade(linha['message_text'], linha['response_text']):
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


def _agente_da_loja(loja):
    from apps.automation.models import CompanyProfile

    perfil = CompanyProfile.objects.filter(store=loja).first()
    agente = perfil.get_default_agent() if perfil else None
    if agente is None:
        raise PedidoInvalido('A loja não tem atendente de IA ativo — ensinar resposta só vale com a IA ligada.')
    return agente


def _resposta(loja, texto, resposta):
    """Pergunta + resposta viram conhecimento manual do agente da loja (upsert pelo texto)."""
    from apps.agents.models import AgentKnowledgeEntry

    agente = _agente_da_loja(loja)
    pergunta = normalizar_mantendo_acento(texto)
    alvo = normalizar(pergunta)
    existente = next(
        (
            e for e in AgentKnowledgeEntry.objects.filter(agent=agente, store=loja, source__in=('manual', 'reviewed'))
            if normalizar(e.example_input) == alvo
        ),
        None,
    )
    if existente is None:
        existente = AgentKnowledgeEntry(
            agent=agente, store=loja, source=AgentKnowledgeEntry.SourceChoice.MANUAL,
            topic=_tema_da_pergunta(pergunta), example_input=pergunta,
        )
    existente.example_response = resposta
    existente.confidence = 1.0
    existente.is_active = True
    existente.save()
    return {'conhecimento_id': str(existente.id), 'pergunta': pergunta}


def _tema_da_pergunta(texto: str) -> str:
    from apps.agents.learning import _classify_topic

    return _classify_topic(texto)


TEMAS_DE_FATO = ('loja', 'produtos', 'entrega', 'pagamento', 'horarios', 'outro')


def _regra(loja, tema, resposta):
    """A resposta vira um fato em `Store.metadata['bot_fatos']` (sem duplicar)."""
    tema = tema if tema in TEMAS_DE_FATO else 'outro'
    dados = dict(loja.metadata or {})
    fatos = [f for f in (dados.get('bot_fatos') or []) if isinstance(f, dict)]
    fato = {'tema': tema, 'texto': resposta, 'ativo': True}
    if not any(normalizar(str(f.get('texto') or '')) == normalizar(resposta) for f in fatos):
        fatos.append(fato)
    dados['bot_fatos'] = fatos
    loja.metadata = dados
    loja.save(update_fields=['metadata', 'updated_at'])
    return {'fato': fato}


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
    elif acao == 'regra':
        resposta = (dados.get('resposta') or '').strip()
        if not resposta:
            raise PedidoInvalido('Informe o fato.')
        resultado.update(_regra(loja, dados.get('tema'), resposta))
        marca = {'ensinado': 'regra'}
    else:
        marca = {'ignorado': True}

    if usuario is not None:
        marca['resolvido_por'] = usuario.id
    marca['resolvido_em'] = timezone.now().isoformat()
    resultado['marcadas'] = _marcar(loja, texto, marca)
    return resultado
