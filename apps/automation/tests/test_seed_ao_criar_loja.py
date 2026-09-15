"""Criar loja semeia as mensagens automáticas em produção — e só na suíte pode não semear.

A suíte desliga o seed (`AUTOMATION_SEMEAR_MENSAGENS_AO_CRIAR_LOJA=False` em
config/settings/test.py) porque ele custava 17 get_or_create por loja criada.
Estes testes travam os dois lados: desligado não cria nada, ligado (o padrão de
produção) cria o conjunto padrão — e o CompanyProfile nasce nos dois casos.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store

User = get_user_model()


class SeedAoCriarLojaTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-seed', password='x')

    def _loja(self, slug):
        return Store.objects.create(name='Loja Seed', slug=slug, owner=self.dono)

    def test_suite_nao_semeia_mas_cria_o_perfil(self):
        loja = self._loja('loja-seed-off')
        perfil = CompanyProfile.objects.get(store=loja)
        self.assertEqual(AutoMessage.objects.filter(company=perfil).count(), 0)

    @override_settings(AUTOMATION_SEMEAR_MENSAGENS_AO_CRIAR_LOJA=True)
    def test_producao_semeia_as_mensagens_padrao(self):
        loja = self._loja('loja-seed-on')
        perfil = CompanyProfile.objects.get(store=loja)
        self.assertGreater(AutoMessage.objects.filter(company=perfil).count(), 0)
