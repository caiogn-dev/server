"""Campo salvo em branco tem que cair no padrão, não ir vazio para a SEFAZ.

O painel grava string vazia quando o dono não digita nada. `.get(chave, default)`
só usa o default se a CHAVE FALTA — com `''` salvo, o vazio vai para o XML e a
SEFAZ rejeita ("codigo ncm não pode ser vazio").
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.fiscal.services import build_nfce_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

CFG_COM_CAMPOS_EM_BRANCO = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok',
    'cnpj': '12.345.678/0001-90',
    'serie': '1',
    'habilitado': True,
    'ncm_padrao': '',
    'cfop_padrao': '',
    'csosn': '',
}


class CamposEmBrancoTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='o-ncm', email='o-ncm@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja NCM', slug='loja-ncm', owner=owner, status='active',
            metadata={'fiscal': dict(CFG_COM_CAMPOS_EM_BRANCO)},
        )
        cat = StoreCategory.objects.create(store=self.store, name='Geral', slug='g-ncm')
        produto = StoreProduct.objects.create(
            store=self.store, name='Almôndega', price=30.75, track_stock=False,
            category=cat, sku='ALM1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Ana Gabrielly', customer_phone='63984301666',
            customer_email='a@local.invalid', subtotal=92.25, total=92.25,
            payment_method='pix', delivery_method='pickup',
            status='pending', payment_status='pending',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=produto, product_name='Almôndega',
            sku='ALM1', unit_price=30.75, quantity=3, subtotal=92.25,
        )

    def test_ncm_em_branco_cai_no_padrao_de_8_digitos(self):
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        ncm = payload['itens'][0]['codigo_ncm']
        self.assertEqual(len(ncm), 8, f'NCM precisa ter 8 dígitos, veio {ncm!r}')
        self.assertEqual(ncm, '21069090')

    def test_cfop_e_csosn_em_branco_tambem_caem_no_padrao(self):
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        item = payload['itens'][0]
        self.assertEqual(item['cfop'], '5102')
        self.assertEqual(item['icms_situacao_tributaria'], '102')
