from django.core.management.base import BaseCommand
from django.db import transaction

from apps.nutrition.models import NutritionIngredient, ProductRecipe, RecipeItem
from apps.nutrition.services.description_parser import parse_weighted_ingredients
from apps.stores.models import StoreProduct


class Command(BaseCommand):
    help = "Analisa descrições e, com --apply, cria apenas receitas estimadas completas."

    def add_arguments(self, parser):
        parser.add_argument("--store", action="append", dest="stores", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--verbose", "-v", action="store_true", dest="detail")

    @transaction.atomic
    def handle(self, *args, **options):
        products = StoreProduct.objects.filter(store__slug__in=options["stores"], is_active=True).exclude(description="").select_related("store")
        ingredient_by_name = {i.display_name: i for i in NutritionIngredient.objects.filter(store__isnull=True, is_active=True)}
        stats = {"analyzed": 0, "ready": 0, "created": 0, "skipped_existing": 0, "ambiguous": 0}
        for product in products:
            stats["analyzed"] += 1
            if ProductRecipe.objects.filter(product=product).exists():
                stats["skipped_existing"] += 1
                continue
            parsed = parse_weighted_ingredients(product.description)
            resolved = [(ingredient_by_name.get(row["ingredient_name"]), row) for row in parsed["items"]]
            missing = [row["ingredient_name"] for ingredient, row in resolved if ingredient is None]
            if len(resolved) < 2 or parsed["unmatched_weights"] or missing:
                if parsed["items"] or parsed["unmatched_weights"]:
                    stats["ambiguous"] += 1
                    if options["detail"]:
                        self.stdout.write(f"PULAR | {product.store.slug} | {product.name} | pesos_sem_item={parsed['unmatched_weights']} | base_sem_item={missing}")
                continue
            stats["ready"] += 1
            total = sum((row["quantity_g"] for _, row in resolved), start=0)
            if options["detail"]:
                summary = ", ".join(f"{row['ingredient_name']}={row['quantity_g']}g" for _, row in resolved)
                self.stdout.write(f"PRONTO | {product.store.slug} | {product.name} | {summary}")
            if options["apply"]:
                recipe = ProductRecipe.objects.create(
                    product=product, serving_size_g=total, prepared_weight_g=total,
                    status=ProductRecipe.Status.ESTIMATED,
                    source_notes="Gerada da descrição do produto; revisar temperos, molhos e rendimento antes de aprovar para impressão.",
                )
                RecipeItem.objects.bulk_create([
                    RecipeItem(recipe=recipe, ingredient=ingredient, quantity_g=row["quantity_g"], sort_order=index)
                    for index, (ingredient, row) in enumerate(resolved)
                ])
                stats["created"] += 1
        self.stdout.write(self.style.SUCCESS(" | ".join(f"{key}={value}" for key, value in stats.items())))
