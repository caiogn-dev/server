"""
Foto das opções do combo precisa sair com endereço COMPLETO.

O storefront roda em outro domínio (cardapidex.com.br) e o backend serve a
mídia. `/media/...` relativo resolve contra o domínio da vitrine e dá 404 —
foi o que quebrou as fotos no detalhe dos combos da Agrião em 03/10/2026,
enquanto o mesmo produto, fora do combo, aparecia normal (o serializer de
produto já passava por `get_main_image_url`).
"""
from django.conf import settings
from django.test import TestCase

from apps.stores.api.serializers import build_combo_groups
from apps.stores.tests.factories import make_combo_with_groups


class FotoDasOpcoesDoComboTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=1, variants=1, options=1)
        grupo = cls.combo.groups.get()
        opcao = grupo.product_options.get().product
        opcao.main_image_url = '/media/stores/products/loja/prato.webp'
        opcao.save(update_fields=['main_image_url'])
        variante = grupo.variant_limits.get().variant
        variante.image_url = '/media/stores/variants/loja/variante.webp'
        variante.save(update_fields=['image_url'])

    def _grupo(self):
        return build_combo_groups(self.combo)[0]

    def test_opcao_de_produto_sai_com_endereco_completo(self):
        url = self._grupo()['product_options'][0]['image_url']
        assert url == f"{settings.BACKEND_URL.rstrip('/')}/media/stores/products/loja/prato.webp"

    def test_opcao_de_variante_sai_com_endereco_completo(self):
        url = self._grupo()['variant_limits'][0]['image_url']
        assert url == f"{settings.BACKEND_URL.rstrip('/')}/media/stores/variants/loja/variante.webp"

    def test_opcao_sem_foto_nao_inventa_endereco(self):
        # Sem foto, nada de "https://backend/" pelado: o modal trataria como
        # imagem e mostraria o ícone de quebrada.
        grupo = self.combo.groups.get()
        p = grupo.product_options.get().product
        p.main_image_url = ''
        p.save(update_fields=['main_image_url'])
        assert not self._grupo()['product_options'][0]['image_url']
