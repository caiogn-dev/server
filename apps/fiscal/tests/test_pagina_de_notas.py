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


class EnviarNotaPorEmailTests(APITestCase):
    """A nota autorizada vai para o e-mail do destinatário, com a marca da
    loja, DANFE e XML anexos — sem o dono baixar o PDF e abrir o Gmail."""

    def setUp(self):
        self.owner = User.objects.create_user(username='dono-email', email='dono@t.com', password='x')
        self.store = _loja('loja-email', self.owner)
        self.order = _pedido(self.store, metadata={
            'cpf_nota': CNPJ_CLIENTE,
            'destinatario_nota': {'documento': CNPJ_CLIENTE, 'nome': 'Sindicato LTDA', 'endereco': {}},
        })
        self.doc = FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='authorized', ambiente='homologacao', ref='nfe-email-1',
            numero='3', serie='1', chave_acesso='1' * 44,
            danfe_url='https://api.focusnfe.com.br/arquivos/danfe.pdf',
            xml_url='https://api.focusnfe.com.br/arquivos/nota.xml',
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/fiscal/notas/{self.doc.id}/enviar-email/'

    def _baixa(self, conteudo=b'%PDF-1.4 conteudo', status=200):
        resposta = type('R', (), {'status_code': status, 'content': conteudo})()
        return patch('apps.fiscal.envio.requests.get', return_value=resposta)

    def _envio(self, sucesso=True):
        return patch(
            'apps.fiscal.envio.EmailMarketingService.send_single_email',
            return_value={'success': sucesso, 'id': 'e1'} if sucesso else {'success': False, 'error': 'x'},
        )

    def test_envia_com_danfe_e_xml_anexos(self):
        with self._baixa(), self._envio() as envio:
            resp = self.client.post(self.url, {'email': 'Financeiro@Sindicato.org '}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        chamada = envio.call_args.kwargs
        self.assertEqual(chamada['to_email'], 'financeiro@sindicato.org')
        self.assertIn('NF-e', chamada['subject'])
        self.assertIn(self.store.name, chamada['from_name'])
        self.assertEqual(
            sorted(a['filename'] for a in chamada['attachments']),
            ['NF-e-3.pdf', 'NF-e-3.xml'],
        )
        self.assertIn('1' * 44, chamada['html_content'])

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.email_enviado_para, 'financeiro@sindicato.org')
        self.assertIsNotNone(self.doc.email_enviado_em)
        self.assertEqual(resp.data['email_enviado_para'], 'financeiro@sindicato.org')

    def test_email_informado_fica_no_cadastro_do_destinatario(self):
        DestinatarioFiscal.objects.create(store=self.store, documento=CNPJ_CLIENTE, nome='Sindicato LTDA')
        with self._baixa(), self._envio():
            self.client.post(self.url, {'email': 'financeiro@sindicato.org'}, format='json')
        self.assertEqual(
            DestinatarioFiscal.objects.get(store=self.store).email, 'financeiro@sindicato.org',
        )

    def test_sem_email_no_corpo_usa_o_do_cadastro(self):
        DestinatarioFiscal.objects.create(
            store=self.store, documento=CNPJ_CLIENTE, nome='Sindicato LTDA', email='salvo@sindicato.org',
        )
        with self._baixa(), self._envio() as envio:
            resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(envio.call_args.kwargs['to_email'], 'salvo@sindicato.org')

    def test_sem_email_em_lugar_nenhum_pede_o_endereco(self):
        with self._baixa(), self._envio() as envio:
            resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        envio.assert_not_called()

    def test_email_invalido_e_recusado(self):
        with self._baixa(), self._envio() as envio:
            resp = self.client.post(self.url, {'email': 'sem-arroba'}, format='json')
        self.assertEqual(resp.status_code, 400)
        envio.assert_not_called()

    def test_nota_que_nao_foi_autorizada_nao_vai_por_email(self):
        self.doc.status = 'rejected'
        self.doc.save(update_fields=['status'])
        with self._baixa(), self._envio() as envio:
            resp = self.client.post(self.url, {'email': 'a@b.org'}, format='json')
        self.assertEqual(resp.status_code, 400)
        envio.assert_not_called()

    def test_arquivo_que_nao_baixa_nao_impede_o_envio(self):
        """O e-mail leva os links; sem o anexo ainda é melhor do que não avisar."""
        with self._baixa(status=500), self._envio() as envio:
            resp = self.client.post(self.url, {'email': 'a@b.org'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(envio.call_args.kwargs['attachments'], [])
        self.assertIn('https://api.focusnfe.com.br/arquivos/danfe.pdf', envio.call_args.kwargs['html_content'])

    def test_falha_do_provedor_de_email_vira_erro_e_nao_marca_enviado(self):
        with self._baixa(), self._envio(sucesso=False):
            resp = self.client.post(self.url, {'email': 'a@b.org'}, format='json')
        self.assertEqual(resp.status_code, 502)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.email_enviado_para, '')

    def test_nota_de_outra_loja_nao_envia(self):
        outro = User.objects.create_user(username='outro-email', email='o2@t.com', password='x')
        self.client.force_authenticate(outro)
        _loja('loja-do-outro', outro)
        resp = self.client.post(
            f'/api/v1/stores/loja-do-outro/fiscal/notas/{self.doc.id}/enviar-email/',
            {'email': 'a@b.org'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)


class EmitirEEnviarTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-ee', email='ee@t.com', password='x')
        self.store = _loja('loja-ee', self.owner)
        self.order = _pedido(self.store)
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/fiscal/notas/emitir/'
        self.corpo = {
            'order_id': str(self.order.id), 'modelo': '55', 'enviar_email': True,
            'destinatario': {**DESTINATARIO, 'email': 'financeiro@sindicato.org'},
        }

    @patch('apps.fiscal.envio.EmailMarketingService.send_single_email', return_value={'success': True})
    @patch('apps.fiscal.envio.requests.get')
    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_autorizada_ja_sai_por_email(self, mock_emit, mock_get, mock_envio):
        mock_emit.return_value = EmitResult(
            status='authorized', chave_acesso='5' * 44, numero='4', serie='1',
            danfe_url='https://api.focusnfe.com.br/d.pdf', xml_url='https://api.focusnfe.com.br/n.xml',
        )
        mock_get.return_value = type('R', (), {'status_code': 200, 'content': b'x'})()
        resp = self.client.post(self.url, self.corpo, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(mock_envio.call_args.kwargs['to_email'], 'financeiro@sindicato.org')
        self.assertEqual(resp.data['email_enviado_para'], 'financeiro@sindicato.org')

    @patch('apps.fiscal.envio.EmailMarketingService.send_single_email')
    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_rejeitada_nao_manda_email(self, mock_emit, mock_envio):
        mock_emit.return_value = EmitResult(status='rejected', error_message='x')
        self.client.post(self.url, self.corpo, format='json')
        mock_envio.assert_not_called()

    @patch('apps.fiscal.envio.EmailMarketingService.send_single_email', return_value={'success': False})
    @patch('apps.fiscal.envio.requests.get')
    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_email_que_falha_nao_desfaz_a_nota(self, mock_emit, mock_get, mock_envio):
        """A nota já existe na SEFAZ: o erro do e-mail vai junto na resposta,
        e o operador reenvia pela lista."""
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='4')
        mock_get.return_value = type('R', (), {'status_code': 200, 'content': b'x'})()
        resp = self.client.post(self.url, self.corpo, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['status'], 'authorized')
        self.assertTrue(resp.data['email_erro'])


class EnvioQuandoASefazDemoraTests(APITestCase):
    """30/set, nota real do Sindicato: a NF-e voltou "processando" e o e-mail
    pedido na emissão nunca saiu — só sai nota autorizada. O pedido de envio
    fica guardado e dispara quando a consulta traz a autorização."""

    def setUp(self):
        self.owner = User.objects.create_user(username='dono-fila', email='fila@t.com', password='x')
        self.store = _loja('loja-fila', self.owner)
        self.order = _pedido(self.store)
        self.client.force_authenticate(self.owner)
        self.base = f'/api/v1/stores/{self.store.slug}/fiscal'

    @patch('apps.fiscal.envio.requests.get')
    @patch('apps.fiscal.envio.EmailMarketingService.send_single_email', return_value={'success': True})
    @patch('apps.fiscal.services.FocusProvider.consult')
    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_email_sai_quando_a_nota_processando_e_autorizada(self, mock_emit, mock_consult, mock_envio, mock_get):
        mock_get.return_value = type('R', (), {'status_code': 200, 'content': b'x'})()
        mock_emit.return_value = EmitResult(status='pending')
        resp = self.client.post(f'{self.base}/notas/emitir/', {
            'order_id': str(self.order.id), 'modelo': '55', 'enviar_email': True,
            'destinatario': {**DESTINATARIO, 'email': 'financeiro@sindicato.org'},
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        mock_envio.assert_not_called()
        self.assertIsNone(resp.data['email_enviado_em'])

        mock_consult.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='3', serie='1')
        lista = self.client.get(f'{self.base}/notas/')
        self.assertEqual(mock_envio.call_count, 1)
        self.assertEqual(mock_envio.call_args.kwargs['to_email'], 'financeiro@sindicato.org')
        self.assertIsNotNone(lista.data['notas'][0]['email_enviado_em'])

        self.client.get(f'{self.base}/notas/')
        self.assertEqual(mock_envio.call_count, 1)

    @patch('apps.fiscal.envio.EmailMarketingService.send_single_email')
    @patch('apps.fiscal.services.FocusProvider.consult')
    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_processando_que_vira_rejeitada_nao_manda(self, mock_emit, mock_consult, mock_envio):
        mock_emit.return_value = EmitResult(status='pending')
        self.client.post(f'{self.base}/notas/emitir/', {
            'order_id': str(self.order.id), 'modelo': '55', 'enviar_email': True,
            'destinatario': {**DESTINATARIO, 'email': 'financeiro@sindicato.org'},
        }, format='json')
        mock_consult.return_value = EmitResult(status='rejected', error_message='x')
        self.client.get(f'{self.base}/notas/')
        mock_envio.assert_not_called()
