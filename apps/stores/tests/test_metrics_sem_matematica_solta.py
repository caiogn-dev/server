"""Catraca: a matemática de dinheiro solta só pode DIMINUIR.

A fragmentação não voltou por má-fé — voltou porque escrever `Sum('total')` na
view era mais rápido que procurar onde ficava a regra. Seis arquivos fizeram
isso e o painel passou a mostrar três números diferentes para o mesmo dia. Code
review não pegou em nenhuma das vezes.

O ideal seria zero cálculo fora de `apps/stores/metrics/`. Hoje são 61
ocorrências em 17 arquivos — a migração está em andamento e leva horas de
verificação por relatório, porque cada um dos 20 relatórios de
`analytics_views.py` precisa ser conferido individualmente contra a saída atual.

Então a regra não é "zero". A regra é: **nunca mais aumentar**. O número de cada
arquivo está congelado em `divida_de_metricas.json`. Se você:

- adicionar cálculo num arquivo da lista  -> o teste falha;
- criar um arquivo novo com cálculo       -> o teste falha;
- migrar um arquivo para o núcleo         -> o teste manda apertar a catraca.

Assim a dívida vira um número que só anda para baixo, e o próximo a mexer aqui
sabe exatamente quanto falta.
"""
import json
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[3]
APPS = RAIZ / 'apps'
NUCLEO = APPS / 'stores' / 'metrics'
BASELINE = Path(__file__).parent / 'divida_de_metricas.json'

PROIBIDOS = [
    (
        re.compile(r"Sum\(\s*['\"]total['\"]"),
        "Sum('total') solto — use metrics.totais() ou metrics.serie_temporal()",
    ),
    (
        re.compile(r"payment_status\s*=\s*['\"]paid['\"]"),
        "payment_status='paid' não é a regra de receita (falta excluir "
        "cancelado, estornado e pedido de teste) — use metrics.apenas_receita()",
    ),
    (
        re.compile(r"\.replace\(\s*hour\s*=\s*0"),
        "início de dia à mão — em UTC vira 21h do dia anterior; "
        "use metrics.inicio_do_dia()",
    ),
    (
        re.compile(r"timezone\.now\(\)\.date\(\)"),
        "data em UTC, não no fuso da loja — use metrics.hoje_local()",
    ),
]

# Migrações são histórico congelado; testes montam cenário na mão.
IGNORADOS = {'migrations', 'tests'}


def _contar_por_arquivo():
    contagem = {}
    for caminho in sorted(APPS.rglob('*.py')):
        if NUCLEO in caminho.parents or IGNORADOS & set(caminho.parts):
            continue
        n = 0
        for linha in caminho.read_text(encoding='utf-8', errors='ignore').split('\n'):
            if linha.lstrip().startswith('#'):
                continue
            if any(padrao.search(linha) for padrao, _ in PROIBIDOS):
                n += 1
        if n:
            contagem[str(caminho.relative_to(RAIZ)).replace('\\', '/')] = n
    return contagem


class CatracaDaMatematicaDeDinheiroTests(SimpleTestCase):
    def setUp(self):
        self.baseline = json.loads(BASELINE.read_text())
        self.atual = _contar_por_arquivo()

    def test_nenhum_arquivo_novo_calcula_dinheiro_por_conta_propria(self):
        novos = sorted(set(self.atual) - set(self.baseline))
        self.assertEqual(
            novos, [],
            'arquivo novo calculando faturamento fora de apps/stores/metrics/:\n  '
            + '\n  '.join(novos)
            + '\n\nSe o número precisa existir, ele nasce no núcleo — aí todas as '
              'telas ganham juntas e não divergem.',
        )

    def test_nenhum_arquivo_piorou(self):
        piores = [
            f'  {arq}: {self.baseline[arq]} -> {qtd}'
            for arq, qtd in sorted(self.atual.items())
            if arq in self.baseline and qtd > self.baseline[arq]
        ]
        self.assertEqual(
            piores, [],
            'a dívida de métricas aumentou nestes arquivos:\n' + '\n'.join(piores),
        )

    def test_catraca_aperta_quando_a_divida_cai(self):
        """Migrou um arquivo? Atualize o baseline — senão a catraca afrouxa sozinha."""
        melhores = [
            f'  {arq}: {self.baseline[arq]} -> {self.atual.get(arq, 0)}'
            for arq in sorted(self.baseline)
            if self.atual.get(arq, 0) < self.baseline[arq]
        ]
        self.assertEqual(
            melhores, [],
            'boa notícia: a dívida caiu. Rode para congelar o novo patamar:\n\n'
            '  python -c "'
            'import apps.stores.tests.test_metrics_sem_matematica_solta as t, json;'
            'open(t.BASELINE,\'w\').write(json.dumps(t._contar_por_arquivo(),'
            'indent=2,sort_keys=True)+chr(10))"\n\n'
            + '\n'.join(melhores),
        )

    def test_o_nucleo_exporta_o_essencial(self):
        from apps.stores import metrics

        for nome in ('totais', 'serie_temporal', 'serie_completa',
                     'pedidos_de_receita', 'apenas_receita', 'contagem_operacional',
                     'hoje', 'hoje_local', 'inicio_do_dia', 'ultimos_dias'):
            self.assertTrue(
                hasattr(metrics, nome), f'apps.stores.metrics não expõe {nome}',
            )
