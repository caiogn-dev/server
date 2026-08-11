from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from apps.nutrition.models import NutritionIngredient, ProductNutritionProfile, ProductRecipe, RecipeItem
from apps.nutrition.services.calculator import calculate_recipe
from apps.nutrition.services.description_parser import ALIASES, format_recipe_description, normalize, parse_raw_components
from apps.stores.models import StoreProduct


AGRIAO_COMPONENTS = {
    "Assadinho de panela com arroz, feijão preto e couve.": [("carne bovina cozida", 120), ("arroz branco", 130), ("couve refogada", 40), ("feijão preto", 40)],
    "Bobó de Frango e arroz": [("bobó de frango", 180), ("arroz branco", 100), ("cenoura", 40)],
    "Coxa e sobre coxa grelhada ao molho 3 queijo com legumes": [("coxa e sobrecoxa grelhada", 120), ("legumes salteados", 80), ("arroz branco", 110), ("molho três queijos", 40)],
    "Escondidinho de Patinho com purê de Banana-da-Terra": [("patinho moído", 120), ("purê de banana-da-terra", 160), ("queijo muçarela", 20)],
    "Escondidinho de frango com purê de banana-da-terra": [("frango desfiado", 120), ("purê de banana-da-terra", 160), ("muçarela zero lactose", 20)],
    "Talharim ao molho bolonhesa e queijo mussarela 440G": [("talharim cozido", 200), ("molho bolonhesa com patinho", 220), ("queijo muçarela", 20)],
    "Escondidinho de frango com purê de batata": [("purê de batata inglesa", 160), ("frango desfiado", 120), ("muçarela zero lactose", 20)],
    "Escondidinho de frango e purê de mandioca": [("purê de mandioca", 160), ("frango desfiado", 130)],
    "Escondidinho de patinho com purê de mandioca": [("purê de mandioca", 160), ("patinho moído", 130)],
    "Escondidinho de patinho e purê de batata.": [("patinho moído", 120), ("purê de batata inglesa", 160), ("muçarela zero lactose", 20)],
    "Estrogonofe de frango com arroz branco e brócolis.": [("estrogonofe de frango", 160), ("arroz branco", 130), ("brócolis", 30)],
    "Filé de frango grelhado com arroz branco e creme de milho": [("filé de frango grelhado", 130), ("arroz branco", 130), ("creme de milho", 80)],
    "Parmegiana de frango com arroz integral e purê de batata": [("filé de frango à parmegiana", 120), ("arroz integral", 100), ("purê de batata inglesa", 130), ("queijo muçarela", 30)],
    "Picadinho de panela com mandioca, couve e arroz": [("picadinho de panela", 120), ("mandioca cozida", 60), ("couve com alho", 30), ("arroz branco", 100)],
    "Carne desfiada com arroz branco e feijão carioca e couve flor": [("carne desfiada", 120), ("arroz branco", 110), ("couve-flor", 20), ("feijão carioca", 80)],
    "Carne desfiada com arroz branco e feijão preto e couve": [("carne desfiada", 120), ("arroz branco", 110), ("couve refogada", 20), ("feijão preto", 80)],
    "Carne desfiada com arroz branco e feijão preto e couve flor": [("carne desfiada", 120), ("arroz branco", 110), ("couve-flor", 20), ("feijão preto", 80)],
    "Patinho moído, arroz, brócolis gratinado": [("patinho moído", 120), ("arroz branco", 130), ("brócolis gratinado", 80)],
}


def resolve_global(raw_name, globals_by_name):
    raw = normalize(raw_name)
    candidates = []
    for alias, display in ALIASES.items():
        if raw == alias or raw in alias or alias in raw:
            candidates.append((abs(len(raw) - len(alias)), -len(alias), display))
    if not candidates:
        return None
    return globals_by_name.get(min(candidates)[2])


class Command(BaseCommand):
    help = "Estrutura receitas de descrições com pesos; pendências viram ingredientes da loja sem valores inventados."

    def add_arguments(self, parser):
        parser.add_argument("--store", action="append", dest="stores", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--standardize-descriptions", action="store_true")
        parser.add_argument("--detail", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        detail = options["detail"] or options.get("verbosity", 1) >= 2
        products = StoreProduct.objects.filter(store__slug__in=options["stores"], is_active=True).exclude(description="").select_related("store")
        globals_by_name = {item.display_name: item for item in NutritionIngredient.objects.filter(store__isnull=True, is_active=True)}
        stats = {"analyzed": 0, "structured": 0, "existing": 0, "placeholders": 0, "descriptions": 0, "insufficient": 0}
        for product in products:
            stats["analyzed"] += 1
            if product.store.slug == "agriao-comida-saudavel":
                declared = AGRIAO_COMPONENTS.get(product.name, [])
                components = [{"raw_name": name, "quantity_g": Decimal(str(quantity)), "position": index} for index, (name, quantity) in enumerate(declared)]
            else:
                if "salada" not in (product.tags or []):
                    stats["insufficient"] += 1
                    continue
                components = parse_raw_components(product.description)
            if len(components) < 2:
                stats["insufficient"] += 1
                continue
            existing = ProductRecipe.objects.filter(product=product).first()
            if existing:
                stats["existing"] += 1
            if detail:
                self.stdout.write(f"ESTRUTURAR | {product.store.slug} | {product.name} | " + ", ".join(f"{row['raw_name']}={row['quantity_g']}g" for row in components))
            if not options["apply"]:
                continue
            if options["standardize_descriptions"]:
                standardized = format_recipe_description(product.name, components, product.description)
                if standardized != product.description:
                    product.description = standardized
                    product.save(update_fields=("description", "updated_at"))
                    stats["descriptions"] += 1
            if existing:
                continue
            resolved = []
            for row in components:
                ingredient = resolve_global(row["raw_name"], globals_by_name)
                if ingredient is None:
                    canonical = normalize(row["raw_name"])
                    ingredient, created = NutritionIngredient.objects.get_or_create(
                        store=product.store, canonical_name=canonical, preparation_state="",
                        defaults={"display_name": row["raw_name"].strip().capitalize(), "category": "pendente",
                                  "source": NutritionIngredient.Source.MANUAL,
                                  "notes": "Criado da descrição do produto. Preencher fonte e valores por 100 g antes de aprovar a impressão."},
                    )
                    stats["placeholders"] += int(created)
                resolved.append((ingredient, row))
            total = sum((row["quantity_g"] for _, row in resolved), start=0)
            recipe = ProductRecipe.objects.create(
                product=product, serving_size_g=total, prepared_weight_g=total,
                status=ProductRecipe.Status.ESTIMATED,
                source_notes="Estruturada da descrição; ingredientes pendentes permanecem sem valor, nunca como zero.",
            )
            RecipeItem.objects.bulk_create([
                RecipeItem(recipe=recipe, ingredient=ingredient, quantity_g=row["quantity_g"], sort_order=index)
                for index, (ingredient, row) in enumerate(resolved)
            ])
            calculated = calculate_recipe(recipe)
            ProductNutritionProfile.objects.create(
                product=product, recipe=recipe, serving_size_g=total,
                value_source=ProductNutritionProfile.ValueSource.CALCULATED,
                is_print_approved=False, **calculated["per_100g"],
            )
            stats["structured"] += 1
        self.stdout.write(self.style.SUCCESS(" | ".join(f"{key}={value}" for key, value in stats.items())))
