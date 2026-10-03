"""Relatório de IA do painel: um modelo NVIDIA que falha não pode virar silêncio.

MEDIDO EM 02/out/2026 (prompt real do resumo diário da Cê Saladas, direto na
NIM, 6 chamadas por modelo):

    nvidia/nemotron-3-super-120b-a12b   6/6 JSON   1,4–7,3 s   ← primeiro
    nvidia/nemotron-3-ultra-550b-a55b   3/3 JSON   6,6–19,9 s  ← segundo
    openai/gpt-oss-20b                  5/6 JSON   7,9–29,9 s  (1 resposta VAZIA)
    nvidia/llama-3.1-nemotron-70b       404 3/3 — LISTADO em /v1/models
    nvidia/nemotron-nano-3-30b-a3b      404 3/3 — LISTADO em /v1/models

O que estava errado no caminho do painel:

  1. Uma tentativa só. Se o nemotron-super pendurasse, o resumo ia direto
     para o template — o segundo degrau da escada (gpt-oss-20b, 19–30 s)
     nem caberia no prazo de 18 s, então a "escada" era de um degrau.
  2. O cliente OpenAI do langchain refaz a chamada 2x por padrão: o prazo
     "de 18 s" era na verdade até 54 s com a NIM pendurada.
  3. Resposta 200 com conteúdo vazio ou prosa caía no template SEM log
     nenhum: a falha do modelo era indistinguível de "não tinha o que dizer".
  4. Sem chave NVIDIA o painel tentava Anthropic/Kimi/OpenAI — fora da regra
     da casa (provedor é NVIDIA NIM, ponto).
  5. `/v1/models` lista modelos que dão 404 para a conta; o catálogo vivo
     confiava na listagem e aceitava pedir um defunto.
"""
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.agents.runtime import modelos
from apps.stores.services import ai_insights

# 03/out/2026: o super-120b morreu (410). A escada medida virou ultra → gpt-oss-20b.
# Os nomes PRIMEIRO/SEGUNDO seguem o lugar na escada, não o modelo.
PRIMEIRO = 'nvidia/nemotron-3-ultra-550b-a55b'
SEGUNDO = 'openai/gpt-oss-20b'

JSON_BOM = '{"blocos":[{"tipo":"resultado","titulo":"Ontem","texto":"3 pedidos."}]}'


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, comportamento):
        self.comportamento = comportamento

    def bind(self, **_):
        return self

    def invoke(self, _prompt):
        if isinstance(self.comportamento, Exception):
            raise self.comportamento
        return _Resp(self.comportamento)


def _fabrica(por_modelo, registro):
    """`create_llm` falso: cada modelo responde do seu jeito."""
    def _create_llm(agent):
        registro.append({
            'model': agent.model_name,
            'provider': agent.provider,
            'timeout': agent.timeout,
            'max_retries': getattr(agent, 'max_retries', None),
        })
        return _FakeLLM(por_modelo.get(agent.model_name, RuntimeError('modelo inesperado')))
    return _create_llm


@pytest.fixture(autouse=True)
def catalogo_com_os_dois():
    with patch.object(modelos, 'catalogo_vivo', return_value=frozenset({PRIMEIRO, SEGUNDO})):
        yield


def _loja():
    return type('Loja', (), {'name': 'Cê Saladas', 'id': 1})()


def _resumo(por_modelo, registro):
    with override_settings(NVIDIA_API_KEY='nvapi-teste', NVIDIA_INSIGHTS_MODEL=''), \
         patch('apps.agents.runtime.factory.create_llm', _fabrica(por_modelo, registro)), \
         patch.object(ai_insights, 'compute_daily_stats', return_value={
             'date': '2026-10-01', 'orders': 3, 'revenue': 90.0, 'avg_ticket': 30.0,
             'orders_prev_day': 2, 'revenue_prev_day': 60.0, 'top_products': [],
             'peak_hour': 12, 'cancelled': 0}), \
         patch.object(ai_insights, 'compute_forecast', return_value={'trend_pct': 1.0}):
        return ai_insights.generate_daily_summary(_loja())


class TestEscadaDeModelos:
    def test_primeiro_pendura_segundo_nvidia_responde(self):
        registro = []
        r = _resumo({PRIMEIRO: TimeoutError('read timeout'), SEGUNDO: JSON_BOM}, registro)

        assert r['source'] == 'llm'
        assert r['model'] == SEGUNDO
        assert [c['model'] for c in registro] == [PRIMEIRO, SEGUNDO]

    def test_resposta_vazia_nao_vira_insight_tenta_o_proximo(self):
        """O gpt-oss-20b devolveu 200 com content='' em 1 de 6 chamadas."""
        registro = []
        r = _resumo({PRIMEIRO: '', SEGUNDO: JSON_BOM}, registro)

        assert r['source'] == 'llm'
        assert r['model'] == SEGUNDO

    def test_prosa_sem_json_tenta_o_proximo(self):
        registro = []
        r = _resumo({PRIMEIRO: 'Claro! Aqui vai o resumo do dia...', SEGUNDO: JSON_BOM}, registro)
        assert r['model'] == SEGUNDO

    def test_todos_falham_template_com_motivo_visivel(self, caplog):
        registro = []
        with caplog.at_level('ERROR', logger='apps.stores.services.ai_insights'):
            r = _resumo({PRIMEIRO: TimeoutError('read timeout'), SEGUNDO: ''}, registro)

        assert r['source'] == 'template'
        assert r['blocos']
        # O motivo sai no payload e no log ERROR — não só num WARNING que
        # ninguém lê.
        assert PRIMEIRO in r['llm_error'] and SEGUNDO in r['llm_error']
        assert 'vazia' in r['llm_error']
        assert any(rec.levelname == 'ERROR' for rec in caplog.records)

    def test_sucesso_nao_traz_llm_error(self):
        r = _resumo({PRIMEIRO: JSON_BOM}, [])
        assert r['source'] == 'llm'
        assert r['model'] == PRIMEIRO
        assert not r.get('llm_error')


class TestOrcamentoDeTempo:
    def test_cliente_nao_refaz_a_chamada_sozinho(self):
        registro = []
        _resumo({PRIMEIRO: TimeoutError('x'), SEGUNDO: TimeoutError('y')}, registro)
        assert registro and all(c['max_retries'] == 0 for c in registro)

    def test_soma_dos_prazos_cabe_no_orcamento_do_painel(self):
        # Relógio falso: cada tentativa gasta o prazo inteiro, como a NIM
        # pendurada faz de verdade.
        relogio = {'t': 1000.0}
        registro = []

        class _Pendura(_FakeLLM):
            def __init__(self, prazo):
                self.prazo = prazo

            def invoke(self, _prompt):
                relogio['t'] += self.prazo
                raise TimeoutError('read timeout')

        def _create_llm(agent):
            registro.append({'timeout': agent.timeout})
            return _Pendura(agent.timeout)

        with override_settings(NVIDIA_API_KEY='nvapi-teste', NVIDIA_INSIGHTS_MODEL=''), \
             patch('apps.agents.runtime.factory.create_llm', _create_llm), \
             patch('time.monotonic', lambda: relogio['t']), \
             patch.object(ai_insights, 'compute_daily_stats', return_value={
                 'date': '2026-10-01', 'orders': 0, 'revenue': 0, 'avg_ticket': 0,
                 'orders_prev_day': 0, 'top_products': [], 'peak_hour': None,
                 'cancelled': 0}), \
             patch.object(ai_insights, 'compute_forecast', return_value={}):
            r = ai_insights.generate_daily_summary(_loja())

        assert r['source'] == 'template'
        assert len(registro) == 2
        # Pior caso real: cada tentativa gasta o prazo inteiro.
        assert sum(c['timeout'] for c in registro) <= ai_insights.LLM_TIMEOUT_PAINEL
        # E o primeiro não pode comer o orçamento todo: o super responde em
        # até 7,3 s medidos, sobra tempo para o segundo degrau.
        assert registro[0]['timeout'] <= ai_insights.LLM_TIMEOUT_TENTATIVA < ai_insights.LLM_TIMEOUT_PAINEL

    def test_factory_repassa_max_retries_ao_cliente(self):
        from apps.agents.models import Agent
        from apps.agents.runtime.factory import create_llm

        agent = Agent(name='x', provider=Agent.AgentProvider.NVIDIA, model_name=PRIMEIRO,
                      temperature=0.3, max_tokens=100, timeout=10, base_url='')
        agent.max_retries = 0
        with override_settings(NVIDIA_API_KEY='nvapi-teste'):
            llm = create_llm(agent)
        assert llm.max_retries == 0


class TestSoNvidia:
    @override_settings(NVIDIA_API_KEY='', OPENAI_API_KEY='sk-x', ANTHROPIC_API_KEY='sk-ant',
                       KIMI_API_KEY='k')
    def test_sem_chave_nvidia_nao_cai_em_outro_provedor(self):
        registro = []
        with patch('apps.agents.runtime.factory.create_llm', _fabrica({}, registro)):
            with pytest.raises(RuntimeError):
                ai_insights.get_insights_llm()
        assert registro == []


class TestConversas:
    def test_conversa_primeiro_sem_json_segundo_responde(self):
        registro = []
        bom = '{"faqs": [], "complaints": [], "opportunities": [], "sentiment": "neutro", "summary": "ok"}'
        with override_settings(NVIDIA_API_KEY='nvapi-teste', NVIDIA_INSIGHTS_MODEL=''), \
             patch('apps.agents.runtime.factory.create_llm',
                   _fabrica({PRIMEIRO: 'não sei', SEGUNDO: bom}, registro)), \
             patch.object(ai_insights, 'collect_conversation_sample', return_value=['oi']):
            r = ai_insights.generate_conversation_insights(_loja())
        assert r['source'] == 'llm'
        assert r['model'] == SEGUNDO

    def test_conversa_todos_falham_mostra_motivo(self):
        with override_settings(NVIDIA_API_KEY='nvapi-teste', NVIDIA_INSIGHTS_MODEL=''), \
             patch('apps.agents.runtime.factory.create_llm',
                   _fabrica({PRIMEIRO: '', SEGUNDO: TimeoutError('t')}, [])), \
             patch.object(ai_insights, 'collect_conversation_sample', return_value=['oi']):
            r = ai_insights.generate_conversation_insights(_loja())
        assert r['source'] == 'error'
        assert PRIMEIRO in r['llm_error']


class TestCatalogoListadoNaoEServido:
    def test_aposentado_listado_no_catalogo_continua_recusado(self):
        """`/v1/models` lista o llama-3.1-nemotron-70b, mas ele dá 404."""
        morto = 'nvidia/llama-3.1-nemotron-70b-instruct'
        assert morto in modelos.MODELOS_APOSENTADOS
        with patch.object(modelos, 'catalogo_vivo', return_value=frozenset({morto, PRIMEIRO})):
            assert modelos.modelo_vivo(morto) == PRIMEIRO

    def test_escada_comeca_pelo_pedido_e_so_tem_vivos(self):
        with patch.object(modelos, 'catalogo_vivo', return_value=frozenset({PRIMEIRO, SEGUNDO, 'x/y'})):
            escada = modelos.escada_de_modelos('x/y')
        assert escada[0] == 'x/y'
        assert escada[1:] == [PRIMEIRO, SEGUNDO]

    def test_escada_sem_repetir_e_sem_lapide(self):
        with patch.object(modelos, 'catalogo_vivo', return_value=None):
            escada = modelos.escada_de_modelos(PRIMEIRO)
        assert escada[0] == PRIMEIRO
        assert len(escada) == len(set(escada))
        assert not set(escada) & modelos.MODELOS_APOSENTADOS

    def test_segundo_degrau_e_o_ultra_medido(self):
        assert modelos.PREFERENCIA[:2] == (PRIMEIRO, SEGUNDO)


class TestPromptDizQueDiaFoiOntem:
    def test_prompt_nomeia_o_dia_de_ontem(self):
        """02/out (sexta): o resumo comparou ONTEM (quinta) com a "média de
        sexta" — o prompt só dava a média do dia de hoje."""
        capturado = {}

        def espiao(prompt):
            capturado['p'] = prompt
            raise RuntimeError('sem modelo')

        with patch.object(ai_insights, '_llm_text', espiao), \
             patch.object(ai_insights, 'compute_daily_stats', return_value={
                 'date': '2026-10-01', 'orders': 0, 'revenue': 0, 'avg_ticket': 0,
                 'orders_prev_day': 0, 'top_products': [], 'peak_hour': None,
                 'cancelled': 0}), \
             patch.object(ai_insights, 'compute_forecast', return_value={}):
            ai_insights.generate_daily_summary(_loja())

        # 01/10/2026 é quinta — o dia dos números, não o dia de hoje.
        assert 'ONTEM foi quinta' in capturado['p']
