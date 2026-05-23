from unittest.mock import patch, MagicMock
from django.test import TestCase
from PIL import Image
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost
from apps.postado.tasks import generate_pack


class TestGeneratePackTask(TestCase):
    def setUp(self):
        self.client_obj = PostadoClient.objects.create(
            business_name="Test Restaurant",
            niche=PostadoClient.Niche.RESTAURANT,
            tone=PostadoClient.Tone.CASUAL,
            email="task@test.com",
            whatsapp="61900000002",
        )
        self.pack = PostadoPack.objects.create(
            client=self.client_obj, month="2026-06"
        )

    @patch('apps.postado.tasks.DriveService')
    @patch('apps.postado.tasks.ImageService')
    @patch('apps.postado.tasks.CopyService')
    def test_generate_pack_creates_12_posts(self, mock_copy_cls, mock_img_cls, mock_drive_cls):
        mock_copy = MagicMock()
        mock_copy_cls.return_value = mock_copy
        mock_copy.generate.return_value = {
            'caption': 'Test caption',
            'cta': 'Peça já',
            'hashtags': '#test',
        }

        mock_img = MagicMock()
        mock_img_cls.return_value = mock_img
        mock_img.generate_base_image.return_value = Image.new('RGB', (1080, 1080))
        mock_img.composite_feed.return_value = Image.new('RGB', (1080, 1080))
        mock_img.to_stories.return_value = Image.new('RGB', (1080, 1920))
        mock_img.save_to_bytes.return_value = b'PNG_DATA'

        mock_drive = MagicMock()
        mock_drive_cls.return_value = mock_drive
        mock_drive.create_client_folder.return_value = ('folder_id', 'https://drive.google.com/folder')
        mock_drive.create_subfolder.return_value = 'subfolder_id'
        mock_drive.upload_image.return_value = ('file_id', 'https://drive.google.com/file')

        generate_pack(str(self.pack.id))

        self.pack.refresh_from_db()
        self.assertEqual(self.pack.status, PostadoPack.Status.REVIEW)
        self.assertEqual(self.pack.posts.count(), 12)
        self.assertTrue(all(
            p.status == PostadoPost.Status.GENERATED
            for p in self.pack.posts.all()
        ))

    @patch('apps.postado.tasks.DriveService')
    @patch('apps.postado.tasks.ImageService')
    @patch('apps.postado.tasks.CopyService')
    def test_generate_pack_sets_generating_then_review(self, mock_copy_cls, mock_img_cls, mock_drive_cls):
        statuses = []

        original_save = PostadoPack.save
        def track_save(instance, *args, **kwargs):
            statuses.append(instance.status)
            original_save(instance, *args, **kwargs)

        mock_copy_cls.return_value.generate.return_value = {'caption': '', 'cta': '', 'hashtags': ''}
        mock_img_cls.return_value.generate_base_image.return_value = Image.new('RGB', (1080, 1080))
        mock_img_cls.return_value.composite_feed.return_value = Image.new('RGB', (1080, 1080))
        mock_img_cls.return_value.to_stories.return_value = Image.new('RGB', (1080, 1920))
        mock_img_cls.return_value.save_to_bytes.return_value = b'PNG'
        mock_drive_cls.return_value.create_client_folder.return_value = ('fid', '')
        mock_drive_cls.return_value.create_subfolder.return_value = 'sfid'
        mock_drive_cls.return_value.upload_image.return_value = ('fid', '')

        with patch.object(PostadoPack, 'save', track_save):
            generate_pack(str(self.pack.id))

        self.assertIn(PostadoPack.Status.GENERATING, statuses)
        self.assertIn(PostadoPack.Status.REVIEW, statuses)

    def test_generate_pack_nonexistent_pack(self):
        import uuid
        # Should not raise, just log error
        generate_pack(str(uuid.uuid4()))
