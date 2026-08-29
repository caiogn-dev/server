"""Quem apertou "Parar promoções" tem que parar de receber.

INCIDENTE QUE ORIGINOU ESTE ARQUIVO (28/ago/2026)

Oito pessoas apertaram o botão "Parar promoções" nas campanhas da Cê Saladas
(5 em 25/ago, 3 em 28/ago). Nenhuma linha do server2 tratava isso: o botão
chega como mensagem `type: button`, virava conversa comum, o bot respondia
qualquer coisa e ninguém era marcado. As CINCO de 25/ago receberam a campanha
de novo em 28/ago.

Isso não é chatice de UX. É:
  - risco de bloqueio: a Meta derruba número com muita marcação de spam;
  - risco de LGPD: pedido de oposição registrado e ignorado;
  - dinheiro: cada janela de marketing é paga.

O RECONHECIMENTO DE TEXTO É DELIBERADAMENTE ESTREITO

Só a mensagem INTEIRA valendo uma das frases de saída conta. "quero parar de
comer salada kkk" contém "parar" e NÃO pode descadastrar ninguém: um opt-out
falso é irreversível na prática, porque a pessoa nunca mais recebe e nunca vai
reclamar de algo que ela não sabe que perdeu.
"""
from django.test import SimpleTestCase

from apps.campaigns.services.optout import (
    FRASES_DE_SAIDA,
    TEXTO_DE_CONFIRMACAO,
    eh_pedido_de_saida,
)


class BotaoDaMetaTests(SimpleTestCase):
    def test_reconhece_o_botao_em_portugues(self):
        # Texto exato que chegou nas 8 mensagens reais do banco.
        self.assertTrue(eh_pedido_de_saida('Parar promoções', tipo='button'))

    def test_reconhece_o_botao_em_ingles(self):
        # A Meta troca o idioma do botão conforme o template.
        self.assertTrue(eh_pedido_de_saida('Stop promotions', tipo='button'))

    def test_acento_e_caixa_nao_importam(self):
        self.assertTrue(eh_pedido_de_saida('PARAR PROMOCOES', tipo='button'))
        self.assertTrue(eh_pedido_de_saida('  parar promoções  ', tipo='button'))

    def test_outro_botao_qualquer_nao_descadastra(self):
        # O bot usa botões para pedir e confirmar pedido. Um falso positivo
        # aqui silenciaria um cliente ativo no meio da compra.
        self.assertFalse(eh_pedido_de_saida('Ver cardápio', tipo='button'))
        self.assertFalse(eh_pedido_de_saida('Confirmar pedido', tipo='button'))


class TextoLivreTests(SimpleTestCase):
    def test_mensagem_inteira_igual_a_frase_de_saida_conta(self):
        for frase in FRASES_DE_SAIDA:
            self.assertTrue(
                eh_pedido_de_saida(frase, tipo='text'),
                f'"{frase}" deveria contar como pedido de saída',
            )

    def test_frase_de_saida_dentro_de_outra_frase_nao_conta(self):
        self.assertFalse(eh_pedido_de_saida('quero parar de comer salada kkk', tipo='text'))
        self.assertFalse(eh_pedido_de_saida('pode parar o pedido por favor?', tipo='text'))
        self.assertFalse(eh_pedido_de_saida('vou sair agora, chega em 20min?', tipo='text'))

    def test_pontuacao_no_fim_nao_atrapalha(self):
        self.assertTrue(eh_pedido_de_saida('PARAR.', tipo='text'))
        self.assertTrue(eh_pedido_de_saida('sair!', tipo='text'))

    def test_mensagem_vazia_nao_conta(self):
        self.assertFalse(eh_pedido_de_saida('', tipo='text'))
        self.assertFalse(eh_pedido_de_saida(None, tipo='text'))


class ConfirmacaoTests(SimpleTestCase):
    def test_a_confirmacao_diz_o_que_para_e_o_que_continua(self):
        # Sem dizer que o pedido continua chegando, a pessoa acha que se
        # desligou da loja inteira e liga perguntando cadê a entrega.
        texto = TEXTO_DE_CONFIRMACAO.casefold()
        self.assertIn('promo', texto)
        self.assertIn('pedido', texto)
