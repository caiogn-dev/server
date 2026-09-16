"""`custom_domain` só aceita hostname; qualquer outra coisa é recusada.

Incidente 16/set: o primeiro cliente pago gravou `solo & zelo` no campo de
domínio próprio — provavelmente entendeu que ali ia o nome da loja. O campo
aceitou. O estrago não aparece no painel, aparece no cliente final: o comando
de cardápio do WhatsApp monta `https://{custom_domain}` e passa a mandar
`https://solo & zelo` para quem pede o cardápio.

O campo já normaliza (strip + lower + '' vira None) no save(); o que faltava era
recusar o que não é hostname.
"""
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store

User = get_user_model()


class CustomDomainValidoTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_dominio', email='dono@dominio.com', password='x'
        )

    def _loja(self, dominio, slug='loja-dominio'):
        return Store(name='Loja', slug=slug, owner=self.dono, custom_domain=dominio)

    def test_hostname_valido_passa(self):
        """Âncora: se tudo fosse recusado, os testes de recusa não provariam nada."""
        loja = self._loja('cesaladas.com.br')
        loja.full_clean(exclude=['slug'])
        loja.save()
        self.assertEqual(Store.objects.get(pk=loja.pk).custom_domain, 'cesaladas.com.br')

    def test_vazio_continua_virando_none(self):
        loja = self._loja('   ', slug='loja-vazia')
        loja.save()
        self.assertIsNone(Store.objects.get(pk=loja.pk).custom_domain)

    def test_nome_com_espaco_e_e_comercial_e_recusado(self):
        with self.assertRaises(ValidationError):
            self._loja('solo & zelo').full_clean(exclude=['slug'])

    def test_url_completa_e_recusada(self):
        """Colar a URL inteira é o erro seguinte ao de colar o nome."""
        with self.assertRaises(ValidationError):
            self._loja('https://cesaladas.com.br/cardapio').full_clean(exclude=['slug'])

    def test_hostname_sem_ponto_e_recusado(self):
        with self.assertRaises(ValidationError):
            self._loja('cesaladas').full_clean(exclude=['slug'])


class LimpezaDeDominiosGravadosTest(TestCase):
    """A migration 0082 limpa o que JÁ está gravado errado.

    Sem isso o validador novo tranca o lojista fora da própria loja: o valor
    inválido viaja em todo PATCH do painel, e ele passa a levar erro ao salvar
    qualquer OUTRO campo — cor, horário — por causa de um campo que nem está
    editando.
    """

    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_limpeza', email='dono@limpeza.com', password='x'
        )

    def _gravar_sem_validar(self, slug, dominio):
        """update() não passa por save()/validators — simula o dado legado."""
        loja = Store.objects.create(name='L', slug=slug, owner=self.dono)
        Store.objects.filter(pk=loja.pk).update(custom_domain=dominio)
        return loja

    def _rodar_limpeza(self):
        import importlib
        from django.apps import apps as django_apps

        mod = importlib.import_module(
            'apps.stores.migrations.0082_dominio_proprio_validado'
        )
        mod.limpar_dominios_invalidos(django_apps, None)

    def test_invalido_vira_none_e_valido_sobrevive(self):
        ruim = self._gravar_sem_validar('loja-ruim', 'solo & zelo')
        bom = self._gravar_sem_validar('loja-boa', 'cesaladas.com.br')

        self._rodar_limpeza()

        ruim.refresh_from_db()
        bom.refresh_from_db()
        self.assertIsNone(ruim.custom_domain)
        self.assertEqual(
            bom.custom_domain, 'cesaladas.com.br', 'âncora: domínio bom não pode sumir'
        )

    def test_apos_limpeza_a_loja_volta_a_salvar(self):
        loja = self._gravar_sem_validar('loja-travada', 'solo & zelo')
        self._rodar_limpeza()

        loja.refresh_from_db()
        loja.primary_color = '#123456'
        loja.full_clean(exclude=['slug'])
        loja.save()
        self.assertEqual(Store.objects.get(pk=loja.pk).primary_color, '#123456')
