"""Autenticação do iFood: um app, muitos restaurantes.

O DONO PEDIU (05/09): "deixe pronto para o ifood oauth, ou então por token...
veja qual melhor e aí eu configuro a conta depois".

NÃO EXISTE TOKEN ESTÁTICO. O iFood só oferece OAuth2, e os dois fluxos batem no
mesmo endereço — `POST /authentication/v1.0/oauth/token`, corpo
`x-www-form-urlencoded`. O que muda é o `grantType`:

  centralizado   `client_credentials` — para quem integra as PRÓPRIAS lojas.
                 Não devolve refreshToken: cada renovação repete a chamada.

  distribuído    `authorization_code` e depois `refresh_token` — para quem
                 integra lojas DE TERCEIROS. Cada lojista autoriza uma vez com
                 um `userCode`, e a partir daí o refresh renova sozinho.

ESCOLHI DISTRIBUÍDO, e a razão é o negócio: o Cardapidex é vendido para donos
de restaurante, cada um com o próprio cadastro no iFood. Centralizado só
serviria se todas as lojas fossem do Caio. Fazer centralizado agora e migrar
depois seria refazer o vínculo com cada cliente, um a um, pedindo que
autorizem de novo.

O TOKEN DURA 6 HORAS. Isso é o coração deste arquivo, e é onde este projeto já
se queimou: o OAuth do Mercado Pago tinha `renovar()` escrito e SEM NENHUM
CALLER — a loja conectava, funcionava, e pararia de vender meses depois sem
ninguém entender por quê. Aqui a renovação tem dono, e um teste garante que ela
continue tendo.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store
from apps.stores.services import ifood_oauth

User = get_user_model()

CREDENCIAIS = {'IFOOD_CLIENT_ID': 'app-123', 'IFOOD_CLIENT_SECRET': 'segredo'}


@override_settings(**CREDENCIAIS)
class IfoodAutenticacaoTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-ifood', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-ifood', owner=dono,
            store_type='food', status='active',
        )

    # ── o vínculo: o lojista autoriza uma vez ───────────────────────────

    def test_pede_o_codigo_que_o_lojista_digita_no_portal(self):
        resposta = {
            'userCode': 'ABCD-1234',
            'authorizationCodeVerifier': 'verificador-xyz',
            'verificationUrl': 'https://portal.ifood.com.br/apps/code',
            'expiresIn': 600,
        }
        with patch.object(ifood_oauth, '_post', return_value=resposta):
            vinculo = ifood_oauth.iniciar_vinculo(self.store)

        self.assertEqual(vinculo['user_code'], 'ABCD-1234')
        self.assertIn('portal.ifood', vinculo['url'])

    def test_guarda_o_verificador_ate_o_lojista_voltar(self):
        """O verificador só existe entre pedir o código e trocar por token.

        Perdê-lo obriga o lojista a começar de novo — e ele já saiu da tela.
        """
        with patch.object(ifood_oauth, '_post', return_value={
            'userCode': 'ABCD-1234', 'authorizationCodeVerifier': 'verificador-xyz',
            'verificationUrl': 'https://portal.ifood.com.br/apps/code', 'expiresIn': 600,
        }):
            ifood_oauth.iniciar_vinculo(self.store)

        integracao = ifood_oauth.integracao_da_loja(self.store)
        self.assertEqual(integracao.authorization_code_verifier, 'verificador-xyz')

    def test_conclui_o_vinculo_e_guarda_os_dois_tokens(self):
        self._com_verificador()
        resposta = {
            'accessToken': 'tok-de-acesso',
            'refreshToken': 'tok-de-renovacao',
            'expiresIn': 21600,
        }
        with patch.object(ifood_oauth, '_post', return_value=resposta) as chamada:
            ifood_oauth.concluir_vinculo(self.store, 'codigo-do-portal')

        corpo = chamada.call_args.kwargs['dados']
        self.assertEqual(corpo['grantType'], 'authorization_code')
        self.assertEqual(corpo['authorizationCode'], 'codigo-do-portal')
        self.assertEqual(corpo['authorizationCodeVerifier'], 'verificador-xyz')

        integracao = ifood_oauth.integracao_da_loja(self.store)
        self.assertEqual(integracao.access_token, 'tok-de-acesso')
        self.assertEqual(integracao.refresh_token, 'tok-de-renovacao')
        self.assertTrue(integracao.conectado)

    def test_o_token_nao_fica_legivel_no_banco(self):
        """Token do iFood é credencial de terceiro: vai cifrado, como o do MP.

        A conferência é na COLUNA, não no atributo: `EncryptedCharField`
        decifra na leitura, então ler pelo modelo devolveria o texto claro e o
        teste passaria mesmo com a cifra desligada.
        """
        self._conectada(access='tok-secreto')

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token_encrypted FROM store_ifood_integrations '
                'WHERE store_id = %s', [str(self.store.id)],
            )
            (guardado,) = cursor.fetchone()

        self.assertNotIn('tok-secreto', guardado)
        self.assertTrue(guardado)

    # ── a renovação, que é onde este projeto já se queimou ──────────────

    def test_token_perto_de_vencer_e_renovado_antes_de_usar(self):
        self._conectada(expira_em=timedelta(minutes=4))
        with patch.object(ifood_oauth, '_post', return_value={
            'accessToken': 'novo', 'refreshToken': 'novo-refresh', 'expiresIn': 21600,
        }) as chamada:
            token = ifood_oauth.token_valido(self.store)

        self.assertEqual(token, 'novo')
        self.assertEqual(chamada.call_args.kwargs['dados']['grantType'], 'refresh_token')

    def test_token_com_folga_nao_gasta_chamada(self):
        self._conectada(expira_em=timedelta(hours=5))
        with patch.object(ifood_oauth, '_post') as chamada:
            token = ifood_oauth.token_valido(self.store)

        self.assertEqual(token, 'tok-de-acesso')
        chamada.assert_not_called()

    def test_loja_sem_vinculo_nao_devolve_token(self):
        self.assertIsNone(ifood_oauth.token_valido(self.store))

    def test_refresh_recusado_marca_a_loja_como_desconectada(self):
        """Lojista revogou o acesso no portal. A loja precisa SABER.

        Falhar calado aqui é o pedido do iFood parando de entrar sem ninguém
        perceber — o modo de falha mais caro de uma integração de vendas.
        """
        self._conectada(expira_em=timedelta(minutes=1))
        with patch.object(ifood_oauth, '_post', side_effect=ifood_oauth.IfoodRecusou('invalid_grant')):
            token = ifood_oauth.token_valido(self.store)

        self.assertIsNone(token)
        integracao = ifood_oauth.integracao_da_loja(self.store)
        self.assertFalse(integracao.conectado)
        self.assertIn('invalid_grant', integracao.ultimo_erro)

    # ── configuração ────────────────────────────────────────────────────

    @override_settings(IFOOD_CLIENT_ID='', IFOOD_CLIENT_SECRET='')
    def test_sem_credencial_do_app_avisa_em_vez_de_falhar_estranho(self):
        with self.assertRaises(ifood_oauth.IfoodNaoConfigurado):
            ifood_oauth.iniciar_vinculo(self.store)

    def test_o_endereco_e_o_da_api_de_lojista(self):
        self.assertEqual(
            ifood_oauth.URL_TOKEN,
            'https://merchant-api.ifood.com.br/authentication/v1.0/oauth/token',
        )

    # ── apoio ───────────────────────────────────────────────────────────

    def _com_verificador(self):
        with patch.object(ifood_oauth, '_post', return_value={
            'userCode': 'ABCD-1234', 'authorizationCodeVerifier': 'verificador-xyz',
            'verificationUrl': 'https://portal.ifood.com.br/apps/code', 'expiresIn': 600,
        }):
            ifood_oauth.iniciar_vinculo(self.store)

    def _conectada(self, access='tok-de-acesso', expira_em=timedelta(hours=5)):
        self._com_verificador()
        with patch.object(ifood_oauth, '_post', return_value={
            'accessToken': access, 'refreshToken': 'tok-de-renovacao', 'expiresIn': 21600,
        }):
            ifood_oauth.concluir_vinculo(self.store, 'codigo-do-portal')
        integracao = ifood_oauth.integracao_da_loja(self.store)
        integracao.token_expires_at = timezone.now() + expira_em
        integracao.save(update_fields=['token_expires_at'])
