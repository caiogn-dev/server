"""Duas rodadas ao mesmo tempo não podem mandar a mesma promoção duas vezes.

O agendador roda de minuto em minuto e pode pegar o mesmo destinatário em duas
rodadas (fila atrasada, worker lento, retry). A reserva é um UPDATE condicional:
quem consegue mudar de `pending` para `sending` é dono do envio. Ler e depois
gravar não serve — entre as duas coisas cabe a outra rodada, e o cliente recebe
a mensagem duas vezes.

E `sending` velho significa worker morto no meio do caminho: volta para a fila,
senão aquele cliente nunca mais recebe.
"""
from datetime import timedelta
from threading import Thread

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.rodada_da_janela import liberar_reservas_presas, reservar
from apps.whatsapp.models import WhatsAppAccount


def _destinatario():
    conta = WhatsAppAccount.objects.create(name='Loja', phone_number_id='PH-R', waba_id='WABA-R')
    campanha = Campaign.objects.create(account=conta, name='Promo')
    return CampaignRecipient.objects.create(
        campaign=campanha, phone_number='556399999001', contact_name='Cliente',
    )


class ReservaTests(TestCase):
    def setUp(self):
        self.destinatario = _destinatario()

    def test_reserva_devolve_true_uma_vez_so(self):
        self.assertTrue(reservar(self.destinatario.id))
        self.assertFalse(reservar(self.destinatario.id))

    def test_quem_reservou_fica_como_enviando(self):
        reservar(self.destinatario.id)

        self.destinatario.refresh_from_db()
        self.assertEqual(self.destinatario.status, CampaignRecipient.RecipientStatus.SENDING)

    def test_quem_ja_foi_enviado_nao_e_reservado_de_novo(self):
        CampaignRecipient.objects.filter(id=self.destinatario.id).update(status='sent')

        self.assertFalse(reservar(self.destinatario.id))

    def test_reserva_presa_volta_para_pendente_depois_de_10_min(self):
        CampaignRecipient.objects.filter(id=self.destinatario.id).update(
            status='sending', updated_at=timezone.now() - timedelta(minutes=11),
        )

        self.assertEqual(liberar_reservas_presas(), 1)
        self.destinatario.refresh_from_db()
        self.assertEqual(self.destinatario.status, CampaignRecipient.RecipientStatus.PENDING)

    def test_reserva_recente_nao_e_liberada(self):
        CampaignRecipient.objects.filter(id=self.destinatario.id).update(
            status='sending', updated_at=timezone.now(),
        )

        self.assertEqual(liberar_reservas_presas(), 0)


class ReservaSobCorridaTests(TransactionTestCase):
    """O teste que importa: dois processos disputando o mesmo destinatário."""

    def test_duas_rodadas_simultaneas_so_uma_envia(self):
        destinatario = _destinatario()
        resultados = []

        def tentar():
            try:
                resultados.append(reservar(destinatario.id))
            finally:
                connection.close()

        threads = [Thread(target=tentar) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(resultados), [False, True])
