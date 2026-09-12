"""O painel precisa MOSTRAR o que já está configurado.

A loja configurava o vale, saía da tela, voltava — e encontrava tudo em branco,
como se nunca tivesse configurado nada. Três defeitos somados produziam isso, e
cada um sozinho já bastava para a tela mentir.

O segredo NÃO volta, e isso está certo. O que tem que voltar é o ESTADO: que a
chave existe, qual é a pública (o cardápio já a entrega a todo cliente) e quais
bandeiras estão marcadas.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.payment_serializers import (
    StorePaymentGatewayListSerializer,
    StorePaymentGatewaySerializer,
)
from apps.stores.models import Store, StorePaymentGateway

User = get_user_model()


class EstadoDoGatewayTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-gw', password='x', email='o-gw@real.com')
        self.store = Store.objects.create(
            name='Loja GW', slug='loja-gw', owner=self.owner, status='active')
        self.gateway = StorePaymentGateway.objects.create(
            store=self.store, name='Pagar.me (vale)', gateway_type='pagarme',
            is_enabled=True,
            api_key='sk_test_segredo',
            public_key='pk_test_publica',
            configuration={'voucher_brands': ['vr', 'sodexo', 'ticket']},
        )

    # ── o que a LISTA devolve (é ela que o painel chama) ────────────────────
    def test_a_lista_diz_quais_bandeiras_estao_marcadas(self):
        """Sem `configuration` na lista, o painel desmarcava tudo ao abrir — e
        um Salvar depois disso APAGARIA a configuração real da loja."""
        dados = StorePaymentGatewayListSerializer(self.gateway).data
        self.assertEqual(dados['configuration']['voucher_brands'],
                         ['vr', 'sodexo', 'ticket'])

    def test_a_lista_devolve_a_chave_PUBLICA(self):
        """Pública é pública: o cardápio já a entrega a todo cliente que abre o
        checkout. Esconder dela o lojista não protege nada e impede que ele
        confira se cadastrou a conta certa."""
        dados = StorePaymentGatewayListSerializer(self.gateway).data
        self.assertEqual(dados['public_key'], 'pk_test_publica')

    def test_a_lista_NUNCA_devolve_o_segredo(self):
        dados = StorePaymentGatewayListSerializer(self.gateway).data
        texto = str(dados)
        self.assertNotIn('sk_test_segredo', texto)
        for campo in ('api_key', 'api_secret', 'access_token', 'webhook_secret'):
            self.assertNotIn(campo, dados)

    def test_a_lista_diz_que_EXISTE_credencial(self):
        """O Pagar.me guarda o segredo em `api_key`; só o Mercado Pago usa
        `access_token`. Olhando só para o token, toda loja de vale aparecia
        como 'sem credencial' — configurada e marcada como não configurada."""
        dados = StorePaymentGatewayListSerializer(self.gateway).data
        self.assertTrue(dados['tem_credencial'])

    def test_gateway_sem_nenhum_segredo_e_honesto(self):
        vazio = StorePaymentGateway.objects.create(
            store=self.store, name='Vazio', gateway_type='pagarme', is_enabled=False)
        dados = StorePaymentGatewayListSerializer(vazio).data
        self.assertFalse(dados['tem_credencial'])

    def test_o_token_do_mercado_pago_tambem_conta(self):
        mp = StorePaymentGateway.objects.create(
            store=self.store, name='MP', gateway_type='mercadopago',
            access_token='APP_USR-xxx')
        self.assertTrue(StorePaymentGatewayListSerializer(mp).data['tem_credencial'])

    # ── o detalhe segue a mesma regra ───────────────────────────────────────
    def test_o_detalhe_tambem_devolve_a_publica_e_esconde_o_segredo(self):
        dados = StorePaymentGatewaySerializer(self.gateway).data
        self.assertEqual(dados['public_key'], 'pk_test_publica')
        self.assertNotIn('sk_test_segredo', str(dados))

    def test_salvar_sem_mandar_a_publica_NAO_apaga_a_publica(self):
        """Campo de segredo em branco é 'não mexi nisso'. A pública agora volta
        preenchida na tela, então ela chega de volta; mas se um cliente antigo
        mandar vazio, apagar seria quebrar o cartão em produção."""
        s = StorePaymentGatewaySerializer(
            self.gateway, data={'public_key': ''}, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        self.gateway.refresh_from_db()
        self.assertEqual(self.gateway.public_key, 'pk_test_publica')

    # ── ponta a ponta, como o painel chama ──────────────────────────────────
    def test_o_painel_ve_a_configuracao_ao_abrir_a_tela(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get('/api/v1/stores/payments/gateways/',
                            {'store': str(self.store.id)})
        self.assertEqual(r.status_code, 200, r.content)
        linhas = r.data['results'] if isinstance(r.data, dict) else r.data
        pagarme = next(g for g in linhas if g['gateway_type'] == 'pagarme')
        self.assertEqual(pagarme['configuration']['voucher_brands'],
                         ['vr', 'sodexo', 'ticket'])
        self.assertEqual(pagarme['public_key'], 'pk_test_publica')
        self.assertTrue(pagarme['tem_credencial'])
        self.assertNotIn('sk_test_segredo', str(r.data))
