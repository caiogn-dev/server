"""O telefone entra no pedido em UM formato só.

O CASO REAL (04/09): "tem muitos cadastros duplicados na verdade, e já era algo
que estávamos falando e ainda assim continua duplicando".

Ele estava certo, e a medição confirma: 121 dos 160 pedidos da Cê Saladas
gravaram o telefone SEM o DDI 55 — todos vindos do site, e continuava
acontecendo de hora em hora no dia da reclamação.

A CAUSA: `checkout_service` gravava `customer_data['phone']` exatamente como a
cliente digitou. O projeto tem normalizador canônico desde agosto
(`normalize_phone_number`, libphonenumber), e este caminho — o que mais cria
pedido — nunca o chamou. Sete das noventa clientes viraram duas pessoas cada:
Aline Nasche, Leani, Ana Paula, Karla, Nair, Yeda.

O ESTRAGO NÃO É SÓ COSMÉTICO. Toda contagem por cliente passa a mentir: a
ficha mostra metade dos pedidos, o RFM classifica a mesma pessoa em dois
segmentos, e o "melhor cliente da loja" não aparece no topo de lista nenhuma
porque está partido ao meio. A Aline gastou R$ 1.152 e aparecia com R$ 603.

Cashback e carteira escaparam porque `_creditar` e `balance` normalizam nas
duas pontas — o saldo funciona. É a única parte do sistema que já fazia isto,
e é por isso que o dono não perdeu dinheiro, só visibilidade.

O consenso do projeto: normalizar na ESCRITA. Normalizar só na leitura obriga
todo lugar que consulta a lembrar da regra, e um esquecimento vira um número
errado na tela sem erro nenhum.

E a normalização entra no `save()` do PEDIDO, não no checkout. Existem sete
caminhos que criam pedido — site, PDV, bot do WhatsApp, link de pagamento,
painel, importação, agente — e consertar só o do site deixaria os outros seis
livres para recriar o problema. O modelo é o único ponto por onde todos passam.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class TelefoneDoPedidoNormalizadoTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-tel', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-tel', owner=dono,
            store_type='food', status='active',
        )
    def _pedido_com_telefone(self, telefone):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Aline Nasche', customer_phone=telefone,
            subtotal=Decimal('36.99'), total=Decimal('36.99'),
            status='pending', payment_status='pending',
        )

    def test_o_numero_como_a_cliente_digita_vira_o_formato_da_casa(self):
        pedido = self._pedido_com_telefone('63992618115')

        self.assertEqual(pedido.customer_phone, '5563992618115')

    def test_todos_os_formatos_da_mesma_pessoa_viram_um_so(self):
        """Este é o bug: cada porta de entrada gravava um formato diferente."""
        formatos = [
            '63992618115',        # como se digita em Palmas
            '5563992618115',      # com DDI
            '(63) 99261-8115',    # como o painel formata
            '+55 63 99261-8115',  # colado do contato do celular
            ' 63 9 9261 8115 ',   # com espaços
        ]

        gravados = {self._pedido_com_telefone(f).customer_phone for f in formatos}

        self.assertEqual(gravados, {'5563992618115'})

    def test_o_formato_legado_e_gravado_COMO_VEIO(self):
        """O que grava aqui é ENDEREÇO de entrega da mensagem, não identidade.

        `556391124171` é o formato que o wa_id do WhatsApp entrega — celular
        brasileiro antes da migração do nono dígito. Ele é o endereço que
        comprovadamente entrega: medido nas 7.640 mensagens da base, enviando
        neste formato 4.335 saíram e 65 falharam (1,5%); acrescentando o nono
        dígito, 290 saíram e 117 falharam (29%).

        Quem colapsa `556391124171` com `5563991124171` para saber que é a
        mesma pessoa é a LEITURA. O endereço fica como veio.
        """
        pedido = self._pedido_com_telefone('556391124171')

        self.assertEqual(pedido.customer_phone, '556391124171')

    def test_numero_de_fora_do_brasil_nao_ganha_55(self):
        """A cliente da Espanha (+34) tem 11 dígitos igual a um celular BR.

        Grudar 55 no número dela cria um telefone que não existe, e o aviso do
        pedido nunca chega. Já aconteceu aqui em agosto.
        """
        pedido = self._pedido_com_telefone('+34 647 52 08 24')

        self.assertEqual(pedido.customer_phone, '34647520824')

    def test_telefone_vazio_continua_vazio(self):
        """Checkout de balcão pode não ter telefone. Não inventar um."""
        self.assertEqual(self._pedido_com_telefone('').customer_phone, '')

    def test_lixo_no_campo_nao_derruba_a_venda(self):
        """Um pedido pago não pode ser recusado por causa do formato."""
        pedido = self._pedido_com_telefone('não tenho')

        self.assertIsNotNone(pedido.id)

    def test_editar_o_pedido_depois_nao_desnormaliza(self):
        """O painel edita o telefone do pedido e formata com parênteses."""
        pedido = self._pedido_com_telefone('5563992618115')

        pedido.customer_phone = '(63) 99261-8115'
        pedido.save(update_fields=['customer_phone'])
        pedido.refresh_from_db()

        self.assertEqual(pedido.customer_phone, '5563992618115')

    def test_a_mesma_pessoa_para_de_virar_duas(self):
        """O sintoma que o dono viu: uma cliente em duas linhas na lista."""
        self._pedido_com_telefone('11975373744')
        self._pedido_com_telefone('5511975373744')

        distintos = set(
            StoreOrder.objects.filter(store=self.store)
            .values_list('customer_phone', flat=True)
        )

        self.assertEqual(distintos, {'5511975373744'})
