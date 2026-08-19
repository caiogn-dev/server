"""GET no webhook do Mercado Pago responde 200.

O painel do MP VALIDA a URL de notificação antes de aceitá-la: ele bate um
GET na URL e exige resposta boa. Como a view só declarava `post`, o DRF
respondia 405 e o formulário recusava a URL com "O endereço deve ser válido"
— impossível cadastrar o webhook, mesmo com a URL correta.

O GET é só sinal de vida: não processa notificação, não lê corpo, não toca
em pedido. Todo o processamento continua exclusivamente no POST.
"""
from django.test import TestCase
from django.urls import reverse


class MPWebhookGetHealthcheckTests(TestCase):
    def test_get_no_webhook_responde_200(self):
        resp = self.client.get(reverse('mercadopago_webhook'))
        self.assertEqual(resp.status_code, 200)

    def test_get_na_rota_por_loja_responde_200(self):
        resp = self.client.get(
            reverse('mercadopago_webhook_slug', kwargs={'store_slug': 'ce-saladas'})
        )
        self.assertEqual(resp.status_code, 200)

    def test_get_nao_processa_notificacao(self):
        """Sinal de vida não pode virar porta de entrada de notificação."""
        with self.assertNumQueries(0):
            resp = self.client.get(
                reverse('mercadopago_webhook') + '?type=payment&data.id=123'
            )
        self.assertEqual(resp.status_code, 200)
