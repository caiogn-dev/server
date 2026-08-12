"""
Importa a Tabela de Composição Nutricional dos Alimentos Consumidos no Brasil
(POF 2008-2009, IBGE) para NutritionIngredient.

Por que ela e não só a TACO: a TACO mede alimento, a POF mede **o que o
brasileiro come**, e traz justamente as três colunas que faltavam para fechar
a etiqueta legal —

    açúcar de adição, gordura saturada e gordura trans

que são os três gatilhos da lupa frontal da RDC 429/2020 (com o sódio, que as
duas têm). Sem a POF, nenhuma receita conseguia concluir se leva selo.

A POF também trata **preparo como dimensão própria** ("CRU(A)", "COZIDO(A)",
"FRITO(A)"), o que encaixa direto em `preparation_state` — a mesma comida em
dois preparos vira duas linhas sem colidir na constraint.

A POF é uma compilação: cada linha cita a fonte original (TACO, USDA, IBGE) na
coluna de referência. Isso vai para as notas, porque quem for auditar a
etiqueta precisa conseguir voltar até a medição.

Arquivo: ftp.ibge.gov.br → Orcamentos_Familiares → POF 2008-2009 →
Tabelas_de_Composicao_Nutricional... → tabelacompleta.zip

Usage:
    python manage.py import_pof_table --arquivo /tmp/pof.xls --dry-run
    python manage.py import_pof_table --arquivo /tmp/pof.xls
"""
import logging
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.nutrition.models import NutritionIngredient

logger = logging.getLogger(__name__)

LINHA_CABECALHO = 3

COLUNAS = {
    "codigo": 0,
    "descricao": 1,
    "preparo": 3,
    "referencia": 5,
    "energy_kcal": 6,
    "protein_g": 7,
    "total_fat_g": 8,
    "carbohydrates_g": 9,
    "fiber_g": 10,
    "sodium_mg": 16,
    "saturated_fat_g": 35,
    "trans_fat_g": 40,
    "total_sugars_g": 41,
    "added_sugars_g": 42,
}
NUTRIENTES = ("energy_kcal", "protein_g", "total_fat_g", "carbohydrates_g", "fiber_g",
              "sodium_mg", "saturated_fat_g", "trans_fat_g", "total_sugars_g", "added_sugars_g")

# Notação oficial do IBGE, seção "Convenções" da publicação. A diferença entre
# o hífen e as reticências decide se a etiqueta consegue concluir:
#
#   -    dado numérico igual a ZERO, não resultante de arredondamento
#   ...  dado numérico NÃO DISPONÍVEL
#   ..   não se aplica
#   x    omitido para não individualizar a informação
#
# Tratar "-" como nulo (o erro óbvio) deixaria 1.520 alimentos sem açúcar de
# adição e nenhuma receita fecharia a lupa frontal — quando na verdade a POF
# está afirmando que o alimento não tem açúcar adicionado.
ZERO_MEDIDO = {"-"}
NAO_DISPONIVEL = {"", "...", "..", "x", "na", "nd", "*", "nao se aplica", "não se aplica"}

SEM_PREPARO = {"nao se aplica", "não se aplica"}


def _numero(bruto):
    if bruto is None:
        return None
    texto = str(bruto).strip()
    if texto in ZERO_MEDIDO:
        return Decimal("0")
    if texto.lower() in NAO_DISPONIVEL:
        return None
    try:
        valor = Decimal(texto.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    # Negativo em tabela de composição é erro de digitação da fonte, não dado.
    return valor if valor >= 0 else None


def _limpo(texto):
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _preparo(bruto):
    texto = _limpo(bruto)
    return "" if texto.lower() in SEM_PREPARO else texto[:80]


def _titulo(texto):
    """POF grava tudo em CAIXA ALTA; vira Título para caber na tela do painel."""
    return _limpo(texto).title()


class Command(BaseCommand):
    help = "Importa a tabela de composição da POF/IBGE para o cadastro de ingredientes"

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="Caminho do tabelacompleta.xls")
        parser.add_argument("--edicao", default="POF 2008-2009 (IBGE)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            import xlrd
        except ImportError:
            raise CommandError("xlrd não instalado (pip install xlrd) — necessário para .xls antigo.")

        try:
            aba = xlrd.open_workbook(options["arquivo"]).sheet_by_index(0)
        except FileNotFoundError:
            raise CommandError(f"Arquivo não encontrado: {options['arquivo']}")

        cabecalho = _limpo(aba.cell_value(LINHA_CABECALHO, COLUNAS["descricao"])).upper()
        if "DESCRIÇÃO DO ALIMENTO" not in cabecalho:
            raise CommandError(f"Layout inesperado: linha {LINHA_CABECALHO} coluna 1 = {cabecalho!r}. "
                               "O arquivo mudou de formato — confira antes de importar.")

        registros = self._ler(aba)
        self.stdout.write(f"📋 {len(registros)} combinações alimento × preparo lidas")

        com_acucar = sum(1 for r in registros if r["added_sugars_g"] is not None)
        com_saturada = sum(1 for r in registros if r["saturated_fat_g"] is not None)
        com_trans = sum(1 for r in registros if r["trans_fat_g"] is not None)
        self.stdout.write(f"   açúcar de adição: {com_acucar} | saturada: {com_saturada} | trans: {com_trans}")

        if options["dry_run"]:
            for r in registros[:5]:
                self.stdout.write(f"   ex.: [{r['source_code']}] {r['display_name'][:44]:44} "
                                  f"({r['preparation_state'] or 'sem preparo'}) "
                                  f"{r['energy_kcal']} kcal, açúcar add {r['added_sugars_g']}")
            self.stdout.write(self.style.WARNING("--dry-run: nada gravado."))
            return

        criados, atualizados = self._gravar(registros, options["edicao"])
        self.stdout.write(self.style.SUCCESS(f"\n✅ {criados} criados, {atualizados} atualizados"))
        self.stdout.write(self.style.WARNING(
            "⚠️  Alergênicos continuam não revisados: a POF também não traz esse dado."))

    def _ler(self, aba):
        registros, vistos = [], set()
        for linha in range(LINHA_CABECALHO + 1, aba.nrows):
            descricao = _limpo(aba.cell_value(linha, COLUNAS["descricao"]))
            if not descricao:
                continue

            preparo = _preparo(aba.cell_value(linha, COLUNAS["preparo"]))
            nome = _titulo(descricao)
            canonico = f"{nome} ({preparo})".lower() if preparo else nome.lower()

            # A POF repete o mesmo alimento×preparo quando muda a referência.
            # Fica a primeira: as demais são a mesma medição por outra fonte.
            chave = (canonico, preparo)
            if chave in vistos:
                continue
            vistos.add(chave)

            valores = {campo: _numero(aba.cell_value(linha, COLUNAS[campo])) for campo in NUTRIENTES}
            registros.append({
                "source_code": _limpo(aba.cell_value(linha, COLUNAS["codigo"])).replace(".0", "")[:80],
                "canonical_name": canonico[:255],
                "display_name": nome[:255],
                "preparation_state": preparo,
                "referencia": _limpo(aba.cell_value(linha, COLUNAS["referencia"])),
                **valores,
            })
        return registros

    @transaction.atomic
    def _gravar(self, registros, edicao):
        criados = atualizados = 0
        for r in registros:
            nota = (f"POF/IBGE {r['source_code']}. Fonte original da medição: "
                    f"{r['referencia']}." if r["referencia"] else f"POF/IBGE {r['source_code']}.")
            _, novo = NutritionIngredient.objects.update_or_create(
                store=None,
                canonical_name=r["canonical_name"],
                preparation_state=r["preparation_state"],
                defaults={
                    "display_name": r["display_name"],
                    "default_unit": "g",
                    "source": NutritionIngredient.Source.POF,
                    "source_code": r["source_code"],
                    "source_edition": edicao,
                    "notes": nota,
                    "is_active": True,
                    **{campo: r[campo] for campo in NUTRIENTES},
                },
            )
            criados += novo
            atualizados += not novo
        return criados, atualizados
