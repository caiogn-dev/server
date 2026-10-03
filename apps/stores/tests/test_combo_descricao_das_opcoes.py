"""
Opção de combo traz uma descrição curta do prato.

No seletor do combo (Combo Família: 30 escolhas entre 26 pratos) o cliente
só via nome e foto. A descrição curta é o que diz "é escondidinho de quê,
com o quê" sem abrir outro modal. Só a 1ª frase/parágrafo, cortada: a lista
é longa e cada linha precisa caber em duas linhas de texto.
"""
from django.test import TestCase

from apps.stores.api.serializers import build_combo_groups
from apps.stores.tests.factories import make_combo_with_groups


class DescricaoDaOpcaoDoComboTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=1, variants=0, options=1)
        cls.produto = cls.combo.groups.get().product_options.get().product

    def _descricao(self):
        return build_combo_groups(self.combo)[0]['product_options'][0]['description']

    def test_usa_a_descricao_curta_quando_existe(self):
        self.produto.short_description = 'Purê de banana-da-terra recheado com frango.'
        self.produto.description = 'Texto longo.\n\nPorção: 300 g.'
        self.produto.save(update_fields=['short_description', 'description'])
        assert self._descricao() == 'Purê de banana-da-terra recheado com frango.'

    def test_sem_curta_usa_o_primeiro_paragrafo_da_completa(self):
        self.produto.short_description = ''
        self.produto.description = 'Frango desfiado com creme de milho.\n\nPorção: 120 g de frango.'
        self.produto.save(update_fields=['short_description', 'description'])
        assert self._descricao() == 'Frango desfiado com creme de milho.'

    def test_corta_texto_longo_sem_partir_palavra(self):
        self.produto.short_description = ('palavra ' * 40).strip()
        self.produto.save(update_fields=['short_description'])
        texto = self._descricao()
        assert len(texto) <= 141
        assert texto.endswith('…')
        assert not texto[:-1].endswith('palavr')

    def test_sem_descricao_nenhuma_vem_vazio(self):
        self.produto.short_description = ''
        self.produto.description = ''
        self.produto.save(update_fields=['short_description', 'description'])
        assert self._descricao() == ''
