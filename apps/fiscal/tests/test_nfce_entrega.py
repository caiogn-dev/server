"""NFC-e de ENTREGA leva endereço do cliente e transportador.

Manual da SEFAZ-TO (Orientações NFC-e, "Entrega em domicílio"): o DANFE acompanha
o trânsito da mercadoria e devem ser informados obrigatoriamente os dados do
consumidor (CPF e endereço) e os do transportador. "Quando o transporte for
feito pela própria empresa, os dados da empresa devem constar do campo Dados
do transportador, independentemente se quem realiza o transporte é um motoboy,
ciclista etc., da própria empresa."

Até 13/set a NFC-e ia como venda presencial (indPres 1), sem endereço e sem
transportador, mesmo quando o pedido era entregue.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.services import build_nfce_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()
CPF = '52998224725'
FISCAL = {
    'provider': 'focus', 'ambiente': 'homologacao', 'focus_token': 't',
    'cnpj': '55599700000136', 'serie': '1', 'habilitado': True, 'uf': 'TO',
    'inscricao_estadual': '295724145',
}
ENDERECO = {'street': 'Quadra 112 Sul Rua SR 1', 'number': '2', 'complement': 'Casa',
            'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO',
            'zip_code': '77020-170'}


class NfceDeEntregaTests(APITestCase):
    def setUp(self):
        dono = User.objects.create_user(username='d-ent', password='x', email='d-ent@t.com')
        self.loja = Store.objects.create(
            name='Cê Saladas', slug='ce-ent', owner=dono, status='active',
            address='Av. JK, 100', city='Palmas', state='TO', zip_code='77001000',
            metadata={'fiscal': dict(FISCAL)})
        cat = StoreCategory.objects.create(store=self.loja, name='G', slug='g')
        self.produto = StoreProduct.objects.create(
            store=self.loja, name='Salada', price=40, track_stock=False, category=cat, sku='S1')

    def _pedido(self, **kw):
        base = dict(store=self.loja, customer_name='Maria Souza', customer_phone='5563999990000',
                    subtotal=Decimal('40'), total=Decimal('49'), delivery_fee=Decimal('9'),
                    payment_method='pix', payment_status='paid', status='delivered',
                    delivery_method='delivery', delivery_address=dict(ENDERECO),
                    metadata={'cpf_nota': CPF})
        base.update(kw)
        pedido = StoreOrder.objects.create(**base)
        StoreOrderItem.objects.create(order=pedido, product=self.produto, product_name='Salada',
                                      sku='S1', unit_price=40, quantity=1, subtotal=40)
        return pedido

    def _payload(self, pedido):
        return build_nfce_payload(pedido, get_fiscal_config(self.loja))

    def test_entrega_e_indicador_de_presenca_4(self):
        self.assertEqual(self._payload(self._pedido())['presenca_comprador'], 4)

    def test_retirada_continua_presencial(self):
        p = self._payload(self._pedido(delivery_method='pickup', delivery_fee=Decimal('0'),
                                       total=Decimal('40')))
        self.assertEqual(p['presenca_comprador'], 1)
        self.assertNotIn('logradouro_destinatario', p)
        self.assertNotIn('nome_transportador', p)

    def test_entrega_leva_o_endereco_do_cliente(self):
        p = self._payload(self._pedido())
        self.assertEqual(p['cpf_destinatario'], CPF)
        self.assertEqual(p['logradouro_destinatario'], 'Quadra 112 Sul Rua SR 1')
        self.assertEqual(p['numero_destinatario'], '2')
        self.assertEqual(p['complemento_destinatario'], 'Casa')
        self.assertEqual(p['bairro_destinatario'], 'Plano Diretor Sul')
        self.assertEqual(p['municipio_destinatario'], 'Palmas')
        self.assertEqual(p['uf_destinatario'], 'TO')
        self.assertEqual(p['cep_destinatario'], '77020170')

    def test_transportador_e_a_propria_loja(self):
        """Motoboy da loja: quem consta como transportador é a empresa."""
        p = self._payload(self._pedido())
        self.assertEqual(p['cnpj_transportador'], '55599700000136')
        self.assertEqual(p['nome_transportador'], 'Cê Saladas')
        self.assertEqual(p['inscricao_estadual_transportador'], '295724145')
        self.assertEqual(p['uf_transportador'], 'TO')
        self.assertEqual(p['municipio_transportador'], 'Palmas')

    def test_frete_por_conta_do_emitente_mesmo_gratis(self):
        """Frete grátis continua sendo entrega feita pela loja — não é 'sem frete'."""
        p = self._payload(self._pedido(delivery_fee=Decimal('0'), total=Decimal('40')))
        self.assertEqual(p['modalidade_frete'], 0)
        self.assertNotIn('frete', p)

    def test_endereco_sem_numero_nao_quebra_a_nota(self):
        """Número faltando: manda 'S/N', que é o que a SEFAZ aceita e o que o
        entregador lê — sem isso a nota inteira seria rejeitada."""
        endereco = dict(ENDERECO, number='')
        p = self._payload(self._pedido(delivery_address=endereco))
        self.assertEqual(p['numero_destinatario'], 'S/N')

    def test_entrega_sem_cpf_sai_sem_endereco(self):
        """Sem CPF/CNPJ o grupo do destinatário não pode existir (o schema exige
        o documento antes do nome e do endereço). A nota sai identificando só a
        entrega e o transportador; o aviso fica no log."""
        p = self._payload(self._pedido(metadata={}))
        self.assertEqual(p['presenca_comprador'], 4)
        self.assertNotIn('logradouro_destinatario', p)
        self.assertNotIn('cpf_destinatario', p)
        self.assertEqual(p['cnpj_transportador'], '55599700000136')
