"""O modelo default do painel morreu duas vezes — e o painel não avisou ninguém.

15/jul/2026: `meta/llama-3.1-405b-instruct` saiu do catálogo da NVIDIA NIM.
26/ago/2026: `meta/llama-3.1-70b-instruct` teve o mesmo fim (410 Gone), e desde
então TODO resumo do painel voltava com o selo "gerado sem IA". O erro só
existia como WARNING no log do container; na tela não havia nenhuma pista de
que o problema era o provedor, e não a loja.

Dois testes, duas lições do incidente:

  1. o default hardcoded não pode ser um modelo já enterrado;
  2. o payload do nano precisa desligar o `thinking` — com ele ligado o
     raciocínio come o orçamento de tokens e o JSON chega truncado
     (medido: 4/4 acertos e 3,7s com thinking off, contra JSON quebrado
     e 10s com ele ligado).
"""
from django.test import SimpleTestCase, override_settings

from apps.stores.services.ai_insights import (
    MODELOS_APOSENTADOS,
    MODELO_INSIGHTS_PADRAO,
    corpo_extra_do_modelo,
)


class ModeloPadraoTests(SimpleTestCase):
    def test_o_default_nao_e_um_modelo_ja_aposentado(self):
        self.assertNotIn(MODELO_INSIGHTS_PADRAO, MODELOS_APOSENTADOS)

    def test_os_dois_modelos_que_morreram_estao_na_lapide(self):
        # A lista existe para que a próxima morte apareça em teste, e não em
        # produção três dias depois.
        self.assertIn('meta/llama-3.1-70b-instruct', MODELOS_APOSENTADOS)
        self.assertIn('meta/llama-3.1-405b-instruct', MODELOS_APOSENTADOS)

    @override_settings(NVIDIA_INSIGHTS_MODEL='meta/llama-3.1-70b-instruct')
    def test_env_apontando_para_modelo_morto_e_ignorado(self):
        # O `.env` de produção continuava apontando para o modelo enterrado.
        # Obedecer o env aqui seria manter a falha de pé por config.
        from apps.stores.services.ai_insights import modelo_de_insights
        self.assertEqual(modelo_de_insights(), MODELO_INSIGHTS_PADRAO)

    @override_settings(NVIDIA_INSIGHTS_MODEL='nvidia/nemotron-3-super-120b-a12b')
    def test_env_com_modelo_vivo_manda(self):
        from apps.stores.services.ai_insights import modelo_de_insights
        self.assertEqual(modelo_de_insights(), 'nvidia/nemotron-3-super-120b-a12b')


class CorpoExtraTests(SimpleTestCase):
    def test_nano_desliga_o_raciocinio(self):
        extra = corpo_extra_do_modelo('nvidia/nemotron-3-nano-30b-a3b')
        self.assertIs(extra['chat_template_kwargs']['thinking'], False)

    def test_modelo_sem_raciocinio_nao_recebe_a_chave(self):
        # Mandar `chat_template_kwargs` para um modelo que não entende a chave
        # é convite a 400 — e um 400 aqui volta a mostrar "gerado sem IA".
        self.assertEqual(corpo_extra_do_modelo('gpt-4o-mini'), {})
