"""O opt-out ponta a ponta: registrar, bloquear o envio e não recontar.

Estes testes reproduzem o incidente real de 25→28/ago/2026, em que cinco
pessoas apertaram "Parar promoções" numa campanha e receberam a campanha
seguinte três dias depois.
"""
from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignOptOut, CampaignRecipient
from apps.campaigns.services.optout import (
    chaves_bloqueadas,
    registrar_saida,
    revogar_saida,
)
from apps.whatsapp.models import WhatsAppAccount


class OptOutIntegracaoTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH1', waba_id='WABA1'
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Oferta do dia', total_recipients=1
        )
        CampaignRecipient.objects.create(
            campaign=self.campanha,
            phone_number='556392157531',
            status=CampaignRecipient.RecipientStatus.SENT,
            sent_at=timezone.now(),
        )

    def test_saida_e_atribuida_a_campanha_que_acabou_de_enviar(self):
        registro = registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        self.assertEqual(registro.campaign_id, self.campanha.id)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.messages_opted_out, 1)

    def test_webhook_repetido_nao_conta_duas_vezes(self):
        # A Meta reenvia webhook. Somar a cada reenvio transformaria
        # "1 descadastro" em "5" e destruiria a confiança na métrica.
        for _ in range(4):
            registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.messages_opted_out, 1)
        self.assertEqual(CampaignOptOut.objects.count(), 1)

    def test_bloqueio_pega_o_mesmo_numero_em_outro_formato(self):
        # O núcleo do incidente: a pessoa apertou "parar" numa conversa
        # (wa_id SEM o nono dígito) e a campanha seguinte a alcançou pelo
        # telefone do PEDIDO (COM o nono dígito). Para o sistema antigo eram
        # duas pessoas diferentes.
        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        bloqueadas = chaves_bloqueadas(self.conta)

        from apps.campaigns.services.contatos import chave_do_telefone
        self.assertIn(chave_do_telefone('63992157531'), bloqueadas)
        self.assertIn(chave_do_telefone('+55 (63) 99215-7531'), bloqueadas)

    def test_voltar_reativa_sem_apagar_a_prova(self):
        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        revogar_saida(self.conta, '556392157531')

        self.assertEqual(chaves_bloqueadas(self.conta), set())
        # A linha continua lá: é o registro do pedido de oposição e da data em
        # que ele foi atendido.
        self.assertEqual(CampaignOptOut.objects.count(), 1)
        self.assertIsNotNone(CampaignOptOut.objects.first().revogado_em)

    def test_saida_sem_campanha_recente_nao_culpa_ninguem(self):
        # Quem escreve "PARAR" meses depois não pode fazer a campanha antiga
        # carregar a culpa de um descadastro de hoje.
        CampaignRecipient.objects.update(sent_at=timezone.now() - timezone.timedelta(days=90))
        registro = registrar_saida(self.conta, '556392157531', 'PARAR', 'text')
        self.assertIsNone(registro.campaign_id)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.messages_opted_out, 0)

    def test_conta_diferente_nao_herda_o_bloqueio(self):
        # Parar de receber da Cê Saladas não pode silenciar a Pastita.
        outra = WhatsAppAccount.objects.create(
            name='Pastita', phone_number_id='PH2', waba_id='WABA2'
        )
        registrar_saida(self.conta, '556392157531', 'Parar promoções', 'button')
        self.assertEqual(chaves_bloqueadas(outra), set())
