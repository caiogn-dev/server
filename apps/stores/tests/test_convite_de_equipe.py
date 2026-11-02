"""Convidar colaborador pelo TELEFONE, não por UUID.

O CRUD de equipe existe desde sempre em `/stores/{slug}/team/`, e mesmo assim
nenhuma loja em produção usa: medido em 22/09, 4 membros no total, e a
`ce-saladas` com ZERO.

A razão está no serializer: `TeamMemberCreateSerializer` exige `user_id`, um
UUID. O dono da loja não tem como saber o UUID de ninguém — e a regra da casa
é que o painel é produto do lojista, não debugger: ID, token e endereço de API
não aparecem na tela. Então a tela nunca pôde ser feita.

Telefone é a identidade natural deste sistema: é assim que o cliente entra
(OTP do WhatsApp), é a chave que o bot usa e é o que o dono sabe de cor do
funcionário dele.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.core.models import UserProfile
from apps.stores.models import Store, StoreTeamMember

User = get_user_model()


class ConviteDeEquipeTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-eq', password='x', email='dono-eq@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Equipe', slug='loja-equipe', owner=self.dono, status='active',
        )
        self.client.force_authenticate(user=self.dono)

    def _convidar(self, **corpo):
        return self.client.post(f'/api/v1/stores/{self.store.slug}/team/', corpo, format='json')

    def test_convida_pelo_telefone_e_cria_a_pessoa_que_ainda_nao_existe(self):
        r = self._convidar(phone='63 99999-0001', name='Maria Souza', role='operator')

        self.assertIn(r.status_code, (200, 201), r.data)
        membro = StoreTeamMember.objects.get(tenant=self.store)
        self.assertEqual(membro.role, 'operator')
        self.assertEqual(membro.user.first_name, 'Maria')
        self.assertTrue(
            UserProfile.objects.filter(user=membro.user).exclude(phone='').exists(),
            'o telefone não ficou gravado no perfil',
        )

    def test_mesmo_telefone_em_outro_formato_nao_cria_pessoa_duplicada(self):
        """'63 99999-0001' e '+5563999990001' são a mesma pessoa.

        Sem isso o dono convida, não vê a pessoa na lista, convida de novo e a
        loja fica com dois cadastros para o mesmo funcionário.
        """
        self._convidar(phone='63 99999-0002', name='João Lima', role='operator')
        antes = User.objects.count()

        r = self._convidar(phone='+55 63 99999-0002', name='João Lima', role='manager')

        self.assertEqual(User.objects.count(), antes, 'criou usuário duplicado')
        self.assertEqual(StoreTeamMember.objects.filter(tenant=self.store).count(), 1)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(
            StoreTeamMember.objects.get(tenant=self.store).role, 'manager',
            'reconvidar deveria atualizar o papel',
        )

    def test_telefone_curto_demais_e_recusado_com_mensagem_de_gente(self):
        r = self._convidar(phone='99999', name='Alguém', role='operator')

        self.assertEqual(r.status_code, 400)
        texto = str(r.data).lower()
        self.assertIn('telefone', texto)
        self.assertNotIn('uuid', texto)

    def test_reativa_quem_foi_removido_em_vez_de_estourar_unique(self):
        """DELETE é soft delete (is_active=False), e `unique_together` é
        (tenant, user). Convidar de volta sem tratar isso dá IntegrityError."""
        self._convidar(phone='63 99999-0003', name='Ana Reis', role='operator')
        membro = StoreTeamMember.objects.get(tenant=self.store)
        membro.is_active = False
        membro.save(update_fields=['is_active'])

        r = self._convidar(phone='63 99999-0003', name='Ana Reis', role='viewer')

        self.assertIn(r.status_code, (200, 201), r.data)
        membro.refresh_from_db()
        self.assertTrue(membro.is_active)
        self.assertEqual(membro.role, 'viewer')

    def test_user_id_continua_funcionando(self):
        """Compatibilidade: quem já chamava com UUID não pode quebrar."""
        outro = User.objects.create_user(username='outro-eq', password='x', email='o-eq@real.com')

        r = self._convidar(user_id=str(outro.pk), role='viewer')

        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertTrue(
            StoreTeamMember.objects.filter(tenant=self.store, user=outro).exists()
        )


class ColaboradorEntraNoPainelTests(APITestCase):
    """O convite criava a pessoa com senha INUTILIZÁVEL e o login só aceitava
    e-mail: ninguém convidado conseguia entrar (28/09)."""

    def setUp(self):
        self.dono = User.objects.create_user(username='dono-eq2', password='x', email='dono-eq2@real.com')
        self.store = Store.objects.create(name='Loja Equipe 2', slug='loja-equipe-2', owner=self.dono, status='active')
        self.client.force_authenticate(user=self.dono)

    def _convidar(self, **corpo):
        return self.client.post(f'/api/v1/stores/{self.store.slug}/team/', corpo, format='json')

    def _login(self, identificador, senha):
        from rest_framework.test import APIClient
        anonimo = APIClient()
        return anonimo.post('/api/v1/auth/login/', {'email': identificador, 'password': senha}, format='json')

    def test_convite_com_senha_permite_entrar_pelo_celular(self):
        r = self._convidar(phone='63 98888-0002', name='João Lima', role='operator', password='segredo1')
        self.assertIn(r.status_code, (200, 201), r.data)

        for como in ('63 98888-0002', '5563988880002', '(63) 98888-0002'):
            r = self._login(como, 'segredo1')
            self.assertEqual(r.status_code, 200, (como, r.data))
            self.assertIn('token', r.data)

        self.assertEqual(self._login('63 98888-0002', 'errada').status_code, 401)

    def test_senha_curta_e_recusada(self):
        r = self._convidar(phone='63 98888-0003', role='operator', password='123')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', str(r.data))

    def test_sem_senha_continua_convidando_mas_sem_acesso(self):
        r = self._convidar(phone='63 98888-0004', role='operator')
        self.assertIn(r.status_code, (200, 201))
        self.assertEqual(self._login('63 98888-0004', 'qualquer1').status_code, 401)

    def test_a_senha_nao_volta_na_resposta(self):
        r = self._convidar(phone='63 98888-0005', role='operator', password='segredo1')
        self.assertNotIn('segredo1', str(r.data))


class ConviteNaoTrocaSenhaDeContaExistenteTests(APITestCase):
    """Convite define senha só de quem nasceu nele.

    Até 02/11 o dono da loja A mandava o telefone do dono da loja B (ou de
    qualquer cliente) com uma senha no convite, e a conta passava a ser dele.
    """

    SENHA_ORIGINAL = 'senha-original-1'
    SENHA_DO_ATACANTE = 'senha-do-atacante'

    def setUp(self):
        self.atacante = User.objects.create_user(username='dono-a', password='x', email='a@real.com')
        self.loja_a = Store.objects.create(name='Loja A', slug='loja-a', owner=self.atacante, status='active')
        self.vitima = User.objects.create_user(
            username='dono-b', password=self.SENHA_ORIGINAL, email='b@real.com',
        )
        UserProfile.objects.update_or_create(user=self.vitima, defaults={'phone': '5563977770001'})
        self.client.force_authenticate(user=self.atacante)

    def _convidar(self, **corpo):
        return self.client.post(f'/api/v1/stores/{self.loja_a.slug}/team/', corpo, format='json')

    def _senha_intacta(self, usuario=None):
        usuario = usuario or self.vitima
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(self.SENHA_ORIGINAL), 'a senha da conta foi trocada')
        self.assertFalse(usuario.check_password(self.SENHA_DO_ATACANTE))

    def test_pelo_telefone_nao_troca_a_senha_e_a_tela_fica_sabendo(self):
        r = self._convidar(phone='63 97777-0001', role='operator', password=self.SENHA_DO_ATACANTE)

        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertIs(r.data['senha_definida'], False)
        self._senha_intacta()
        self.assertTrue(StoreTeamMember.objects.filter(tenant=self.loja_a, user=self.vitima).exists())

    def test_pelo_user_id_nao_troca_a_senha(self):
        r = self._convidar(user_id=self.vitima.pk, role='operator', password=self.SENHA_DO_ATACANTE)

        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertIs(r.data['senha_definida'], False)
        self._senha_intacta()

    def test_superusuario_nao_tem_a_senha_trocada(self):
        admin = User.objects.create_superuser(
            username='admin-x', password=self.SENHA_ORIGINAL, email='adm@real.com',
        )
        self._convidar(user_id=admin.pk, role='operator', password=self.SENHA_DO_ATACANTE)
        self._senha_intacta(admin)

    def test_convidar_em_duas_etapas_nao_abre_o_caminho(self):
        """Primeiro entra na equipe sem senha, depois tenta definir a senha."""
        self._convidar(phone='63 97777-0001', role='operator')
        self._convidar(phone='63 97777-0001', role='operator', password=self.SENHA_DO_ATACANTE)
        self._senha_intacta()

    def test_pessoa_nova_continua_recebendo_a_senha(self):
        r = self._convidar(phone='63 97777-0002', name='Nova', role='operator', password='segredo1')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertIs(r.data['senha_definida'], True)
        membro = StoreTeamMember.objects.get(tenant=self.loja_a, user__profile__phone__contains='63977770002')
        self.assertTrue(membro.user.check_password('segredo1'))
