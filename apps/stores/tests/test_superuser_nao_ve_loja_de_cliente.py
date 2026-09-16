"""Superuser da plataforma NÃO enxerga a loja do cliente no painel.

Incidente 16/set: o primeiro cliente pago (Solo e Zelo) apareceu no painel do
dono da plataforma no mesmo dia em que assinou. Não era IDOR de query param —
era `is_superuser` valendo como chave-mestra em `accessible_store_ids` e em
`user_can_access_store`, as duas funções que TODO o resto da API consulta.

Contrato: acesso a uma loja vem de VÍNCULO (owner, staff M2M legado ou
StoreTeamMember ativo), nunca de flag global de conta. Suporte a cliente se faz
pelo /admin do Django ou entrando no staff da loja — de forma registrada.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.permissions import accessible_store_ids, user_can_access_store
from apps.stores.models import Store

User = get_user_model()


class SuperuserNaoVeLojaDeClienteTest(TestCase):
    def setUp(self):
        self.plataforma = User.objects.create_superuser(
            username='dono_plataforma', email='dono@plataforma.com', password='x'
        )
        self.loja_propria = Store.objects.create(
            name='Loja Propria', slug='loja-propria', owner=self.plataforma, status='active'
        )
        self.cliente = User.objects.create_user(
            username='cliente_pagante', email='cliente@loja.com', password='x'
        )
        self.loja_cliente = Store.objects.create(
            name='Loja do Cliente', slug='loja-do-cliente', owner=self.cliente, status='active'
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.plataforma)

    def test_accessible_store_ids_exclui_loja_sem_vinculo(self):
        ids = list(accessible_store_ids(self.plataforma))
        self.assertIn(self.loja_propria.id, ids)
        self.assertNotIn(self.loja_cliente.id, ids)

    def test_user_can_access_store_false_para_loja_sem_vinculo(self):
        self.assertTrue(user_can_access_store(self.plataforma, self.loja_propria))
        self.assertFalse(user_can_access_store(self.plataforma, self.loja_cliente))

    def test_listagem_do_painel_nao_traz_loja_do_cliente(self):
        resp = self.api.get('/api/v1/stores/stores/')
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        itens = dados.get('results', dados) if isinstance(dados, dict) else dados
        slugs = {item['slug'] for item in itens}
        self.assertIn('loja-propria', slugs)
        self.assertNotIn('loja-do-cliente', slugs)

    def test_detalhe_da_loja_do_cliente_responde_404(self):
        """Ancorado na loja própria: se o detalhe respondesse 404 para TODA
        loja, o assert de 404 seria vazio e nunca acusaria o vazamento."""
        propria = self.api.get(f'/api/v1/stores/stores/{self.loja_propria.slug}/')
        self.assertEqual(propria.status_code, 200)
        alheia = self.api.get(f'/api/v1/stores/stores/{self.loja_cliente.slug}/')
        self.assertEqual(alheia.status_code, 404)

    def test_vinculo_explicito_devolve_o_acesso(self):
        """Entrar no staff da loja é o caminho legítimo de dar suporte."""
        self.loja_cliente.staff.add(self.plataforma)
        self.assertTrue(user_can_access_store(self.plataforma, self.loja_cliente))
        self.assertIn(self.loja_cliente.id, list(accessible_store_ids(self.plataforma)))
