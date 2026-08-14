"""O portão do checkout tem que usar o estado que ele já conhece.

`_estado_deve_capturar` sabe se o cliente está no estado de ENDEREÇO ou de
OBSERVAÇÃO — os dois métodos existem e são chamados na linha de cima. E mesmo
assim `triar()` era chamado sem `esperando`, jogando fora a informação que
evita o erro.

O erro concreto: no estado de observação, "Quero salada" virou
"✅ Anotado: Quero salada" e fechou um pedido de R$ 20 quando o real era R$ 100.

O classificador NIM entra SÓ no estado de observação. No de endereço, o cliente
está digitando um endereço: o catálogo não casa nada, a resposta determinística
já está certa, e chamar a NVIDIA seria uma ida à rede por endereço digitado sem
mudar decisão nenhuma.
"""
from unittest.mock import MagicMock, patch

import pytest


def _servico():
    from apps.automation.services.unified_service import UnifiedService

    s = UnifiedService.__new__(UnifiedService)
    s.store = None
    return s


class TestOEstadoChegaNaTriagem:
    def test_estado_de_observacao_e_declarado(self):
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=False), \
             patch.object(type(s), '_has_pending_notes_session', return_value=True), \
             patch('apps.automation.services.triagem.triar') as triagem:
            triagem.return_value = MagicMock(intencao=None)
            s._estado_deve_capturar('aquele grande')

        assert triagem.call_args.kwargs['esperando'] == 'observacao'

    def test_estado_de_endereco_e_declarado(self):
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=True), \
             patch.object(type(s), '_has_pending_notes_session', return_value=False), \
             patch('apps.automation.services.triagem.triar') as triagem:
            triagem.return_value = MagicMock(intencao=None)
            s._estado_deve_capturar('quadra 110 sul lote 21')

        assert triagem.call_args.kwargs['esperando'] == 'endereco'


class TestOndeOModeloEGasto:
    def test_observacao_recebe_o_classificador(self):
        """É onde a dúvida custa uma venda."""
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=False), \
             patch.object(type(s), '_has_pending_notes_session', return_value=True), \
             patch('apps.automation.services.triagem.triar') as triagem:
            triagem.return_value = MagicMock(intencao=None)
            s._estado_deve_capturar('aquele grande')

        assert triagem.call_args.kwargs['classificador'] is not None

    def test_endereco_NAO_gasta_chamada_de_rede(self):
        """Uma ida à NVIDIA por endereço digitado, sem mudar decisão nenhuma."""
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=True), \
             patch.object(type(s), '_has_pending_notes_session', return_value=False), \
             patch('apps.automation.services.triagem.triar') as triagem:
            triagem.return_value = MagicMock(intencao=None)
            s._estado_deve_capturar('quadra 110 sul lote 21')

        assert triagem.call_args.kwargs['classificador'] is None


class TestOQueNaoPodeRegredir:
    def test_sem_estado_nenhum_nao_captura(self):
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=False), \
             patch.object(type(s), '_has_pending_notes_session', return_value=False):
            assert s._estado_deve_capturar('qualquer coisa') is False

    def test_pedir_produto_escapa_do_estado(self):
        """O bug da Yeda, no seu teste original."""
        from apps.automation.services.triagem import Intencao

        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=False), \
             patch.object(type(s), '_has_pending_notes_session', return_value=True), \
             patch('apps.automation.services.triagem.triar') as triagem:
            triagem.return_value = MagicMock(intencao=Intencao.ITEM)
            assert s._estado_deve_capturar('Quero salada') is False

    def test_triagem_quebrada_continua_capturando(self):
        """Comportamento seguro quando tudo falha — não solta o cliente do checkout."""
        s = _servico()
        with patch.object(type(s), '_has_pending_delivery_address_session', return_value=True), \
             patch.object(type(s), '_has_pending_notes_session', return_value=False), \
             patch('apps.automation.services.triagem.triar', side_effect=RuntimeError('boom')):
            assert s._estado_deve_capturar('rua x') is True
