"""Registrar o opt-out não vale nada se o envio não olhar para ele.

O incidente de 25→28/ago aconteceria de novo se o bloqueio existisse só no
banco: a campanha de 28/ago montou a lista de destinatários do zero, a partir
dos contatos do sistema, e ninguém consultou quem tinha pedido para sair.

Por isso o bloqueio é aplicado em DUAS camadas:

  1. ao montar a lista  — a pessoa nem entra como destinatária;
  2. na hora de enviar  — porque uma campanha pode ter sido montada ANTES do
     opt-out e disparada depois, que é exatamente a janela de três dias do
     incidente real.

A segunda camada é a que teria evitado o incidente. A primeira é a que deixa o
número da tela honesto ("278 destinatários" incluía cinco que não podiam
receber).
"""
from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.campaign_service import CampaignService
from apps.campaigns.services.optout import registrar_saida
from apps.whatsapp.models import WhatsAppAccount


class EnvioRespeitaOptOutTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH1', waba_id='WABA1'
        )
        self.service = CampaignService()

    def _campanha(self):
        return Campaign.objects.create(account=self.conta, name='Oferta do dia')

    def test_quem_saiu_nao_vira_destinatario(self):
        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        campanha = self._campanha()

        criados = self.service._create_recipients(campanha, [
            {'phone': '556392157531', 'name': 'Saiu'},
            {'phone': '556399999999', 'name': 'Fica'},
        ])

        self.assertEqual(criados, 1)
        self.assertEqual(
            list(campanha.recipients.values_list('phone_number', flat=True)),
            ['556399999999'],
        )

    def test_bloqueio_pega_o_mesmo_numero_em_outro_formato(self):
        # O coração do incidente: saiu pela conversa (sem o nono dígito),
        # voltaria para a lista pelo telefone do pedido (com o nono dígito).
        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        campanha = self._campanha()

        criados = self.service._create_recipients(campanha, [
            {'phone': '63992157531', 'name': 'Mesma pessoa, outro formato'},
        ])

        self.assertEqual(criados, 0)
        self.assertEqual(campanha.recipients.count(), 0)

    def test_optout_depois_da_montagem_barra_no_envio(self):
        # A janela real de três dias: a lista foi montada quando a pessoa ainda
        # aceitava, e o disparo aconteceu depois do pedido de saída.
        campanha = self._campanha()
        self.service._create_recipients(campanha, [{'phone': '556392157531', 'name': 'Saiu depois'}])
        self.assertEqual(campanha.recipients.count(), 1)

        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')

        campanha.status = Campaign.CampaignStatus.RUNNING
        campanha.started_at = timezone.now()
        campanha.save()

        resultado = self.service.process_campaign_batch(str(campanha.id))

        destinatario = campanha.recipients.get()
        self.assertEqual(destinatario.status, CampaignRecipient.RecipientStatus.SKIPPED)
        self.assertEqual(resultado['processed'], 0)
        # Pular não é falhar: contar como falha faria a taxa de entrega mentir
        # e sugeriria problema técnico onde houve escolha do cliente.
        campanha.refresh_from_db()
        self.assertEqual(campanha.messages_failed, 0)
        self.assertEqual(campanha.messages_sent, 0)
