"""O celular brasileiro sem o nono dígito é a MESMA pessoa.

O CASO REAL (04/09): "tem muitos cadastros duplicados na verdade, e já era algo
que estávamos falando e ainda assim continua duplicando".

Eram DUAS causas, não uma. A primeira — telefone gravado sem o DDI 55 — foi
resolvida normalizando na escrita do pedido. A segunda sobrevive à
normalização e é esta:

    Zanya maria    556391124171   e   5563991124171
    Yeda Lopes     556399619019   e   5563999619019

O mesmo número, um sem o nono dígito. É o `wa_id` do WhatsApp, que entrega o
formato legado, contra o checkout do site, que grava com o 9. As duas formas
já têm o 55, então passavam pelo normalizador intactas e viravam dois
cadastros.

A REGRA, e por que ela é segura: depois de 55 + DDD, celular brasileiro tem 9
dígitos e começa com 9. Os 8 dígitos são o formato anterior à migração (que
terminou em 2016), e nesse formato celular começa com 6, 7, 8 ou 9 — fixo
começa com 2, 3, 4 ou 5. Então o 9 só entra quando o primeiro dígito prova que
é celular, e telefone fixo nunca é tocado.

O que NÃO fazer: mexer em número estrangeiro. Um celular espanhol tem 9
dígitos e a Layane já teve a conversa quebrada por regra de tamanho aplicada
sem olhar o país (26/ago). Só entra aqui o que começa com 55 e tem DDD válido.
"""
from django.test import SimpleTestCase

from apps.core.utils import normalize_phone_number


class NonoDigitoTest(SimpleTestCase):

    def test_celular_legado_ganha_o_nono_digito(self):
        """O caso da Zanya: wa_id sem o 9 virava um segundo cadastro."""
        self.assertEqual(normalize_phone_number('556391124171'), '5563991124171')

    def test_as_duas_formas_viram_a_mesma(self):
        antiga = normalize_phone_number('556399619019')
        nova = normalize_phone_number('5563999619019')

        self.assertEqual(antiga, nova)
        self.assertEqual(antiga, '5563999619019')

    def test_quem_ja_tem_nove_digitos_nao_muda(self):
        self.assertEqual(normalize_phone_number('5563992618115'), '5563992618115')

    def test_fixo_nao_ganha_nono_digito(self):
        """(63) 3218-4000 é fixo. Enfiar um 9 cria um número que não existe."""
        self.assertEqual(normalize_phone_number('556332184000'), '556332184000')

    def test_estrangeiro_fica_intacto(self):
        """Celular espanhol tem 9 dígitos; regra de tamanho já quebrou aqui."""
        self.assertEqual(normalize_phone_number('34647520824'), '34647520824')

    def test_numero_local_sem_ddi_continua_virando_brasileiro(self):
        self.assertEqual(normalize_phone_number('63992618115'), '5563992618115')

    def test_local_legado_sem_ddi_tambem_se_resolve(self):
        """Como a cliente digita no site: sem o 55 e sem o 9."""
        self.assertEqual(normalize_phone_number('6391124171'), '5563991124171')

    def test_vazio_continua_vazio(self):
        self.assertEqual(normalize_phone_number(''), '')
        self.assertEqual(normalize_phone_number(None), '')

    def test_o_ddi_escrito_pelo_cliente_manda(self):
        """A regra de 10 dígitos não pode reabrir o caso da cliente espanhola.

        Quem escreve '+' está AFIRMANDO o país, e isso vence qualquer
        heurística de tamanho.
        """
        self.assertEqual(normalize_phone_number('+34 647 52 08 24'), '34647520824')
        self.assertEqual(normalize_phone_number('+1 555 404 4637'), '15554044637')

    def test_ddd_invalido_nao_e_tocado(self):
        """55 + '01' não é DDD nenhum: não inventar dígito em cima de lixo."""
        self.assertEqual(normalize_phone_number('550112345678'), '550112345678')


class EnvioNaoEIdentidadeTest(SimpleTestCase):
    """Identidade e ENVIO são coisas diferentes, e confundi-las cala o cliente.

    O nono dígito entrou em `normalize_phone_number` (05/09) para parar a
    duplicação: `556391124171` do wa_id e `5563991124171` do checkout são a
    mesma pessoa, e sem colapsar isso ela vira dois cadastros.

    Mas isso mudou também o número usado para ENVIAR. E aí o risco muda de
    natureza: identidade errada é relatório torto; número de envio errado é a
    mensagem não chegando — que é o modo de falha mais caro deste sistema, e
    que já aconteceu (agosto: notificação nenhuma saiu por telefone sem o 55, e
    o log dizia "sent").

    A REGRA: para ENVIAR, o número vai como a gente o conhece — o wa_id que o
    WhatsApp entregou, ou o que a cliente digitou. Só o DDI é garantido, porque
    sem ele a Meta recusa. Inventar dígito num número que já funciona é apostar
    contra algo que está entregando hoje.
    """

    def test_envio_preserva_o_formato_legado(self):
        from apps.core.utils import telefone_para_envio_e164

        self.assertEqual(telefone_para_envio_e164('556391124171'), '556391124171')

    def test_envio_garante_o_ddi(self):
        """Sem o 55 a Meta recusa — isso sim tem que ser consertado."""
        from apps.core.utils import telefone_para_envio_e164

        self.assertEqual(telefone_para_envio_e164('63991124171'), '5563991124171')

    def test_envio_nao_toca_em_estrangeiro(self):
        from apps.core.utils import telefone_para_envio_e164

        self.assertEqual(telefone_para_envio_e164('+34 647 52 08 24'), '34647520824')

    def test_a_identidade_continua_colapsando_os_dois_formatos(self):
        """O conserto da duplicação não pode ser desfeito por este ajuste."""
        from apps.core.utils import normalize_phone_number

        self.assertEqual(
            normalize_phone_number('556391124171'),
            normalize_phone_number('5563991124171'),
        )
