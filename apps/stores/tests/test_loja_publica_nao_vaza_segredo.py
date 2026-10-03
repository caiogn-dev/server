"""`GET /api/v1/stores/<slug>/` é público (AllowAny) e devolvia o cadastro
inteiro da loja com o serializer do painel — medido em 02/10: dono, plano,
fim do teste grátis, taxa do vale, gateway e todo o `metadata`, incluindo
`metadata.fiscal.focus_token` (o token da Focus NFe: com ele qualquer um emite
e cancela nota em nome da loja), CNPJ e inscrição estadual.

O painel usa a MESMA rota logado e precisa do cadastro completo (Configurações,
Vitrine, Zonas de entrega). Regra: quem tem acesso à loja recebe tudo; o resto
do mundo recebe só a vitrine.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store

SEGREDO = 'f0cu5t0k3nf0cu5t0k3nf0cu5t0k3n00'


class LojaPublicaNaoVazaSegredoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.dono = User.objects.create_user(username='dono_lp', email='d@lp.com', password='x')
        self.store = Store.objects.create(
            name='Cê Saladas', slug='ce-saladas-lp', owner=self.dono, status='active',
            metadata={
                'fiscal': {'focus_token': SEGREDO, 'cnpj': '12345678000199'},
                'voucher_fee_percent': 5,
            },
        )
        self.url = f'/api/v1/stores/{self.store.slug}/'

    def test_anonimo_nao_recebe_token_fiscal_nem_dados_internos(self):
        resposta = APIClient().get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(SEGREDO, resposta.content.decode())
        # metadata sai só com as chaves da vitrine (capa, cidade…): ver
        # CatalogoPublicoNaoVazaSegredoTests.
        self.assertEqual(resposta.data.get('metadata'), {})
        for campo in ('owner', 'plan', 'trial_ends_at', 'orders_count',
                      'usa_gateway_da_plataforma', 'voucher_fee_percent',
                      'integrations_count', 'onboarding_completed', 'email',
                      'meta_pixel_id', 'clarity_id'):
            self.assertNotIn(campo, resposta.data, campo)

    def test_anonimo_continua_recebendo_a_vitrine(self):
        """O sitemap do cardapidex-web lê is_active/products_count/updated_at/logo."""
        resposta = APIClient().get(self.url)
        for campo in ('id', 'name', 'slug', 'logo_url', 'is_active', 'is_open',
                      'products_count', 'updated_at', 'city', 'primary_color'):
            self.assertIn(campo, resposta.data, campo)

    def test_dono_logado_continua_recebendo_o_cadastro_completo(self):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.dono).key}')
        resposta = cliente.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data['metadata']['fiscal']['focus_token'], SEGREDO)
        self.assertIn('plan', resposta.data)

    def test_usuario_logado_de_outra_loja_recebe_so_a_vitrine(self):
        User = get_user_model()
        outro = User.objects.create_user(username='outro_lp', email='o@lp.com', password='x')
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=outro).key}')
        resposta = cliente.get(self.url)
        self.assertNotIn(SEGREDO, resposta.content.decode())
        self.assertEqual(resposta.data.get('metadata'), {})


class CatalogoPublicoNaoVazaSegredoTests(TestCase):
    """03/10: `GET /stores/<slug>/catalog/` (público) devolvia o `metadata`
    inteiro da loja — token da Focus NFe, CNPJ, IE, fatos do bot, layouts de
    etiqueta (88 KB). A correção de 02/10 tinha coberto só a rota da loja."""

    def setUp(self):
        User = get_user_model()
        self.dono = User.objects.create_user(username='dono_cat', email='d@cat.com', password='x')
        self.store = Store.objects.create(
            name='Cê Saladas', slug='ce-saladas-cat', owner=self.dono, status='active',
            metadata={
                'fiscal': {'focus_token': SEGREDO, 'cnpj': '12345678000199'},
                'bot_fatos': [{'texto': 'interno'}],
                'cover_image_url': 'https://x/capa.jpg',
                'city': 'Palmas',
            },
        )

    def test_anonimo_nao_ve_segredo_mas_ve_o_que_a_vitrine_usa(self):
        r = APIClient().get(f'/api/v1/stores/{self.store.slug}/catalog/')
        self.assertEqual(r.status_code, 200)
        corpo = r.content.decode()
        self.assertNotIn(SEGREDO, corpo)
        self.assertNotIn('12345678000199', corpo)
        self.assertNotIn('bot_fatos', corpo)
        loja = r.json()['store']
        self.assertEqual(loja['metadata'], {'cover_image_url': 'https://x/capa.jpg', 'city': 'Palmas'})
        self.assertNotIn('owner', loja)

    def test_rota_da_loja_tambem_entrega_so_o_metadata_da_vitrine(self):
        r = APIClient().get(f'/api/v1/stores/{self.store.slug}/')
        self.assertNotIn(SEGREDO, r.content.decode())
        self.assertEqual(r.json().get('metadata'), {'cover_image_url': 'https://x/capa.jpg', 'city': 'Palmas'})
