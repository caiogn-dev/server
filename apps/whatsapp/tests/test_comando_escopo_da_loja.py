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
from unittest.mock import patch

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

    def test_membro_da_equipe_PODE_agir(self):
        """Segunda causa do 403 em produção: a regra caseira só olhava owner.

        Existem dois usuários com o mesmo e-mail — `graccius` (id 1) e `graco`
        (id 14). A loja pertence a um, a sessão do painel é do outro, e a
        checagem à mão negava. `user_can_access_store` é a regra que o resto do
        painel usa para listar pedidos e produtos.
        """
        from unittest.mock import MagicMock

        from apps.stores.tests.factories import make_store
        from apps.whatsapp.api.comando_views import ExecutarComandoView

        loja = make_store(name='Cê Saladas')
        conversa = MagicMock()
        conversa.account.company_profile.store = loja

        with patch(
            'apps.core.permissions.user_can_access_store', return_value=True,
        ):
            assert ExecutarComandoView._loja_do_usuario(MagicMock(), conversa) == loja

    def test_usa_a_regra_canonica_e_nao_uma_propria(self):
        """Trava contra escrever a QUARTA versão da regra de acesso."""
        import inspect

        from apps.whatsapp.api import comando_views

        fonte = inspect.getsource(comando_views.ExecutarComandoView._loja_do_usuario)
        assert 'user_can_access_store' in fonte
        assert 'StoreTeamMember.objects' not in fonte, 'voltou a checar permissão à mão'

    def test_conversa_sem_perfil_nao_estoura(self):
        from unittest.mock import MagicMock

        from apps.whatsapp.api.comando_views import ExecutarComandoView

        conversa = MagicMock()
        conversa.account.company_profile = None

        assert ExecutarComandoView._loja_do_usuario(MagicMock(), conversa) is None

    def test_conversa_sem_conta_nao_estoura(self):
        from apps.whatsapp.api.comando_views import ExecutarComandoView

        assert ExecutarComandoView._loja_do_usuario(None, object()) is None
