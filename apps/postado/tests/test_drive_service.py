from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.postado.services.drive_service import DriveService


class TestDriveService(TestCase):
    @patch('apps.postado.services.drive_service.build')
    @patch('apps.postado.services.drive_service.service_account')
    def test_create_client_folder(self, mock_sa, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files.return_value.create.return_value.execute.return_value = {
            'id': 'folder_abc123',
            'webViewLink': 'https://drive.google.com/folder/abc123'
        }
        mock_service.permissions.return_value.create.return_value.execute.return_value = {}
        mock_sa.Credentials.from_service_account_file.return_value = MagicMock()

        svc = DriveService()
        folder_id, url = svc.create_client_folder("Salão da Maria")
        self.assertEqual(folder_id, 'folder_abc123')
        self.assertIn('drive.google.com', url)

    @patch('apps.postado.services.drive_service.build')
    @patch('apps.postado.services.drive_service.service_account')
    def test_create_subfolder(self, mock_sa, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files.return_value.create.return_value.execute.return_value = {
            'id': 'subfolder_xyz'
        }
        mock_sa.Credentials.from_service_account_file.return_value = MagicMock()

        svc = DriveService()
        folder_id = svc.create_subfolder("feed", "parent_abc")
        self.assertEqual(folder_id, 'subfolder_xyz')

    @patch('apps.postado.services.drive_service.build')
    @patch('apps.postado.services.drive_service.service_account')
    def test_upload_image(self, mock_sa, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files.return_value.create.return_value.execute.return_value = {
            'id': 'file_xyz',
            'webViewLink': 'https://drive.google.com/file/xyz'
        }
        mock_sa.Credentials.from_service_account_file.return_value = MagicMock()

        svc = DriveService()
        file_id, url = svc.upload_image(b'\x89PNG', 'post_01.png', 'folder_abc123')
        self.assertEqual(file_id, 'file_xyz')
        self.assertIn('drive.google.com', url)

    @patch('apps.postado.services.drive_service.build')
    @patch('apps.postado.services.drive_service.service_account')
    def test_service_cached(self, mock_sa, mock_build):
        """_get_service() should only build once (lazy singleton)."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files.return_value.create.return_value.execute.return_value = {
            'id': 'f1', 'webViewLink': 'https://drive.google.com/f1'
        }
        mock_service.permissions.return_value.create.return_value.execute.return_value = {}
        mock_sa.Credentials.from_service_account_file.return_value = MagicMock()

        svc = DriveService()
        svc.create_client_folder("Biz A")
        svc.create_subfolder("feed", "parent")
        self.assertEqual(mock_build.call_count, 1)
