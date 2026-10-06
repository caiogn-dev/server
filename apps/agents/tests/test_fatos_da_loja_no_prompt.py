"""O que o dono confirmou entra no prompt como FATO; o resto a IA não chuta.

28/09/2026, Cê Saladas, 12:11: "quantos dias dura a salada na geladeira?".
A IA respondeu "até 24 horas" — inventado. A loja nunca disse isso a ela.
O prompt já proibia inventar, mas proibição sem fonte só troca o chute por
um chute educado. Aqui o dono escreve os fatos no painel
(`store.metadata['bot_fatos']`) e eles chegam ao modelo com a ordem: o que
não está aqui, diga que vai confirmar.
"""
import pytest

from apps.agents.graph.nodes import _build_system_prompt, _load_knowledge_context, fatos_da_loja
from apps.agents.models import Agent, AgentKnowledgeEntry
from apps.stores.tests.factories import make_store


@pytest.fixture
def agent(db):
    return Agent.objects.create(name='Atendente', provider=Agent.AgentProvider.NVIDIA, system_prompt='')


def _state(store, **extra):
    base = {
        'store': store, 'messages': [], 'store_context': 'Itens: • Salada — R$ 28,00',
        'delivery_info': 'Taxa varia.', 'customer_context': '', 'knowledge_context': '',
    }
    base.update(extra)
    return base


def _loja_com_fatos(fatos):
    store = make_store()
    store.metadata = {**(store.metadata or {}), 'bot_fatos': fatos}
    store.save(update_fields=['metadata'])
    return store


def test_fatos_ativos_entram_agrupados_por_tema(agent, db):
    store = _loja_com_fatos([
        {'tema': 'produtos', 'texto': 'A salada dura até 2 dias na geladeira, fechada.', 'ativo': True},
        {'tema': 'entrega', 'texto': 'Entregamos em Taquaralto de segunda a sexta.', 'ativo': True},
        {'tema': 'entrega', 'texto': 'Fato desligado', 'ativo': False},
    ])

    prompt = _build_system_prompt(_state(store), agent)

    assert 'O QUE A LOJA CONFIRMOU' in prompt
    assert 'Produtos' in prompt and 'dura até 2 dias' in prompt
    assert 'Entrega' in prompt and 'Taquaralto' in prompt
    assert 'Fato desligado' not in prompt
    # A ordem que evita o chute: sem fato, confirma com a loja.
    assert 'diga que vai confirmar' in prompt


def test_sem_fatos_a_secao_nao_existe(agent, db):
    prompt = _build_system_prompt(_state(make_store()), agent)
    assert 'O QUE A LOJA CONFIRMOU' not in prompt


def test_fatos_da_loja_ignora_lixo_no_metadata(db):
    store = _loja_com_fatos(['string solta', {'tema': 'x'}, {'texto': '   '}, {'texto': 'Vale', 'tema': 'zzz'}])
    texto = fatos_da_loja(store)
    assert 'Vale' in texto
    assert 'string solta' not in texto


def test_conhecimento_manual_vem_antes_do_automatico_e_cabem_mais_de_cinco(agent, db):
    """Os 5 automáticos de confiança 1.0 empurravam o ensino do dono para fora.

    06/10: o extraído sozinho nem entra mais (ensinava promoção velha e erro);
    só manual e aprovado. A regra de ordem e de espaço continua.
    """
    store = make_store()
    for i in range(6):
        AgentKnowledgeEntry.objects.create(
            agent=agent, store=store, topic='cardapio', source='reviewed', confidence=1.0,
            example_input=f'aprovado {i}', example_response=f'resposta aprovada {i}',
        )
    AgentKnowledgeEntry.objects.create(
        agent=agent, store=store, topic='cardapio', source='auto', confidence=1.0,
        example_input='auto velho', example_response='hoje a promoção é o camarão',
    )
    AgentKnowledgeEntry.objects.create(
        agent=agent, store=store, topic='outro', source='manual', confidence=1.0,
        example_input='aceita vale refeição?', example_response='Aceitamos VR e VA.',
    )

    contexto = _load_knowledge_context(agent=agent, store=store)

    assert 'Cliente: "aceita vale refeição?"' in contexto
    assert contexto.count('Cliente:') >= 7
    assert 'auto velho' not in contexto
