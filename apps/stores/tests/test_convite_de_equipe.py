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
