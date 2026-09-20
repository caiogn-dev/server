"""O dia inteiro da campanha, com o relógio na mão.

A campanha de texto livre só chega de graça a quem falou com a loja nas
últimas 24 h. Em 18/set, 380 contatos viraram 28 recebidos: a campanha disparou
de uma vez às 10:20 e quem tinha falado às 9:00 do dia anterior já estava fora.

A rodada resolve isso mandando cada pessoa no horário DELA: uma hora antes da
janela fechar, ou no horário da campanha, o que vier primeiro. Cada rodada é
uma foto — recalcula tudo, porque quem responder ao bot no meio do dia renova
a própria janela e volta a caber.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.janela import MARCA
from apps.campaigns.services.optout import registrar_saida
from apps.campaigns.services.rodada_da_janela import processar_rodada_da_janela
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

SP = ZoneInfo('America/Sao_Paulo')
TELEFONE = '556399990101'


def _hoje_as(hora: int, dia: int = 15) -> datetime:
    return datetime(2026, 9, dia, hora, 0, tzinfo=SP)


class RodadaDaJanelaTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH-RJ', waba_id='WABA-RJ',
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Promoção do dia',
            message_content={'text': 'Oi {nome}, salada hoje?'},
            audience_filters={MARCA: True},
            status=Campaign.CampaignStatus.SCHEDULED,
            scheduled_at=_hoje_as(20),
            messages_per_minute=60,
        )

    # ── cenário ──────────────────────────────────────────────────────────
    def _cliente(self, falou_em: datetime, telefone: str = TELEFONE):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone, contact_name='Cliente',
            last_customer_message_at=falou_em,
        )
        return CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number=telefone, contact_name='Cliente',
        )

    def _rodar(self, hora: int, dia: int = 15, envio=None):
        envio = envio or MagicMock(return_value=MagicMock(id='msg-1', whatsapp_message_id='wamid.1'))
        with patch('apps.whatsapp.services.message_service.MessageService.send_text_message', envio):
            return processar_rodada_da_janela(self.campanha, agora=_hoje_as(hora, dia)), envio

    def _destinatario(self):
        return CampaignRecipient.objects.get(phone_number=TELEFONE)

    # ── testes ───────────────────────────────────────────────────────────
    def test_quem_tem_janela_larga_so_recebe_no_horario_da_campanha(self):
        """Falou hoje 09:00 → fecha amanhã 09:00 → cabe no horário da campanha."""
        self._cliente(_hoje_as(9))

        resultado, _ = self._rodar(11)
        self.assertEqual(resultado['enviados'], 0)
        self.assertEqual(resultado['aguardando'], 1)

        resultado, _ = self._rodar(20)
        self.assertEqual(resultado['enviados'], 1)

    def test_quem_fecharia_antes_e_antecipado_uma_hora(self):
        """Falou ontem 12:00 → fecha hoje 12:00 → recebe 11:00, não às 20:00."""
        self._cliente(_hoje_as(12, dia=14))

        resultado, envio = self._rodar(11)

        self.assertEqual(resultado['enviados'], 1)
        envio.assert_called_once()

    def test_ninguem_recebe_duas_vezes_ao_longo_do_dia(self):
        self._cliente(_hoje_as(12, dia=14))

        for hora in range(8, 22):
            self._rodar(hora)

        self.assertEqual(
            CampaignRecipient.objects.filter(status=CampaignRecipient.RecipientStatus.SENT).count(), 1,
        )

    def test_quem_nao_cabe_na_janela_vira_pulado_e_nao_falha(self):
        """Falou há mais de 24 h: não dá para mandar de graça."""
        self._cliente(_hoje_as(10, dia=13))

        resultado, envio = self._rodar(21)

        self.assertEqual(resultado['pulados'], 1)
        envio.assert_not_called()
        self.assertEqual(self._destinatario().status, CampaignRecipient.RecipientStatus.SKIPPED)
        self.assertEqual(self._destinatario().error_code, 'fora_da_janela')

    def test_antes_do_horario_da_campanha_ainda_espera(self):
        """Até a hora da campanha, a pessoa ainda pode responder e reabrir a janela."""
        self._cliente(_hoje_as(10, dia=13))

        resultado, _ = self._rodar(15)

        self.assertEqual(resultado['aguardando'], 1)
        self.assertEqual(self._destinatario().status, CampaignRecipient.RecipientStatus.PENDING)

    def test_campanha_fecha_na_rodada_em_que_o_ultimo_recebe(self):
        """Passou o horário e ninguém mais espera: acabou ali mesmo."""
        self._cliente(_hoje_as(9))

        resultado, _ = self._rodar(20)

        self.campanha.refresh_from_db()
        self.assertTrue(resultado['concluida'])
        self.assertEqual(self.campanha.status, Campaign.CampaignStatus.COMPLETED)

    def test_campanha_concluida_nao_envia_mais_nada(self):
        self._cliente(_hoje_as(9))
        self._rodar(20)

        resultado, envio = self._rodar(21)

        envio.assert_not_called()
        self.assertEqual(resultado['enviados'], 0)

    def test_campanha_pausada_nao_envia_nada(self):
        self._cliente(_hoje_as(9))
        Campaign.objects.filter(pk=self.campanha.pk).update(status=Campaign.CampaignStatus.PAUSED)
        self.campanha.refresh_from_db()

        resultado, envio = self._rodar(20)

        self.assertEqual(resultado['enviados'], 0)
        envio.assert_not_called()

    def test_janela_que_fecha_na_corrida_vira_pulado(self):
        """A Meta ainda pode recusar entre o cálculo e o envio (131047)."""
        self._cliente(_hoje_as(9))
        envio = MagicMock(side_effect=Exception('(#131047) Re-engagement message'))

        resultado, _ = self._rodar(20, envio=envio)

        self.assertEqual(resultado['enviados'], 0)
        self.assertEqual(self._destinatario().status, CampaignRecipient.RecipientStatus.SKIPPED)
        self.assertEqual(self._destinatario().error_code, '131047')

    def test_falha_de_verdade_continua_sendo_falha(self):
        self._cliente(_hoje_as(9))
        envio = MagicMock(side_effect=Exception('connection reset'))

        self._rodar(20, envio=envio)

        self.assertEqual(self._destinatario().status, CampaignRecipient.RecipientStatus.FAILED)

    def test_respeita_o_teto_de_mensagens_por_minuto(self):
        for i in range(5):
            self._cliente(_hoje_as(9), telefone=f'55639999020{i}')
        Campaign.objects.filter(pk=self.campanha.pk).update(messages_per_minute=2)
        self.campanha.refresh_from_db()

        resultado, _ = self._rodar(20)

        self.assertEqual(resultado['enviados'], 2)
        self.assertEqual(resultado['aguardando'], 3)

    def test_quem_pediu_para_parar_nao_recebe(self):
        self._cliente(_hoje_as(9))
        registrar_saida(self.conta, TELEFONE, 'Parar promoções', 'button')

        resultado, envio = self._rodar(20)

        self.assertEqual(resultado['enviados'], 0)
        envio.assert_not_called()
        self.assertEqual(self._destinatario().error_code, 'pediu_para_parar')

    def test_contador_da_campanha_sobe_com_o_envio(self):
        self._cliente(_hoje_as(9))

        self._rodar(20)

        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.messages_sent, 1)
