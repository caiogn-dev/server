"""Código de barras interno para produto que não tem código de fabricante.

A etiqueta e o leitor do balcão precisam de um código, e a maioria dos
produtos das lojas é feita na cozinha — não vem com EAN de fábrica. Em
produção (12/ago): Agrião 0 de 47, Cê Saladas 1 de 35, Ivoneth 0 de 45.
Só a Pastita tinha todos, e com códigos de fabricante.

O código gerado é **EAN-13 começando com 2**, que é a faixa que o GS1 reserva
para uso interno de loja. Isso importa por dois motivos: nunca colide com o
código de um produto de indústria, e qualquer leitor lê nativamente, sem
configuração. A "Queridinha" da Cê Saladas já usava 24…, então a convenção
não é invenção nova — está sendo padronizada.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.stores.services.codigo_interno import (
    digito_verificador_ean13,
    gerar_codigo_interno,
    valido_ean13,
)

User = get_user_model()


class DigitoVerificadorTest(TestCase):
    def test_confere_com_codigos_reais(self):
        # EAN-13 de verdade, conferidos à mão pela regra dos pesos 1/3.
        # 4006381333931 é o exemplar clássico de teste da própria GS1.
        self.assertEqual(digito_verificador_ean13('400638133393'), 1)
        self.assertEqual(digito_verificador_ean13('789123456789'), 5)

    def test_valido_ean13_aceita_o_que_fecha_e_recusa_o_que_nao(self):
        self.assertTrue(valido_ean13('4006381333931'))
        # 🚨 Este é um código REAL do banco (Pastita, "Rondelli de Bacalhau") e
        # ele NÃO fecha: é placeholder de seed que um leitor recusaria no
        # balcão. Fica como teste para o dia em que alguém o copiar de novo.
        self.assertFalse(valido_ean13('7891234567894'))
        self.assertFalse(valido_ean13('789123456789'))    # curto demais
        self.assertFalse(valido_ean13('78912345678a4'))   # não é dígito


class GerarCodigoInternoTest(TestCase):
    def test_sempre_comeca_com_2_e_tem_13_digitos(self):
        codigo = gerar_codigo_interno(loja=1, sequencial=1)

        self.assertEqual(len(codigo), 13)
        self.assertTrue(codigo.startswith('2'))
        self.assertTrue(valido_ean13(codigo))

    def test_lojas_diferentes_nunca_colidem(self):
        a = gerar_codigo_interno(loja=1, sequencial=1)
        b = gerar_codigo_interno(loja=2, sequencial=1)

        self.assertNotEqual(a, b)

    def test_mesmo_par_gera_o_mesmo_codigo(self):
        """Determinístico: rodar de novo não inventa código novo."""
        self.assertEqual(
            gerar_codigo_interno(loja=7, sequencial=42),
            gerar_codigo_interno(loja=7, sequencial=42),
        )

    def test_recusa_loja_fora_da_faixa(self):
        with self.assertRaises(ValueError):
            gerar_codigo_interno(loja=100, sequencial=1)
        with self.assertRaises(ValueError):
            gerar_codigo_interno(loja=0, sequencial=1)


class ComandoGerarCodigosTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-cb', password='x')
        self.store = Store.objects.create(
            name='Loja CB', slug='loja-cb', owner=dono, status='active',
        )
        self.especiais = StoreCategory.objects.create(
            store=self.store, name='Saladas Especiais', slug='saladas-especiais',
        )
        self.bebidas = StoreCategory.objects.create(
            store=self.store, name='Bebidas', slug='bebidas',
        )

    def _produto(self, nome, categoria, barcode='', status='active'):
        return StoreProduct.objects.create(
            store=self.store, category=categoria, name=nome,
            slug=nome.lower().replace(' ', '-'), price=30,
            barcode=barcode, status=status,
        )

    def _rodar(self, **kwargs):
        from django.core.management import call_command
        from io import StringIO
        saida = StringIO()
        call_command('gerar_codigos_internos', loja='loja-cb', stdout=saida, **kwargs)
        return saida.getvalue()

    def test_gera_para_quem_nao_tem(self):
        p = self._produto('Tilápia Suprema', self.especiais)

        self._rodar()

        p.refresh_from_db()
        self.assertTrue(valido_ean13(p.barcode))
        self.assertTrue(p.barcode.startswith('2'))

    def test_nao_toca_em_quem_ja_tem_codigo(self):
        """Código de fabricante é a identidade real do produto — não sobrescrever."""
        p = self._produto('Refrigerante', self.bebidas, barcode='7891234567894')

        self._rodar()

        p.refresh_from_db()
        self.assertEqual(p.barcode, '7891234567894')

    def test_filtra_por_categoria(self):
        alvo = self._produto('Salada Especial', self.especiais)
        fora = self._produto('Suco', self.bebidas)

        self._rodar(categoria=['Saladas Especiais'])

        alvo.refresh_from_db(); fora.refresh_from_db()
        self.assertTrue(alvo.barcode)
        self.assertEqual(fora.barcode, '')

    def test_dry_run_nao_grava(self):
        p = self._produto('Salada', self.especiais)

        saida = self._rodar(dry_run=True)

        p.refresh_from_db()
        self.assertEqual(p.barcode, '')
        self.assertIn('Salada', saida)

    def test_dois_produtos_nunca_recebem_o_mesmo_codigo(self):
        a = self._produto('Salada A', self.especiais)
        b = self._produto('Salada B', self.especiais)

        self._rodar()

        a.refresh_from_db(); b.refresh_from_db()
        self.assertNotEqual(a.barcode, b.barcode)

    def test_rodar_duas_vezes_nao_muda_o_codigo_ja_gerado(self):
        """Idempotente: o código impresso na etiqueta de ontem tem que valer hoje."""
        p = self._produto('Salada', self.especiais)
        self._rodar()
        p.refresh_from_db()
        primeiro = p.barcode

        self._rodar()

        p.refresh_from_db()
        self.assertEqual(p.barcode, primeiro)

    def test_ignora_produto_inativo(self):
        p = self._produto('Fora de linha', self.especiais, status='inactive')

        self._rodar()

        p.refresh_from_db()
        self.assertEqual(p.barcode, '')
