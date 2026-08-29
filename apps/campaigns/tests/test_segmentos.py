"""A régua que decide QUEM recebe a campanha.

Até 28/ago/2026 o painel mandava `source: 'all'` fixo e a única escolha era
"todos". Campanha para todo mundo é a que mais queima base: quem comprou ontem
recebe "sentimos sua falta" e quem nunca comprou recebe "seu de sempre".

As faixas repetem os cortes que o CRM já usava (`StoreCustomerViewSet.DIAS_ATIVO`
/ `DIAS_RISCO` e o perfil novo/ocasional/VIP do painel). Duplicar o número seria
o começo de duas verdades — por isso as constantes vivem AQUI e o resto importa.

POR QUE AGREGAR DE `StoreOrder` E NÃO DE `StoreCustomer`

`StoreCustomer.total_orders` é um contador denormalizado que pode ficar velho, e
na Cê Saladas ele cobre 63 dos 73 telefones que já pediram — 10 pessoas reais
ficariam invisíveis para toda campanha. O pedido é o fato; o contador é a cópia.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from apps.campaigns.services.segmentos import (
    DIAS_ATIVO,
    DIAS_RISCO,
    PEDIDOS_VIP,
    Recencia,
    Frequencia,
    classificar_frequencia,
    classificar_recencia,
    descrever_filtros,
)


def dias_atras(n):
    return timezone.now() - timedelta(days=n)


class RecenciaTests(SimpleTestCase):
    def test_sem_nenhuma_compra_e_nunca_comprou_nao_e_inativo(self):
        # A diferença decide a mensagem: "volta pra gente" versus "primeira
        # compra com 10% off". Tratar null como inativo manda a oferta errada.
        self.assertEqual(classificar_recencia(None), Recencia.NUNCA_COMPROU)

    def test_comprou_hoje_e_ativo(self):
        self.assertEqual(classificar_recencia(dias_atras(0)), Recencia.ATIVO)

    def test_ultimo_dia_da_janela_ainda_e_ativo(self):
        self.assertEqual(classificar_recencia(dias_atras(DIAS_ATIVO)), Recencia.ATIVO)

    def test_um_dia_depois_da_janela_vira_em_risco(self):
        self.assertEqual(classificar_recencia(dias_atras(DIAS_ATIVO + 1)), Recencia.EM_RISCO)

    def test_no_corte_de_risco_ainda_e_em_risco(self):
        self.assertEqual(classificar_recencia(dias_atras(DIAS_RISCO)), Recencia.EM_RISCO)

    def test_passado_o_corte_de_risco_vira_inativo(self):
        self.assertEqual(classificar_recencia(dias_atras(DIAS_RISCO + 1)), Recencia.INATIVO)


class FrequenciaTests(SimpleTestCase):
    def test_zero_pedidos_nao_e_novo_e_sim_sem_compra(self):
        self.assertIsNone(classificar_frequencia(0))

    def test_um_pedido_e_novo(self):
        self.assertEqual(classificar_frequencia(1), Frequencia.NOVO)

    def test_de_dois_a_quatro_e_ocasional(self):
        self.assertEqual(classificar_frequencia(2), Frequencia.OCASIONAL)
        self.assertEqual(classificar_frequencia(4), Frequencia.OCASIONAL)

    def test_a_partir_do_corte_e_vip(self):
        self.assertEqual(classificar_frequencia(PEDIDOS_VIP), Frequencia.VIP)
        self.assertEqual(classificar_frequencia(PEDIDOS_VIP + 10), Frequencia.VIP)


class QuemContaComoClienteTests(SimpleTestCase):
    """A regra de "quem já comprou" é a mesma de "o que conta como dinheiro".

    A primeira versão deste módulo tinha a própria lista de status e foi pega
    pela catraca `test_metrics_sem_matematica_solta`. O defeito era real, não
    estilístico: filtrar por status sem checar `payment_status` contaria pedido
    não pago, e não excluir pedido de TESTE faria o dono virar VIP da própria
    loja e receber a campanha de reativação dele mesmo — os pedidos de teste
    chegaram a ser ~40% do volume.
    """

    def test_usa_a_funcao_do_nucleo_e_nao_uma_copia(self):
        from apps.campaigns.services import segmentos
        from apps.stores.metrics.definicoes import pedidos_de_receita

        self.assertIs(segmentos.pedidos_de_receita, pedidos_de_receita)

    def test_o_modulo_nao_tem_regra_de_status_propria(self):
        # Catraca local: se alguém reintroduzir a lista, este teste cai antes
        # da catraca global — com a explicação do porquê ao lado.
        import inspect
        from apps.campaigns.services import segmentos

        codigo = [
            ln for ln in inspect.getsource(segmentos).splitlines()
            if not ln.lstrip().startswith('#')
        ]
        fonte = '\n'.join(codigo)
        self.assertNotIn('STATUS_QUE_CONTAM', fonte)
        self.assertNotIn("status__in=", fonte)


class DescreverFiltrosTests(SimpleTestCase):
    """O painel precisa dizer em português quem vai receber, antes de enviar."""

    def test_sem_filtro_nenhum_diz_todos(self):
        self.assertEqual(descrever_filtros({}), 'Todos os contatos')

    def test_uma_recencia_vira_frase_legivel(self):
        self.assertEqual(
            descrever_filtros({'recencia': ['em_risco']}),
            f'{DIAS_ATIVO} a {DIAS_RISCO} dias sem comprar',
        )

    def test_filtros_combinados_sao_unidos_por_e(self):
        texto = descrever_filtros({'recencia': ['ativo'], 'frequencia': ['vip']})
        self.assertIn('últimos %d dias' % DIAS_ATIVO, texto)
        self.assertIn('VIP', texto)
        self.assertIn(' e ', texto)

    def test_faixa_de_ticket_aparece_em_reais(self):
        texto = descrever_filtros({'ticket_min': Decimal('50')})
        self.assertIn('R$', texto)
        self.assertIn('50', texto)
