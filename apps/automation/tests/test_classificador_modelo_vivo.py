"""O classificador não pode pedir um modelo aposentado.

MEDIDO (logs do celery, 06/10): "[classificador] falhou (Error code: 410 ...
'Gone' ... The model ...)". O modelo estava cravado no código
(`meta/llama-3.1-8b-instruct`), a NVIDIA o aposentou e TODA classificação
de intenção falhava em silêncio — a triagem seguia só com regras fixas.

O projeto já tem `modelo_vivo()` (troca lápide por modelo vivo) e
`corpo_extra_do_modelo()` (desliga o raciocínio, que comeria os tokens de
uma resposta curta). O classificador passa a usar os dois.
"""
from unittest.mock import patch

from apps.automation.services import classificador as cl


def _carregar(env_modelo=None):
    with patch.dict('os.environ', {'NVIDIA_API_KEY': 'k', **({'NVIDIA_MODELO_CLASSIFICADOR': env_modelo} if env_modelo else {})}, clear=False), \
         patch('apps.agents.runtime.modelos.catalogo_vivo', return_value=frozenset({
             'nvidia/nemotron-3-ultra-550b-a55b', 'openai/gpt-oss-20b'})):
        if not env_modelo:
            import os
            os.environ.pop('NVIDIA_MODELO_CLASSIFICADOR', None)
        return cl.ClassificadorNIM()._carregar()


def _nome(modelo):
    alvo = getattr(modelo, 'bound', modelo)
    return getattr(alvo, 'model_name', None) or getattr(alvo, 'model', None)


def test_padrao_nao_e_modelo_aposentado():
    assert _nome(_carregar()) != 'meta/llama-3.1-8b-instruct'


def test_padrao_e_o_pequeno_vivo():
    assert _nome(_carregar()) == 'openai/gpt-oss-20b'


def test_env_apontando_para_lapide_e_trocado():
    assert _nome(_carregar('meta/llama-3.1-8b-instruct')) in (
        'nvidia/nemotron-3-ultra-550b-a55b', 'openai/gpt-oss-20b')


def test_modelo_que_raciocina_vem_com_raciocinio_desligado():
    modelo = _carregar('nvidia/nemotron-3-ultra-550b-a55b')
    extra = (getattr(modelo, 'kwargs', None) or {}).get('extra_body') or {}
    assert extra.get('chat_template_kwargs', {}).get('thinking') is False
