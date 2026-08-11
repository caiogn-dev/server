from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.nutrition.models import NUTRIENT_FIELDS, NutritionIngredient, ProductNutritionProfile, RecipeItem
from apps.nutrition.services.calculator import calculate_recipe
from apps.stores.models import StoreProduct


REFERENCE = "https://nepa.unicamp.br/publicacoes/tabela-taco-excel/"

# TACO/NEPA-Unicamp, 4ª edição, valores por 100 g. Cebola roxa e batata
# palha usam o alimento TACO mais próximo e permanecem identificadas como
# aproximações. Campos ausentes na TACO não são convertidos em zero.
ROWS = {
    "milho": ("Milho, verde, enlatado, drenado", 97.5649, 17.1351, 3.2283, 2.3533, 4.6433, 260.3499, False),
    "gergelim": ("Gergelim, semente", 583.5467, 21.6177, 21.1647, 50.4327, 11.8683, 2.5750, False),
    "cebola roxa": ("Cebola, crua", 39.4200, 8.8532, 1.7101, 0.0800, 2.1867, 0.5967, True),
    "batata palha": ("Batata, frita, tipo chips, industrializada", 542.7347, 51.2223, 5.5833, 36.6150, 2.4557, 607.3993, True),
}

QUERIDINHA_600G = (
    ("Frango cozido", 200),
    ("Alface", 150),
    ("Cenoura", 50),
    ("milho", 50),
    ("Abobrinha", 50),
    ("batata palha", 50),
    ("cebola roxa", 50),
)


class Command(BaseCommand):
    help = "Completa ingredientes das saladas com referências TACO rastreáveis e recalcula os perfis."

    @transaction.atomic
    def handle(self, *args, **options):
        store_slug = "ce-saladas"
        updated = 0
        for canonical, row in ROWS.items():
            source_name, kcal, carbs, protein, fat, fiber, sodium, approximate = row
            ingredient, _ = NutritionIngredient.objects.get_or_create(
                store__slug=store_slug,
                canonical_name=canonical,
                preparation_state="",
                defaults={"store": StoreProduct.objects.filter(store__slug=store_slug).first().store,
                          "display_name": canonical.capitalize()},
            )
            ingredient.category = "vegetais" if canonical in {"milho", "cebola roxa"} else "complementos"
            ingredient.source = NutritionIngredient.Source.TACO
            ingredient.source_code = source_name
            ingredient.source_edition = "4ª edição revisada e ampliada, 2011"
            ingredient.source_reference = REFERENCE
            ingredient.source_accessed_at = date.today()
            qualifier = "aproximação pelo alimento mais próximo" if approximate else "correspondência direta"
            ingredient.notes = f"TACO: {source_name}; {qualifier}. Valores por 100 g."
            ingredient.energy_kcal = Decimal(str(kcal))
            ingredient.carbohydrates_g = Decimal(str(carbs))
            ingredient.protein_g = Decimal(str(protein))
            ingredient.total_fat_g = Decimal(str(fat))
            ingredient.fiber_g = Decimal(str(fiber))
            ingredient.sodium_mg = Decimal(str(sodium))
            ingredient.save()
            updated += 1

        # Ficha técnica “QUERIDINHA” enviada pelo responsável em 11/08/2026.
        # O molho permanece fora do peso/cálculo porque a ficha informa apenas
        # o custo, sem quantidade em gramas nem receita.
        product = StoreProduct.objects.get(store__slug=store_slug, name="Queridinha")
        recipe = product.nutrition_recipe
        ingredients = []
        for ingredient_name, quantity in QUERIDINHA_600G:
            ingredient = (
                NutritionIngredient.objects.filter(store=product.store, canonical_name=ingredient_name).first()
                or NutritionIngredient.objects.get(store__isnull=True, display_name=ingredient_name)
            )
            ingredients.append((ingredient, Decimal(str(quantity))))
        recipe.items.all().delete()
        RecipeItem.objects.bulk_create([
            RecipeItem(recipe=recipe, ingredient=ingredient, quantity_g=quantity, sort_order=index)
            for index, (ingredient, quantity) in enumerate(ingredients)
        ])
        recipe.serving_size_g = Decimal("600")
        recipe.prepared_weight_g = Decimal("600")
        recipe.status = recipe.Status.ESTIMATED
        recipe.source_notes = (
            "Ficha técnica QUERIDINHA (Google Sheets, recebida em 11/08/2026). "
            "Molho não incluído: ficha informa custo, mas não peso ou composição."
        )
        recipe.save()
        product.description = "\n".join([
            "- Frango desfiado 200 g",
            "- Alface 150 g",
            "- Cenoura 50 g",
            "- Milho 50 g",
            "- Abobrinha 50 g",
            "- Batata palha 50 g",
            "- Cebola roxa 50 g",
            "",
            "*Porção total cadastrada: 600 g*",
            "*Acompanha molho de mostarda e mel; peso e composição do molho pendentes.*",
        ])
        product.save(update_fields=("description", "updated_at"))

        recalculated = 0
        for profile in ProductNutritionProfile.objects.filter(product__store__slug=store_slug, recipe__isnull=False):
            calculation = calculate_recipe(profile.recipe)
            if profile.value_source == ProductNutritionProfile.ValueSource.CALCULATED:
                for field in NUTRIENT_FIELDS:
                    setattr(profile, field, calculation["per_100g"][field])
                profile.is_print_approved = False
                profile.serving_size_g = profile.recipe.serving_size_g
                profile.save()
                recalculated += 1
        self.stdout.write(self.style.SUCCESS(f"ingredientes_atualizados={updated} | perfis_recalculados={recalculated}"))
