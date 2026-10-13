"""
Foto do cardápio padronizada no envio.

13/10: as 343 fotos de produto/combo/variante/categoria somavam 187 MB (média
545 KB), 115 em PNG, com proporções misturadas. Nada era tratado no upload —
o celular manda 4000 px deitado pelo EXIF e a vitrine baixava isso inteiro.
Agora: gira pelo EXIF, reduz para no máximo 1280 px e grava WebP.
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.stores.services.foto_do_cardapio import LADO_MAXIMO, normalizar_bytes
from apps.stores.tests.factories import make_product, make_store


def _imagem(formato='PNG', tamanho=(3000, 2000), modo='RGB', exif_girada=False):
    img = Image.new(modo, tamanho, (200, 30, 30) if modo == 'RGB' else (200, 30, 30, 128))
    saida = io.BytesIO()
    kwargs = {}
    if exif_girada:
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: girar 90° no sentido horário
        kwargs['exif'] = exif
    img.save(saida, formato, **kwargs)
    return saida.getvalue()


def _abrir(conteudo):
    img = Image.open(io.BytesIO(conteudo))
    img.load()
    return img


class NormalizarBytesTest(TestCase):
    def test_foto_grande_vira_webp_no_lado_maximo(self):
        saida = _abrir(normalizar_bytes(_imagem('PNG', (3000, 2000))))
        assert saida.format == 'WEBP'
        assert max(saida.size) == LADO_MAXIMO
        assert saida.size == (1280, 853)

    def test_foto_pequena_nao_e_ampliada(self):
        saida = _abrir(normalizar_bytes(_imagem('JPEG', (600, 400))))
        assert saida.size == (600, 400)
        assert saida.format == 'WEBP'

    def test_foto_deitada_pelo_exif_fica_em_pe(self):
        saida = _abrir(normalizar_bytes(_imagem('JPEG', (2000, 1000), exif_girada=True)))
        assert saida.size[1] > saida.size[0]

    def test_transparencia_do_png_e_mantida(self):
        saida = _abrir(normalizar_bytes(_imagem('PNG', (800, 800), modo='RGBA')))
        assert saida.mode == 'RGBA'

    def test_gif_animado_passa_sem_mexer(self):
        quadros = [Image.new('RGB', (50, 50), c) for c in ((255, 0, 0), (0, 255, 0))]
        buf = io.BytesIO()
        quadros[0].save(buf, 'GIF', save_all=True, append_images=quadros[1:])
        assert normalizar_bytes(buf.getvalue()) is None

    def test_arquivo_que_nao_abre_devolve_none(self):
        assert normalizar_bytes(b'nao sou imagem') is None


class FotoDoProdutoNoUploadTest(TestCase):
    def test_upload_de_produto_grava_webp_reduzido(self):
        loja = make_store()
        produto = make_product(loja)
        produto.main_image = SimpleUploadedFile('prato.png', _imagem('PNG', (3000, 3000)), content_type='image/png')
        produto.save()
        produto.refresh_from_db()
        assert produto.main_image.name.endswith('.webp')
        with produto.main_image.open('rb') as f:
            img = _abrir(f.read())
        assert img.size == (1280, 1280)

    def test_salvar_de_novo_sem_trocar_a_foto_nao_reprocessa(self):
        loja = make_store()
        produto = make_product(loja)
        produto.main_image = SimpleUploadedFile('prato.png', _imagem('PNG', (900, 900)), content_type='image/png')
        produto.save()
        nome = produto.main_image.name
        produto.name = 'Outro nome'
        produto.save()
        produto.refresh_from_db()
        assert produto.main_image.name == nome


class ComandoDePadronizarFotosTest(TestCase):
    def _produto_com_png_grande(self):
        from django.core.files.base import ContentFile
        loja = make_store()
        produto = make_product(loja)
        # Grava SEM passar pelo sinal: simula foto antiga, de antes da regra.
        produto.main_image.save('antiga.png', ContentFile(_imagem('PNG', (2400, 1600))), save=False)
        type(produto).objects.filter(pk=produto.pk).update(main_image=produto.main_image.name)
        return produto

    def test_simulacao_nao_mexe_em_nada(self):
        from django.core.management import call_command
        produto = self._produto_com_png_grande()
        nome = produto.main_image.name
        call_command('padronizar_fotos_do_cardapio')
        produto.refresh_from_db()
        assert produto.main_image.name == nome

    def test_aplicar_converte_e_preserva_o_original(self):
        from django.core.management import call_command
        produto = self._produto_com_png_grande()
        antigo = produto.main_image.name
        call_command('padronizar_fotos_do_cardapio', '--aplicar')
        produto.refresh_from_db()
        assert produto.main_image.name.endswith('.webp')
        assert produto.main_image.storage.exists(antigo)
        with produto.main_image.open('rb') as f:
            assert max(_abrir(f.read()).size) == LADO_MAXIMO
