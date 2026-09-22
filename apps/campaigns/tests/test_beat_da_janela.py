"""O agendador precisa rodar a campanha marcada o DIA INTEIRO, não só na hora.

Quem fecharia a janela às 12h recebe às 11h — antes do horário da campanha.
Se o Beat só olhasse `scheduled_at <= agora`, essa pessoa nunca receberia, que
é exatamente o que aconteceu em 18/set (380 contatos, 28 recebidos).

Campanha com modelo aprovado (template) não depende da janela e segue o caminho
antigo: vira RUNNING no horário marcado e o lote cuida do resto.
"""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.campaign_service import CampaignService
from apps.campaigns.services.janela import MARCA
from apps.campaigns.tasks import check_scheduled_campaigns
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

SP = ZoneInfo('America/Sao_Paulo')


def _as(hora: int, dia: int = 15) -> datetime:
    return datetime(2026, 9, dia, hora, 0, tzinfo=SP)


class BeatDaJanelaTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH-BJ', waba_id='WABA-BJ',
        )
        self.marcada = self._campanha('Promo de hoje', _as(20), marcada=True)
        self.de_amanha = self._campanha('Promo de amanhã', _as(20, dia=16), marcada=True)
        self.com_template = self._campanha('Com modelo', _as(20), marcada=False)

    def _campanha(self, nome, quando, marcada):
        return Campaign.objects.create(
            account=self.conta, name=nome, scheduled_at=quando,
            status=Campaign.CampaignStatus.SCHEDULED,
            message_content={'text': 'oi'},
            audience_filters={MARCA: True} if marcada else {},
        )

    def _destinatario(self, campanha, telefone='556399990301', falou_em=None):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone,
            last_customer_message_at=falou_em or _as(9),
        )
        return CampaignRecipient.objects.create(
            campaign=campanha, phone_number=telefone, contact_name='Cliente',
        )

    def _rodar(self, hora: int):
        with patch('apps.campaigns.tasks.timezone.now', return_value=_as(hora)), \
                patch('apps.campaigns.services.rodada_da_janela.processar_rodada_da_janela') as rodada, \
                patch('apps.campaigns.tasks.process_campaign.delay') as lote:
            check_scheduled_campaigns()
        return rodada, lote

    def _campanhas_rodadas(self, rodada):
        return {c.args[0].id for c in rodada.call_args_list}

    def test_campanha_marcada_roda_no_dia_mesmo_antes_do_horario(self):
        """Às 11h a campanha das 20h já precisa rodar: é quando o antecipado sai."""
        rodada, _ = self._rodar(11)

        self.assertIn(self.marcada.id, self._campanhas_rodadas(rodada))

    def test_campanha_marcada_de_amanha_nao_roda_hoje(self):
        rodada, _ = self._rodar(11)

        self.assertNotIn(self.de_amanha.id, self._campanhas_rodadas(rodada))

    def test_campanha_com_modelo_segue_o_caminho_antigo(self):
        rodada, lote = self._rodar(20)

        self.com_template.refresh_from_db()
        self.assertEqual(self.com_template.status, Campaign.CampaignStatus.RUNNING)
        lote.assert_called_once_with(str(self.com_template.id))
        self.assertNotIn(self.com_template.id, self._campanhas_rodadas(rodada))

    def test_campanha_marcada_nao_cai_no_caminho_antigo(self):
        _, lote = self._rodar(21)

        enviados = [c.args[0] for c in lote.call_args_list]
        self.assertNotIn(str(self.marcada.id), enviados)

    def test_reservas_presas_voltam_para_a_fila_a_cada_passagem(self):
        destinatario = self._destinatario(self.marcada)
        # O relógio da rodada é o do teste: a reserva ficou presa 11 min ANTES
        # das 12h do dia da campanha.
        CampaignRecipient.objects.filter(id=destinatario.id).update(
            status='sending', updated_at=_as(12) - timedelta(minutes=11),
        )

        self._rodar(12)

        destinatario.refresh_from_db()
        self.assertEqual(destinatario.status, CampaignRecipient.RecipientStatus.PENDING)


class StartCampaignNaoRecortaTests(TestCase):
    """Disparar agora não pode jogar fora quem só caberia mais tarde."""

    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH-SC', waba_id='WABA-SC',
        )

    def _campanha(self, marcada: bool):
        campanha = Campaign.objects.create(
            account=self.conta, name='Promo', message_content={'text': 'oi'},
            status=Campaign.CampaignStatus.DRAFT,
            audience_filters={MARCA: True} if marcada else {},
        )
        Conversation.objects.create(
            account=self.conta, phone_number='556399990401',
            last_customer_message_at=timezone.now() - timedelta(hours=30),
        )
        CampaignRecipient.objects.create(
            campaign=campanha, phone_number='556399990401', contact_name='Cliente',
        )
        return campanha

    def test_campanha_marcada_nao_e_recortada_no_disparo(self):
        campanha = self._campanha(marcada=True)

        CampaignService().start_campaign(str(campanha.id))

        destinatario = CampaignRecipient.objects.get(campaign=campanha)
        self.assertEqual(destinatario.status, CampaignRecipient.RecipientStatus.PENDING)

    def test_campanha_marcada_sem_horario_ganha_o_de_agora(self):
        campanha = self._campanha(marcada=True)

        CampaignService().start_campaign(str(campanha.id))

        campanha.refresh_from_db()
        self.assertIsNotNone(campanha.scheduled_at)
