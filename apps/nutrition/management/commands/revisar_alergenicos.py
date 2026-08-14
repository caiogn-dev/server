"""
Revisa alergênicos em lote, pela linha de comando.

Mesma regra da tela: alimento oficial não é editável, então a loja adota uma
cópia antes de gravar; e "sem alergênico" é uma AFIRMAÇÃO, nunca um padrão.

Existe porque o gargalo do nutricional é humano, não técnico: enquanto houver
um ingrediente não revisado numa receita, a etiqueta dela não declara nada —
nem para dizer que não contém.

O comando separa o que dá para afirmar em bloco do que exige decisão. A
separação é por PALAVRA NO NOME, e por isso é conservadora: qualquer suspeita
manda o ingrediente para a lista de decisão manual. Errar para o lado de
perguntar demais custa tempo; errar para o outro manda alguém ao hospital.

Usage:
    python manage.py revisar_alergenicos --loja ce-saladas
    python manage.py revisar_alergenicos --loja ce-saladas --sem-alergenico --aplicar
"""
import logging
import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.nutrition.models import IngredientComponent  # noqa: F401  (garante o app carregado)
from apps.nutrition.models import NutritionIngredient, RecipeItem
from apps.stores.models import Store

logger = logging.getLogger(__name__)

# Palavra no nome que obriga decisão humana. Não é a lista da RDC: é a lista
# do que costuma APARECER em nome de ingrediente e carrega alergênico.
SUSPEITAS = {
    "leite": ("leite", "queijo", "mucarela", "muçarela", "requeijao", "requeijão", "creme",
              "manteiga", "iogurte", "nata", "cream", "gorgonzola", "parmesao", "parmesão",
              "brie", "provolone", "ricota", "chantilly", "doce de leite", "condensado"),
    "trigo": ("trigo", "farinha", "macarrao", "macarrão", "penne", "pao", "pão", "massa",
              "biscoito", "bolo", "torrada", "empanado", "milanesa", "lasanha", "nhoque",
              "cuscuz", "aveia", "cevada", "centeio", "malte", "cerveja"),
    "ovo": ("ovo", "maionese", "merengue", "gemada"),
    "soja": ("soja", "shoyu", "tofu", "missô", "misso"),
    "peixe": ("peixe", "salmao", "salmão", "tilapia", "tilápia", "bacalhau", "atum",
              "sardinha", "pirarucu", "anchova"),
    "crustaceo": ("camarao", "camarão", "lagosta", "siri", "caranguejo", "crustaceo"),
    "castanha": ("castanha", "amendoa", "amêndoa", "noz", "nozes", "avela", "avelã",
                 "pistache", "macadamia", "macadâmia", "pecã", "peca", "amendoim"),
}

# Nome de PRATO que carrega alergênico pela receita, não pela palavra: entram
# como reforço, mas a trava de verdade é a regra de preparação abaixo.
PRATOS_SUSPEITOS = (
    "parmegiana", "parmigiana", "estrogonofe", "strogonoff", "estrogonof",
    "pure", "purê", "gratinado", "bechamel", "molho branco", "quatro queijos",
    "3 queijos", "tres queijos", "à milanesa", "a milanesa", "nhoque", "torta",
    "bobo", "bobó", "escondidinho", "lasanha", "empadao", "empadão", "quiche",
)


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def suspeitas_no_nome(nome):
    """Grupos alergênicos que o NOME sugere. Vazio não prova ausência."""
    limpo = _sem_acento(nome)
    achados = []
    for grupo, palavras in SUSPEITAS.items():
        if any(re.search(rf"\b{re.escape(_sem_acento(p))}", limpo) for p in palavras):
            achados.append(grupo)
    if not achados and any(_sem_acento(p) in limpo for p in PRATOS_SUSPEITOS):
        achados.append("preparo")
    return achados


def e_preparacao_da_loja(ing):
    """Prato feito pela loja, e não alimento íntegro de tabela oficial.

    A heurística de nome funciona para ingrediente único — "leite" tem leite,
    "alface" não tem nada. Ela NÃO funciona para prato: os alergênicos de uma
    parmegiana vêm da receita (queijo, empanado, ovo), e nenhuma palavra do
    nome denuncia isso. "Estrogonofe" tem creme de leite; "purê" tem leite e
    manteiga.

    Então preparação da loja nunca entra no bloco automático, por mais
    inocente que o nome pareça. É a diferença entre errar para o lado de
    perguntar e errar para o lado de alguém passar mal.
    """
    return ing.store_id is not None and ing.source not in ("taco", "pof", "tbca")


class Command(BaseCommand):
    help = "Revisa alergênicos dos ingredientes usados em receita, em lote"

    def add_arguments(self, parser):
        parser.add_argument("--loja", required=True, help="Slug da loja")
        parser.add_argument("--sem-alergenico", action="store_true",
                            help="Marca como revisado, SEM alergênico, os que o nome não levanta suspeita")
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        try:
            loja = Store.objects.get(slug=options["loja"])
        except Store.DoesNotExist:
            raise CommandError(f"Loja {options['loja']} não encontrada")

        pendentes = list(NutritionIngredient.objects.filter(
            allergens_reviewed=False,
            recipe_items__recipe__product__store=loja,
        ).distinct().order_by("display_name"))

        if not pendentes:
            self.stdout.write(self.style.SUCCESS("✅ Nada pendente nesta loja."))
            return

        limpos, decidir = [], []
        for ing in pendentes:
            suspeito = bool(suspeitas_no_nome(ing.display_name)) or e_preparacao_da_loja(ing)
            (decidir if suspeito else limpos).append(ing)

        self.stdout.write(f"\n🟢 {len(limpos)} sem suspeita no nome (candidatos a 'sem alergênico'):")
        for ing in limpos:
            origem = "oficial" if ing.store_id is None else "da loja"
            self.stdout.write(f"    {ing.display_name[:52]:54} [{origem}]")

        self.stdout.write(self.style.WARNING(f"\n🔴 {len(decidir)} precisam da SUA decisão:"))
        for ing in decidir:
            grupos = ", ".join(suspeitas_no_nome(ing.display_name))
            motivo = grupos or "preparação da loja — depende da receita"
            self.stdout.write(f"    {ing.display_name[:44]:46} → {motivo}")

        if not options["sem_alergenico"]:
            self.stdout.write(self.style.WARNING(
                "\nNada gravado. Para confirmar os 🟢 como SEM alergênico:\n"
                f"  --loja {options['loja']} --sem-alergenico --aplicar\n"
                "Os 🔴 continuam pendentes de propósito — marque cada um pelo painel."))
            return

        if not options["aplicar"]:
            self.stdout.write(self.style.WARNING(f"\nFaltou --aplicar. {len(limpos)} seriam marcados."))
            return

        marcados = self._marcar(limpos, loja)
        self.stdout.write(self.style.SUCCESS(f"\n✅ {marcados} marcados como revisados, sem alergênico"))
        self.stdout.write(f"   Restam {len(decidir)} para você decidir um a um.")

    @transaction.atomic
    def _marcar(self, ingredientes, loja):
        marcados = 0
        for ing in ingredientes:
            alvo = ing
            if ing.store_id is None:
                # Oficial é somente leitura e compartilhado: a loja revisa numa
                # cópia sua, e as receitas dela passam a apontar para a cópia.
                alvo = NutritionIngredient.objects.filter(
                    store=loja, canonical_name=ing.canonical_name,
                    preparation_state=ing.preparation_state).first()
                if not alvo:
                    alvo = NutritionIngredient.objects.get(pk=ing.pk)
                    alvo.pk = None
                    alvo.store = loja
                    alvo.notes = (f"{ing.notes}\nCópia de {ing.get_source_display()} "
                                  f"#{ing.source_code} adotada para revisão de alergênico.").strip()
                    alvo.save()
                RecipeItem.objects.filter(
                    ingredient=ing, recipe__product__store=loja).update(ingredient=alvo)

            alvo.allergens = []
            alvo.allergens_reviewed = True
            alvo.save(update_fields=["allergens", "allergens_reviewed", "updated_at"])
            marcados += 1
        return marcados
