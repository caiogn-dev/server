"""O guarda que impede o sistema de pedir um modelo já enterrado.

Ver `apps/agents/runtime/modelos.py` para o histórico dos dois incidentes.
O caso que mais importa aqui é o ÚLTIMO teste: o env de produção continuou
apontando para o modelo morto depois do 410, porque o env mora assado dentro
da imagem. Se o código obedecesse o env cegamente, a correção não teria efeito
nenhum em produção.
"""
from django.test import SimpleTestCase, override_settings

from apps.agents.runtime.modelos import (
    MODELOS_APOSENTADOS,
    MODELO_PADRAO,
    corpo_extra_do_modelo,
    modelo_vivo,
)


class ModeloVivoTests(SimpleTestCase):
    def test_o_padrao_nao_e_um_modelo_enterrado(self):
        self.assertNotIn(MODELO_PADRAO, MODELOS_APOSENTADOS)

    def test_modelo_vivo_passa_intacto(self):
        self.assertEqual(
            modelo_vivo('deepseek-ai/deepseek-v4-flash-0731'),
            'deepseek-ai/deepseek-v4-flash-0731',
        )

    def test_modelo_aposentado_cai_no_padrao(self):
        self.assertEqual(modelo_vivo('meta/llama-3.1-70b-instruct'), MODELO_PADRAO)

    def test_vazio_e_none_caem_no_padrao(self):
        self.assertEqual(modelo_vivo(''), MODELO_PADRAO)
        self.assertEqual(modelo_vivo(None), MODELO_PADRAO)
        self.assertEqual(modelo_vivo('   '), MODELO_PADRAO)

    def test_nao_levanta_nunca(self):
        # Um modelo ruim tem que degradar a resposta, nunca derrubar a tela.
        for entrada in (None, '', 'lixo/inexistente', 123):
            modelo_vivo(str(entrada) if entrada is not None else None)


class FactoryTests(SimpleTestCase):
    @override_settings(NVIDIA_MODEL_NAME='meta/llama-3.1-70b-instruct')
    def test_factory_ignora_env_apontando_para_lapide(self):
        # Este é o teste que representa a produção real: o container tinha
        # NVIDIA_MODEL_NAME=meta/llama-3.1-70b-instruct assado dentro da imagem.
        from apps.agents.models import Agent
        from apps.agents.runtime import factory

        capturado = {}

        class FakeChat:
            def __init__(self, **kwargs):
                capturado.update(kwargs)

        agente = Agent(
            name='t', provider=Agent.AgentProvider.NVIDIA, model_name='',
            temperature=0.3, max_tokens=100, timeout=10, base_url='',
        )
        import langchain_openai
        original = langchain_openai.ChatOpenAI
        langchain_openai.ChatOpenAI = FakeChat
        try:
            factory.create_llm(agente)
        finally:
            langchain_openai.ChatOpenAI = original

        self.assertNotIn(capturado.get('model'), MODELOS_APOSENTADOS)
        self.assertEqual(capturado.get('model'), MODELO_PADRAO)


class CorpoExtraTests(SimpleTestCase):
    def test_nano_desliga_o_raciocinio(self):
        extra = corpo_extra_do_modelo('nvidia/nemotron-3-nano-30b-a3b')
        self.assertIs(extra['chat_template_kwargs']['thinking'], False)

    def test_modelo_sem_raciocinio_nao_recebe_a_chave(self):
        self.assertEqual(corpo_extra_do_modelo('gpt-4o-mini'), {})
        self.assertEqual(corpo_extra_do_modelo(None), {})
