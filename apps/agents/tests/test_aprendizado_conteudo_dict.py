"""A tarefa de aprendizado do agente quebrava a cada 5 minutos desde set/2026:
`'dict' object has no attribute 'strip'`. O conteúdo das mensagens vem em
vários formatos (texto puro, {"text": ...}, {"text": {"body": ...}}, botões,
imagem) e o código fazia .strip() direto no campo."""
from django.test import SimpleTestCase

from apps.agents.learning import _texto_da_mensagem


class TextoDaMensagemTest(SimpleTestCase):
    def test_texto_puro(self):
        self.assertEqual(_texto_da_mensagem("  oi  "), "oi")

    def test_dict_com_text(self):
        self.assertEqual(_texto_da_mensagem({"text": "Boa noite"}), "Boa noite")

    def test_dict_com_text_body(self):
        self.assertEqual(_texto_da_mensagem({"type": "text", "text": {"body": "quero salada"}}), "quero salada")

    def test_botao_usa_body_text(self):
        self.assertEqual(_texto_da_mensagem({"type": "button", "body_text": "Oi Larissa"}), "Oi Larissa")

    def test_imagem_e_vazio_viram_texto_vazio(self):
        self.assertEqual(_texto_da_mensagem({"type": "image", "image": {"id": "1"}}), "")
        self.assertEqual(_texto_da_mensagem(None), "")
