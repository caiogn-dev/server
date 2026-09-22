"""O raciocínio do modelo nunca pode chegar ao cliente.

17/09 12:12, Cê Saladas. A cliente perguntou "Olá! Tem almôndega hj?" e
recebeu, em inglês, 2.696 caracteres do raciocínio interno do modelo —
"Okay, the user is asking if we have almôndega today. Let me check the
cardápio first..." — cortado no meio de uma frase. O atendente humano teve que
entrar.

Causa (reproduzida contra a NVIDIA em 18/09): o `nemotron-3-super`, que virou
o modelo dos agentes em 17/09 11:19, raciocina POR PADRÃO. Com
`max_tokens=700` ele gasta o orçamento inteiro pensando: 24,6s e
`finish_reason=length`. Com `chat_template_kwargs.thinking=False`: 1,8s,
`finish_reason=stop`, resposta em português — e tool calling intacto.

`corpo_extra_do_modelo` já existia e desligava isso — mas só os Insights do
painel a usavam; o atendente tinha a própria fábrica de LLM e nunca passou
por ela.

Três camadas, testadas aqui:
  1. o atendente desliga o raciocínio da família que raciocina;
  2. resposta truncada ou com cara de raciocínio NÃO sai: vira falha da IA,
     e a conversa vai para o atendente humano (caminho de 17/09);
  3. o texto útil depois de um bloco <think> é aproveitado.
"""
import pytest
from langchain_core.messages import AIMessage

from apps.agents.services.resposta_do_modelo import (
    RespostaDoModeloInvalida,
    texto_para_o_cliente,
)

VAZAMENTO_REAL = (
    'Okay, the user is asking if we have almôndega today. Let me check the '
    'cardápio first. Looking at the menu, I see under Saladas Especiais: '
    '"Almôndega Premium — R$ 44.99" with a description. But wait, the rules '
    'say I shouldn\'t invent ingredients. But let me see if there\'s any '
    'trick. The card'
)


class TestTextoParaOCliente:
    def test_resposta_normal_passa(self):
        assert texto_para_o_cliente('Temos sim! 😊', 'stop') == 'Temos sim! 😊'

    def test_resposta_cortada_pelo_limite_nao_sai(self):
        with pytest.raises(RespostaDoModeloInvalida):
            texto_para_o_cliente('Não, hoje não temos', 'length')

    def test_o_vazamento_de_17_09_nao_sai(self):
        with pytest.raises(RespostaDoModeloInvalida):
            texto_para_o_cliente(VAZAMENTO_REAL, 'stop')

    def test_bloco_think_e_removido_e_a_resposta_fica(self):
        texto = '<think>the user wants meatballs</think>\nTemos sim, a Almôndega Premium!'
        assert texto_para_o_cliente(texto, 'stop') == 'Temos sim, a Almôndega Premium!'

    def test_think_sem_resposta_depois_nao_sai(self):
        with pytest.raises(RespostaDoModeloInvalida):
            texto_para_o_cliente('<think>the user wants meatballs, let me', 'stop')

    def test_portugues_que_cita_usuario_passa(self):
        """Não pode barrar resposta legítima por palavra solta."""
        texto = 'Olá! O usuário do app pode pedir pelo link também. Temos sim!'
        assert texto_para_o_cliente(texto, 'stop') == texto


@pytest.mark.django_db
class TestAtendenteDesligaORaciocinio:
    def _servico(self, modelo):
        from apps.agents.models import Agent
        from apps.agents.services.langchain_service import LangchainService
        agente = Agent.objects.create(
            name='Teste', provider=Agent.AgentProvider.NVIDIA, model_name=modelo,
        )
        return LangchainService(agente)

    def test_nemotron_super_vai_com_raciocinio_desligado(self):
        llm = self._servico('nvidia/nemotron-3-super-120b-a12b').llm
        assert (llm.extra_body or {}).get('chat_template_kwargs') == {'thinking': False}

    def test_modelo_que_nao_raciocina_nao_recebe_a_chave(self):
        """Mandar chat_template_kwargs a quem não entende é convite a 400."""
        llm = self._servico('openai/gpt-oss-20b').llm
        assert not (llm.extra_body or {}).get('chat_template_kwargs')


class _LLMFalso:
    """Devolve sempre a mesma AIMessage; serve com e sem bind_tools."""

    def __init__(self, resposta):
        self.resposta = resposta

    def bind_tools(self, _tools):
        return self

    def invoke(self, _mensagens):
        return self.resposta


@pytest.mark.django_db
class TestProcessMessageNaoEntregaRaciocinio:
    def _servico(self, resposta):
        from apps.agents.models import Agent
        from apps.agents.services.langchain_service import LangchainService
        agente = Agent.objects.create(
            name='Teste', provider=Agent.AgentProvider.NVIDIA,
            model_name='nvidia/nemotron-3-super-120b-a12b',
        )
        servico = LangchainService(agente)
        servico.llm = _LLMFalso(resposta)
        return servico

    def test_resposta_truncada_vira_falha_da_ia(self):
        servico = self._servico(AIMessage(
            content=VAZAMENTO_REAL, response_metadata={'finish_reason': 'length'},
        ))
        with pytest.raises(Exception) as erro:
            servico.process_message(message='Tem almôndega hj?', session_id=None)
        assert 'RespostaDoModeloInvalida' in repr(erro.value) or isinstance(
            erro.value, RespostaDoModeloInvalida,
        )

    def test_resposta_boa_segue_normal(self):
        servico = self._servico(AIMessage(
            content='Temos sim! Quer a Almôndega Premium?',
            response_metadata={'finish_reason': 'stop'},
        ))
        r = servico.process_message(message='Tem almôndega hj?', session_id=None)
        assert r['response'] == 'Temos sim! Quer a Almôndega Premium?'
