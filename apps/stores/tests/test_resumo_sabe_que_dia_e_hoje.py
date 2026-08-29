"""O resumo dizia "Hoje é terça" numa sexta-feira.

RELATADO PELO DONO em 28/ago/2026 (uma sexta):

    "Hoje é terça, nosso melhor dia; vamos reforçar o horário de pico às 10h."
    -> "como assim hoje é terça? hoje é sexta ue kkkkk relatorio bugado"

CAUSA: o prompt mandava `best_weekday: "terça"` — o dia da semana que mais
fatura — e NENHUMA data. O modelo não tinha como saber que dia era hoje, então
preencheu o buraco com o único dia da semana que estava no texto.

Não é o modelo sendo ruim: é a gente pedindo "UMA coisa concreta para hoje" sem
dizer que dia é hoje. A correção é dar o dado, não brigar com o modelo.

E a lição vale além deste campo: qualquer instrução com "hoje" num prompt sem
data é um convite à invenção.
"""
from django.test import SimpleTestCase
from unittest.mock import patch

from apps.stores.services import ai_insights


class PromptSabeODiaTests(SimpleTestCase):
    def _prompt_gerado(self):
        capturado = {}

        def espiao(prompt):
            capturado['prompt'] = prompt
            raise RuntimeError('não queremos chamar o modelo de verdade')

        loja = type('Loja', (), {'name': 'Cê Saladas', 'id': 1})()

        with patch.object(ai_insights, '_llm_text', espiao), \
             patch.object(ai_insights, 'compute_daily_stats', return_value={'orders': 6}), \
             patch.object(ai_insights, 'compute_forecast', return_value={
                 'best_weekday': 'terça', 'worst_weekday': 'domingo',
             }), \
             patch.object(ai_insights, '_template_blocos', return_value=[
                 {'tipo': 'resultado', 'titulo': 'x', 'texto': 'y'}
             ]):
            ai_insights.generate_daily_summary(loja)

        return capturado['prompt']

    def test_o_prompt_diz_que_dia_da_semana_e_hoje(self):
        from django.utils import timezone
        prompt = self._prompt_gerado()

        # O nome do dia em português precisa aparecer literalmente: é o que
        # impede o modelo de pegar `best_weekday` e chamá-lo de hoje.
        dia_de_hoje = ai_insights.DIAS_DA_SEMANA[timezone.localtime().weekday()]
        self.assertIn(dia_de_hoje, prompt)

    def test_o_prompt_proibe_confundir_o_melhor_dia_com_hoje(self):
        prompt = self._prompt_gerado().lower()
        self.assertIn('best_weekday', prompt)
        # A regra tem que estar escrita, não só implícita nos dados.
        self.assertIn('não é hoje', prompt)


class DiasDaSemanaTests(SimpleTestCase):
    def test_a_tabela_cobre_a_semana_inteira_em_portugues(self):
        self.assertEqual(len(ai_insights.DIAS_DA_SEMANA), 7)
        self.assertEqual(ai_insights.DIAS_DA_SEMANA[0], 'segunda')
        self.assertEqual(ai_insights.DIAS_DA_SEMANA[4], 'sexta')
        self.assertEqual(ai_insights.DIAS_DA_SEMANA[6], 'domingo')

    def test_bate_com_o_vocabulario_que_o_forecast_ja_usa(self):
        # `compute_forecast` devolve 'terça', 'sábado' com acento. Duas grafias
        # fariam o modelo achar que são dias diferentes.
        from apps.stores.services.ai_insights import DIAS_DA_SEMANA
        self.assertIn('terça', DIAS_DA_SEMANA)
        self.assertIn('sábado', DIAS_DA_SEMANA)
