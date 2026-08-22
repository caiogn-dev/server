"""
Testes de regressão para os métodos de cooldown/anti-loop do SessionManager.

Cobre dois contratos críticos:
- `bump_address_attempts` / `clear_address_attempts`: anti-loop de geocode
  (após 2 falhas consecutivas, aceita o endereço como digitado sem travar o bot)
- `should_send_unknown_helper`: cooldown de 15 min para a mensagem "não entendi"
  (evita o bot disparar a mensagem de ajuda a cada mensagem não reconhecida)

Todos os testes são SimpleTestCase com mocks — sem PostgreSQL, Redis ou Docker.
"""
import sys
from datetime import datetime, timezone as dt_tz
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

# Stubs de deps transientes para permitir importar session_manager sem infra.
# Salvamos o estado atual, instalamos os stubs, primamos o cache do módulo e
# restauramos — assim os stubs não vazam para outros testes do processo.
_STUB_MODULES = [
    'langchain_core', 'langchain_core.messages', 'langchain_core.tools',
    'langchain_core.language_models', 'langchain_core.language_models.base',
    'langchain_core.runnables', 'langchain_core.output_parsers',
    'langchain_core.prompts', 'langchain_core.callbacks',
    'langchain_openai', 'langchain_anthropic',
    'apps.agents.services', 'apps.agents.services.langchain_service',
    'apps.automation.services.unified_service',
    'apps.automation.services.flow_executor',
    'apps.automation.services.unified_messaging',
    'apps.automation.services.automation_service',
]
_saved_modules = {m: sys.modules.get(m) for m in _STUB_MODULES}
for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
try:
    import apps.automation.services.session_manager  # prime o cache antes de restaurar
finally:
    for _mod, _val in _saved_modules.items():
        if _val is None:
            sys.modules.pop(_mod, None)
        else:
            sys.modules[_mod] = _val

# Sentinel para distinguir "não passou cart_data" de "passou explicitamente None".
_MISSING = object()


def _make_session(cart_data=_MISSING):
    """Retorna um mock de CustomerSession com cart_data controlável.

    Sem argumento → cart_data={}.  cart_data=None → valor None real no mock,
    exercitando o branch `session.cart_data or {}` dos métodos testados.
    """
    session = MagicMock()
    session.cart_data = {} if cart_data is _MISSING else cart_data
    session.save = MagicMock()
    return session


def _make_manager(session=None):
    """Retorna um SessionManager com get_or_create_session mockado."""
    from apps.automation.services.session_manager import SessionManager
    mgr = object.__new__(SessionManager)
    mgr._session = None
    mgr._context = None
    mgr.phone_number = '11999990000'
    mgr.phone_number_variants = ['11999990000']
    mgr.company = MagicMock()
    mgr.account = MagicMock()
    mgr.store = MagicMock()
    mgr.get_or_create_session = MagicMock(return_value=session)
    return mgr


class TestBumpAddressAttempts(SimpleTestCase):
    """bump_address_attempts conta falhas consecutivas de geocode."""

    def test_primeira_falha_retorna_1(self):
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        result = mgr.bump_address_attempts()
        self.assertEqual(result, 1)

    def test_segunda_falha_retorna_2(self):
        session = _make_session(cart_data={'address_attempts': 1})
        mgr = _make_manager(session)
        result = mgr.bump_address_attempts()
        self.assertEqual(result, 2)

    def test_valor_persiste_em_cart_data(self):
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        mgr.bump_address_attempts()
        self.assertEqual(session.cart_data['address_attempts'], 1)

    def test_session_save_chamado(self):
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        mgr.bump_address_attempts()
        session.save.assert_called_once()

    def test_cart_data_none_trata_como_vazio(self):
        session = _make_session(cart_data=None)
        mgr = _make_manager(session)
        result = mgr.bump_address_attempts()
        self.assertEqual(result, 1)

    def test_sem_sessao_retorna_zero(self):
        mgr = _make_manager(session=None)
        result = mgr.bump_address_attempts()
        self.assertEqual(result, 0)

    def test_atingir_limiar_2_acumula_corretamente(self):
        """Ao atingir 2 tentativas, o anti-loop deve aceitar o endereço."""
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        mgr.bump_address_attempts()  # 1
        result = mgr.bump_address_attempts()  # 2
        self.assertGreaterEqual(result, 2)


class TestClearAddressAttempts(SimpleTestCase):
    """clear_address_attempts remove o contador depois do geocode bem-sucedido."""

    def test_remove_address_attempts(self):
        session = _make_session(cart_data={'address_attempts': 2})
        mgr = _make_manager(session)
        mgr.clear_address_attempts()
        self.assertNotIn('address_attempts', session.cart_data)

    def test_sem_attempts_nao_lanca(self):
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        mgr.clear_address_attempts()  # não deve levantar

    def test_sem_sessao_nao_lanca(self):
        mgr = _make_manager(session=None)
        mgr.clear_address_attempts()  # não deve levantar

    def test_outros_campos_preservados(self):
        session = _make_session(cart_data={'address_attempts': 1, 'outro': 'valor'})
        mgr = _make_manager(session)
        mgr.clear_address_attempts()
        self.assertEqual(session.cart_data.get('outro'), 'valor')


class TestShouldSendUnknownHelper(SimpleTestCase):
    """should_send_unknown_helper aplica cooldown de 15 min para mensagem de ajuda."""

    def _now_iso(self, delta_seconds=0):
        from django.utils import timezone
        return (timezone.now().replace(tzinfo=dt_tz.utc) if timezone.now().tzinfo is None
                else timezone.now()).isoformat()

    def test_primeira_mensagem_retorna_true(self):
        session = _make_session(cart_data={})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)
            result = mgr.should_send_unknown_helper()
        self.assertTrue(result)

    def test_dentro_do_cooldown_retorna_false(self):
        """Segunda mensagem dentro de 900s retorna False (silêncio do bot)."""
        from django.utils import timezone
        t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)
        t1 = datetime(2026, 8, 22, 12, 10, 0, tzinfo=dt_tz.utc)  # +10 min < 15 min
        session = _make_session(cart_data={'unknown_helper_at': t0.isoformat()})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now', return_value=t1):
            result = mgr.should_send_unknown_helper(cooldown_seconds=900)
        self.assertFalse(result)

    def test_apos_cooldown_retorna_true(self):
        """Após 15 min expirado, o bot pode enviar a mensagem novamente."""
        t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)
        t1 = datetime(2026, 8, 22, 12, 16, 0, tzinfo=dt_tz.utc)  # +16 min > 15 min
        session = _make_session(cart_data={'unknown_helper_at': t0.isoformat()})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now', return_value=t1):
            result = mgr.should_send_unknown_helper(cooldown_seconds=900)
        self.assertTrue(result)

    def test_timestamp_atualizado_apos_envio(self):
        """Quando retorna True, persiste o novo timestamp em cart_data."""
        t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)
        t1 = datetime(2026, 8, 22, 12, 20, 0, tzinfo=dt_tz.utc)  # após cooldown
        session = _make_session(cart_data={'unknown_helper_at': t0.isoformat()})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now', return_value=t1):
            mgr.should_send_unknown_helper(cooldown_seconds=900)
        stored = session.cart_data.get('unknown_helper_at', '')
        self.assertIn('12:20', stored)

    def test_sem_sessao_retorna_true_fail_open(self):
        """Sem sessão disponível, permite envio (fail-open) para não silenciar indefinidamente."""
        mgr = _make_manager(session=None)
        result = mgr.should_send_unknown_helper()
        self.assertTrue(result)

    def test_timestamp_corrompido_tratado_sem_excecao(self):
        """Valor inválido em unknown_helper_at não deve levantar — trata como ausente."""
        session = _make_session(cart_data={'unknown_helper_at': 'INVALIDO'})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now',
                   return_value=datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)):
            result = mgr.should_send_unknown_helper()
        self.assertTrue(result)

    def test_cooldown_customizado_respeitado(self):
        """Parâmetro cooldown_seconds é respeitado (permite teste com cooldown curto)."""
        t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=dt_tz.utc)
        t1 = datetime(2026, 8, 22, 12, 0, 30, tzinfo=dt_tz.utc)  # +30s
        session = _make_session(cart_data={'unknown_helper_at': t0.isoformat()})
        mgr = _make_manager(session)
        with patch('django.utils.timezone.now', return_value=t1):
            dentro = mgr.should_send_unknown_helper(cooldown_seconds=60)
            self.assertFalse(dentro)
        t2 = datetime(2026, 8, 22, 12, 1, 5, tzinfo=dt_tz.utc)  # +65s > 60s
        session2 = _make_session(cart_data={'unknown_helper_at': t0.isoformat()})
        mgr2 = _make_manager(session2)
        with patch('django.utils.timezone.now', return_value=t2):
            fora = mgr2.should_send_unknown_helper(cooldown_seconds=60)
            self.assertTrue(fora)
