"""Nota fragmentada (28/10): "não puxa o endereço, não puxa os dados, e
destinatário salvo aparece apenas clientes que já gerei nota".

O cadastro do cliente (PF/PJ com documento e endereço) é a fonte: a sugestão
do pedido e a lista de destinatários salvos partem dele, não só do histórico
de notas.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import DestinatarioFiscal
from apps.stores.models import StoreCustomer, StoreCustomerAddress

from .test_pagina_de_notas import CNPJ_CLIENTE, _loja, _pedido

User = get_user_model()

ENDERECO_DO_CADASTRO = {
    'street': 'Quadra ARSE 22 Alameda 2', 'number': '05', 'complement': 'Loja 29',
    'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77020514',
}


class NotaPuxaOCadastroTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-frag', email='f@t.com', password='x')
        self.store = _loja('loja-frag', self.owner)
        self.cliente_user = User.objects.create_user(username='cliente_5561984319122', password='x')
        self.cliente = StoreCustomer.objects.create(
            store=self.store, user=self.cliente_user, phone='5561984319122',
            tipo_pessoa='pj', documento=CNPJ_CLIENTE,
            razao_social='HOA COMERCIO DE MOVEIS LTDA', inscricao_estadual='291234567',
            email='compras@hoa.com.br',
        )
        StoreCustomerAddress.objects.create(customer=self.cliente, is_default=True, **ENDERECO_DO_CADASTRO)
        self.client.force_authenticate(self.owner)
        self.base = f'/api/v1/stores/{self.store.slug}/fiscal'

    def _sugestao(self, order):
        resp = self.client.get(f'{self.base}/pedidos/', {'id': str(order.id)})
        return resp.data[0]['sugestao']

    def test_retirada_puxa_o_endereco_do_cadastro(self):
        order = _pedido(self.store, customer=self.cliente_user, customer_phone='5561984319122',
                        delivery_address={})
        sug = self._sugestao(order)
        self.assertEqual(sug['documento'], CNPJ_CLIENTE)
        self.assertEqual(sug['endereco'], ENDERECO_DO_CADASTRO)

    def test_acha_o_cliente_pelo_telefone_sem_ddi(self):
        order = _pedido(self.store, customer=None, customer_phone='61984319122', delivery_address={})
        sug = self._sugestao(order)
        self.assertEqual(sug['nome'], 'HOA COMERCIO DE MOVEIS LTDA')
        self.assertEqual(sug['endereco']['city'], 'Palmas')

    def test_destinatario_salvo_sem_endereco_completa_pelo_cadastro(self):
        DestinatarioFiscal.objects.create(store=self.store, documento=CNPJ_CLIENTE, nome='HOA COMERCIO DE MOVEIS LTDA')
        order = _pedido(self.store, customer=self.cliente_user, customer_phone='5561984319122',
                        delivery_address={})
        sug = self._sugestao(order)
        self.assertEqual(sug['endereco'], ENDERECO_DO_CADASTRO)

    def test_lista_de_salvos_inclui_cliente_com_documento_sem_nota(self):
        resp = self.client.get(f'{self.base}/destinatarios/')
        self.assertEqual(resp.status_code, 200)
        [cliente] = [d for d in resp.data if d['documento'] == CNPJ_CLIENTE]
        self.assertEqual(cliente['nome'], 'HOA COMERCIO DE MOVEIS LTDA')
        self.assertEqual(cliente['inscricao_estadual'], '291234567')
        self.assertEqual(cliente['endereco'], ENDERECO_DO_CADASTRO)

    def test_lista_nao_repete_quem_ja_tem_nota_e_busca_pela_razao_social(self):
        DestinatarioFiscal.objects.create(store=self.store, documento=CNPJ_CLIENTE, nome='HOA COMERCIO DE MOVEIS LTDA')
        resp = self.client.get(f'{self.base}/destinatarios/')
        self.assertEqual([d['documento'] for d in resp.data].count(CNPJ_CLIENTE), 1)
        # O salvo sem endereço ganha o do cadastro.
        self.assertEqual(resp.data[0]['endereco'], ENDERECO_DO_CADASTRO)
        resp = self.client.get(f'{self.base}/destinatarios/', {'q': 'hoa comercio'})
        self.assertEqual(len(resp.data), 1)

    def test_cliente_sem_documento_nao_entra_na_lista(self):
        outro = User.objects.create_user(username='cliente_5563999990001', password='x')
        StoreCustomer.objects.create(store=self.store, user=outro, phone='5563999990001')
        resp = self.client.get(f'{self.base}/destinatarios/')
        self.assertEqual(len(resp.data), 1)


class ConsultaForaDoArTests(APITestCase):
    """502 da origem a Cloudflare troca pela página dela, sem CORS: o painel
    via "Sem conexão com o servidor" em vez da mensagem (28/10)."""

    def test_consulta_fora_do_ar_responde_503_com_mensagem(self):
        from unittest.mock import patch
        from apps.fiscal.consulta_cnpj import ConsultaIndisponivel
        owner = User.objects.create_user(username='dono-503', email='x@t.com', password='x')
        store = _loja('loja-503', owner)
        self.client.force_authenticate(owner)
        with patch('apps.fiscal.views.consultar_cnpj', side_effect=ConsultaIndisponivel()):
            resp = self.client.get(f'/api/v1/stores/{store.slug}/fiscal/cnpj/{CNPJ_CLIENTE}/')
        self.assertEqual(resp.status_code, 503)
        self.assertIn('à mão', resp.data['error'])


def test_isento_sobrevive_a_limpeza_do_destinatario():
    from apps.fiscal import destinatarios
    from apps.fiscal.models import FiscalDocument
    limpo = destinatarios.normalizar(
        {'documento': CNPJ_CLIENTE, 'nome': 'HOA', 'inscricao_estadual': 'isento', 'endereco': ENDERECO_DO_CADASTRO},
        FiscalDocument.Modelo.NFE,
    )
    assert limpo['inscricao_estadual'] == 'ISENTO'
    limpo = destinatarios.normalizar(
        {'documento': CNPJ_CLIENTE, 'nome': 'HOA', 'inscricao_estadual': '29.123.456-7', 'endereco': ENDERECO_DO_CADASTRO},
        FiscalDocument.Modelo.NFE,
    )
    assert limpo['inscricao_estadual'] == '291234567'
