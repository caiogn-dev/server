"""`{nome}`, `{customer_name}` e `{primeiro_nome}` são apelidos do mesmo dado.

Mensagens antigas (escritas com qualquer um dos três) têm de continuar saindo
preenchidas, em qualquer envio, seja qual for a chave que o envio mandou.
"""
from django.test import SimpleTestCase

from apps.automation.variaveis import preencher
from apps.campaigns.services.campaign_service import CampaignService


class ApelidosDeNomeTests(SimpleTestCase):
    def test_customer_name_no_contexto_preenche_os_tres(self):
        ctx = {'customer_name': 'Maria Souza'}
        self.assertEqual(preencher('Oi {nome}!', ctx), 'Oi Maria Souza!')
        self.assertEqual(preencher('Oi {customer_name}!', ctx), 'Oi Maria Souza!')
        self.assertEqual(preencher('Oi {primeiro_nome}!', ctx), 'Oi Maria!')

    def test_nome_no_contexto_preenche_os_tres(self):
        ctx = {'nome': 'João Pedro Lima'}
        self.assertEqual(preencher('{customer_name}|{primeiro_nome}|{nome}', ctx), 'João Pedro Lima|João|João Pedro Lima')

    def test_primeiro_nome_so_no_contexto(self):
        self.assertEqual(preencher('{primeiro_nome} / {nome}', {'primeiro_nome': 'Ana'}), 'Ana / Ana')

    def test_valor_explicito_vence_o_apelido(self):
        ctx = {'customer_name': 'Maria Souza', 'primeiro_nome': 'Mari'}
        self.assertEqual(preencher('{primeiro_nome}', ctx), 'Mari')

    def test_sem_nome_nenhum_apelido_vira_vazio_nao_cru(self):
        self.assertEqual(preencher('Oi {nome}{primeiro_nome}!', {}), 'Oi !')

    def test_campanha_aceita_chave_simples_e_dupla(self):
        svc = CampaignService()
        vars_ = {'nome': 'Ana Paula'}
        self.assertEqual(svc._personalize_message('Oi {{nome}}', vars_), 'Oi Ana Paula')
        self.assertEqual(svc._personalize_message('Oi {nome}', vars_), 'Oi Ana Paula')
        self.assertEqual(svc._personalize_message('Oi {customer_name}', vars_), 'Oi Ana Paula')
        self.assertEqual(svc._personalize_message('Oi {primeiro_nome}', vars_), 'Oi Ana')
