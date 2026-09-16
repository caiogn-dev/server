"""Regressão de segurança: extensão de arquivo em upload_media deve vir do MIME, não do nome do arquivo.

Antes do fix, documentos usavam `os.path.splitext(file_obj.name)[1]` — um cliente
autenticado poderia enviar Content-Type: application/pdf com filename='shell.php'
e o arquivo seria salvo como <uuid>.php no storage.
"""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import SimpleTestCase

try:
    from apps.campaigns.api.views import CampaignViewSet
    _CAMPAIGNS_IMPORTABLE = True
except ImportError:
    CampaignViewSet = None
    _CAMPAIGNS_IMPORTABLE = False


@unittest.skipUnless(_CAMPAIGNS_IMPORTABLE, "campaigns não importável (deps IA ausentes)")
class UploadMediaExtensionTest(SimpleTestCase):
    """A extensão salva no storage deve ser determinada pelo MIME, nunca pelo nome do arquivo."""

    def _make_view(self):
        view = CampaignViewSet()
        view.format_kwarg = None
        return view

    def _make_request(self, content_type, filename, content=b'data'):
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth import get_user_model

        factory = APIRequestFactory()
        file_mock = MagicMock()
        file_mock.content_type = content_type
        file_mock.name = filename
        file_mock.read.return_value = content
        file_mock.size = len(content)
        file_mock.seek = MagicMock()

        request = factory.post('/upload-media/', {'file': file_mock}, format='multipart')
        User = get_user_model()
        user = MagicMock(spec=User)
        user.is_authenticated = True
        request.user = user
        return request, file_mock

    def _call_upload(self, content_type, filename, saved_paths):
        """Chama upload_media e coleta o caminho salvo via mock de default_storage."""
        request, file_mock = self._make_request(content_type, filename)

        with patch('apps.campaigns.api.views.default_storage') as mock_storage, \
             patch('apps.campaigns.api.views.build_absolute_media_url', return_value='http://x/f'):
            mock_storage.save.side_effect = lambda path, f: saved_paths.append(path) or path
            mock_storage.url.return_value = '/media/f'

            from rest_framework.test import force_authenticate
            view = CampaignViewSet.as_view({'post': 'upload_media'})

            from django.test import RequestFactory
            from rest_framework.request import Request
            from rest_framework.parsers import MultiPartParser, FormParser

            # Monta DRF request manualmente
            drf_request = MagicMock()
            drf_request.FILES = {'file': file_mock}
            drf_request.user = request.user
            drf_request.data = {}

            instance = self._make_view()
            instance.request = drf_request
            instance.kwargs = {}
            instance.args = ()

            response = instance.upload_media(drf_request)
        return response, saved_paths

    def test_jpeg_extension_from_mime(self):
        """image/jpeg → .jpg independente do nome."""
        paths = []
        resp, paths = self._call_upload('image/jpeg', 'photo.JPEG', paths)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(paths[0].endswith('.jpg'), f"Esperado .jpg, obtido: {paths[0]}")

    def test_png_extension_from_mime(self):
        """image/png → .png independente do nome."""
        paths = []
        resp, paths = self._call_upload('image/png', 'image.png', paths)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(paths[0].endswith('.png'), f"Esperado .png, obtido: {paths[0]}")

    def test_pdf_extension_from_mime_not_filename(self):
        """application/pdf → .pdf MESMO QUE o nome seja shell.php."""
        paths = []
        resp, paths = self._call_upload('application/pdf', 'shell.php', paths)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(
            paths[0].endswith('.php'),
            f"Vulnerabilidade presente: arquivo salvo como {paths[0]}"
        )
        self.assertTrue(paths[0].endswith('.pdf'), f"Esperado .pdf, obtido: {paths[0]}")

    def test_pptx_extension_from_mime(self):
        """application/vnd...presentationml.presentation → .pptx."""
        paths = []
        resp, paths = self._call_upload(
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'slides.pptx',
            paths,
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(paths[0].endswith('.pptx'), f"Esperado .pptx, obtido: {paths[0]}")

    def test_unsupported_application_mime_is_rejected(self):
        """application/octet-stream e outros fora da whitelist devem retornar 400."""
        paths = []
        resp, paths = self._call_upload('application/octet-stream', 'evil.exe', paths)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(len(paths), 0, "Arquivo não deveria ter sido salvo")
