"""Adicional "Etiqueta ANVISA": catálogo, gate, cobrança e contratação.

R$ 390 de implantação + R$ 79/mês. O módulo de nutrição já existia inteiro e
saía de graça para qualquer loja — este arquivo é o que o transforma em
fatura. Valores literais de propósito: são o preço de venda, e mudar preço
tem que quebrar teste.
"""
from datetime import datetime, timezone as dtz
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.stores import billing
from apps.stores.models import Store, StorePayment, StoreSubscription
from apps.stores.services import pix_billing_service
from apps.stores.tests.test_pix_billing import _orders_fatura

ETIQUETA = 'etiqueta_anvisa'


class CatalogoDoAdicionalTest(TestCase):
    def test_preco_de_venda(self):
        adicional = billing.ADICIONAIS[ETIQUETA]
        self.assertEqual(adicional['implantacao'], Decimal('390.00'))
        self.assertEqual(adicional['mensal'], Decimal('79.00'))
        self.assertTrue(adicional['nome'])
        self.assertTrue(adicional['descricao'])

    def test_vitrine_publica_traz_o_adicional(self):
        cache.clear()
        r = APIClient().get('/api/v1/public/plans/')
        self.assertEqual(r.status_code, 200)
        etiqueta = next(a for a in r.json()['adicionais'] if a['key'] == ETIQUETA)
        self.assertEqual(etiqueta['implantacao'], 390.0)
        self.assertEqual(etiqueta['mensal'], 79.0)
        self.assertEqual(etiqueta['anual'], 790.0)
        self.assertTrue(etiqueta['inclui'])


class ValorDosAdicionaisTest(TestCase):
    """Conta pura: o que os adicionais somam numa fatura."""

    def test_mensal_primeira_fatura_cobra_implantacao(self):
        conta = billing.valor_dos_adicionais({ETIQUETA: {}}, 'monthly')
        self.assertEqual(conta['total'], Decimal('469.00'))  # 390 + 79
        self.assertEqual(conta['chaves'], [ETIQUETA])

    def test_mensal_depois_da_implantacao_quitada(self):
        conta = billing.valor_dos_adicionais({ETIQUETA: {'implantacao_quitada': True}}, 'monthly')
        self.assertEqual(conta['total'], Decimal('79.00'))

    def test_anual_isenta_implantacao_e_cobra_dez_meses(self):
        conta = billing.valor_dos_adicionais({ETIQUETA: {}}, 'annual')
        self.assertEqual(conta['total'], Decimal('790.00'))

    def test_sem_adicional_soma_zero(self):
        self.assertEqual(billing.valor_dos_adicionais({}, 'monthly')['total'], Decimal('0'))

    def test_chave_desconhecida_nao_vira_cobranca(self):
        conta = billing.valor_dos_adicionais({'inventado': {}}, 'monthly')
        self.assertEqual(conta['total'], Decimal('0'))
        self.assertEqual(conta['chaves'], [])


class LojaTemAdicionalTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user('dono_adic', 'dono_adic@x.com', 'x')
        self.loja = Store.objects.create(name='Loja', slug='loja-adic', owner=self.dono)

    def test_sem_assinatura_nao_tem(self):
        self.assertFalse(billing.loja_tem_adicional(self.loja, ETIQUETA))

    def test_assinatura_sem_adicional_nao_tem(self):
        StoreSubscription.objects.create(store=self.loja, plan='pro')
        self.loja.refresh_from_db()
        self.assertFalse(billing.loja_tem_adicional(self.loja, ETIQUETA))

    def test_contratado_tem(self):
        StoreSubscription.objects.create(store=self.loja, plan='pro', adicionais={ETIQUETA: {}})
        self.loja.refresh_from_db()
        self.assertTrue(billing.loja_tem_adicional(self.loja, ETIQUETA))

    def test_grandfather_tem_sem_contratar(self):
        self.loja.billing_exempt = True
        self.loja.save()
        self.assertTrue(billing.loja_tem_adicional(self.loja, ETIQUETA))
        self.assertEqual(billing.adicionais_da_loja(self.loja), [ETIQUETA])

    def test_filtro_de_banco_bate_com_o_helper(self):
        contratada = Store.objects.create(name='C', slug='c-adic', owner=self.dono)
        StoreSubscription.objects.create(store=contratada, plan='pro', adicionais={ETIQUETA: {}})
        isenta = Store.objects.create(name='I', slug='i-adic', owner=self.dono, billing_exempt=True)
        ids = set(Store.objects.filter(billing.q_lojas_com_adicional(ETIQUETA)).values_list('id', flat=True))
        self.assertEqual(ids, {contratada.id, isenta.id})


class FaturaComAdicionalTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user('dono_fat', 'dono_fat@x.com', 'x')
        self.loja = Store.objects.create(name='Loja F', slug='loja-fat', plan='pro', owner=self.dono)
        self.sub = StoreSubscription.objects.create(
            store=self.loja, plan='pro', adicionais={ETIQUETA: {}},
        )
        self.agora = datetime(2026, 10, 4, tzinfo=dtz.utc)

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_primeira_fatura_mensal_soma_plano_implantacao_e_mensal(self, criar):
        criar.return_value = _orders_fatura()
        fatura = pix_billing_service.generate_invoice(self.sub, now=self.agora)
        self.assertEqual(fatura.amount, Decimal('718.00'))  # 249 + 390 + 79
        self.assertEqual(criar.call_args[0][1]['total_amount'], '718.00')
        self.assertEqual(fatura.metadata['adicionais'], [ETIQUETA])

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_fatura_seguinte_so_a_mensalidade(self, criar):
        criar.return_value = _orders_fatura()
        self.sub.adicionais = {ETIQUETA: {'implantacao_quitada': True}}
        self.sub.save()
        fatura = pix_billing_service.generate_invoice(self.sub, now=self.agora)
        self.assertEqual(fatura.amount, Decimal('328.00'))  # 249 + 79

    @patch.object(pix_billing_service.mp_orders, 'create_order')
    def test_anual_dez_meses_sem_implantacao(self, criar):
        criar.return_value = _orders_fatura()
        self.sub.billing_cycle = 'annual'
        self.sub.save()
        fatura = pix_billing_service.generate_invoice(self.sub, now=self.agora)
        self.assertEqual(fatura.amount, Decimal('3280.00'))  # 2490 + 790

    def test_pagar_a_fatura_quita_a_implantacao(self):
        fatura = StorePayment.objects.create(
            store=self.loja, order=None, amount=Decimal('718.00'), currency='BRL',
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_reference=f'subpix:{self.sub.id}:2026-10',
            metadata={'kind': 'monthly', 'subscription_id': str(self.sub.id),
                      'adicionais': [ETIQUETA]},
        )
        pix_billing_service.apply_invoice_paid(fatura)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.adicionais[ETIQUETA]['implantacao_quitada'])
        conta = billing.valor_dos_adicionais(self.sub.adicionais, 'monthly')
        self.assertEqual(conta['total'], Decimal('79.00'))


class ContratarAdicionalAPITest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user('dono_api', 'dono_api@x.com', 'x')
        self.loja = Store.objects.create(name='Loja A', slug='loja-api', owner=self.dono)
        self.sub = StoreSubscription.objects.create(store=self.loja, plan='pro', status='active')
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.dono)
        self.url = f'/api/v1/stores/{self.loja.slug}/subscription/adicionais/'

    def test_contratar_grava_e_aparece_na_assinatura(self):
        r = self.cliente.post(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['adicionais'], [ETIQUETA])
        self.sub.refresh_from_db()
        self.assertIn(ETIQUETA, self.sub.adicionais)
        self.assertFalse(self.sub.adicionais[ETIQUETA]['implantacao_quitada'])
        detalhe = self.cliente.get(f'/api/v1/stores/{self.loja.slug}/subscription/')
        self.assertEqual(detalhe.json()['adicionais'], [ETIQUETA])
        self.assertEqual(detalhe.json()['adicionais_inclusos'], [])

    def test_contratar_duas_vezes_nao_zera_a_implantacao_quitada(self):
        self.sub.adicionais = {ETIQUETA: {'implantacao_quitada': True}}
        self.sub.save()
        r = self.cliente.post(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 200)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.adicionais[ETIQUETA]['implantacao_quitada'])

    def test_cancelar_remove(self):
        self.sub.adicionais = {ETIQUETA: {'implantacao_quitada': True}}
        self.sub.save()
        r = self.cliente.delete(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['adicionais'], [])
        self.sub.refresh_from_db()
        self.assertNotIn(ETIQUETA, self.sub.adicionais)

    def test_adicional_desconhecido_400(self):
        r = self.cliente.post(self.url, {'adicional': 'inventado'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_sem_assinatura_ativa_pede_plano(self):
        self.sub.status = 'canceled'
        self.sub.save()
        r = self.cliente.post(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('plano', r.json()['detail'].lower())

    def test_grandfather_ja_tem_incluso(self):
        self.loja.billing_exempt = True
        self.loja.save()
        r = self.cliente.post(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 400)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.adicionais, {})

    def test_detalhe_da_grandfather_mostra_o_adicional_mesmo_sem_assinatura(self):
        self.sub.delete()
        self.loja.billing_exempt = True
        self.loja.save()
        r = self.cliente.get(f'/api/v1/stores/{self.loja.slug}/subscription/')
        self.assertEqual(r.json()['status'], 'none')
        self.assertEqual(r.json()['adicionais'], [ETIQUETA])
        self.assertEqual(r.json()['adicionais_inclusos'], [ETIQUETA])

    def test_quem_nao_e_da_loja_recebe_403(self):
        outro = User.objects.create_user('intruso_adic', 'intruso_adic@x.com', 'x')
        c = APIClient()
        c.force_authenticate(outro)
        r = c.post(self.url, {'adicional': ETIQUETA}, format='json')
        self.assertEqual(r.status_code, 403)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.adicionais, {})
