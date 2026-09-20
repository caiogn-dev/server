"""A prévia precisa dizer QUANDO cada um recebe, não só quantos cabem.

Com a rodada, a campanha deixou de sair toda às 20h: quem fecharia a janela às
12h recebe às 11h. A tela tem que mostrar isso ANTES do dono agendar — e o
número da prévia tem que ser o mesmo que a rodada vai fazer. Número de tela que
mente é pior que número nenhum (o card "Pediram para parar" dizia 0 com 11
opt-outs, e o dono parou de acreditar na tela).
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.janela import MARCA, resumo_da_janela
from apps.campaigns.services.rodada_da_janela import processar_rodada_da_janela
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

SP = ZoneInfo('America/Sao_Paulo')
FUSO = 'America/Sao_Paulo'


def _as(hora: int, dia: int = 15, minuto: int = 0) -> datetime:
    return datetime(2026, 9, dia, hora, minuto, tzinfo=SP)


class PreviaEmFaixasTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH-PF', waba_id='WABA-PF',
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Promo', message_content={'text': 'oi {nome}'},
            audience_filters={MARCA: True}, status=Campaign.CampaignStatus.SCHEDULED,
            scheduled_at=_as(20), messages_per_minute=60,
        )
        # Dois que cabem no horário cheio (falaram hoje de manhã).
        self._cliente('556399991001', _as(9))
        self._cliente('556399991002', _as(10))
        # Um antecipado: falou ontem ao meio-dia, fecha hoje 12h → recebe 11h.
        self._cliente('556399991003', _as(12, dia=14))
        # Um fora: falou anteontem.
        self._cliente('556399991004', _as(10, dia=13))

    def _cliente(self, telefone, falou_em):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone, contact_name=f'Cliente {telefone[-4:]}',
            last_customer_message_at=falou_em,
        )
        return CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number=telefone, contact_name='Cliente',
        )

    def _resumo(self):
        return resumo_da_janela([self.conta.id], em=_as(20), fuso=FUSO)

    def test_separa_quem_recebe_no_horario_de_quem_e_antecipado(self):
        resumo = self._resumo()

        self.assertEqual(resumo['no_horario'], 2)
        self.assertEqual(resumo['antecipados'], 1)
        self.assertEqual(resumo['de_fora'], 1)

    def test_continua_dizendo_quantos_cabem_no_total(self):
        """`dentro`/`fora` são o que a tela já mostra hoje — não podem sumir."""
        resumo = self._resumo()

        self.assertEqual(resumo['dentro'] + resumo['fora'], 4)

    def test_devolve_as_faixas_do_dia(self):
        resumo = self._resumo()

        faixas = {f['hora']: f['quantidade'] for f in resumo['faixas']}
        self.assertEqual(faixas.get(11), 1)
        self.assertEqual(faixas.get(20), 2)
        self.assertEqual(resumo['primeiro_antecipado_em'].hour, 11)

    def test_sem_antecipado_nao_inventa_horario(self):
        Conversation.objects.filter(phone_number='556399991003').update(
            last_customer_message_at=_as(9),
        )

        resumo = self._resumo()

        self.assertEqual(resumo['antecipados'], 0)
        self.assertIsNone(resumo['primeiro_antecipado_em'])

    def test_a_previa_bate_com_o_que_a_rodada_faz(self):
        """Prévia e envio usam a MESMA conta."""
        previa = self._resumo()
        envio = MagicMock(return_value=MagicMock(id='m', whatsapp_message_id='w'))

        with patch('apps.whatsapp.services.message_service.MessageService.send_text_message', envio):
            for hora in range(8, 23):
                processar_rodada_da_janela(self.campanha, agora=_as(hora))

        enviados = CampaignRecipient.objects.filter(
            campaign=self.campanha, status=CampaignRecipient.RecipientStatus.SENT,
        ).count()
        self.assertEqual(enviados, previa['no_horario'] + previa['antecipados'])


class FaixasDaCampanhaNaApiTests(TestCase):
    """O dono acompanha a campanha rodando: o que já saiu e o que falta."""

    def setUp(self):
        self.dono = get_user_model().objects.create_user(username='dono-faixas', password='x')
        self.conta = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH-FX', waba_id='WABA-FX', owner=self.dono,
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Promo', message_content={'text': 'oi'},
            audience_filters={MARCA: True}, status=Campaign.CampaignStatus.RUNNING,
            scheduled_at=_as(20), created_by=self.dono,
        )
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.dono)

    def _destinatario(self, telefone, falou_em, status='pending'):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone, contact_name='Cliente',
            last_customer_message_at=falou_em,
        )
        return CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number=telefone, contact_name='Cliente', status=status,
        )

    def _faixas(self, em=None):
        url = f'/api/v1/campaigns/campaigns/{self.campanha.id}/faixas/'
        return self.cliente.get(url, {'em': (em or _as(11)).isoformat()})

    def test_mostra_enviadas_e_aguardando_por_faixa(self):
        self._destinatario('556399992001', _as(12, dia=14), status='sent')  # antecipado, já saiu
        self._destinatario('556399992002', _as(9))                          # espera as 20h

        resposta = self._faixas()

        self.assertEqual(resposta.status_code, 200, resposta.content)
        faixas = {f['hora']: f for f in resposta.data['faixas']}
        self.assertEqual(faixas[11]['enviadas'], 1)
        self.assertEqual(faixas[20]['aguardando'], 1)

    def test_diz_qual_e_a_proxima_faixa(self):
        self._destinatario('556399992003', _as(9))

        resposta = self._faixas()

        self.assertEqual(resposta.data['proxima_faixa'], 20)

    def test_campanha_de_outra_loja_nao_aparece(self):
        outro = get_user_model().objects.create_user(username='intruso-faixas', password='x')
        intruso = APIClient()
        intruso.force_authenticate(outro)

        resposta = intruso.get(f'/api/v1/campaigns/campaigns/{self.campanha.id}/faixas/')

        self.assertIn(resposta.status_code, (403, 404))
