"""A mensagem que o bot entrega para encaminhar precisa dizer QUEM indicou.

O CASO REAL (04/09): a Elisangela tocou em "🎁 Indicar um amigo" e o bot
respondeu com o texto pronto para ela encaminhar:

    10% de desconto no primeiro pedido na Cê Saladas!
    Usa o cupom *INDICA10* em https://cesaladas.com.br

O dono perguntou por que ela não recebeu o link dela. Ela recebeu uma
mensagem — que é justamente a mensagem que torna a indicação dela invisível.

`INDICA10` é FIXO e igual para todos, de propósito: código pessoal já foi
tentado aqui (13 AVALIA5-XXXXXX criados, 0 usados) porque ninguém digita hash
no carrinho. Só que código igual não carrega identidade, e o link ia pelado.
Resultado: a amiga compra, ganha os 10%, e o cashback da Elisangela não sai —
o backend não tem como saber de quem veio.

Quem carrega a identidade é o LINK: `?indica=<telefone de quem indicou>`. O
storefront guarda esse número 30 dias no navegador do amigo e ele viaja com o
pedido, virando `metadata.indicado_por` e creditando quem indicou.

O telefone vem do PEDIDO de quem clicou, não da conversa: o wa_id do WhatsApp
chega sem o nono dígito, e é o telefone do pedido que o crédito casa depois.

E O ENDEREÇO TEM QUE SER O DO CARDAPIDEX, não o domínio próprio da loja.
`cesaladas.com.br` é OUTRO APP (buildId diferente do cardapidex-web): a
captura do `?indica=` não existe lá. Mandar a indicação para o domínio próprio
é mandar para um lugar que não sabe ler o parâmetro — o link parece certo, o
amigo compra, e o crédito nunca sai.
"""
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler

User = get_user_model()


class BotIndicaComIdentidadeTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-indica-bot', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-indica-bot', owner=dono,
            store_type='food', status='active',
            metadata={'cashback_enabled': True},
        )
        self.telefone = '5563999547790'
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Elisangela', customer_phone=self.telefone,
            subtotal=Decimal('50'), total=Decimal('50'),
            status='delivered', payment_status='paid',
        )

    def _clicar_em_indicar(self, telefone_da_conversa=None):
        handler = InteractiveReplyHandler.__new__(InteractiveReplyHandler)
        handler.conversation = MagicMock()
        handler.conversation.phone_number = telefone_da_conversa or self.telefone
        handler.company_profile = None
        return handler._handle_refer_friend(f'refer_friend_{self.pedido.id}')

    def test_a_mensagem_traz_o_link_com_o_numero_de_quem_indicou(self):
        texto = self._clicar_em_indicar().response_text

        self.assertIn(f'indica={self.telefone}', texto)

    def test_aponta_para_o_cardapidex_e_nao_para_o_dominio_proprio(self):
        """O domínio próprio é outro app e não lê `?indica=`.

        A loja tem custom_domain configurado; se o link seguisse ele, a
        indicação iria para um storefront sem a captura do parâmetro.
        """
        self.store.custom_domain = 'cesaladas.com.br'
        self.store.metadata = {**self.store.metadata, 'frontend_url': 'https://cesaladas.com.br'}
        self.store.save(update_fields=['custom_domain', 'metadata'])

        texto = self._clicar_em_indicar().response_text

        self.assertIn('cardapidex.com.br', texto)
        self.assertIn(self.store.slug, texto)
        self.assertNotIn('cesaladas.com.br', texto)

    def test_o_link_pelado_nao_aparece_mais(self):
        """Link sem o parâmetro é o bug: a amiga compra e ninguém é creditado."""
        texto = self._clicar_em_indicar().response_text

        import re
        # Todo endereço da loja no texto tem que carregar a identidade.
        for url in re.findall(r'https?://\S+', texto):
            self.assertIn('indica=', url, f'link sem identidade na mensagem: {url}')

    def test_o_cupom_continua_no_texto(self):
        """O link rastreia; o cupom é o que faz o amigo querer clicar."""
        texto = self._clicar_em_indicar().response_text

        self.assertIn('INDICA10', texto)

    def test_funciona_com_o_wa_id_sem_o_nono_digito(self):
        """O WhatsApp entrega o número sem o nono dígito; o pedido tem com."""
        resposta = self._clicar_em_indicar(telefone_da_conversa='556399547790')

        self.assertIn('indica=', resposta.response_text)
        self.assertNotIn('Não encontrei', resposta.response_text)

    def test_usa_o_telefone_do_pedido_e_nao_o_da_conversa(self):
        """O crédito casa com o telefone do PEDIDO — o link tem que usar esse.

        Se o link levasse o wa_id sem o nono dígito, a indicação chegaria com
        um telefone que nunca casa com o cadastro, e o crédito sumiria em
        silêncio — o pior modo de falha para dinheiro.
        """
        texto = self._clicar_em_indicar(telefone_da_conversa='556399547790').response_text

        self.assertIn(f'indica={self.telefone}', texto)
