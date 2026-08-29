"""
O botão "Respostas Automáticas" do painel precisa DESLIGAR o bot.

Varredura de 29/ago, procurando campos que o painel escreve e o backend nunca
lê. Três apareceram, todos em CompanyProfileDetailPage:

  auto_reply_enabled       "Habilitar respostas automáticas para mensagens"
  welcome_message_enabled  "Enviar boas-vindas na primeira mensagem"
  menu_auto_send           "Enviar cardápio junto com boas-vindas"

Nenhum gatilha nada. `auto_reply_enabled` chega a aparecer uma vez no
backend — mas só sendo ECOADO num payload de status, nunca decidindo. Ou
seja: o lojista que quer assumir a conversa desliga o botão, e o bot continua
respondendo por cima dele.

A trava vai em `process_message`, que é o invólucro por onde TUDO passa. O
docstring dele já explicava por que ele existe: `_processar_mensagem` tem
dezenas de `return` (atalho de localização, checkout pendente, modo humano,
erro), e mexer lá dentro garantiria que algum ramo ficasse de fora.

Semântica escolhida: desligado, o bot não processa — não é só "não responde".
Quem desligou vai atender à mão, e um bot mantendo carrinho por baixo do
atendente humano é pior do que bot nenhum. A mensagem do cliente continua
sendo gravada na caixa de entrada, que é trabalho do webhook, não daqui.
"""
from unittest import mock

import pytest


pytestmark = pytest.mark.django_db


class _PerfilFalso:
    def __init__(self, ligado):
        self.auto_reply_enabled = ligado
        self.id = 'perfil-teste'


def _servico(auto_reply_ligado):
    """Instância mínima do serviço, sem tocar no banco."""
    from apps.automation.services.unified_service import UnifiedService

    svc = UnifiedService.__new__(UnifiedService)
    svc.company = _PerfilFalso(auto_reply_ligado)
    return svc


class TestBotaoDesligado:
    def test_desligado_o_bot_nao_responde(self):
        svc = _servico(False)
        with mock.patch.object(
            svc, '_processar_mensagem', return_value='RESPOSTA'
        ) as processar:
            assert svc.process_message('oi') is None
            assert not processar.called, 'nem devia processar'

    def test_ligado_responde_normalmente(self):
        svc = _servico(True)
        with mock.patch.object(svc, '_processar_mensagem', return_value='RESPOSTA'), \
             mock.patch.object(svc, '_registrar_intencao'):
            assert svc.process_message('oi') == 'RESPOSTA'

    def test_sem_perfil_nenhum_o_bot_segue_funcionando(self):
        # Ausência de perfil não pode calar o bot: seria pior do que o bug.
        svc = _servico(True)
        svc.company = None
        with mock.patch.object(svc, '_processar_mensagem', return_value='RESPOSTA'), \
             mock.patch.object(svc, '_registrar_intencao'):
            assert svc.process_message('oi') == 'RESPOSTA'

    def test_campo_ausente_no_perfil_nao_cala_o_bot(self):
        # Perfil antigo, sem o campo: comportamento de antes.
        class SemCampo:
            id = 'x'

        svc = _servico(True)
        svc.company = SemCampo()
        with mock.patch.object(svc, '_processar_mensagem', return_value='RESPOSTA'), \
             mock.patch.object(svc, '_registrar_intencao'):
            assert svc.process_message('oi') == 'RESPOSTA'
