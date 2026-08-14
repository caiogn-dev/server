"""A conversa pertence à loja pela CONTA, não por um campo `store`.

Reportado pelo dono em 14/ago: `{"ok":false,"texto":"Conversa não pertence a
esta loja."}` numa conversa que pertencia. Todo comando "/" devolvia 403.

A causa: `Conversation` NÃO tem campo `store`. A view fazia
`getattr(conversa, 'store', None)`, recebia None e negava — e como o `getattr`
tem default, não houve exceção nenhuma para denunciar o erro. Falha silenciosa
que só aparece como "não pertence" para quem é dono.

O caminho real é o mesmo que os handlers do bot já usavam:
conversa → account → company_profile → store.
"""
import pytest


@pytest.mark.django_db
class TestOCaminhoDaLoja:
    def test_Conversation_NAO_tem_campo_store(self):
        """A premissa errada, travada — se um dia ganhar `store`, este teste avisa."""
        from apps.conversations.models import Conversation

        assert not any(f.name == 'store' for f in Conversation._meta.fields)

    def test_a_loja_vem_pela_conta(self, django_user_model):
        from unittest.mock import MagicMock

        from apps.stores.tests.factories import make_store
        from apps.whatsapp.api.comando_views import ExecutarComandoView

        loja = make_store(name='Cê Saladas')
        conversa = MagicMock()
        conversa.account.company_profile.store = loja

        achada = ExecutarComandoView._loja_do_usuario(loja.owner, conversa)

        assert achada == loja

    def test_quem_nao_e_da_loja_e_barrado(self, django_user_model):
        from unittest.mock import MagicMock

        from apps.stores.tests.factories import make_store
        from apps.whatsapp.api.comando_views import ExecutarComandoView

        loja = make_store(name='Cê Saladas')
        estranho = django_user_model.objects.create_user(username='xereta', password='x')
        conversa = MagicMock()
        conversa.account.company_profile.store = loja

        assert ExecutarComandoView._loja_do_usuario(estranho, conversa) is None

    def test_conversa_sem_perfil_nao_estoura(self):
        from unittest.mock import MagicMock

        from apps.whatsapp.api.comando_views import ExecutarComandoView

        conversa = MagicMock()
        conversa.account.company_profile = None

        assert ExecutarComandoView._loja_do_usuario(MagicMock(), conversa) is None

    def test_conversa_sem_conta_nao_estoura(self):
        from apps.whatsapp.api.comando_views import ExecutarComandoView

        assert ExecutarComandoView._loja_do_usuario(None, object()) is None
