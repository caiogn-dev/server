"""O classificador de verdade: NVIDIA NIM, JSON apertado, timeout curto.

Terceira peça do redesenho. A triagem já roteia pelo catálogo; o que ela ainda
não faz é entender frase que não nomeia produto — "Qual opção de hj", que na
conversa da Yeda virou "Como posso te ajudar? 👇".

Restrições que vêm da história deste projeto, não de preferência:

- **NVIDIA NIM.** Produção nunca chamou Anthropic nem OpenAI.
- **Timeout curto e explícito.** O bot já teve 3 minutos de latência e resposta
  descartada no timeout de 90s. Um classificador que demora é pior que um
  classificador que erra: o cliente já foi embora.
- **JSON e nada mais.** Ele devolve uma decisão, não um texto para o cliente.
  Texto para o cliente é papel de quem responde, não de quem roteia.
- **Falhou, cai fora.** Devolve None e a triagem segue determinística. Isso já
  está coberto em test_triagem; aqui o foco é o formato.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.classificador import (
    ClassificadorNIM, _decisao_do_json,
)
from apps.automation.services.triagem import Intencao


class _Resposta:
    def __init__(self, content):
        self.content = content


class TestLeituraDoJson:
    def test_json_limpo_vira_decisao(self):
        d = _decisao_do_json('{"intencao": "consultiva", "confianca": 0.8}')

        assert d.intencao is Intencao.CONSULTIVA
        assert d.confianca == 0.8
        assert d.origem == 'llm'

    def test_json_dentro_de_cerca_de_codigo(self):
        """Modelo aberto adora embrulhar em ```json — é o caso comum, não a exceção."""
        d = _decisao_do_json('```json\n{"intencao": "item"}\n```')

        assert d.intencao is Intencao.ITEM

    def test_texto_em_volta_do_json_nao_atrapalha(self):
        d = _decisao_do_json('Claro! {"intencao": "observacao"} espero ter ajudado')

        assert d.intencao is Intencao.OBSERVACAO

    def test_intencao_inventada_e_recusada(self):
        """Modelo alucina rótulo. Recusar é mais seguro que adivinhar."""
        assert _decisao_do_json('{"intencao": "comprar_tudo"}') is None

    def test_json_quebrado_e_recusado(self):
        assert _decisao_do_json('{"intencao": ') is None

    def test_resposta_vazia_e_recusada(self):
        assert _decisao_do_json('') is None
        assert _decisao_do_json(None) is None


class TestChamadaAoModelo:
    def _classificador(self, resposta=None, erro=None):
        modelo = MagicMock()
        if erro:
            modelo.invoke.side_effect = erro
        else:
            modelo.invoke.return_value = _Resposta(resposta)
        c = ClassificadorNIM()
        c._modelo = modelo
        return c, modelo

    def test_devolve_decisao_do_modelo(self, db):
        c, _ = self._classificador('{"intencao": "consultiva"}')

        d = c('Qual opção de hj', store=None, esperando=None)

        assert d.intencao is Intencao.CONSULTIVA

    def test_timeout_devolve_none_em_vez_de_levantar(self, db):
        c, _ = self._classificador(erro=TimeoutError('demorou'))

        assert c('qualquer coisa', store=None, esperando=None) is None

    def test_erro_de_rede_devolve_none(self, db):
        c, _ = self._classificador(erro=ConnectionError('nim fora'))

        assert c('qualquer coisa', store=None, esperando=None) is None

    def test_o_catalogo_vai_no_prompt(self, db):
        """Sem catálogo o modelo inventa produto que a loja não vende."""
        from apps.stores.models import StoreProduct
        from apps.stores.tests.factories import make_store

        loja = make_store(name='Cê Saladas')
        StoreProduct.objects.create(
            store=loja, name='Salada Caesar', slug='sc', price=20, is_active=True,
        )
        c, modelo = self._classificador('{"intencao": "consultiva"}')

        c('o que tem hoje', store=loja, esperando=None)

        enviado = str(modelo.invoke.call_args)
        assert 'Salada Caesar' in enviado

    def test_nao_pede_texto_para_o_cliente(self, db):
        """Quem escreve para o cliente é o handler. O roteador só rotula."""
        c, modelo = self._classificador('{"intencao": "consultiva"}')

        c('oi tudo bem', store=None, esperando=None)

        enviado = str(modelo.invoke.call_args).lower()
        assert 'json' in enviado
        assert 'responda ao cliente' not in enviado


class TestTetoDeLatenciaDeVerdade:
    """Timeout sem desligar retry é teto de mentira.

    Medido contra o NIM real: 'o que voces recomendam' levou 9.869 ms com um
    retry interno do cliente, mais que o DOBRO do timeout de 6s configurado. O
    cliente da OpenAI tenta de novo sozinho, e cada tentativa ganha o timeout
    cheio.

    Num fluxo onde o cliente está esperando, a segunda tentativa não ajuda: ela
    chega depois que a pessoa desistiu. Uma tentativa, curta, e cai fora.
    """

    def test_cliente_nao_faz_retry_interno(self, db):
        with patch('langchain_openai.ChatOpenAI') as fake:
            with patch.dict('os.environ', {'NVIDIA_API_KEY': 'x'}):
                ClassificadorNIM()._carregar()

        assert fake.call_args.kwargs['max_retries'] == 0

    def test_timeout_vai_para_o_cliente(self, db):
        with patch('langchain_openai.ChatOpenAI') as fake:
            with patch.dict('os.environ', {'NVIDIA_API_KEY': 'x'}):
                ClassificadorNIM(timeout=3)._carregar()

        assert fake.call_args.kwargs['timeout'] == 3


class TestModeloPequenoDeProposito:
    """O classificador NÃO usa o modelo do agente.

    Medido contra o NIM real com gabarito de 10 frases da conversa da Yeda:

        llama-3.1-8b    acerto 8/10   mediana   431 ms
        llama-3.1-70b   acerto 6/10   mediana 9.521 ms

    O 70b não erra por burrice — ele estoura o tempo, e 4 das 10 viraram
    FALHOU. Num roteador no caminho do cliente, o modelo grande perde nos dois
    eixos ao mesmo tempo.
    """

    def test_usa_modelo_proprio_e_nao_o_do_agente(self, db):
        with patch('langchain_openai.ChatOpenAI') as fake:
            with patch.dict('os.environ', {
                'NVIDIA_API_KEY': 'x',
                'NVIDIA_MODEL_NAME': 'meta/llama-3.1-70b-instruct',
            }, clear=False):
                ClassificadorNIM()._carregar()

        assert fake.call_args.kwargs['model'] == 'meta/llama-3.1-8b-instruct'

    def test_da_para_trocar_por_ambiente_sem_deploy(self, db):
        with patch('langchain_openai.ChatOpenAI') as fake:
            with patch.dict('os.environ', {
                'NVIDIA_API_KEY': 'x',
                'NVIDIA_MODELO_CLASSIFICADOR': 'outro/modelo',
            }, clear=False):
                ClassificadorNIM()._carregar()

        assert fake.call_args.kwargs['model'] == 'outro/modelo'
