"""A tela precisa saber quantos estão na janela NO HORÁRIO ESCOLHIDO.

Sem esse número o dono agenda no escuro: "manda às 20h" pode significar 10
pessoas ou 2, e ele só descobre depois que a campanha rodou.

O parâmetro `em` é o coração disto. A janela encolhe com o tempo — quem falou
com a loja há 20 horas está dentro agora e fora daqui a cinco. Perguntar
"quantos estarão dentro às 20h" é uma pergunta diferente de "quantos estão
dentro agora", e é a que decide o horário do disparo.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

URL = '/api/v1/campaigns/audiencia/janela/'


class JanelaNaApiTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-janela-api', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-janela-api', owner=self.dono,
            store_type='food', status='active',
        )
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number='556300000000', phone_number_id='11',
        )
        self.store.whatsapp_account = self.conta
        self.store.save(update_fields=['whatsapp_account'])
        self.client = APIClient()
        self.client.force_authenticate(self.dono)

    def _conversa(self, telefone, ha_horas):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone,
            last_customer_message_at=timezone.now() - timedelta(hours=ha_horas),
        )

    def test_diz_quantos_estao_na_janela_agora(self):
        self._conversa('5563992618115', ha_horas=2)
        self._conversa('5563984143551', ha_horas=30)

        r = self.client.get(URL)

        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['dentro'], 1)
        self.assertEqual(r.data['fora'], 1)

    def test_responde_para_o_horario_do_disparo(self):
        """A pergunta que decide o horário: quantos estarão dentro às 20h."""
        self._conversa('5563992618115', ha_horas=20)

        agora = self.client.get(URL).data
        daqui_a_cinco = self.client.get(
            URL, {'em': (timezone.now() + timedelta(hours=5)).isoformat()},
        ).data

        self.assertEqual(agora['dentro'], 1)
        self.assertEqual(daqui_a_cinco['dentro'], 0)

    def test_horario_invalido_nao_derruba_a_tela(self):
        """Campo de data meio digitado não pode virar erro vermelho."""
        self._conversa('5563992618115', ha_horas=1)

        r = self.client.get(URL, {'em': 'amanhã às 8'})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['dentro'], 1)

    def test_diz_quanto_dura_a_janela(self):
        """A tela explica a regra; o número vem do backend, não hardcoded."""
        self.assertEqual(self.client.get(URL).data['janela_horas'], 24)

    def test_visitante_nao_ve(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(URL).status_code, (401, 403))

    def test_nao_conta_conversa_de_loja_alheia(self):
        outro = User.objects.create_user(username='outro-dono-janela', password='x')
        outra_loja = Store.objects.create(
            billing_exempt=True, name='Outra', slug='outra-janela-api', owner=outro,
            store_type='food', status='active',
        )
        outra_conta = WhatsAppAccount.objects.create(
            name='Outra', phone_number='556311111111', phone_number_id='12',
        )
        outra_loja.whatsapp_account = outra_conta
        outra_loja.save(update_fields=['whatsapp_account'])
        Conversation.objects.create(
            account=outra_conta, phone_number='5563992618115',
            last_customer_message_at=timezone.now(),
        )

        self.assertEqual(self.client.get(URL).data['dentro'], 0)
