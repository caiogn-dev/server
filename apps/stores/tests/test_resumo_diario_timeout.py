"""O resumo do painel não pode esperar o LLM sem pressa.

Sintoma em produção (08/ago): clicar em atualizar no card devolvia "Não foi
possível atualizar o resumo IA". O serviço estava certo — o provedor é que
demorava. Com `timeout=45` e as 2 novas tentativas do cliente OpenAI, uma
chamada morta consumia ~135s antes de desistir. O navegador desiste muito
antes, então o dono via erro num fluxo que, do lado do servidor, tinha
terminado bem: o template gerou os quatro blocos.

Pior: só o resultado de LLM era cacheado. Sem cache, TODA visita à home
pagava o timeout inteiro de novo — inclusive a primeira do dia, que é
justamente quando o dono abre o painel.

Duas correções, uma para cada metade do problema:
  - orçamento de tempo curto no LLM deste caminho;
  - cachear também o template, com TTL curto, para não repetir a espera.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store
from apps.stores.services import ai_insights

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-to', email='to@x.com', password='x')
    return Store.objects.create(name='Loja TO', slug='loja-to', owner=dono, status='active')


@pytest.mark.django_db
class TestOrcamentoDeTempo:
    def test_o_llm_do_painel_tem_prazo_curto(self, loja):
        # 45s x 3 tentativas = mais de dois minutos. Nenhum navegador espera
        # isso, e o card já tem o template pronto para mostrar no lugar.
        capturado = {}

        class _FakeLLM:
            def invoke(self, _):
                raise RuntimeError('não deve chegar aqui')

        def _fake_create_llm(agent):
            capturado['timeout'] = agent.timeout
            capturado['max_retries'] = getattr(agent, 'max_retries', None)
            return _FakeLLM()

        with patch('apps.agents.runtime.factory.create_llm', _fake_create_llm):
            ai_insights.get_insights_llm()

        assert capturado['timeout'] <= 20, (
            f"resumo do painel com timeout de {capturado['timeout']}s — o dono "
            'desiste antes, e o template já está pronto'
        )

    def test_llm_lento_nao_deixa_o_painel_sem_resposta(self, loja):
        # O contrato que importa: LLM indisponível vira template, não erro.
        with patch.object(ai_insights, '_llm_text', side_effect=TimeoutError('demorou')):
            r = ai_insights.generate_daily_summary(loja)
        assert r['source'] == 'template'
        assert r['blocos']
