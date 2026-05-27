from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost
import uuid


@override_settings(POSTADO_ADMIN_TOKEN='test-token-123')
class AdminAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_token_returns_401(self):
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer wrong-token')
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 401)

    def test_correct_token_returns_200(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token-123')
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 200)


@override_settings(POSTADO_ADMIN_TOKEN='test-token-123')
class AdminDashboardDataTest(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer test-token-123')
        self.postado_client = PostadoClient.objects.create(
            business_name='Test Restaurant', niche='restaurant', tone='casual',
            email='test@test.com', whatsapp='11999999999',
        )
        self.pack = PostadoPack.objects.create(
            client=self.postado_client, month='2025-06', status='review',
        )

    def test_dashboard_returns_kpis(self):
        response = self.api.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('total_clients', data)
        self.assertIn('active_clients', data)
        self.assertIn('packs_in_review', data)
        self.assertIn('packs_generating', data)
        self.assertIn('review_queue', data)
        self.assertEqual(data['packs_in_review'], 1)

    def test_dashboard_review_queue_has_pack(self):
        response = self.api.get('/api/postado/admin/dashboard/')
        data = response.json()
        self.assertEqual(len(data['review_queue']), 1)
        self.assertEqual(data['review_queue'][0]['month'], '2025-06')

    def test_client_list(self):
        response = self.api.get('/api/postado/admin/clients/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['business_name'], 'Test Restaurant')

    def test_client_detail(self):
        response = self.api.get(f'/api/postado/admin/clients/{self.postado_client.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['business_name'], 'Test Restaurant')
        self.assertIn('packs', data)

    def test_client_detail_404(self):
        response = self.api.get(f'/api/postado/admin/clients/{uuid.uuid4()}/')
        self.assertEqual(response.status_code, 404)


@override_settings(POSTADO_ADMIN_TOKEN='test-token-123')
class AdminPackPostActionsTest(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer test-token-123')
        self.postado_client = PostadoClient.objects.create(
            business_name='Test', niche='restaurant', tone='casual',
            email='action@test.com', whatsapp='11988888888',
        )
        self.pack = PostadoPack.objects.create(
            client=self.postado_client, month='2025-06', status='review',
        )
        self.post = PostadoPost.objects.create(
            pack=self.pack, post_number=1, post_type='promo',
            caption='Original caption', cta='Peça agora', status='generated',
        )

    def test_pack_detail_returns_posts(self):
        response = self.api.get(f'/api/postado/admin/packs/{self.pack.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['posts']), 1)
        self.assertEqual(data['posts'][0]['caption'], 'Original caption')

    def test_patch_post_updates_caption_and_cta(self):
        response = self.api.patch(
            f'/api/postado/admin/posts/{self.post.id}/',
            {'caption': 'Nova legenda', 'cta': 'Clique aqui'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.caption, 'Nova legenda')
        self.assertEqual(self.post.cta, 'Clique aqui')

    def test_approve_post(self):
        response = self.api.patch(
            f'/api/postado/admin/posts/{self.post.id}/',
            {'status': 'approved'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'approved')

    def test_reject_post_with_notes(self):
        response = self.api.patch(
            f'/api/postado/admin/posts/{self.post.id}/',
            {'status': 'rejected', 'revision_notes': 'Imagem ruim'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'rejected')
        self.assertEqual(self.post.revision_notes, 'Imagem ruim')

    def test_approve_pack(self):
        response = self.api.post(f'/api/postado/admin/packs/{self.pack.id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.pack.refresh_from_db()
        self.assertEqual(self.pack.status, 'approved')
        self.assertIsNotNone(self.pack.approved_at)

    @patch('apps.postado.tasks.regenerate_single_post')
    def test_regenerate_post_triggers_task(self, mock_task):
        response = self.api.post(f'/api/postado/admin/posts/{self.post.id}/regenerate/')
        self.assertEqual(response.status_code, 202)
        mock_task.delay.assert_called_once_with(str(self.post.id))
