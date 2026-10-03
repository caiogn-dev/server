"""Fatura de assinatura: PIX com validade real + aviso ao dono (03/10/2026).

- O PIX da Orders API vence em ~24 h (date_of_expiration); o sistema gravava
  +3 dias e reaproveitava o código vencido.
- Nenhum código mandava a fatura ao dono: ela só existia na tela de Plano.
"""
from datetime import datetime, timedelta, timezone as dtz
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from apps.stores.models import Store, StoreSubscription, StorePayment
from apps.stores.services import pix_billing_service, aviso_de_fatura


def _orders(payment_id='111', qr='PIXCODE', venc='2026-10-12T10:00:00.000-04:00'):
    return (201, {'id': 'ORD1', 'status': 'action_required', 'transactions': {'payments': [{
        'id': 'PAY1', 'date_of_expiration': venc,
        'payment_method': {'id': 'pix', 'type': 'bank_transfer', 'qr_code': qr,
                           'qr_code_base64': 'B64', 'ticket_url': f'https://www.mercadopago.com.br/payments/{payment_id}/ticket'},
    }]}})


class PixComValidadeRealTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user('dono_fat', 'dono@fat.com', 'x')
        self.loja = Store.objects.create(name='Nathaluecake', slug='nath-fat', plan='starter', owner=dono)
        self.sub = StoreSubscription.objects.create(store=self.loja, plan='starter')
        self.agora = datetime(2026, 10, 11, 12, 0, tzinfo=dtz.utc)

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_grava_a_validade_que_o_mercado_pago_devolve(self, criar):
        criar.return_value = _orders(venc='2026-10-12T10:00:00.000-04:00')
        fat = pix_billing_service.generate_invoice(self.sub, now=self.agora)
        self.assertEqual(fat.expires_at, datetime(2026, 10, 12, 14, 0, tzinfo=dtz.utc))

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_pix_vencido_ganha_codigo_novo_na_mesma_fatura(self, criar):
        criar.return_value = _orders(payment_id='111', qr='VELHO', venc='2026-10-12T10:00:00.000-04:00')
        fat = pix_billing_service.generate_invoice(self.sub, now=self.agora)
        criar.return_value = _orders(payment_id='222', qr='NOVO', venc='2026-10-14T10:00:00.000-04:00')
        depois = self.agora + timedelta(days=2)
        nova = pix_billing_service.generate_invoice(self.sub, now=depois)
        self.assertEqual(nova.pk, fat.pk)
        self.assertEqual((nova.qr_code, nova.external_id), ('NOVO', '222'))
        self.assertEqual(StorePayment.objects.filter(store=self.loja).count(), 1)

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_pix_valido_nao_chama_o_mercado_pago_de_novo(self, criar):
        criar.return_value = _orders()
        pix_billing_service.generate_invoice(self.sub, now=self.agora)
        pix_billing_service.generate_invoice(self.sub, now=self.agora + timedelta(hours=2))
        self.assertEqual(criar.call_count, 1)


class AvisoDeFaturaTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user('dono_av', 'jonathan@icloud.com', 'x', first_name='Jonathan')
        self.loja = Store.objects.create(name='Nathaluecake', slug='nath-av', plan='starter', owner=self.dono)
        self.fatura = StorePayment.objects.create(
            store=self.loja, order=None, amount=79, currency='BRL',
            payment_method=StorePayment.PaymentMethod.PIX, status=StorePayment.PaymentStatus.PENDING,
            external_id='111', external_reference='subpix-x-2026-10', qr_code='PIXCOPIA',
            metadata={'kind': 'monthly', 'sent_steps': []},
        )
        self.venc = datetime(2026, 10, 14, 13, 38, tzinfo=dtz.utc)

    def _avisar(self, agora):
        with patch.object(aviso_de_fatura, '_enviar_email', return_value=True) as env:
            aviso_de_fatura.avisar(self.fatura, vencimento=self.venc, agora=agora)
        return env

    def test_tres_dias_antes_manda_o_pix_por_email(self):
        env = self._avisar(datetime(2026, 10, 11, 7, 0, tzinfo=dtz.utc))
        env.assert_called_once()
        para, assunto, corpo = env.call_args[0]
        self.assertEqual(para, 'jonathan@icloud.com')
        self.assertIn('PIXCOPIA', corpo)
        self.assertIn('79,00', corpo)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.metadata['sent_steps'], ['d3'])

    def test_mesmo_passo_nao_repete(self):
        self._avisar(datetime(2026, 10, 11, 7, 0, tzinfo=dtz.utc))
        env = self._avisar(datetime(2026, 10, 12, 1, 0, tzinfo=dtz.utc))
        env.assert_not_called()

    def test_vespera_e_dia_sao_passos_proprios(self):
        self._avisar(datetime(2026, 10, 11, 7, 0, tzinfo=dtz.utc))
        self._avisar(datetime(2026, 10, 13, 7, 0, tzinfo=dtz.utc))
        self._avisar(datetime(2026, 10, 14, 7, 0, tzinfo=dtz.utc))
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.metadata['sent_steps'], ['d3', 'd1', 'd0'])

    def test_sem_email_real_nao_envia(self):
        self.dono.email = '83993371684@cardapidex.local'
        self.dono.save()
        env = self._avisar(datetime(2026, 10, 11, 7, 0, tzinfo=dtz.utc))
        env.assert_not_called()

    def test_fatura_paga_nao_avisa(self):
        self.fatura.status = StorePayment.PaymentStatus.COMPLETED
        self.fatura.save()
        env = self._avisar(datetime(2026, 10, 11, 7, 0, tzinfo=dtz.utc))
        env.assert_not_called()
