"""14/10 — pedido CE-2610141687 (Enna, WhatsApp) entrou no painel sem
localização e como "Cliente WhatsApp".

1. LOCALIZAÇÃO. O endereço salvo dela só tinha texto (os dois pedidos
   anteriores foram lançados no PDV sem pino). Para cotar o frete o servidor
   geocodificou o texto — achou o ponto, 1,51 km — e jogou a coordenada fora:
   o pedido saiu sem `delivery_lat/lng`, o entregador sem mapa, e o cadastro
   dela continuou sem ponto para o próximo pedido.

2. NOME. A ferramenta `finalizar_pedido` do agente lia `StoreCustomer.name`,
   campo que não existe; o erro era engolido e o pedido nascia "Cliente
   WhatsApp". Pior: o cadastro aceitava esse nome reserva por cima do nome de
   verdade — o usuário dela passou a se chamar "Cliente WhatsApp".
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreOrder, StoreProduct
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.unified_delivery_service import UnifiedDeliveryService

User = get_user_model()

TEXTO = 'Secretaria de Cidadania e Justiça, Av. Juscelino Kubitscheck, 78-162 - Plano Diretor Norte, Palmas - TO'


class _Loja(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='enna-owner', email='eo@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Cê', slug='ce-enna', status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD, city='Palmas', state='TO',
        )
        cat = StoreCategory.objects.create(store=self.store, name='Saladas', slug='saladas-enna', is_active=True)
        self.produto = StoreProduct.objects.create(
            store=self.store, category=cat, name='Magnífico Camarão', slug='camarao-enna',
            price=Decimal('48.99'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )

    def _carrinho(self):
        cart = StoreCart.objects.create(store=self.store, session_key=f'enna-{StoreCart.objects.count()}')
        StoreCartItem.objects.create(cart=cart, product=self.produto, quantity=1)
        return cart


@patch('apps.stores.services.checkout_service.trigger_order_email_automation')
@patch('apps.stores.services.print_service.enqueue_order_print_job')
class LocalizacaoDoPedidoTests(_Loja):
    COTACAO = {
        'fee': 8.0, 'distance_km': 1.51, 'duration_minutes': 3, 'is_valid': True, 'available': True,
        'zone_name': 'Dinâmica', 'lat': -10.1801, 'lng': -48.3322, 'coordinate_source': 'endereco_escrito',
    }

    def _pedido(self, endereco):
        with patch.object(CheckoutService, 'calculate_delivery_fee_for_payload', return_value=dict(self.COTACAO)):
            return CheckoutService.create_order(
                cart=self._carrinho(),
                customer_data={'name': 'Enna Hannes', 'email': '', 'phone': '5563992129009'},
                delivery_data={'method': 'delivery', 'address': endereco},
            )

    def test_endereco_so_com_texto_ganha_o_ponto_que_a_cotacao_achou(self, _p, _e):
        pedido = self._pedido({'raw_address': TEXTO})
        self.assertEqual(float(pedido.delivery_lat), -10.1801)
        self.assertEqual(float(pedido.delivery_lng), -48.3322)
        self.assertEqual(pedido.delivery_address['lat'], -10.1801)
        # Ponto do texto, não do cliente: o painel não pode tratá-lo como pino confirmado.
        self.assertEqual(pedido.delivery_address['coordinate_source'], 'endereco_escrito')
        self.assertFalse(pedido.delivery_address['coordinates_confirmed'])

    def test_pino_do_cliente_nunca_e_trocado_pelo_ponto_da_cotacao(self, _p, _e):
        pedido = self._pedido({'raw_address': TEXTO, 'lat': -10.2, 'lng': -48.3, 'coordinates_confirmed': True})
        self.assertEqual(float(pedido.delivery_lat), -10.2)
        self.assertEqual(pedido.delivery_address['lat'], -10.2)
        self.assertNotEqual(pedido.delivery_address.get('coordinate_source'), 'endereco_escrito')


class CotacaoDevolveOPontoTests(TestCase):
    def test_ponto_achado_pelo_texto_volta_na_cotacao(self):
        with patch.object(UnifiedDeliveryService, '_resolve_coordinates',
                          return_value={'success': True, 'lat': -10.18, 'lng': -48.33}), \
             patch.object(UnifiedDeliveryService, '_calcular_com_ponto',
                          return_value={'success': True, 'fee': 8.0}) as calcular:
            r = UnifiedDeliveryService.calculate_delivery_fee(store=None, address_text=TEXTO)
        self.assertEqual((r['lat'], r['lng']), (-10.18, -48.33))
        self.assertEqual(r['coordinate_source'], 'endereco_escrito')
        # O ponto resolvido segue para o cálculo: nada de geocodificar duas vezes.
        self.assertEqual(calcular.call_args.kwargs['lat'], -10.18)

    def test_com_pino_a_origem_e_o_pino(self):
        with patch.object(UnifiedDeliveryService, '_resolve_coordinates',
                          return_value={'success': True, 'lat': -10.2, 'lng': -48.3}), \
             patch.object(UnifiedDeliveryService, '_calcular_com_ponto', return_value={'success': True, 'fee': 8.0}):
            r = UnifiedDeliveryService.calculate_delivery_fee(store=None, address_text=TEXTO, lat=-10.2, lng=-48.3)
        self.assertEqual(r['coordinate_source'], 'pin')

    def test_falha_nao_inventa_ponto(self):
        with patch.object(UnifiedDeliveryService, '_resolve_coordinates',
                          return_value={'success': False, 'error': 'não achei'}):
            r = UnifiedDeliveryService.calculate_delivery_fee(store=None, address_text='xyz')
        self.assertFalse(r['success'])
        self.assertNotIn('lat', r)


class NomeDoClienteTests(_Loja):
    def test_nome_reserva_e_reconhecido(self):
        for nome in ('Cliente WhatsApp', 'Cliente', 'cliente web', 'Cliente PDV'):
            self.assertTrue(CustomerIdentityService.is_placeholder_name(nome), nome)
        for nome in ('Enna Hannes', 'Clientela Silva'):
            self.assertFalse(CustomerIdentityService.is_placeholder_name(nome), nome)

    def test_nome_reserva_nao_apaga_o_nome_do_cadastro(self):
        CustomerIdentityService.resolve_user(phone='5563992129009', full_name='Enna Hannes')
        resolvido, _, _ = CustomerIdentityService.resolve_user(phone='5563992129009', full_name='Cliente WhatsApp')
        resolvido.refresh_from_db()
        self.assertEqual((resolvido.first_name, resolvido.last_name), ('Enna', 'Hannes'))

    def test_melhor_nome_vem_do_pedido_anterior_quando_o_cadastro_e_reserva(self):
        dj = User.objects.create_user(username='enna2', first_name='Cliente', last_name='WhatsApp')
        StoreOrder.objects.create(
            store=self.store, customer=dj, customer_name='Enna Hannes', customer_phone='5563992129009',
            subtotal=Decimal('40'), total=Decimal('40'),
        )
        self.assertEqual(CustomerIdentityService.melhor_nome('5563992129009', store=self.store), 'Enna Hannes')

    def test_melhor_nome_limpa_emoji_do_contato(self):
        with patch.object(CustomerIdentityService, 'whatsapp_name', return_value='🌸 Enna  Hannes 🌸'):
            self.assertEqual(CustomerIdentityService.melhor_nome('5563900000000', store=self.store), 'Enna Hannes')

    def test_sem_nome_nenhum_devolve_vazio(self):
        with patch.object(CustomerIdentityService, 'whatsapp_name', return_value=''):
            self.assertEqual(CustomerIdentityService.melhor_nome('5563900000001', store=self.store), '')
