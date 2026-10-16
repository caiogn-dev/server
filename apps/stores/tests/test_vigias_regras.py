"""Regras dos vigias: quando avisar e — tão importante quanto — quando calar.

Os números do cenário imitam a Cê Saladas de out/2026: vende de segunda a
sexta, ~14 saladas por dia, quinta é o pico, Queridinha é ~1/3 do volume.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores.models import StoreOrder, StoreOrderItem
from apps.stores.tests.factories import make_store
from apps.stores.vigias import regras

TZ = timezone.get_current_timezone()


def local(y, m, d, h=12, mi=0):
    return timezone.make_aware(datetime(y, m, d, h, mi), TZ)


def pedido(loja, quando, itens, telefone='5563999990000', nome='Cliente', status='delivered',
           pago=True, teste=False):
    total = sum(Decimal(str(p)) * q for _, q, p, _ in itens)
    o = StoreOrder.objects.create(
        store=loja, customer_name=nome, customer_phone=telefone,
        subtotal=total, total=total, delivery_fee=Decimal('0'),
        status=status, payment_status='paid' if pago else 'pending',
        metadata={'is_test': True} if teste else {},
    )
    for nome_item, qtd, preco, custo in itens:
        StoreOrderItem.objects.create(
            order=o, product_name=nome_item, quantity=qtd,
            unit_price=Decimal(str(preco)), subtotal=Decimal(str(preco)) * qtd,
            unit_cost=None if custo is None else Decimal(str(custo)),
        )
    StoreOrder.objects.filter(pk=o.pk).update(created_at=quando, paid_at=quando if pago else None)
    return o


def dias_uteis(fim, quantos):
    """Os `quantos` dias úteis (seg–sex) até `fim`, inclusive, do mais antigo ao mais novo."""
    dias, d = [], fim
    while len(dias) < quantos:
        if d.weekday() < 5:
            dias.append(d)
        d -= timedelta(days=1)
    return list(reversed(dias))


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas Teste')


# ── Resumo da manhã ───────────────────────────────────────────────────────

class TestResumoDaManha:
    # sexta 16/10/2026, 8h; ontem = quinta 15/10
    AGORA = local(2026, 10, 16, 8, 5)

    def _quintas(self, loja, pedidos_por_quinta=10):
        for semanas in range(1, 5):
            dia = local(2026, 10, 15) - timedelta(days=7 * semanas)
            for _ in range(pedidos_por_quinta):
                pedido(loja, dia, [('Queridinha', 1, 36.99, 14)])

    def test_resume_ontem_e_compara_com_as_mesmas_quintas(self, loja):
        self._quintas(loja, 10)
        for _ in range(12):
            pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 1, 36.99, 14)])
        pedido(loja, local(2026, 10, 15, 13), [('Tilápia Suprema', 1, 46.99, 22)])

        fatos = regras.resumo_da_manha(loja, self.AGORA)

        assert len(fatos) == 1
        f = fatos[0]
        assert f.chave == 'resumo:2026-10-15'
        assert '13 pedidos' in f.texto
        assert '30% acima' in f.texto  # 13 contra média 10
        assert 'Queridinha (12)' in f.texto
        assert f.dados['base_dias'] == 4

    def test_segunda_resume_a_sexta(self, loja):
        pedido(loja, local(2026, 10, 16, 12), [('Queridinha', 2, 36.99, 14)])
        segunda = local(2026, 10, 19, 8, 0)

        fatos = regras.resumo_da_manha(loja, segunda)

        assert fatos[0].chave == 'resumo:2026-10-16'
        assert 'sex 16/10' in fatos[0].titulo

    def test_sem_venda_nos_ultimos_tres_dias_cala(self, loja):
        pedido(loja, local(2026, 10, 10, 12), [('Queridinha', 1, 36.99, 14)])
        assert regras.resumo_da_manha(loja, self.AGORA) == []

    def test_base_curta_nao_inventa_percentual(self, loja):
        pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 1, 36.99, 14)])
        pedido(loja, local(2026, 10, 8, 12), [('Queridinha', 1, 36.99, 14)])

        texto = regras.resumo_da_manha(loja, self.AGORA)[0].texto
        assert '%' not in texto

    def test_cancelado_e_teste_nao_contam(self, loja):
        pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 1, 36.99, 14)])
        pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 5, 36.99, 14)], status='cancelled')
        pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 5, 36.99, 14)], teste=True)

        assert '1 pedido' in regras.resumo_da_manha(loja, self.AGORA)[0].texto

    def test_outra_loja_nao_vaza(self, loja, db):
        outra = make_store(name='Outra')
        pedido(outra, local(2026, 10, 15, 12), [('Queridinha', 9, 36.99, 14)])
        assert regras.resumo_da_manha(loja, self.AGORA) == []


# ── Sabor em queda ────────────────────────────────────────────────────────

class TestSaborEmQueda:
    AGORA = local(2026, 10, 16, 8, 0)  # sexta; janela atual = 09/10..15/10

    def _historico(self, loja, almondega_atual, queridinha_atual=4):
        ontem = local(2026, 10, 15).date()
        dias = dias_uteis(ontem, 25)  # 5 atuais + 20 de base
        for i, d in enumerate(dias):
            quando = local(d.year, d.month, d.day)
            atual = i >= 20
            pedido(loja, quando, [('Queridinha', queridinha_atual if atual else 4, 36.99, 14)])
            q = almondega_atual if atual else 2
            if q:
                pedido(loja, quando, [('Almôndega Premium', q, 44.99, 20)])

    def test_sabor_que_despencou_vira_aviso(self, loja):
        self._historico(loja, almondega_atual=0)

        fatos = regras.sabor_em_queda(loja, self.AGORA)

        assert [f.dados['produto'] for f in fatos] == ['Almôndega Premium']
        f = fatos[0]
        assert f.grupo == 'sabor_em_queda:almondega-premium'
        assert '100%' in f.texto or 'nenhuma' in f.texto.lower()

    def test_variacao_pequena_cala(self, loja):
        self._historico(loja, almondega_atual=2)
        assert regras.sabor_em_queda(loja, self.AGORA) == []

    def test_base_pequena_cala(self, loja):
        ontem = local(2026, 10, 15).date()
        for d in dias_uteis(ontem, 25)[:20:4]:  # 5 unidades na base inteira
            pedido(loja, local(d.year, d.month, d.day), [('Salmão Sublime', 1, 52.9, 25)])
        assert regras.sabor_em_queda(loja, self.AGORA) == []

    def test_semana_com_feriado_compara_por_dia_aberto(self, loja):
        """Semana com 3 dias abertos e o mesmo ritmo por dia não é queda."""
        ontem = local(2026, 10, 15).date()
        base = dias_uteis(ontem - timedelta(days=7), 20)
        for d in base:
            pedido(loja, local(d.year, d.month, d.day), [('Queridinha', 4, 36.99, 14)])
        for d in (ontem, ontem - timedelta(days=1), ontem - timedelta(days=2)):
            pedido(loja, local(d.year, d.month, d.day), [('Queridinha', 4, 36.99, 14)])
        assert regras.sabor_em_queda(loja, self.AGORA) == []

    def test_no_maximo_dois_sabores(self, loja):
        ontem = local(2026, 10, 15).date()
        for i, d in enumerate(dias_uteis(ontem, 25)):
            quando = local(d.year, d.month, d.day)
            if i < 20:
                for nome in ('A Um', 'B Dois', 'C Tres', 'D Quatro'):
                    pedido(loja, quando, [(nome, 3, 30, 10)])
            else:
                pedido(loja, quando, [('Queridinha', 1, 36.99, 14)])
        assert len(regras.sabor_em_queda(loja, self.AGORA)) == 2

    def test_poucos_dias_abertos_na_semana_cala(self, loja):
        self._historico(loja, almondega_atual=0)
        StoreOrder.objects.filter(store=loja, created_at__date__gte=local(2026, 10, 13).date()).delete()
        assert regras.sabor_em_queda(loja, self.AGORA) == []


# ── Cliente fiel sumiu ────────────────────────────────────────────────────

class TestFielSumiu:
    AGORA = local(2026, 10, 19, 8, 0)  # segunda

    def _cliente(self, loja, telefone, nome, ultimos_dias_atras, intervalo, vezes=4):
        hoje = self.AGORA
        for k in range(vezes):
            pedido(loja, hoje - timedelta(days=ultimos_dias_atras + k * intervalo),
                   [('Queridinha', 1, 36.99, 14)], telefone=telefone, nome=nome)

    def test_quem_pedia_toda_semana_e_parou_aparece(self, loja):
        self._cliente(loja, '5563911110001', 'Raquel', ultimos_dias_atras=20, intervalo=7)
        self._cliente(loja, '5563911110002', 'Pedro', ultimos_dias_atras=5, intervalo=7)

        fatos = regras.fiel_sumiu(loja, self.AGORA)

        assert len(fatos) == 1
        nomes = [c['nome'] for c in fatos[0].dados['clientes']]
        assert nomes == ['Raquel']
        assert 'Raquel' in fatos[0].texto
        assert fatos[0].chave == 'fiel_sumiu:2026-W43'

    def test_cliente_de_um_pedido_so_nao_e_fiel(self, loja):
        self._cliente(loja, '5563911110003', 'Ana', ultimos_dias_atras=30, intervalo=7, vezes=1)
        assert regras.fiel_sumiu(loja, self.AGORA) == []

    def test_sumido_ha_muito_tempo_ja_nao_e_alerta(self, loja):
        self._cliente(loja, '5563911110004', 'Bia', ultimos_dias_atras=90, intervalo=7)
        assert regras.fiel_sumiu(loja, self.AGORA) == []

    def test_mesmo_cliente_com_telefone_em_formatos_diferentes(self, loja):
        hoje = self.AGORA
        for k, tel in enumerate(['+55 (63) 91111-0005', '5563911110005', '63911110005']):
            pedido(loja, hoje - timedelta(days=21 + 7 * k), [('Queridinha', 1, 36.99, 14)],
                   telefone=tel, nome='Lia')
        fatos = regras.fiel_sumiu(loja, self.AGORA)
        assert [c['nome'] for c in fatos[0].dados['clientes']] == ['Lia']

    def test_lista_no_maximo_tres_nomes(self, loja):
        for i in range(5):
            self._cliente(loja, f'556391111010{i}', f'C{i}', ultimos_dias_atras=20 + i, intervalo=7)
        f = regras.fiel_sumiu(loja, self.AGORA)[0]
        assert f.dados['total'] == 5
        assert len(f.dados['clientes']) == 3
        assert '+2' in f.texto


# ── Custo e margem ────────────────────────────────────────────────────────

class TestCustoEMargem:
    AGORA = local(2026, 10, 19, 8, 0)

    def test_sabor_sem_custo_com_receita_relevante(self, loja):
        for d in range(1, 6):
            pedido(loja, self.AGORA - timedelta(days=d),
                   [('Queridinha', 3, 36.99, 14), ('Tilápia Suprema', 2, 46.99, None)])
        f = regras.sem_custo(loja, self.AGORA)
        assert len(f) == 1
        assert f[0].dados['produtos'] == ['Tilápia Suprema']
        assert '%' in f[0].texto

    def test_tudo_com_custo_cala(self, loja):
        pedido(loja, self.AGORA - timedelta(days=1), [('Queridinha', 3, 36.99, 14)])
        assert regras.sem_custo(loja, self.AGORA) == []

    def test_margem_baixa_com_volume(self, loja):
        for d in range(1, 7):
            pedido(loja, self.AGORA - timedelta(days=d), [('Magnífico Camarão', 1, 34.90, 25)])
        f = regras.margem_baixa(loja, self.AGORA)
        assert [x.dados['produto'] for x in f] == ['Magnífico Camarão']
        assert '28%' in f[0].texto

    def test_margem_baixa_sem_volume_cala(self, loja):
        for d in range(1, 4):
            pedido(loja, self.AGORA - timedelta(days=d), [('Magnífico Camarão', 1, 34.90, 25)])
        assert regras.margem_baixa(loja, self.AGORA) == []


# ── Nenhum pedido hoje (alerta) ───────────────────────────────────────────

class TestSemPedidoHoje:
    AGORA = local(2026, 10, 15, 12, 40)  # quinta

    def _quintas_movimentadas(self, loja, antes_do_meio_dia=5):
        for semanas in range(1, 5):
            dia = self.AGORA - timedelta(days=7 * semanas)
            for k in range(antes_do_meio_dia):
                pedido(loja, dia.replace(hour=11, minute=k), [('Queridinha', 1, 36.99, 14)])

    def test_quinta_sem_nenhum_pedido_ate_meio_dia_e_meia(self, loja):
        self._quintas_movimentadas(loja)
        f = regras.sem_pedido_hoje(loja, self.AGORA, hora_alerta=time(12, 30))
        assert len(f) == 1
        assert f[0].chave == 'sem_pedido:2026-10-15'
        assert '5' in f[0].texto

    def test_um_pedido_hoje_cala(self, loja):
        self._quintas_movimentadas(loja)
        pedido(loja, self.AGORA.replace(hour=11), [('Queridinha', 1, 36.99, 14)], pago=False)
        assert regras.sem_pedido_hoje(loja, self.AGORA, hora_alerta=time(12, 30)) == []

    def test_antes_da_hora_cala(self, loja):
        self._quintas_movimentadas(loja)
        cedo = self.AGORA.replace(hour=11, minute=0)
        assert regras.sem_pedido_hoje(loja, cedo, hora_alerta=time(12, 30)) == []

    def test_depois_das_15h_ja_nao_adianta(self, loja):
        self._quintas_movimentadas(loja)
        tarde = self.AGORA.replace(hour=15, minute=30)
        assert regras.sem_pedido_hoje(loja, tarde, hora_alerta=time(12, 30)) == []

    def test_dia_que_normalmente_e_fraco_cala(self, loja):
        self._quintas_movimentadas(loja, antes_do_meio_dia=1)
        assert regras.sem_pedido_hoje(loja, self.AGORA, hora_alerta=time(12, 30)) == []
