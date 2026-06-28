"""
Testes TDD para ExportViewSet — garante isolamento de tenant e ausência do NameError
histórico (_accessible_accounts não importada).

Sem dependência de Celery/Redis; usa mocks para o banco e serviços externos.
"""
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()


class ExportViewConversationsTest(TestCase):
    """
    Verifica que o branch 'conversations' do ExportViewSet usa
    accessible_whatsapp_account_ids e NÃO chama _accessible_accounts
    (que não existe no módulo e causava NameError em produção).
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User(id=1, username='testuser')
        self.user.is_superuser = False

    @patch('apps.audit.api.views.ExportService')
    @patch('apps.audit.api.views.AuditService')
    @patch('apps.audit.api.views.Conversation')
    @patch('apps.audit.api.views.accessible_whatsapp_account_ids')
    def test_conversations_export_usa_accessible_whatsapp_account_ids(
        self, mock_accessible, mock_conv_model, mock_audit_svc, mock_export_svc
    ):
        """
        O branch 'conversations' deve usar accessible_whatsapp_account_ids(user)
        e escopar o queryset por ela — isolamento cross-tenant garantido.
        """
        from apps.audit.api.views import ExportViewSet
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request

        mock_accessible.return_value = [10, 20]

        fake_qs = MagicMock()
        fake_qs.filter.return_value = fake_qs
        fake_qs.count.return_value = 5
        mock_conv_model.objects.filter.return_value = fake_qs

        mock_response = MagicMock()
        mock_export_svc.return_value.export_conversations.return_value = mock_response
        mock_audit_svc.return_value.log_export.return_value = None

        rf = APIRequestFactory()
        raw_request = rf.post(
            '/audit/export/',
            data={'export_type': 'conversations', 'export_format': 'csv'},
            format='json',
        )
        raw_request.user = self.user

        view = ExportViewSet.as_view({'post': 'export'})

        with patch('apps.audit.api.views.ExportRequestSerializer') as mock_ser_cls:
            mock_ser = MagicMock()
            mock_ser.is_valid.return_value = True
            mock_ser.validated_data = {
                'export_type': 'conversations',
                'export_format': 'csv',
                'filters': {},
            }
            mock_ser_cls.return_value = mock_ser

            response = view(raw_request)

        # accessible_whatsapp_account_ids deve ter sido chamada com o user correto
        mock_accessible.assert_called_once_with(self.user)

        # Conversation.objects.filter deve escopar por account_id__in=[10, 20]
        mock_conv_model.objects.filter.assert_called_once_with(
            is_active=True, account_id__in=[10, 20]
        )

    @patch('apps.audit.api.views.ExportService')
    @patch('apps.audit.api.views.AuditService')
    @patch('apps.audit.api.views.StoreOrder')
    @patch('apps.audit.api.views.accessible_store_ids')
    def test_orders_export_usa_accessible_store_ids(
        self, mock_accessible, mock_order_model, mock_audit_svc, mock_export_svc
    ):
        """
        O branch 'orders' deve usar accessible_store_ids(user) — regressão não-introduzida.
        """
        from apps.audit.api.views import ExportViewSet
        from rest_framework.test import APIRequestFactory

        mock_accessible.return_value = [1, 2]

        fake_qs = MagicMock()
        fake_qs.filter.return_value = fake_qs
        fake_qs.count.return_value = 3
        mock_order_model.objects.filter.return_value = fake_qs

        mock_response = MagicMock()
        mock_export_svc.return_value.export_orders.return_value = mock_response
        mock_audit_svc.return_value.log_export.return_value = None

        rf = APIRequestFactory()
        raw_request = rf.post(
            '/audit/export/',
            data={'export_type': 'orders', 'export_format': 'csv'},
            format='json',
        )
        raw_request.user = self.user

        view = ExportViewSet.as_view({'post': 'export'})

        with patch('apps.audit.api.views.ExportRequestSerializer') as mock_ser_cls:
            mock_ser = MagicMock()
            mock_ser.is_valid.return_value = True
            mock_ser.validated_data = {
                'export_type': 'orders',
                'export_format': 'csv',
                'filters': {},
            }
            mock_ser_cls.return_value = mock_ser

            response = view(raw_request)

        mock_accessible.assert_called_once_with(self.user)
        mock_order_model.objects.filter.assert_called_once_with(
            is_active=True, store_id__in=[1, 2]
        )

    def test_accessible_whatsapp_account_ids_importado_no_modulo(self):
        """
        Garante que accessible_whatsapp_account_ids está de fato importado em
        apps.audit.api.views — evita regressão se alguém remover o import.
        """
        import apps.audit.api.views as views_mod
        self.assertTrue(
            hasattr(views_mod, 'accessible_whatsapp_account_ids'),
            "accessible_whatsapp_account_ids deve ser importado em apps/audit/api/views.py",
        )

    def test_accessible_accounts_local_nao_existe_no_modulo(self):
        """
        _accessible_accounts NÃO deve existir no módulo de views do audit.
        Se existir, pode mascarar um problema de escopo de tenant.
        """
        import apps.audit.api.views as views_mod
        self.assertFalse(
            hasattr(views_mod, '_accessible_accounts'),
            "_accessible_accounts não deve estar definida/importada em apps/audit/api/views.py",
        )
