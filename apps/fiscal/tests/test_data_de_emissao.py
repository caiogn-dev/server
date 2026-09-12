"""A SEFAZ rejeita nota com data de emissão atrasada.

REJEIÇÃO REAL, 12/SET, primeira emissão depois do certificado ser aprovado:

    Rejeicao: NFC-e ou NF-e com DANFE Simplificado Tipo 2 com
    Data-Hora de emissão atrasada

O payload mandava `data_emissao = order.created_at` — a hora em que o CLIENTE
FEZ O PEDIDO. Mas `dhEmi` não é a data da venda: é a hora em que a nota é
emitida, e a SEFAZ só aceita uma janela de poucos minutos entre ela e a
transmissão. Como a loja emite depois de preparar e entregar, TODA nota nascia
atrasada — a emissão fiscal estava quebrada para 100% dos pedidos.

A data da venda não se perde: ela continua no pedido, e a nota referencia o
pedido. O que muda é só o campo que a SEFAZ usa para medir o atraso.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from apps.fiscal.services import build_nfce_payload, build_nfe_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '12.345.678/0001-90',
    'serie': '1',
    'habilitado': True,
    'uf': 'TO',
}


class DataDeEmissaoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-dhemi', email='owner-dhemi@test.com', password='x')
        self.store = Store.objects.create(
            name='Loja DhEmi', slug='loja-dhemi', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)})
        cat = StoreCategory.objects.create(store=self.store, name='Geral', slug='g')
        produto = StoreProduct.objects.create(
            store=self.store, name='Salada', price=20, track_stock=False,
            category=cat, sku='SAL1')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='63999990000',
            customer_email='x@local.invalid',
            subtotal=Decimal('20.00'), total=Decimal('20.00'),
            payment_method='pix', delivery_method='pickup',
            status='delivered', payment_status='paid',
            # A NF-e (modelo 55) exige documento do destinatário.
            metadata={'cpf_nota': '52998224725'},
            delivery_address={'street': 'Q 101', 'number': '10', 'city': 'Palmas',
                              'state': 'TO', 'zip_code': '77001000',
                              'neighborhood': 'Centro'},
        )
        StoreOrderItem.objects.create(
            order=self.order, product=produto, product_name='Salada',
            sku='SAL1', unit_price=20, quantity=1, subtotal=20)
        # Pedido de ONTEM: é o caso normal — a loja emite depois de entregar.
        StoreOrder.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(days=1))
        self.order.refresh_from_db()

    def _idade_em_segundos(self, payload):
        emitida = parse_datetime(payload['data_emissao'])
        self.assertIsNotNone(emitida, payload['data_emissao'])
        return abs((timezone.now() - emitida).total_seconds())

    def test_nfce_emite_com_a_hora_de_AGORA(self):
        """Ontem + 'atrasada' = rejeição 703, que foi o que aconteceu."""
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertLess(self._idade_em_segundos(payload), 60)

    def test_nfe_emite_com_a_hora_de_AGORA(self):
        payload = build_nfe_payload(self.order, get_fiscal_config(self.store))
        self.assertLess(self._idade_em_segundos(payload), 60)

    def test_a_data_de_emissao_NAO_e_a_data_do_pedido(self):
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertNotEqual(payload['data_emissao'], self.order.created_at.isoformat())

    def test_a_data_de_emissao_tem_fuso(self):
        """Sem offset a SEFAZ lê como UTC e a nota nasce 3h no futuro — que é
        a rejeição espelhada (data-hora de emissão posterior ao permitido)."""
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        emitida = parse_datetime(payload['data_emissao'])
        self.assertIsNotNone(emitida.tzinfo, payload['data_emissao'])

    def test_o_pedido_guarda_a_data_real_da_venda(self):
        """Trocar `dhEmi` não pode apagar QUANDO a venda aconteceu — ela
        continua no pedido, que é quem a nota referencia pelo `ref`."""
        ontem = timezone.now() - timedelta(days=1)
        self.assertLess(abs((self.order.created_at - ontem).total_seconds()), 120)


class AcrescimoNaNotaTests(DataDeEmissaoTests):
    """Cliente pagou com acréscimo do vale: a nota tem que somar o que ele pagou."""

    def test_acrescimo_do_vale_entra_como_outras_despesas_e_a_soma_fecha(self):
        StoreOrder.objects.filter(pk=self.order.pk).update(
            voucher_fee=Decimal('2.00'), total=Decimal('22.00'))
        self.order.refresh_from_db()
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertEqual(payload['valor_outras_despesas'], 2.0)
        itens = sum(i['valor_bruto'] for i in payload['itens'])
        pago = sum(f['valor_pagamento'] for f in payload['formas_pagamento'])
        soma = (itens + payload.get('frete', 0) + payload['valor_outras_despesas']
                - payload.get('valor_desconto', 0))
        self.assertAlmostEqual(soma, pago, places=2)

    def test_pedido_sem_acrescimo_nao_manda_o_campo(self):
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertNotIn('valor_outras_despesas', payload)
