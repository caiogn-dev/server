"""O resumo do dia devolve BLOCOS, não um parágrafo.

O card do painel recebia `summary` como texto corrido de 4 a 6 frases e
imprimia tudo num bloco só. Três problemas:

  - parágrafo denso não se lê no celular entre um pedido e outro, que é onde e
    quando o dono abre o painel;
  - a informação tem naturezas diferentes — como foi ontem, para onde está
    indo, o que fazer hoje — e o texto corrido nivela as três;
  - a AÇÃO, que é a única parte acionável, fica enterrada na última frase.

Agora o LLM devolve `blocos`: uma lista de `{tipo, titulo, texto}`. `summary`
continua existindo, montado a partir dos blocos, porque há consumidor antigo
(WhatsApp, e-mail) que só sabe lidar com texto.

O fallback de template produz os MESMOS blocos: quando o LLM cai — e ele cai,
o provedor é externo — a tela não pode mudar de forma.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store
from apps.stores.services import ai_insights

User = get_user_model()

TIPOS_VALIDOS = {'resultado', 'tendencia', 'atencao', 'acao'}


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-ai', email='ai@x.com', password='x')
    return Store.objects.create(name='Loja AI', slug='loja-ai', owner=dono, status='active')


@pytest.mark.django_db
class TestResumoEstruturado:
    def test_sem_llm_o_template_produz_blocos(self, loja):
        # O provedor é externo e cai. Quando cair, a tela não pode mudar de
        # forma — se o fallback devolvesse só texto, o card alternaria entre
        # dois layouts sem ninguém entender por quê.
        with patch.object(ai_insights, '_llm_text', side_effect=RuntimeError('sem LLM')):
            r = ai_insights.generate_daily_summary(loja)

        assert r['source'] == 'template'
        assert isinstance(r['blocos'], list) and r['blocos'], 'template precisa gerar blocos'
        for b in r['blocos']:
            assert b['tipo'] in TIPOS_VALIDOS, b
            assert b['titulo'] and b['texto']

    def test_summary_continua_existindo_para_quem_so_le_texto(self, loja):
        # WhatsApp e e-mail consomem `summary`. Trocar o contrato sem manter o
        # campo quebraria os dois em silêncio.
        with patch.object(ai_insights, '_llm_text', side_effect=RuntimeError('x')):
            r = ai_insights.generate_daily_summary(loja)
        assert isinstance(r['summary'], str) and r['summary'].strip()

    def test_resposta_do_llm_em_json_vira_blocos(self, loja):
        resposta = (
            '{"blocos":[{"tipo":"resultado","titulo":"Ontem","texto":"12 pedidos."},'
            '{"tipo":"acao","titulo":"Hoje","texto":"Reforce as 19h."}]}'
        )
        with patch.object(ai_insights, '_llm_text', return_value=resposta):
            r = ai_insights.generate_daily_summary(loja)

        assert r['source'] == 'llm'
        assert [b['tipo'] for b in r['blocos']] == ['resultado', 'acao']
        # O texto de compatibilidade sai dos blocos, não de uma segunda geração.
        assert '12 pedidos.' in r['summary'] and 'Reforce as 19h.' in r['summary']

    def test_json_embrulhado_em_cerca_de_codigo_ainda_e_lido(self, loja):
        # Modelo instruído a devolver JSON devolve ```json ... ``` metade das
        # vezes. Falhar nisso jogaria todo mundo no template sem motivo.
        resposta = '```json\n{"blocos":[{"tipo":"acao","titulo":"Hoje","texto":"Ligue o cupom."}]}\n```'
        with patch.object(ai_insights, '_llm_text', return_value=resposta):
            r = ai_insights.generate_daily_summary(loja)
        assert r['blocos'][0]['texto'] == 'Ligue o cupom.'

    def test_json_invalido_cai_no_template_em_vez_de_quebrar(self, loja):
        with patch.object(ai_insights, '_llm_text', return_value='não é json nenhum'):
            r = ai_insights.generate_daily_summary(loja)
        assert r['source'] == 'template'
        assert r['blocos']

    def test_tipo_desconhecido_do_llm_e_normalizado(self, loja):
        # O modelo inventa rótulo. Um `tipo` fora do conjunto quebraria o
        # ícone e a cor no frontend — melhor cair no neutro do que sumir.
        resposta = '{"blocos":[{"tipo":"insight_incrivel","titulo":"X","texto":"Y"}]}'
        with patch.object(ai_insights, '_llm_text', return_value=resposta):
            r = ai_insights.generate_daily_summary(loja)
        assert r['blocos'][0]['tipo'] in TIPOS_VALIDOS

    def test_bloco_sem_texto_e_descartado(self, loja):
        resposta = (
            '{"blocos":[{"tipo":"acao","titulo":"Hoje","texto":"  "},'
            '{"tipo":"resultado","titulo":"Ontem","texto":"5 pedidos."}]}'
        )
        with patch.object(ai_insights, '_llm_text', return_value=resposta):
            r = ai_insights.generate_daily_summary(loja)
        assert len(r['blocos']) == 1
        assert r['blocos'][0]['tipo'] == 'resultado'

    def test_todos_os_blocos_vazios_cai_no_template(self, loja):
        # Lista vazia renderizaria um card sem conteúdo, que lê como falha
        # nossa. O template tem o que dizer.
        resposta = '{"blocos":[{"tipo":"acao","titulo":"","texto":""}]}'
        with patch.object(ai_insights, '_llm_text', return_value=resposta):
            r = ai_insights.generate_daily_summary(loja)
        assert r['source'] == 'template'
        assert r['blocos']
