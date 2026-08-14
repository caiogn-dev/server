"""O classificador precisa estar LIGADO — e só onde vale o custo.

`ClassificadorNIM` foi construído e testado em 13/ago e nunca foi injetado em
lugar nenhum: `triar()` era sempre chamado sem ele. É o mesmo padrão do agente
que ficou `inactive` em 13 perfis — código pronto, desligado, e ninguém percebe
porque nada quebra.

Duas decisões aqui, e as duas custam dinheiro se erradas:

1. **Onde ligar.** O único chamador de `triar()` é o portão do checkout, e ele
   não passava `esperando` — a informação que evita o erro estava disponível e
   era jogada fora. Passa a passar.

2. **Quando consultar o modelo.** No estado de ENDEREÇO o cliente está
   digitando um endereço: o catálogo não casa nada e a resposta determinística
   (não é item → captura) já está certa. Chamar a NVIDIA ali seria uma ida à
   rede por endereço digitado, sem mudar decisão nenhuma.

   No estado de OBSERVAÇÃO é o oposto: foi exatamente ali que "Quero salada"
   virou "✅ Anotado: Quero salada" e fechou um pedido de R$ 20 no lugar de
   R$ 100. Quando o catálogo não casa, a dúvida é real e vale os 4 segundos.
"""
from unittest.mock import MagicMock

from apps.automation.services.triagem import Decisao, Intencao, triar


class TestQuandoOModeloEConsultado:
    def test_catalogo_que_resolve_nao_gasta_chamada(self):
        """Modelo é o último recurso, nunca o primeiro."""
        modelo = MagicMock()
        # Sem store não há catálogo, mas o texto é pergunta — resolve antes.
        triar('vocês entregam no centro?', classificador=modelo)

        modelo.assert_not_called()

    def test_saudacao_nao_gasta_chamada(self):
        modelo = MagicMock()

        triar('oi', classificador=modelo)

        modelo.assert_not_called()

    def test_negacao_nao_gasta_chamada(self):
        modelo = MagicMock()

        triar('sem cebola', esperando='observacao', classificador=modelo)

        modelo.assert_not_called()

    def test_texto_desconhecido_consulta_o_modelo(self):
        """O caso que motivou o classificador: catálogo não casou e a dúvida é real."""
        modelo = MagicMock(return_value=Decisao(intencao=Intencao.ITEM, texto='x'))

        d = triar('manda mais uma daquela de frango', esperando='observacao',
                  classificador=modelo)

        modelo.assert_called_once()
        assert d.intencao is Intencao.ITEM

    def test_o_estado_chega_ao_modelo(self):
        """Sem `esperando`, o modelo classifica no escuro."""
        modelo = MagicMock(return_value=None)

        triar('aquele grande', esperando='observacao', classificador=modelo)

        assert modelo.call_args.kwargs['esperando'] == 'observacao'


class TestOModeloNaoPodeDerrubarNada:
    def test_modelo_que_explode_cai_no_deterministico(self):
        modelo = MagicMock(side_effect=RuntimeError('NIM fora do ar'))

        d = triar('aquele grande', esperando='observacao', classificador=modelo)

        assert d.intencao is Intencao.OBSERVACAO

    def test_modelo_que_devolve_lixo_cai_no_deterministico(self):
        modelo = MagicMock(return_value={'intencao': 'item'})

        d = triar('aquele grande', esperando='observacao', classificador=modelo)

        assert d.intencao is Intencao.OBSERVACAO

    def test_sem_classificador_o_comportamento_e_o_de_antes(self):
        assert triar('aquele grande', esperando='observacao').intencao is Intencao.OBSERVACAO
