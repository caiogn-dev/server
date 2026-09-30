"""Fiscal: a página de Notas — destinatário próprio, lista e emissão manual.

O que quebrou (30/set): pedido de RETIRADA para o Sindicato da PF. A NF-e lia o
destinatário de `order.delivery_address`, que num pedido de retirada só tinha
rua, cidade, UF e CEP — e não existia tela para completar número e bairro. A
saída em 19/set tinha sido um script no banco. O destinatário da nota não é o
endereço de entrega: é um cadastro, e o operador precisa poder preenchê-lo.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import DestinatarioFiscal, FiscalDocument
from apps.fiscal.providers.base import EmitResult
from apps.fiscal.services import build_nfe_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '11444777000161',
    'serie': '1',
    'habilitado': True,
    'uf': 'TO',
    'inscricao_estadual': '29.572.414-5',
}

CNPJ_CLIENTE = '11222333000181'

# O endereço como o pedido de retirada guardou: sem número e sem bairro.
ENDERECO_INCOMPLETO = {
    'street': 'Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins',
    'city': 'Palmas',
    'state': 'TO',
    'zip_code': '77020170',
}

DESTINATARIO = {
    'documento': '11.222.333/0001-81',
    'nome': 'Sindicato dos Servidores LTDA',
    'inscricao_estadual': '',
    'endereco': {
        'street': 'Quadra 103 Sul, Avenida LO 1',
        'number': 'SN',
        'complement': 'Conj 04 Lote 51 Sala 03',
        'neighborhood': 'Plano Diretor Sul',
        'city': 'Palmas',
        'state': 'to',
        'zip_code': '77015-028',
    },
}


def _loja(slug, owner):
    return Store.objects.create(
        name=f'Loja {slug}', slug=slug, owner=owner, status='active',
        metadata={'fiscal': dict(FISCAL_CFG)},
    )


def _pedido(store, **extra):
    category, _ = StoreCategory.objects.get_or_create(store=store, slug='geral', defaults={'name': 'Geral'})
    product, _ = StoreProduct.objects.get_or_create(
        store=store, sku='CB1',
        defaults={'name': 'Coffee break', 'price': 760, 'track_stock': False, 'category': category},
    )
    campos = dict(
        store=store, customer_name='Fulano que retirou',
        customer_phone='63999990000',
        subtotal=Decimal('760.00'), total=Decimal('760.00'),
        payment_method='pix', delivery_method='pickup',
        status='confirmed', payment_status='paid',
        delivery_address=dict(ENDERECO_INCOMPLETO),
        metadata={},
    )
    campos.update(extra)
    order = StoreOrder.objects.create(**campos)
    StoreOrderItem.objects.create(
        order=order, product=product, product_name='Coffee break',
        sku='CB1', unit_price=760, quantity=1, subtotal=760,
    )
    return order


class DestinatarioNoPayloadTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-dest', email='d@t.com', password='x')
        self.store = _loja('loja-dest', self.owner)
        self.order = _pedido(self.store)

    def test_destinatario_registrado_vence_o_endereco_do_pedido(self):
        self.order.metadata = {
            'cpf_nota': CNPJ_CLIENTE,
            'destinatario_nota': {
                'documento': CNPJ_CLIENTE,
                'nome': 'Sindicato dos Servidores LTDA',
                'inscricao_estadual': '',
                'endereco': {
                    'street': 'Quadra 103 Sul, Avenida LO 1', 'number': 'SN',
                    'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas',
                    'state': 'TO', 'zip_code': '77015028',
                },
            },
        }
        self.order.save(update_fields=['metadata'])

        payload = build_nfe_payload(self.order, get_fiscal_config(self.store))

        self.assertEqual(payload['nome_destinatario'], 'Sindicato dos Servidores LTDA')
        self.assertEqual(payload['logradouro_destinatario'], 'Quadra 103 Sul, Avenida LO 1')
        self.assertEqual(payload['numero_destinatario'], 'SN')
        self.assertEqual(payload['bairro_destinatario'], 'Plano Diretor Sul')
        self.assertEqual(payload['cep_destinatario'], '77015028')
        # O endereço de entrega do pedido fica como estava.
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_address, ENDERECO_INCOMPLETO)


class EmitirPelaPaginaTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-notas', email='n@t.com', password='x')
        self.store = _loja('loja-notas', self.owner)
        self.order = _pedido(self.store)
        self.client.force_authenticate(self.owner)
        self.base = f'/api/v1/stores/{self.store.slug}/fiscal'

    def _emitir(self, **extra):
        corpo = {'order_id': str(self.order.id), 'modelo': '55', 'destinatario': DESTINATARIO}
        corpo.update(extra)
        return self.client.post(f'{self.base}/notas/emitir/', corpo, format='json')

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_pedido_de_retirada_emite_nfe_com_destinatario_informado(self, mock_emit):
        mock_emit.return_value = EmitResult(
            status='authorized', chave_acesso='5' * 44, numero='3', serie='1',
        )
        resp = self._emitir()
        self.assertEqual(resp.status_code, 201, resp.content)

        payload = mock_emit.call_args.kwargs['payload']
        self.assertEqual(payload['cnpj_destinatario'], CNPJ_CLIENTE)
        self.assertEqual(payload['nome_destinatario'], 'Sindicato dos Servidores LTDA')
        self.assertEqual(payload['numero_destinatario'], 'SN')
        self.assertEqual(payload['bairro_destinatario'], 'Plano Diretor Sul')
        self.assertEqual(payload['uf_destinatario'], 'TO')
        self.assertEqual(payload['cep_destinatario'], '77015028')

        self.assertEqual(resp.data['destinatario']['nome'], 'Sindicato dos Servidores LTDA')
        self.assertEqual(resp.data['pedido']['id'], str(self.order.id))

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_destinatario_fica_salvo_para_a_proxima_nota(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44)
        self._emitir()

        salvo = DestinatarioFiscal.objects.get(store=self.store)
        self.assertEqual(salvo.documento, CNPJ_CLIENTE)
        self.assertEqual(salvo.neighborhood, 'Plano Diretor Sul')
        self.assertEqual(salvo.state, 'TO')

        resp = self.client.get(f'{self.base}/destinatarios/', {'q': 'sindicato'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['documento'], CNPJ_CLIENTE)

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_emitir_de_novo_para_o_mesmo_cnpj_atualiza_em_vez_de_duplicar(self, mock_emit):
        mock_emit.return_value = EmitResult(status='rejected', error_message='x')
        self._emitir()
        outro = {**DESTINATARIO, 'endereco': {**DESTINATARIO['endereco'], 'number': '51'}}
        self._emitir(destinatario=outro)
        self.assertEqual(DestinatarioFiscal.objects.filter(store=self.store).count(), 1)
        self.assertEqual(DestinatarioFiscal.objects.get(store=self.store).number, '51')

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_destinatario_salvo_emite_pelo_id(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44)
        criado = self.client.post(f'{self.base}/destinatarios/', DESTINATARIO, format='json')
        self.assertEqual(criado.status_code, 201, criado.content)

        resp = self.client.post(f'{self.base}/notas/emitir/', {
            'order_id': str(self.order.id), 'modelo': '55',
            'destinatario_id': criado.data['id'],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(mock_emit.call_args.kwargs['payload']['cnpj_destinatario'], CNPJ_CLIENTE)

    def test_nfe_sem_bairro_diz_o_que_falta_e_nao_grava_nada(self):
        incompleto = {**DESTINATARIO, 'endereco': {**DESTINATARIO['endereco'], 'neighborhood': ''}}
        resp = self._emitir(destinatario=incompleto)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('bairro', resp.data['error'])
        self.assertFalse(FiscalDocument.objects.exists())

    def test_documento_invalido_e_recusado(self):
        resp = self._emitir(destinatario={**DESTINATARIO, 'documento': '11222333000100'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(DestinatarioFiscal.objects.exists())

    def test_pedido_de_outra_loja_nao_emite(self):
        outro_dono = User.objects.create_user(username='outro', email='o@t.com', password='x')
        alheio = _pedido(_loja('loja-alheia', outro_dono))
        resp = self._emitir(order_id=str(alheio.id))
        self.assertEqual(resp.status_code, 404)

    @patch('apps.fiscal.services.FocusProvider.emit_nfce')
    def test_nfce_sai_sem_destinatario(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='6' * 44)
        resp = self.client.post(f'{self.base}/notas/emitir/', {
            'order_id': str(self.order.id), 'modelo': '65',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)


class ListaDeNotasTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-lista', email='l@t.com', password='x')
        self.store = _loja('loja-lista', self.owner)
        self.order = _pedido(self.store, metadata={
            'cpf_nota': CNPJ_CLIENTE,
            'destinatario_nota': {'documento': CNPJ_CLIENTE, 'nome': 'Sindicato LTDA', 'endereco': {}},
        })
        self.doc = FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='authorized', ambiente='homologacao', ref='nfe-lista-1',
            numero='2', serie='1', chave_acesso='1' * 44,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/fiscal/notas/'

    def test_lista_traz_pedido_destinatario_e_valor(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data['habilitado'])
        nota = resp.data['notas'][0]
        self.assertEqual(nota['numero'], '2')
        self.assertEqual(nota['pedido']['order_number'], self.order.order_number)
        self.assertEqual(Decimal(str(nota['pedido']['total'])), Decimal('760.00'))
        self.assertEqual(nota['destinatario']['nome'], 'Sindicato LTDA')
        self.assertEqual(nota['destinatario']['documento'], CNPJ_CLIENTE)

    def test_nota_de_outro_ambiente_nao_aparece(self):
        FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='65',
            status='authorized', ambiente='producao', ref='nfce-prod-1',
        )
        resp = self.client.get(self.url)
        self.assertEqual([n['id'] for n in resp.data['notas']], [str(self.doc.id)])

    def test_filtra_por_status(self):
        resp = self.client.get(self.url, {'status': 'rejected'})
        self.assertEqual(resp.data['notas'], [])

    def test_quem_nao_e_da_loja_nao_ve_as_notas(self):
        estranho = User.objects.create_user(username='estranho', email='e@t.com', password='x')
        self.client.force_authenticate(estranho)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.get(f'/api/v1/stores/{self.store.slug}/fiscal/destinatarios/').status_code, 403,
        )

    def test_pedidos_para_emitir_mostram_o_que_ja_tem_nota(self):
        sem_nota = _pedido(self.store, customer_name='Cliente Sem Nota')
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/fiscal/pedidos/')
        self.assertEqual(resp.status_code, 200, resp.content)
        por_id = {p['id']: p for p in resp.data}
        self.assertEqual(por_id[str(self.order.id)]['notas'], [{'modelo': '55', 'status': 'authorized'}])
        self.assertEqual(por_id[str(sem_nota.id)]['notas'], [])
        # O que o pedido já sabe vira sugestão no formulário.
        self.assertEqual(por_id[str(sem_nota.id)]['sugestao']['endereco']['zip_code'], '77020170')

    def test_pedido_escolhido_pelo_id_vem_sozinho(self):
        _pedido(self.store, customer_name='Outro')
        resp = self.client.get(
            f'/api/v1/stores/{self.store.slug}/fiscal/pedidos/', {'id': str(self.order.id)},
        )
        self.assertEqual([p['id'] for p in resp.data], [str(self.order.id)])

    @patch('apps.fiscal.views.consultar_cnpj')
    def test_consulta_de_cnpj_preenche_o_formulario(self, mock_consulta):
        mock_consulta.return_value = {
            'documento': CNPJ_CLIENTE, 'nome': 'SINDICATO LTDA',
            'endereco': {'street': 'Quadra 103 Sul', 'number': 'SN', 'neighborhood': 'Plano Diretor Sul',
                         'city': 'Palmas', 'state': 'TO', 'zip_code': '77015028', 'complement': ''},
        }
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/fiscal/cnpj/{CNPJ_CLIENTE}/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['endereco']['neighborhood'], 'Plano Diretor Sul')

    def test_consulta_de_cnpj_invalido_nem_sai_para_a_rede(self):
        with patch('apps.fiscal.views.consultar_cnpj') as mock_consulta:
            resp = self.client.get(f'/api/v1/stores/{self.store.slug}/fiscal/cnpj/11222333000100/')
        self.assertEqual(resp.status_code, 400)
        mock_consulta.assert_not_called()
