"""StoreQuerysetMixin e HasStoreAccess não abrem cross-tenant por flag.

Última peça do vazamento de 16/set. O mixin devolvia `None` ("unrestricted")
para superuser, e quem herda dele inclui o ViewSet de GATEWAYS DE PAGAMENTO:
as credenciais com que a loja do cliente recebe o dinheiro dela. Também
cupons, zonas de entrega, pagamentos e eventos de webhook.

O docstring do StorePermissionMixin dizia, por escrito, "Superusers and staff
bypass all restrictions" — era descrição fiel do comportamento, e o
comportamento é que estava errado.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.permissions import StoreQuerysetMixin
from apps.stores.models import Store, StorePaymentGateway

User = get_user_model()


class MixinEscopoSuperuserTest(TestCase):
    def setUp(self):
        self.plataforma = User.objects.create_superuser(
            username='dono_plataforma4', email='dono4@plataforma.com', password='x'
        )
        self.minha = Store.objects.create(
            name='Loja Mixin', slug='loja-mixin', owner=self.plataforma, status='active'
        )
        self.cliente = User.objects.create_user(
            username='cliente4', email='cliente4@loja.com', password='x'
        )
        self.alheia = Store.objects.create(
            name='Loja Mixin Alheia', slug='loja-mixin-alheia', owner=self.cliente,
            status='active',
        )

    def test_mixin_nunca_devolve_escopo_irrestrito(self):
        mixin = StoreQuerysetMixin()
        mixin.request = type('Req', (), {'user': self.plataforma})()
        ids = mixin._get_user_store_ids()
        self.assertIsNotNone(ids, 'None significa "sem filtro": vaza todo tenant')
        ids = {str(i) for i in ids}
        self.assertIn(str(self.minha.id), ids, 'âncora: a própria tem que estar')
        self.assertNotIn(str(self.alheia.id), ids)

    def test_gateway_de_pagamento_alheio_nao_e_listado(self):
        StorePaymentGateway.objects.create(
            store=self.minha, name='MP meu', gateway_type='mercadopago',
            is_enabled=True, access_token='TOKEN-MEU',
        )
        StorePaymentGateway.objects.create(
            store=self.alheia, name='MP alheio', gateway_type='mercadopago',
            is_enabled=True, access_token='TOKEN-ALHEIO',
        )
        api = APIClient()
        api.force_authenticate(user=self.plataforma)
        resp = api.get('/api/v1/stores/payments/gateways/')
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        itens = dados.get('results', dados) if isinstance(dados, dict) else dados
        nomes = {i.get('name') for i in itens}
        self.assertIn('MP meu', nomes, 'âncora: o próprio tem que aparecer')
        self.assertNotIn('MP alheio', nomes)

    def test_has_store_access_recusa_loja_alheia(self):
        from apps.core.permissions import HasStoreAccess

        perm = HasStoreAccess()

        class _View:
            kwargs = {}

        class _Req:
            def __init__(self, user, slug):
                self.user = user
                self.query_params = {'store_slug': slug}

        view = _View()
        view.kwargs = {'store_slug': self.minha.slug}
        self.assertTrue(perm.has_permission(_Req(self.plataforma, self.minha.slug), view))

        view.kwargs = {'store_slug': self.alheia.slug}
        self.assertFalse(perm.has_permission(_Req(self.plataforma, self.alheia.slug), view))

    def test_has_store_access_objeto_alheio_e_recusado(self):
        from apps.core.permissions import HasStoreAccess

        perm = HasStoreAccess()
        req = type('Req', (), {'user': self.plataforma})()
        self.assertTrue(perm.has_object_permission(req, None, self.minha))
        self.assertFalse(perm.has_object_permission(req, None, self.alheia))
