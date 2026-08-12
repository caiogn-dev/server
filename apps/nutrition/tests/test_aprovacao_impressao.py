"""
Aprovar etiqueta para impressão precisa dizer QUEM e QUANDO.

Sem isso é só um booleano. Quando a etiqueta impressa for questionada — e
etiqueta de alimento é questionada por fiscal, não por usuário —, é esse par
que responde quem assumiu a responsabilidade pelo que foi declarado.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import ProductNutritionProfile
from apps.stores.models import Store, StoreProduct


class AprovacaoImpressaoTest(TestCase):
    def setUp(self):
        self.dono = get_user_model().objects.create_user(
            username="dona-loja", email="dona@teste.local", password="x")
        self.store = Store.objects.create(name="Loja", slug="loja-aprovacao", owner=self.dono)
        produto = StoreProduct.objects.create(store=self.store, name="Prato", slug="prato-ap", price=10)
        self.perfil = ProductNutritionProfile.objects.create(product=produto)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.dono).key}")
        self.url = f"/api/v1/nutrition/profiles/{self.perfil.id}/"

    def test_aprovar_carimba_quem_e_quando(self):
        r = self.client.patch(self.url, {"is_print_approved": True}, format="json")
        self.assertEqual(r.status_code, 200)

        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.is_print_approved)
        self.assertEqual(self.perfil.approved_by, self.dono)
        self.assertIsNotNone(self.perfil.approved_at)

    def test_revogar_limpa_o_carimbo(self):
        # Manter o nome de quem aprovou daria a entender que aquela pessoa
        # aprovou o estado atual, que já é outro.
        self.client.patch(self.url, {"is_print_approved": True}, format="json")
        self.client.patch(self.url, {"is_print_approved": False}, format="json")

        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.is_print_approved)
        self.assertIsNone(self.perfil.approved_by)
        self.assertIsNone(self.perfil.approved_at)

    def test_editar_outro_campo_nao_mexe_no_carimbo(self):
        self.client.patch(self.url, {"is_print_approved": True}, format="json")
        self.perfil.refresh_from_db()
        carimbo = self.perfil.approved_at

        self.client.patch(self.url, {"physical_form": "liquido"}, format="json")

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.physical_form, "liquido")
        self.assertEqual(self.perfil.approved_at, carimbo)
        self.assertEqual(self.perfil.approved_by, self.dono)

    def test_cliente_nao_consegue_forjar_o_aprovador(self):
        outro = get_user_model().objects.create_user(
            username="terceiro", email="terceiro@teste.local", password="x")
        self.client.patch(self.url, {"is_print_approved": True, "approved_by": outro.id}, format="json")

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.approved_by, self.dono)
