"""O UnifiedService precisa ter o próprio `_get_session_manager`.

A montagem de combo e o "pôr no carrinho" chamam `self._get_session_manager()`
— método que só existia nos handlers. Os testes do combo substituíam o método
por um MagicMock no objeto, então passavam; em produção cada mensagem durante
a montagem levantava AttributeError, o `except` engolia, e o combo por texto
nunca funcionou (15 falhas em 24h medidas em 23/09).

Este teste NÃO mocka o método: cobra que ele exista na classe e resolva a
sessão pelo mesmo dono que os handlers usam (perfil > loja > conta).
"""
from unittest.mock import MagicMock, patch

from apps.automation.services.unified_service import UnifiedService


def _servico(company=None, store=None):
    s = UnifiedService.__new__(UnifiedService)
    s.company = company
    s.store = store
    s.account = MagicMock(name='conta')
    s.conversation = MagicMock(phone_number='5563999990000')
    return s


def test_metodo_existe_na_classe():
    assert callable(getattr(UnifiedService, '_get_session_manager', None))


def test_usa_o_perfil_quando_existe():
    perfil = MagicMock(name='perfil')
    s = _servico(company=perfil, store=MagicMock(name='loja'))
    with patch('apps.automation.services.get_session_manager') as gsm:
        s._get_session_manager()
    gsm.assert_called_once_with(perfil, '5563999990000')


def test_cai_para_loja_e_depois_conta():
    loja = MagicMock(name='loja')
    s = _servico(store=loja)
    with patch('apps.automation.services.get_session_manager') as gsm:
        s._get_session_manager()
    gsm.assert_called_once_with(loja, '5563999990000')

    s = _servico()
    with patch('apps.automation.services.get_session_manager') as gsm:
        s._get_session_manager()
    gsm.assert_called_once_with(s.account, '5563999990000')
