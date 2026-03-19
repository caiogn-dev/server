"""
seed_salad_ingredients
======================
Cria 1 ingrediente de cada etapa do SaladBuilder para o store ce-saladas.

Uso:
    python manage.py seed_salad_ingredients
    python manage.py seed_salad_ingredients --store ce-saladas

Cada produto recebe:
- A categoria correta (criada se não existir)
- Tags ["ingrediente", "<step>"] — o frontend usa isso para rotear ao section
  'ingredientes' e ao step correto no SaladBuilder

Steps criados:
  base         → Rúcula Fresca (R$ 2,00)
  proteina     → Frango Grelhado (R$ 8,00)
  complemento  → Tomate Cereja (R$ 3,00)
  molho        → Molho Tahini (R$ 4,00)  — tag "ingrediente" garante que vai para
                 section 'ingredientes' mesmo com "molho" no nome
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


INGREDIENTS = [
    {
        "step": "base",
        "category_name": "Ingrediente - Base",
        "category_slug": "ingrediente-base",
        "name": "Rúcula Fresca",
        "slug": "rucula-fresca",
        "description": "Base verde crocante com sabor levemente apimentado.",
        "short_description": "Base verde e crocante",
        "price": "2.00",
        "sort_order": 10,
        "tags": ["ingrediente", "base"],
    },
    {
        "step": "proteina",
        "category_name": "Ingrediente - Proteína",
        "category_slug": "ingrediente-proteina",
        "name": "Frango Grelhado",
        "slug": "frango-grelhado",
        "description": "Peito de frango temperado e grelhado na hora.",
        "short_description": "Frango temperado e grelhado",
        "price": "8.00",
        "sort_order": 20,
        "tags": ["ingrediente", "proteina"],
    },
    {
        "step": "complemento",
        "category_name": "Ingrediente - Complemento",
        "category_slug": "ingrediente-complemento",
        "name": "Tomate Cereja",
        "slug": "tomate-cereja",
        "description": "Tomates cereja frescos, doces e coloridos.",
        "short_description": "Tomatinhos frescos",
        "price": "3.00",
        "sort_order": 30,
        "tags": ["ingrediente", "complemento"],
    },
    {
        "step": "molho",
        # Tag "ingrediente" (not "molho") ensures inferCatalogSection routes this
        # to the 'ingredientes' section so SaladBuilder receives it.
        # The name "Molho …" makes inferIngredientStep classify it as 'molho' step.
        "category_name": "Ingrediente - Molho",
        "category_slug": "ingrediente-molho",
        "name": "Molho Tahini",
        "slug": "molho-tahini",
        "description": "Molho cremoso à base de gergelim, limão e alho.",
        "short_description": "Molho cremoso de gergelim",
        "price": "4.00",
        "sort_order": 40,
        "tags": ["ingrediente"],  # NOT "molho" tag — avoids inferCatalogSection routing to 'molhos'
    },
]


class Command(BaseCommand):
    help = "Seed 1 ingredient per SaladBuilder step for the given store."

    def add_arguments(self, parser):
        parser.add_argument(
            "--store",
            default="ce-saladas",
            help="Store slug (default: ce-saladas)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created without saving",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.stores.models import Store, StoreProduct
        from apps.stores.models.category import StoreCategory

        store_slug = options["store"]
        dry_run = options["dry_run"]

        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            raise CommandError(
                f"Store '{store_slug}' not found. "
                f"Available: {list(Store.objects.values_list('slug', flat=True))}"
            )

        self.stdout.write(f"Store: {store.name} ({store.slug})")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be saved"))

        created_count = 0
        skipped_count = 0

        for ingredient in INGREDIENTS:
            step = ingredient["step"]

            # Get or create category
            category, cat_created = StoreCategory.objects.get_or_create(
                store=store,
                slug=ingredient["category_slug"],
                defaults={
                    "name": ingredient["category_name"],
                    "description": f"Ingredientes do tipo {ingredient['category_name'].replace('Ingrediente - ', '')}",
                    "is_active": True,
                    "sort_order": ingredient["sort_order"],
                },
            )

            if cat_created and not dry_run:
                self.stdout.write(f"  [+] Category created: {category.name}")
            else:
                self.stdout.write(f"  [=] Category exists:  {category.name}")

            # Check if product already exists
            existing = StoreProduct.objects.filter(
                store=store,
                slug=ingredient["slug"],
            ).first()

            if existing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [~] Product already exists: {existing.name} — skipped"
                    )
                )
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [dry] Would create: {ingredient['name']} "
                    f"(step={step}, price=R${ingredient['price']}, tags={ingredient['tags']})"
                )
                created_count += 1
                continue

            product = StoreProduct.objects.create(
                store=store,
                category=category,
                name=ingredient["name"],
                slug=ingredient["slug"],
                description=ingredient["description"],
                short_description=ingredient["short_description"],
                price=ingredient["price"],
                stock_quantity=999,
                track_stock=False,
                status=StoreProduct.ProductStatus.ACTIVE,
                tags=ingredient["tags"],
                sort_order=ingredient["sort_order"],
                featured=False,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  [+] Created: {product.name}  "
                    f"(step={step}, R${product.price}, tags={product.tags})"
                )
            )
            created_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created_count} created, {skipped_count} skipped."
            )
        )
        if not dry_run and created_count > 0:
            self.stdout.write(
                "→ Visit /cardapio and the 'Monte sua Salada' section should now "
                "show the ingredient builder with all 4 steps."
            )
