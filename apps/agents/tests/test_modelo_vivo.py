"""O agente não pode apontar para um modelo morto nem para uma chave inválida.

Em 09/ago/2026 o "Testar Assistente" devolvia 500 em toda mensagem. Duas causas
somadas, nenhuma visível na tela:

1. `model_name` era `moonshotai/kimi-k2-thinking`, descontinuado em
   12/05/2026 — a NVIDIA responde **410 Gone**.
2. A `api_key` gravada no agente era DIFERENTE da do ambiente e não tinha
   permissão de inferência: **403 Authorization failed**. Só apareceu depois
   de corrigir o modelo, porque o 410 acontecia antes da checagem.

Uma chave por agente existe para o caso multi-tenant (cada loja com a sua),
mas quando ela fica para trás o sintoma é um 500 opaco. Este teste garante que
a configuração default nunca fique nesse estado.
"""
import pytest

# Modelos que a NVIDIA já desligou. Não é lista de bloqueio: é memória do que
# já quebrou em produção, para não voltar num copiar-e-colar.
MODELOS_MORTOS = {
    'moonshotai/kimi-k2-thinking',
    'moonshotai/kimi-k2-instruct',
}


@pytest.mark.django_db
def test_nenhum_agente_aponta_para_modelo_descontinuado():
    from apps.agents.models import Agent

    for agente in Agent.objects.all():
        assert agente.model_name not in MODELOS_MORTOS, (
            f'O agente {agente.name!r} usa {agente.model_name!r}, que a NVIDIA '
            f'desligou — toda mensagem vira 500 com 410 Gone.'
        )


@pytest.mark.django_db
def test_agente_sem_chave_propria_herda_a_do_ambiente():
    """Chave vazia é melhor que chave velha.

    Com `api_key` em branco o serviço cai na credencial do ambiente, que é a
    que o resto do sistema usa e mantemos rodando. Com uma chave antiga
    gravada, o agente falha sozinho e ninguém descobre até um cliente reclamar.
    """
    from apps.agents.models import Agent

    campo = Agent._meta.get_field('api_key')
    assert campo.blank, 'api_key precisa aceitar vazio para herdar a do ambiente.'
