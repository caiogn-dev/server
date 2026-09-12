"""A loja precisa conseguir LIGAR o vale por link — pelo painel, sem deploy."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.serializers import StoreSerializer
from apps.stores.models import Store

User = get_user_model()


class ConfigDoValePorLinkTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-vplc', password='x', email='o-vplc@real.com')
        self.store = Store.objects.create(
            name='Loja Config', slug='loja-config', owner=self.owner,
            status='active', whatsapp_number='5563999998888',
            metadata={'owner_phone': '5563911112222'},
        )

    def _salvar(self, valores):
        s = StoreSerializer(self.store, data={'vale_por_link_brands': valores},
                            partial=True)
        s.is_valid(raise_exception=True)
        return s.save()

    def test_ligar_a_volus_grava_no_metadata(self):
        self._salvar(['volus'])
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['voucher_manual_brands'], ['volus'])

    def test_salvar_NAO_apaga_o_resto_do_metadata(self):
        """`metadata` é compartilhado. Trocar o dicionário inteiro apagaria o
        telefone do parceiro — foi assim que editar cliente deletou endereço."""
        self._salvar(['volus'])
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['owner_phone'], '5563911112222')

    def test_desligar_remove_a_chave_em_vez_de_deixar_lista_vazia(self):
        self._salvar(['volus'])
        self._salvar([])
        self.store.refresh_from_db()
        self.assertNotIn('voucher_manual_brands', self.store.metadata)
        self.assertEqual(self.store.metadata['owner_phone'], '5563911112222')

    def test_bandeira_fora_do_catalogo_e_recusada(self):
        """Lixo aqui vira opção na tela do cliente — tem que morrer na porta."""
        s = StoreSerializer(self.store, data={'vale_por_link_brands': ['xpto']},
                            partial=True)
        self.assertFalse(s.is_valid())
        self.assertIn('vale_por_link_brands', s.errors)

    def test_o_painel_le_o_que_esta_ligado(self):
        self._salvar(['volus'])
        self.store.refresh_from_db()
        dados = StoreSerializer(self.store).data
        self.assertEqual(dados['vale_por_link_brands'], ['volus'])

    def test_sem_o_campo_no_PATCH_o_que_ja_estava_fica(self):
        """Salvar outra aba do painel não pode desligar o vale."""
        self._salvar(['volus'])
        s = StoreSerializer(self.store, data={'tagline': 'oi'}, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['voucher_manual_brands'], ['volus'])


class CatalogoManualNaAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-cat', password='x', email='o-cat@real.com')
        self.client.force_authenticate(self.owner)

    def test_o_endpoint_de_bandeiras_serve_tambem_as_manuais(self):
        """Uma chamada, os dois catálogos. Duas rotas seriam duas verdades."""
        r = self.client.get('/api/v1/stores/payments/gateways/bandeiras-de-vale/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('brands', r.data)
        self.assertIn('manual_brands', r.data)
        self.assertIn('volus', [b['value'] for b in r.data['manual_brands']])

    def test_a_volus_NAO_aparece_no_catalogo_integrado(self):
        """Misturar abriria formulário de cartão para bandeira sem cobrança."""
        r = self.client.get('/api/v1/stores/payments/gateways/bandeiras-de-vale/')
        self.assertNotIn('volus', [b['value'] for b in r.data['brands']])
