"""Cliente único + PF/PJ (27/10).

HOA COMERCIO DE MOVEIS LTDA foi criado na Ivoneth pela tela Clientes e não
aparecia no novo pedido: a criação gravava StoreCustomer sem UnifiedUser, e a
busca do novo pedido só lê UnifiedUser. O nome de empresa virava
first_name='HOA' / last_name='COMERCIO DE MOVEIS LTDA', e não havia onde guardar
CNPJ, razão social nem IE — o CNPJ era redigitado a cada nota.

E "criar" com telefone já cadastrado renomeava a pessoa, apagava os endereços
dela e dizia "Cliente criado".
"""
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreCustomer, StoreCustomerAddress

User = get_user_model()

CNPJ_VALIDO = '11222333000181'
CPF_VALIDO = '52998224725'


class ClienteBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-pfpj', email='d@x.com', password='x')
        self.store = Store.objects.create(name='Ivoneth', slug='ivoneth-pfpj', owner=self.owner)
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.url = f'/api/v1/stores/stores/{self.store.slug}/customers/'
        self.busca = f'/api/v1/stores/{self.store.slug}/crm/customers/search/'

    def criar(self, **dados):
        return self.client.post(self.url, dados, format='json')


class TestClienteNasceNaBuscaDoPedido(ClienteBase):
    def test_cliente_criado_aparece_na_busca_do_novo_pedido(self):
        r = self.criar(name='HOA COMERCIO DE MOVEIS LTDA', phone='61984319122')
        self.assertEqual(r.status_code, 201, r.content)

        achados = self.client.get(self.busca, {'q': 'HOA'}).json()

        self.assertEqual(len(achados), 1, achados)
        self.assertEqual(achados[0]['name'], 'HOA COMERCIO DE MOVEIS LTDA')

    def test_endereco_do_cadastro_aparece_no_novo_pedido(self):
        self.criar(
            name='Maria', phone='63999990001',
            address_list=[{'label': 'Casa', 'street': 'Quadra 110 Sul', 'number': '5', 'city': 'Palmas'}],
        )

        achado = self.client.get(self.busca, {'q': 'Maria'}).json()[0]

        self.assertEqual([a['street'] for a in achado['addresses']], ['Quadra 110 Sul'])


class TestPessoaJuridica(ClienteBase):
    def test_pj_guarda_cnpj_razao_social_e_ie(self):
        r = self.criar(
            tipo_pessoa='pj', documento='11.222.333/0001-81',
            razao_social='HOA COMERCIO DE MOVEIS LTDA', nome_fantasia='HOA Móveis',
            inscricao_estadual='29.123.456-7', email='compras@hoa.com.br',
            phone='61984319122',
        )
        self.assertEqual(r.status_code, 201, r.content)
        c = StoreCustomer.objects.get(id=r.data['id'])
        self.assertEqual(c.tipo_pessoa, 'pj')
        self.assertEqual(c.documento, CNPJ_VALIDO)
        self.assertEqual(c.razao_social, 'HOA COMERCIO DE MOVEIS LTDA')
        self.assertEqual(c.inscricao_estadual, '29.123.456-7')
        self.assertEqual(r.data['email'], 'compras@hoa.com.br')

    def test_nome_da_empresa_nao_e_partido_em_nome_e_sobrenome(self):
        r = self.criar(
            tipo_pessoa='pj', documento=CNPJ_VALIDO,
            razao_social='HOA COMERCIO DE MOVEIS LTDA', phone='61984319122',
        )
        self.assertEqual(r.data['user_name'], 'HOA COMERCIO DE MOVEIS LTDA')

    def test_nome_fantasia_e_o_nome_de_exibicao(self):
        r = self.criar(
            tipo_pessoa='pj', documento=CNPJ_VALIDO,
            razao_social='HOA COMERCIO DE MOVEIS LTDA', nome_fantasia='HOA Móveis',
            phone='61984319122',
        )
        self.assertEqual(r.data['user_name'], 'HOA Móveis')

    def test_cnpj_invalido_e_recusado(self):
        r = self.criar(tipo_pessoa='pj', documento='11222333000100', razao_social='X LTDA', phone='61984319122')
        self.assertEqual(r.status_code, 400)
        self.assertIn('documento', r.data['error']['details'])

    def test_pj_sem_razao_social_e_recusado(self):
        r = self.criar(tipo_pessoa='pj', documento=CNPJ_VALIDO, phone='61984319122')
        self.assertEqual(r.status_code, 400)
        self.assertIn('razao_social', r.data['error']['details'])

    def test_busca_do_pedido_acha_pelo_cnpj_e_devolve_os_dados_fiscais(self):
        self.criar(
            tipo_pessoa='pj', documento=CNPJ_VALIDO,
            razao_social='HOA COMERCIO DE MOVEIS LTDA', phone='61984319122',
        )
        achado = self.client.get(self.busca, {'q': '11.222.333'}).json()[0]
        self.assertEqual(achado['cadastro']['tipo_pessoa'], 'pj')
        self.assertEqual(achado['cadastro']['documento'], CNPJ_VALIDO)


class TestPessoaFisica(ClienteBase):
    def test_pf_e_o_padrao_e_guarda_cpf_limpo(self):
        r = self.criar(name='Ana Lima', documento='529.982.247-25', phone='63999990002')
        self.assertEqual(r.status_code, 201, r.content)
        c = StoreCustomer.objects.get(id=r.data['id'])
        self.assertEqual(c.tipo_pessoa, 'pf')
        self.assertEqual(c.documento, CPF_VALIDO)

    def test_cpf_invalido_e_recusado(self):
        r = self.criar(name='Ana', documento='111.111.111-11', phone='63999990003')
        self.assertEqual(r.status_code, 400)

    def test_cnpj_em_pf_e_recusado(self):
        r = self.criar(name='Ana', documento=CNPJ_VALIDO, phone='63999990004')
        self.assertEqual(r.status_code, 400)


class TestTelefoneJaCadastrado(ClienteBase):
    def test_nao_sobrescreve_e_aponta_o_cadastro_existente(self):
        r1 = self.criar(
            name='Joana Original', phone='63999990005', notes='cliente antiga',
            address_list=[{'label': 'Casa', 'street': 'Rua A', 'number': '1'}],
        )
        r2 = self.criar(name='Outra Pessoa', phone='(63) 99999-0005', address_list=[])

        self.assertEqual(r2.status_code, 409, r2.content)
        self.assertEqual(r2.data['error']['code'], 'cliente_existente')
        self.assertEqual(r2.data['error']['details']['cliente_id'], str(r1.data['id']))
        c = StoreCustomer.objects.get(id=r1.data['id'])
        self.assertEqual(c.user.first_name, 'Joana')
        self.assertEqual(c.notes, 'cliente antiga')
        self.assertEqual(StoreCustomerAddress.objects.filter(customer=c).count(), 1)


class TestBuscaDaListaPorNome(ClienteBase):
    def test_lista_de_clientes_acha_por_nome_e_documento(self):
        self.criar(name='HOA COMERCIO DE MOVEIS LTDA', phone='61984319122')
        self.criar(name='Ana Lima', documento=CPF_VALIDO, phone='63999990006')

        por_nome = self.client.get(self.url, {'search': 'hoa'}).json()
        por_doc = self.client.get(self.url, {'search': '529.982'}).json()

        nomes = lambda r: [c['user_name'] for c in (r.get('results') if isinstance(r, dict) else r)]
        self.assertEqual(nomes(por_nome), ['HOA COMERCIO DE MOVEIS LTDA'])
        self.assertEqual(nomes(por_doc), ['Ana Lima'])


class TestEdicao(ClienteBase):
    def test_editar_cliente_antigo_sem_identidade_liga_a_busca(self):
        r = self.criar(name='Flaviane Paes', phone='11976457452')
        c = StoreCustomer.objects.get(id=r.data['id'])
        c.unified_user = None
        c.save(update_fields=['unified_user'])

        self.client.patch(f'{self.url}{c.id}/', {'notes': 'x'}, format='json')

        c.refresh_from_db()
        self.assertIsNotNone(c.unified_user_id)

    def test_pf_vira_pj(self):
        r = self.criar(name='Fulano', phone='63999990007')
        r2 = self.client.patch(f'{self.url}{r.data["id"]}/', {
            'tipo_pessoa': 'pj', 'documento': CNPJ_VALIDO, 'razao_social': 'FULANO ME',
        }, format='json')
        self.assertEqual(r2.status_code, 200, r2.content)
        self.assertEqual(r2.data['user_name'], 'FULANO ME')


class TestTodoClienteTemIdentidade(ClienteBase):
    """28/10: HOA foi criado minutos antes do deploy do fix e ficou órfão de
    novo — a garantia morava no serializer da tela Clientes, e qualquer outro
    caminho (PDV, checkout, bot, código antigo) seguia criando cliente que a
    busca do novo pedido não enxerga. Agora mora no modelo."""

    def _cliente_cru(self, telefone, nome='HOA', sobrenome='COMERCIO DE MOVEIS LTDA'):
        u = User.objects.create_user(username=f'c{telefone}', email=f'{telefone}@x.invalid', password='x',
                                     first_name=nome, last_name=sobrenome)
        return StoreCustomer.objects.create(store=self.store, user=u, phone=telefone)

    def test_cliente_criado_por_qualquer_caminho_ganha_identidade(self):
        c = self._cliente_cru('61984319122')
        c.refresh_from_db()
        self.assertIsNotNone(c.unified_user_id)

        achados = self.client.get(self.busca, {'q': 'HOA'}).json()
        self.assertEqual([a['name'] for a in achados], ['HOA COMERCIO DE MOVEIS LTDA'])

    def test_orfaos_antigos_sao_ligados(self):
        from apps.stores.services.identidade_do_cliente import ligar_orfaos
        c = self._cliente_cru('61984319122')
        StoreCustomer.objects.filter(pk=c.pk).update(unified_user=None)

        self.assertEqual(ligar_orfaos(), 1)

        c.refresh_from_db()
        self.assertIsNotNone(c.unified_user_id)
        self.assertEqual(self.client.get(self.busca, {'q': 'HOA'}).json()[0]['name'], 'HOA COMERCIO DE MOVEIS LTDA')
