"""Banners do cardápio: até 3 imagens, subidas pelo painel, lidas pelo catálogo."""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APITestCase

from apps.stores.api.serializers import StoreSerializer
from apps.stores.models import Store, StoreBanner

User = get_user_model()


def _png(nome='b.png'):
    buf = io.BytesIO()
    Image.new('RGB', (160, 70), (200, 30, 30)).save(buf, format='PNG')
    return SimpleUploadedFile(nome, buf.getvalue(), content_type='image/png')


class BannersTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='d-ban', password='x', email='d-ban@real.com')
        self.loja = Store.objects.create(name='Loja Ban', slug='loja-ban', owner=self.dono, status='active')
        self.client.force_authenticate(self.dono)
        self.url = f'/api/v1/stores/stores/{self.loja.id}/banners/'

    def _subir(self):
        return self.client.post(self.url, {'image': _png()}, format='multipart')

    def test_dono_sobe_banner(self):
        r = self._subir()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(StoreBanner.objects.filter(store=self.loja).count(), 1)
        self.assertTrue(r.data['url'])

    def test_o_quarto_banner_e_recusado(self):
        """O teto é do servidor: painel velho ou chamada direta não passam."""
        for _ in range(3):
            self.assertEqual(self._subir().status_code, 201)
        r = self._subir()
        self.assertEqual(r.status_code, 400)
        self.assertIn('3', r.data['error'])
        self.assertEqual(StoreBanner.objects.filter(store=self.loja).count(), 3)

    def test_sem_arquivo_e_recusado(self):
        self.assertEqual(self.client.post(self.url, {}, format='multipart').status_code, 400)

    def test_o_catalogo_devolve_os_banners_na_ordem(self):
        for _ in range(2):
            self._subir()
        dados = StoreSerializer(self.loja).data
        self.assertEqual([b['position'] for b in dados['banners']], [0, 1])
        self.assertTrue(all(b['url'] for b in dados['banners']))

    def test_apagar_reenumera_sem_buraco(self):
        ids = [self._subir().data['id'] for _ in range(3)]
        r = self.client.delete(f'{self.url}{ids[0]}/')
        self.assertEqual(r.status_code, 204)
        posicoes = list(StoreBanner.objects.filter(store=self.loja).values_list('position', flat=True))
        self.assertEqual(sorted(posicoes), [0, 1])

    def test_outra_loja_nao_mexe_nos_meus_banners(self):
        """Endpoint de loja sem checagem de dono é IDOR."""
        intruso = User.objects.create_user(username='i-ban', password='x', email='i-ban@real.com')
        self.client.force_authenticate(intruso)
        self.assertIn(self._subir().status_code, (403, 404))
