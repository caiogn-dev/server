"""A tela precisa saber quanto o cliente ganha por indicar.

O CASO REAL (04/09): o dono perguntou "a Elisangela quis indicar, mas como vou
saber quem veio pela Elisangela?". A resposta era: não tem como. O rastreio
existe inteiro no backend — link `?indica=<telefone>` guardado 30 dias no
navegador do amigo, que vira `metadata.indicado_por` no pedido e credita quem
indicou — e nenhuma tela gerava esse link. Zero lotes de indicação em produção,
não porque ninguém indica, mas porque não havia o que compartilhar.

Para convidar alguém a indicar é preciso dizer quanto ele ganha, e esse número
mora só no backend (`cashback_referral_percent`, 5% por padrão). Sem ele a tela
teria que escolher entre inventar um número — que é mentir sobre dinheiro — e
falar em silêncio sobre o valor, que não convence ninguém a indicar.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.stores.models import Store


class CarteiraInformaIndicacaoTest(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user(username='dona-indica', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-indica', owner=dono,
            store_type='food', status='active',
        )
        self.store.metadata = {'cashback_enabled': True}
        self.store.save(update_fields=['metadata'])

    def _carteira(self):
        return self.client.get(f'/api/v1/stores/{self.store.slug}/carteira/')

    def test_a_tela_recebe_o_percentual_de_indicacao(self):
        resposta = self._carteira()

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('referral_percent', resposta.data)
        self.assertEqual(Decimal(resposta.data['referral_percent']), Decimal('5'))

    def test_o_percentual_segue_o_que_a_loja_configurou(self):
        """Loja que paga 8% não pode ter a tela prometendo 5%."""
        self.store.metadata = {**self.store.metadata, 'cashback_referral_percent': '8'}
        self.store.save(update_fields=['metadata'])

        self.assertEqual(Decimal(self._carteira().data['referral_percent']), Decimal('8'))

    def test_o_percentual_e_texto_como_os_outros_valores(self):
        """Decimal vira float no JSON e 5.00 já virou 4.999... neste projeto."""
        self.assertIsInstance(self._carteira().data['referral_percent'], str)
