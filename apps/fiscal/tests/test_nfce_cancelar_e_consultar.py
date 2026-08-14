"""Fiscal: cancelar e consultar a NFC-e depois de emitida.

Sem estes dois a emissão é uma via de mão única: nota errada não volta e nota
que ficou 'processando' na SEFAZ nunca sai desse estado no nosso banco.

Prazo legal do cancelamento de NFC-e: 30 minutos após a autorização. Passado
isso, o caminho é outro (nota de devolução) — e a API tem que dizer isso em
vez de deixar o operador clicando.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.fiscal.models import FiscalDocument
from apps.fiscal.providers.base import EmitResult
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus', 'ambiente': 'homologacao', 'focus_token': 'tok-teste',
    'cnpj': '11444777000161', 'serie': '1', 'habilitado': True,
}


class CancelarEConsultarTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-cancel', email='owner-cancel@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Cancel', slug='loja-cancel', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=20, track_stock=False,
            category=category, sku='SAL1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente Balcão', customer_phone='00000000000',
            customer_email='x@local.invalid', subtotal=20, total=20,
            payment_method='cash', delivery_method='pickup',
            status='pending', payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Salada',
            sku='SAL1', unit_price=20, quantity=1, subtotal=20,
        )
        self.doc = FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus',
            status=FiscalDocument.Status.AUTHORIZED, ref=f'nfce-{self.order.id}',
            chave_acesso='1' * 44, numero='10', serie='1',
        )
        self.client.force_authenticate(self.owner)
        self.base = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}'

    # ── cancelamento ──────────────────────────────────────────────
    @patch('apps.fiscal.services.FocusProvider.cancel_nfce')
    def test_cancelar_dentro_do_prazo_marca_cancelada(self, mock_cancel):
        mock_cancel.return_value = EmitResult(status='cancelled', chave_acesso='1' * 44)
        resp = self.client.post(
            f'{self.base}/cancel_nfce/', {'justificativa': 'Pedido cancelado pelo cliente'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, FiscalDocument.Status.CANCELLED)

    def test_justificativa_curta_e_recusada(self):
        """A SEFAZ exige no mínimo 15 caracteres — recusar antes de gastar a
        chamada e receber rejeição."""
        resp = self.client.post(f'{self.base}/cancel_nfce/', {'justificativa': 'errei'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, FiscalDocument.Status.AUTHORIZED)

    @patch('apps.fiscal.services.FocusProvider.cancel_nfce')
    def test_fora_do_prazo_de_30min_explica_o_caminho(self, mock_cancel):
        FiscalDocument.objects.filter(pk=self.doc.pk).update(
            created_at=timezone.now() - timedelta(minutes=31),
        )
        resp = self.client.post(
            f'{self.base}/cancel_nfce/', {'justificativa': 'Cliente desistiu da compra'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('30', resp.data['error'])
        mock_cancel.assert_not_called()

    def test_nota_nao_autorizada_nao_tem_o_que_cancelar(self):
        self.doc.status = FiscalDocument.Status.ERROR
        self.doc.save(update_fields=['status'])
        resp = self.client.post(
            f'{self.base}/cancel_nfce/', {'justificativa': 'Cliente desistiu da compra'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    # ── consulta ──────────────────────────────────────────────────
    @patch('apps.fiscal.services.FocusProvider.consult')
    def test_consulta_atualiza_pendente_que_a_sefaz_ja_autorizou(self, mock_consult):
        self.doc.status = FiscalDocument.Status.PENDING
        self.doc.chave_acesso = ''
        self.doc.save(update_fields=['status', 'chave_acesso'])
        mock_consult.return_value = EmitResult(
            status='authorized', chave_acesso='9' * 44, numero='11',
            qrcode_url='https://sefaz/qr',
        )
        resp = self.client.get(f'{self.base}/nfce/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['documentos'][0]['status'], 'authorized')
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.chave_acesso, '9' * 44)

    @patch('apps.fiscal.services.FocusProvider.consult')
    def test_consulta_de_nota_ja_autorizada_nao_chama_o_provedor(self, mock_consult):
        resp = self.client.get(f'{self.base}/nfce/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['documentos'][0]['chave_acesso'], '1' * 44)
        mock_consult.assert_not_called()

    def test_consulta_diz_se_a_loja_emite(self):
        """O painel só mostra o bloco de nota fiscal em loja que emite — sem
        isso, 12 lojas ganhariam um botão que só sabe dar erro."""
        self.assertTrue(self.client.get(f'{self.base}/nfce/').data['habilitado'])

        self.store.metadata = {'fiscal': {**FISCAL_CFG, 'habilitado': False}}
        self.store.save(update_fields=['metadata'])
        self.assertFalse(self.client.get(f'{self.base}/nfce/').data['habilitado'])

    def test_pedido_sem_nota_responde_vazio_e_nao_404(self):
        """O painel pergunta o estado de todo pedido; 'ainda não emitiu' é
        resposta legítima, não erro."""
        self.doc.delete()
        resp = self.client.get(f'{self.base}/nfce/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['documentos'], [])
