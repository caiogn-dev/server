"""
Salvar o storefront de uma loja SEM domínio próprio devolvia 500.

`custom_domain` é `unique` e aceita tanto NULL quanto string vazia. NULL não
colide com NULL no Postgres, mas `''` colide com `''` — e o painel manda
`custom_domain: ''` sempre que o campo está em branco na tela. Bastou UMA loja
gravar `''` no banco para que TODA loja sem domínio próprio passasse a quebrar
com IntegrityError ao salvar qualquer outra coisa (template, cor, tagline).

Ausência de domínio tem uma única representação: NULL. `''` não é um domínio
vazio, é a ausência dele escrita errado.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store

User = get_user_model()


class DominioProprioVazioTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-dominio', email='dono-dominio@example.com', password='x'
        )

    def _loja(self, slug, **kwargs):
        return Store.objects.create(
            name=slug, slug=slug, owner=self.dono, **kwargs
        )

    def test_string_vazia_vira_null(self):
        """`''` não é um domínio: é ausência, e ausência é NULL."""
        loja = self._loja('loja-sem-dominio', custom_domain='')
        loja.refresh_from_db()
        self.assertIsNone(loja.custom_domain)

    def test_duas_lojas_sem_dominio_convivem(self):
        """Duas ausências não colidem — era exatamente o IntegrityError."""
        self._loja('primeira-sem-dominio', custom_domain='')
        segunda = self._loja('segunda-sem-dominio', custom_domain='')
        segunda.refresh_from_db()
        self.assertIsNone(segunda.custom_domain)

    def test_salvar_template_com_dominio_vazio_nao_quebra(self):
        """O caso real: trocar o template de uma loja sem domínio próprio."""
        outra = self._loja('outra-loja-vazia', custom_domain='')
        loja = self._loja('ivoneth-teste')

        loja.custom_domain = ''
        loja.template = Store.StoreTemplate.DARK
        loja.save()

        loja.refresh_from_db()
        self.assertEqual(loja.template, Store.StoreTemplate.DARK)
        self.assertIsNone(loja.custom_domain)
        self.assertIsNone(Store.objects.get(pk=outra.pk).custom_domain)

    def test_dominio_de_verdade_continua_gravando(self):
        """A normalização mira só o vazio — domínio real é intocado."""
        loja = self._loja('loja-com-dominio', custom_domain='  Minhaloja.COM.br ')
        loja.refresh_from_db()
        self.assertEqual(loja.custom_domain, 'minhaloja.com.br')
