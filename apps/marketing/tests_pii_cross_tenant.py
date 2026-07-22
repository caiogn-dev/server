"""Regressão de segurança: PII cross-tenant em TemplateVariablesViewSet [P0].

Antes do fix:
- preview: User.objects.filter(email=...) sem filtro de tenant → qualquer autenticado
  obtinha nome/email/telefone de cliente alheio passando customer_email.
  Subscriber.objects.filter(email=...) sem store_id também vazava dados cross-tenant.
- sample_customer: User.objects.filter(is_active=True, ...).first() sem escopo de loja
  → retornava nome/email/telefone real do primeiro usuário do banco global.

Fix: preview só usa dados reais de Subscriber.filter(email=..., store_id=store_id)
— sem store_id nenhuma consulta real é feita. sample_customer remove o
User.objects global e depende apenas de Subscriber escopado por store_id.

Técnica: SimpleTestCase + mocks. Sem Docker/PostgreSQL.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

_SETTINGS = dict(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (),
        'DEFAULT_PERMISSION_CLASSES': (),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
)

factory = APIRequestFactory()

_VIEW_MODULE = 'apps.marketing.api.views'


def _user():
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = False
    u.is_staff = False
    return u


def _fake_subscriber(name='João Silva', email='joao@loja.com', phone='11999990000'):
    s = MagicMock()
    s.name = name
    s.email = email
    s.phone = phone
    return s


def _mock_subscriber_qs(subscriber):
    """Return a mock that mimics Subscriber.objects.filter(...).first() → subscriber."""
    mock_qs = MagicMock()
    mock_qs.first.return_value = subscriber
    return mock_qs


@override_settings(**_SETTINGS)
class PreviewCrossTenantPIITest(SimpleTestCase):
    """preview não deve vazar PII de tenants alheios via customer_email."""

    def _call(self, data, subscriber=None):
        from apps.marketing.api.views import TemplateVariablesViewSet
        req = factory.post('/preview/', data, format='json')
        req._force_auth_user = _user()
        view = TemplateVariablesViewSet.as_view({'post': 'preview'})

        fake_store = MagicMock()
        fake_store.name = 'Loja Teste'
        fake_store.website_url = None
        fake_store.slug = 'loja-teste'
        with patch(f'{_VIEW_MODULE}.Subscriber') as mock_sub, \
             patch('apps.stores.models.Store.objects') as mock_store_mgr:
            mock_sub.objects.filter.return_value = _mock_subscriber_qs(subscriber)
            mock_store_mgr.get.return_value = fake_store
            resp = view(req)
        return resp, mock_sub

    def test_sem_store_id_nao_consulta_subscriber(self):
        """Sem store_id, preview usa dados de exemplo sem tocar no banco."""
        resp, mock_sub = self._call({'html_content': '<p>{{customer_name}}</p>'})
        self.assertEqual(resp.status_code, 200)
        mock_sub.objects.filter.assert_not_called()

    def test_customer_email_sem_store_id_nao_vaza_pii(self):
        """customer_email sem store_id → dados de exemplo; sem consulta de subscriber."""
        resp, mock_sub = self._call(
            {'html_content': '<p>{{name}}</p>',
             'customer_email': 'vitima@outro-tenant.com'},
        )
        self.assertEqual(resp.status_code, 200)
        # Sem store_id não se pode escopar → não deve consultar banco
        mock_sub.objects.filter.assert_not_called()
        # Email da vítima não deve aparecer no resultado
        self.assertNotIn('vitima@outro-tenant.com', resp.data.get('preview_html', ''))
        self.assertNotIn('vitima@outro-tenant.com',
                         str(resp.data.get('variables_used', {})))

    def test_customer_email_com_store_id_consulta_subscriber_escopado(self):
        """customer_email + store_id busca subscriber filtrado por store_id."""
        sub = _fake_subscriber(name='Maria Souza', email='maria@loja.com')
        resp, mock_sub = self._call(
            {'html_content': '<p>{{customer_name}}</p>',
             'customer_email': 'maria@loja.com',
             'store': 'store-abc'},
            subscriber=sub,
        )
        self.assertEqual(resp.status_code, 200)
        mock_sub.objects.filter.assert_called_once()
        call_kwargs = mock_sub.objects.filter.call_args[1]
        self.assertIn('store_id', call_kwargs,
                      "filter() deve incluir store_id para evitar cross-tenant")
        self.assertEqual(call_kwargs.get('email'), 'maria@loja.com')

    def test_customer_email_com_store_id_subscriber_nao_encontrado_usa_padrao(self):
        """Subscriber não encontrado na loja → dados padrão, sem exceção."""
        resp, _ = self._call(
            {'html_content': '<p>{{first_name}}</p>',
             'customer_email': 'naoexiste@loja.com',
             'store': 'store-abc'},
            subscriber=None,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Cliente', resp.data.get('preview_html', ''))

    def test_nao_chama_user_objects_filter_global(self):
        """preview nunca deve chamar User.objects.filter() sem escopo de loja."""
        mock_user_model = MagicMock()
        with patch(f'{_VIEW_MODULE}.Subscriber') as mock_sub, \
             patch('apps.stores.models.Store.objects') as mock_store_mgr, \
             patch('django.contrib.auth.get_user_model', return_value=mock_user_model):
            fake_store = MagicMock(); fake_store.name = 'L'; fake_store.website_url = None; fake_store.slug = 's'
            mock_sub.objects.filter.return_value = _mock_subscriber_qs(None)
            mock_store_mgr.get.return_value = fake_store
            from apps.marketing.api.views import TemplateVariablesViewSet
            req = factory.post('/preview/',
                               {'html_content': '<p>x</p>',
                                'customer_email': 'qualquer@email.com',
                                'store': 'store-abc'},
                               format='json')
            req._force_auth_user = _user()
            view = TemplateVariablesViewSet.as_view({'post': 'preview'})
            view(req)
        mock_user_model.objects.filter.assert_not_called()


@override_settings(**_SETTINGS)
class SampleCustomerCrossTenantPIITest(SimpleTestCase):
    """sample_customer não deve retornar PII real sem escopo de loja."""

    def _call(self, store_id=None, subscriber=None):
        from apps.marketing.api.views import TemplateVariablesViewSet
        url = f'/sample-customer/?store={store_id}' if store_id else '/sample-customer/'
        req = factory.get(url)
        req._force_auth_user = _user()
        view = TemplateVariablesViewSet.as_view({'get': 'sample_customer'})

        mock_user_model = MagicMock()
        with patch(f'{_VIEW_MODULE}.Subscriber') as mock_sub, \
             patch('django.contrib.auth.get_user_model', return_value=mock_user_model):
            mock_sub.objects.filter.return_value = _mock_subscriber_qs(subscriber)
            resp = view(req)
        return resp, mock_user_model, mock_sub

    def test_sem_store_id_retorna_dados_exemplo(self):
        """Sem store_id retorna dados de exemplo estáticos, não dados reais."""
        resp, _, _ = self._call(store_id=None)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('email'), 'cliente@exemplo.com',
                         "Sem store_id deve retornar email de exemplo, não real")

    def test_sem_store_id_nao_consulta_user_objects(self):
        """Sem store_id, User.objects.filter() nunca deve ser chamado."""
        _, mock_user_model, _ = self._call(store_id=None)
        mock_user_model.objects.filter.assert_not_called()

    def test_sem_store_id_nao_consulta_subscriber(self):
        """Sem store_id, Subscriber.objects.filter() não deve ser chamado."""
        _, _, mock_sub = self._call(store_id=None)
        mock_sub.objects.filter.assert_not_called()

    def test_com_store_id_sem_subscriber_retorna_dados_exemplo(self):
        """store_id fornecido mas sem subscriber ativo → dados de exemplo."""
        resp, _, _ = self._call(store_id='store-xyz', subscriber=None)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('email'), 'cliente@exemplo.com')

    def test_com_store_id_com_subscriber_retorna_dados_escopados(self):
        """store_id fornecido com subscriber ativo → dados reais do subscriber."""
        sub = _fake_subscriber(name='Ana Lima', email='ana@loja.com', phone='11988887777')
        resp, _, _ = self._call(store_id='store-xyz', subscriber=sub)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('email'), 'ana@loja.com')
        self.assertEqual(resp.data.get('name'), 'Ana Lima')

    def test_nao_chama_user_objects_filter_global(self):
        """sample_customer nunca deve chamar User.objects.filter() sem escopo."""
        _, mock_user_model, _ = self._call(store_id='store-xyz', subscriber=None)
        mock_user_model.objects.filter.assert_not_called()
