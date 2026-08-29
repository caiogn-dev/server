"""
Regression tests — EmbeddedSignupError não deve vazar dados internos da Meta API.

Cobre:
- exchange_code() não inclui dict cru de `data` na mensagem da exceção
- View embedded_signup retorna mensagem genérica (não str(exc)) para EmbeddedSignupError
- View embedded_signup retorna mensagem genérica para Exception genérica

Abordagem: SimpleTestCase (sem banco) com mocks; valida via análise do código-fonte
para padrões inseguros e via comportamento do serviço isolado.
"""
import ast
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class EmbeddedSignupServiceCodeAnalysisTest(unittest.TestCase):
    """Análise estática do código do serviço e da view — detecta padrões de info-disclosure."""

    SERVICE_PATH = os.path.join(
        os.path.dirname(__file__),
        '..', 'services', 'embedded_signup_service.py',
    )
    VIEW_PATH = os.path.join(
        os.path.dirname(__file__),
        '..', 'api', 'views.py',
    )

    def _read_source(self, path):
        with open(os.path.normpath(path)) as f:
            return f.read()

    # ------------------------------------------------------------------ service
    def test_service_exchange_code_does_not_embed_raw_data_in_exception(self):
        """A mensagem de EmbeddedSignupError não deve conter `data` diretamente."""
        src = self._read_source(self.SERVICE_PATH)
        tree = ast.parse(src)

        # Encontra todos os `raise EmbeddedSignupError(...)` dentro de exchange_code
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != 'exchange_code':
                continue
            for child in ast.walk(node):
                if not (isinstance(child, ast.Raise) and child.exc is not None):
                    continue
                exc = child.exc
                # Verifica se o argumento da exceção inclui `data` ou `data.get(...)` diretamente
                exc_src = ast.unparse(exc)
                self.assertNotIn("data.get('error', data)", exc_src,
                    "exchange_code não deve incluir data.get('error', data) na mensagem da exceção "
                    "— isso vaza o dict cru da API Meta para o cliente HTTP")
                self.assertNotIn('{data}', exc_src,
                    "exchange_code não deve interpolar {data} na f-string da exceção")

    def test_view_embedded_signup_error_handler_does_not_use_str_exc(self):
        """O handler de EmbeddedSignupError na view não deve usar str(exc) no response."""
        src = self._read_source(self.VIEW_PATH)
        tree = ast.parse(src)

        # Encontra todos os `except EmbeddedSignupError` e verifica o corpo
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ExceptHandler,)):
                continue
            if node.type is None:
                continue
            type_src = ast.unparse(node.type)
            if 'EmbeddedSignupError' not in type_src:
                continue

            # Inspeciona o corpo do handler
            handler_src = ast.unparse(node)
            # str(exc) ou str(e) como valor de 'error' no response
            self.assertNotRegex(
                handler_src,
                r"str\s*\(\s*(exc|e)\s*\)",
                "handler de EmbeddedSignupError na view não deve retornar str(exc) — "
                "a mensagem da exceção pode conter dados internos da Meta API"
            )

    def test_view_generic_exception_handler_does_not_use_fstring_exc(self):
        """O handler de Exception genérica não deve interpolar {exc} ou {e} no response."""
        src = self._read_source(self.VIEW_PATH)

        # Verifica o padrão antigo que vaza: f'Falha no onboarding: {exc}'
        self.assertNotIn(
            "f'Falha no onboarding: {exc}'", src,
            "handler de Exception genérica não deve interpolar {exc} na f-string do response"
        )
        self.assertNotIn(
            'f"Falha no onboarding: {exc}"', src,
            "handler de Exception genérica não deve interpolar {exc} na f-string do response"
        )


class EmbeddedSignupServiceBehaviorTest(unittest.TestCase):
    """Testes comportamentais do serviço (sem DB, sem app registry)."""

    SERVICE_FILE = os.path.join(
        os.path.dirname(__file__),
        '..', 'services', 'embedded_signup_service.py',
    )

    @classmethod
    def _load_service_module(cls):
        """Importa o módulo do serviço diretamente por caminho, evitando o __init__ do pacote."""
        import importlib.util
        # Configura settings mínimos para que `from django.conf import settings` funcione
        from django.conf import settings
        if not settings.configured:
            import django
            settings.configure(
                SECRET_KEY='test-key-behavior',
                WHATSAPP_API_BASE_URL='https://graph.facebook.com/v19.0',
                META_APP_ID='test-app-id',
                META_APP_SECRET='test-secret',
                DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
                INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'],
                USE_TZ=True,
            )
            django.setup()

        mod_name = 'embedded_signup_service_behavior'
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(
            mod_name,
            os.path.normpath(cls.SERVICE_FILE),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _make_service(self):
        mod = self._load_service_module()
        svc = object.__new__(mod.EmbeddedSignupService)
        svc.base = 'https://graph.facebook.com/v19.0'
        svc.app_id = 'test-app-id'
        svc.app_secret = 'test-secret'
        return svc

    def _patch_get(self, response_json):
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_json
        return patch('embedded_signup_service_behavior.requests.get',
                     return_value=mock_resp)

    def _get_exception_class(self):
        return self._load_service_module().EmbeddedSignupError

    def test_raises_on_missing_access_token(self):
        """exchange_code levanta EmbeddedSignupError quando access_token ausente."""
        EmbeddedSignupError = self._get_exception_class()
        meta_error = {
            'error': {
                'message': 'Invalid OAuth access token.',
                'type': 'OAuthException',
                'code': 190,
                'fbtrace_id': 'AaBbCcDdEeFfSensitiveId',
                'error_subcode': 460,
            }
        }
        svc = self._make_service()
        with self._patch_get(meta_error):
            with self.assertRaises(EmbeddedSignupError) as ctx:
                svc.exchange_code('bad-code')

        err_msg = str(ctx.exception)
        self.assertNotIn('fbtrace_id', err_msg,
                         'fbtrace_id não deve aparecer na mensagem da exceção')
        self.assertNotIn('AaBbCcDdEeFfSensitiveId', err_msg,
                         'trace id concreto não deve aparecer na mensagem da exceção')
        self.assertNotIn('OAuthException', err_msg,
                         'tipo interno OAuth não deve aparecer na mensagem da exceção')
        self.assertNotIn('460', err_msg,
                         'error_subcode não deve aparecer na mensagem da exceção')
        # Mensagem genérica ainda deve indicar o que falhou
        self.assertIn('token', err_msg.lower(),
                      'mensagem deve mencionar "token" para ser útil em logs')

    def test_raises_without_leaking_raw_dict_when_no_error_key(self):
        """Quando resposta não tem chave 'error', o dict cru não vaza na exceção."""
        EmbeddedSignupError = self._get_exception_class()
        malformed = {'unexpected_key': 'unexpected_value', 'internal': 'data'}
        svc = self._make_service()
        with self._patch_get(malformed):
            with self.assertRaises(EmbeddedSignupError) as ctx:
                svc.exchange_code('code')

        err_msg = str(ctx.exception)
        self.assertNotIn('unexpected_key', err_msg,
                         'chave de dict interno não deve aparecer na exceção')
        self.assertNotIn('unexpected_value', err_msg,
                         'valor de dict interno não deve aparecer na exceção')
