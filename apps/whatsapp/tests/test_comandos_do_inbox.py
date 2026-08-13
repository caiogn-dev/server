"""Atalhos "/" no inbox: agir no pedido sem sair da conversa.

13/ago, Yeda × Cê Saladas: o bot montou um pedido errado, e resolver custou à
dona **5 minutos e uma troca de tela** — cancelar o #CE-2608135397 no painel,
refazer o valor, copiar um link de pagamento do Mercado Pago e colar no chat.
Tudo isso enquanto a cliente esperava.

Os comandos existem para essa operação caber na própria conversa.

Contrato, e o que ele protege:

- **`/` só é comando no começo da mensagem.** "5/5 estrelas" e "meio/meio" são
  texto de gente.
- **Comando desconhecido não vira mensagem para o cliente.** O risco óbvio aqui
  é a dona digitar `/pixx`, o sistema não entender e MANDAR "/pixx" para a
  cliente. Erro de digitação não pode virar mensagem enviada.
- **Comando destrutivo pede confirmação.** `/cancelar` cancela um pedido de
  verdade; um toque errado não pode desfazer uma venda.
- **Quem não é da loja não executa nada.** O inbox é multi-loja.
"""
import pytest

from apps.whatsapp.services.comandos import (
    COMANDOS, Comando, interpretar,
)


class TestQuandoEhComando:
    def test_barra_no_comeco_e_comando(self):
        assert interpretar('/pix') is not None

    def test_barra_no_meio_nao_e_comando(self):
        """'5/5 estrelas' é texto de gente, não atalho."""
        assert interpretar('nota 5/5 estrelas') is None

    def test_meio_barra_meio_nao_e_comando(self):
        assert interpretar('quero meio/meio') is None

    def test_texto_normal_nao_e_comando(self):
        assert interpretar('pode mandar o pix') is None

    def test_espaco_antes_da_barra_ainda_conta(self):
        assert interpretar('  /pedido') is not None

    def test_barra_sozinha_nao_explode(self):
        assert interpretar('/') is None


class TestComandoDesconhecido:
    def test_erro_de_digitacao_nao_vira_mensagem_para_o_cliente(self):
        """O risco real: a dona digita /pixx e a cliente recebe '/pixx'."""
        c = interpretar('/pixx')

        assert c is not None, 'tem que ser reconhecido como TENTATIVA de comando'
        assert c.conhecido is False
        assert c.enviar_ao_cliente is False

    def test_desconhecido_sugere_o_parecido(self):
        c = interpretar('/pixx')

        assert 'pix' in (c.sugestao or '')

    def test_desconhecido_sem_parecido_nao_inventa_sugestao(self):
        c = interpretar('/zzzzzz')

        assert c.conhecido is False
        assert not c.sugestao


class TestArgumentos:
    def test_comando_sem_argumento(self):
        c = interpretar('/pedido')

        assert c.nome == 'pedido'
        assert c.argumento == ''

    def test_comando_com_argumento(self):
        c = interpretar('/cupom BEMVINDO10')

        assert c.nome == 'cupom'
        assert c.argumento == 'BEMVINDO10'

    def test_argumento_com_espacos_fica_inteiro(self):
        c = interpretar('/nota cliente pediu sem cebola')

        assert c.argumento == 'cliente pediu sem cebola'

    def test_maiuscula_nao_atrapalha(self):
        assert interpretar('/PIX').nome == 'pix'


class TestSeguranca:
    def test_cancelar_pede_confirmacao(self):
        """Um toque errado não pode desfazer uma venda."""
        assert interpretar('/cancelar').precisa_confirmar is True

    def test_pix_nao_pede_confirmacao(self):
        """Gerar cobrança é reversível; pedir confirmação a toda hora ensina a
        confirmar sem ler, e aí a confirmação do /cancelar também vira reflexo."""
        assert interpretar('/pix').precisa_confirmar is False

    def test_nenhum_comando_e_enviado_ao_cliente_como_texto(self):
        for nome in COMANDOS:
            assert interpretar(f'/{nome}').enviar_ao_cliente is False, nome


class TestCatalogoDeComandos:
    def test_todo_comando_tem_descricao(self):
        """A paleta do painel mostra a descrição — sem ela o atalho é adivinhação."""
        for nome, meta in COMANDOS.items():
            assert meta.get('descricao'), nome

    def test_comandos_de_acao_no_pedido_existem(self):
        """Foi o que custou 5 minutos à dona na conversa da Yeda."""
        assert {'pix', 'pedido', 'status', 'cancelar'} <= set(COMANDOS)
