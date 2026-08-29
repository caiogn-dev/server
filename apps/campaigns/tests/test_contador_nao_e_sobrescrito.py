"""O envio apagava os recibos que chegavam durante o próprio envio.

SINTOMA (medido em produção, 28/ago/2026):

    campanha    painel dizia    realidade nas linhas
    24/ago      16 entregues    138
    25/ago      24 entregues    223
    28/ago      21 entregues    246

A entrega real era 89%. A tela mostrava 7,6% — o dono estava olhando como
fracasso uma campanha que funcionou, e "lidas" aparecia MAIOR que "entregues",
que é impossível e destrói a confiança na tela inteira.

A CAUSA NÃO ERA O RECIBO. `registrar_recibo` já estava correto: incrementa com
`F()` e marca `delivered_at` na linha — e as linhas estavam certas.

A causa era `process_campaign_batch`:

    campaign = Campaign.objects.get(...)   # lê messages_delivered = 0
    ... envia 50 mensagens (demora) ...    # webhooks chegam e incrementam a COLUNA
    campaign.save()                        # grava o objeto em MEMÓRIA -> zera tudo

Um `save()` sem `update_fields` grava todas as colunas com os valores lidos no
início do lote, apagando qualquer escrita concorrente. Só sobreviviam os
recibos que chegavam depois do último `save()`.

A correção é gravar SÓ o que este método é dono de mudar.
"""
from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.campaign_service import CampaignService
from apps.whatsapp.models import WhatsAppAccount


class ContadorNaoESobrescritoTests(TestCase):
    def setUp(self):
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number_id='PH1', waba_id='W1'
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Oferta',
            status=Campaign.CampaignStatus.RUNNING,
            started_at=timezone.now(), total_recipients=1,
        )
        CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number='556391110001',
            status=CampaignRecipient.RecipientStatus.PENDING,
        )

    def test_recibo_que_chega_durante_o_lote_sobrevive(self):
        """A corrida real: o webhook chega DEPOIS do `get` e ANTES do `save`.

        Incrementar antes do `get` não reproduz nada — o lote leria o valor
        novo e o regravaria igual. O bug só aparece quando a coluna muda
        enquanto o lote já está com o objeto velho na mão, e é por isso que a
        simulação acontece de dentro do envio.
        """
        from unittest.mock import patch

        def webhook_chega_durante_o_envio(*args, **kwargs):
            Campaign.objects.filter(id=self.campanha.id).update(
                messages_delivered=138, messages_read=28
            )
            raise RuntimeError('envio simulado')

        servico = CampaignService()
        with patch(
            'apps.campaigns.services.campaign_service.MessageService'
        ) as fake:
            fake.return_value.send_text_message.side_effect = (
                webhook_chega_durante_o_envio
            )
            servico.process_campaign_batch(str(self.campanha.id))

        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.messages_delivered, 138)
        self.assertEqual(self.campanha.messages_read, 28)

    def test_o_lote_ainda_grava_o_que_e_dele(self):
        # A correção não pode ir longe demais: enviadas, falhas e o desfecho da
        # campanha continuam sendo responsabilidade deste método.
        servico = CampaignService()
        servico.process_campaign_batch(str(self.campanha.id))

        self.campanha.refresh_from_db()
        # Sem WhatsApp de verdade o envio falha — e falha CONTA.
        self.assertEqual(
            self.campanha.messages_sent + self.campanha.messages_failed, 1
        )
        self.assertEqual(self.campanha.status, Campaign.CampaignStatus.COMPLETED)
        self.assertIsNotNone(self.campanha.completed_at)
