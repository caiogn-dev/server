"""
seed_salad_ingredients
======================
Popula todos os ingredientes do "Monte sua Salada" para a loja ce-saladas.

Uso:
    python manage.py seed_salad_ingredients
    python manage.py seed_salad_ingredients --store ce-saladas
    python manage.py seed_salad_ingredients --dry-run

Cada produto recebe:
- A categoria correta (criada se não existir)
- Tags ["ingrediente", "<step>"] — o frontend usa para rotear ao SaladBuilder

Steps:
  base        → Alface, Couve, Repolho
  proteina    → Frango Desfiado (R$34,90), Frango Filé, Almôndega, Tilápia, Salmão, Camarão
  complemento → todos os demais toppings
  molho       → Lemon Pepper, Maracujá, Mostarda e Mel, Red Hot

IMPORTANTE: molhos do SaladBuilder usam tag ["ingrediente"] e NÃO "molho",
para que o frontend não os exiba na seção 'molhos' do cardápio.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# ---------------------------------------------------------------------------
# Lista completa de ingredientes
# ---------------------------------------------------------------------------

BASE = [
    {
        "name": "Alface",
        "slug": "ingrediente-alface",
        "description": "Alface fresca e crocante, base clássica para saladas.",
        "short_description": "Base verde e crocante",
        "price": "1.00",
        "sort_order": 11,
    },
    {
        "name": "Couve",
        "slug": "ingrediente-couve",
        "description": "Couve finamente fatiada, rica em fibras e nutrientes.",
        "short_description": "Couve fatiada fresca",
        "price": "1.00",
        "sort_order": 12,
    },
    {
        "name": "Repolho",
        "slug": "ingrediente-repolho",
        "description": "Repolho crocante e refrescante, ótima base para saladas.",
        "short_description": "Repolho crocante",
        "price": "1.00",
        "sort_order": 13,
    },
]

PROTEINAS = [
    {
        "name": "Frango Desfiado",
        "slug": "ingrediente-frango-desfiado",
        "description": "Frango cozido e desfiado, temperado com ervas.",
        "short_description": "Frango desfiado temperado",
        "price": "34.90",
        "sort_order": 21,
    },
    {
        "name": "Frango Filé",
        "slug": "ingrediente-frango-file",
        "description": "Filé de frango grelhado, macio e suculento.",
        "short_description": "Filé de frango grelhado",
        "price": "36.90",
        "sort_order": 22,
    },
    {
        "name": "Almôndega",
        "slug": "ingrediente-almondega",
        "description": "Almôndegas caseiras temperadas ao forno.",
        "short_description": "Almôndegas ao forno",
        "price": "36.90",
        "sort_order": 23,
    },
    {
        "name": "Tilápia",
        "slug": "ingrediente-tilapia",
        "description": "Filé de tilápia grelhado, leve e saboroso.",
        "short_description": "Tilápia grelhada",
        "price": "39.90",
        "sort_order": 24,
    },
    {
        "name": "Salmão",
        "slug": "ingrediente-salmao",
        "description": "Salmão grelhado, rico em ômega-3.",
        "short_description": "Salmão grelhado",
        "price": "49.90",
        "sort_order": 25,
    },
    {
        "name": "Camarão",
        "slug": "ingrediente-camarao",
        "description": "Camarões salteados no azeite com alho.",
        "short_description": "Camarão ao ajillo",
        "price": "54.90",
        "sort_order": 26,
    },
]

COMPLEMENTOS = [
    {
        "name": "Abacaxi",
        "slug": "ingrediente-abacaxi",
        "description": "Cubos de abacaxi fresco, toque tropical e refrescante.",
        "short_description": "Abacaxi fresco em cubos",
        "price": "1.00",
        "sort_order": 31,
    },
    {
        "name": "Abobrinha",
        "slug": "ingrediente-abobrinha",
        "description": "Abobrinha grelhada em fatias.",
        "short_description": "Abobrinha grelhada",
        "price": "1.00",
        "sort_order": 32,
    },
    {
        "name": "Alho Poró",
        "slug": "ingrediente-alho-poro",
        "description": "Alho poró finamente fatiado, sabor delicado.",
        "short_description": "Alho poró fatiado",
        "price": "1.00",
        "sort_order": 33,
    },
    {
        "name": "Azeitona",
        "slug": "ingrediente-azeitona",
        "description": "Azeitonas selecionadas, saborosas e aromáticas.",
        "short_description": "Azeitonas selecionadas",
        "price": "1.00",
        "sort_order": 34,
    },
    {
        "name": "Bacon",
        "slug": "ingrediente-bacon",
        "description": "Bacon crocante em pedacinhos.",
        "short_description": "Bacon crocante",
        "price": "1.00",
        "sort_order": 35,
    },
    {
        "name": "Batata Palha",
        "slug": "ingrediente-batata-palha",
        "description": "Batata palha crocante para um toque especial.",
        "short_description": "Batata palha crocante",
        "price": "1.00",
        "sort_order": 36,
    },
    {
        "name": "Batata Rústica",
        "slug": "ingrediente-batata-rustica",
        "description": "Batata rústica assada com ervas.",
        "short_description": "Batata rústica assada",
        "price": "1.00",
        "sort_order": 37,
    },
    {
        "name": "Brócolis",
        "slug": "ingrediente-brocolis",
        "description": "Brócolis cozido no ponto certo, nutritivo.",
        "short_description": "Brócolis nutritivo",
        "price": "1.00",
        "sort_order": 38,
    },
    {
        "name": "Castanha",
        "slug": "ingrediente-castanha",
        "description": "Castanha-do-pará tostada, crocante e nutritiva.",
        "short_description": "Castanha tostada",
        "price": "1.00",
        "sort_order": 39,
    },
    {
        "name": "Cebola Roxa",
        "slug": "ingrediente-cebola-roxa",
        "description": "Cebola roxa fatiada, sabor marcante.",
        "short_description": "Cebola roxa fatiada",
        "price": "1.00",
        "sort_order": 40,
    },
    {
        "name": "Cenoura",
        "slug": "ingrediente-cenoura",
        "description": "Cenoura ralada ou em palitos, crocante e nutritiva.",
        "short_description": "Cenoura crocante",
        "price": "1.00",
        "sort_order": 41,
    },
    {
        "name": "Chips",
        "slug": "ingrediente-chips",
        "description": "Chips crocantes para um toque especial na salada.",
        "short_description": "Chips crocante",
        "price": "1.00",
        "sort_order": 42,
    },
    {
        "name": "Gergelim",
        "slug": "ingrediente-gergelim",
        "description": "Gergelim tostado, levemente amendoado.",
        "short_description": "Gergelim tostado",
        "price": "1.00",
        "sort_order": 43,
    },
    {
        "name": "Macarrão",
        "slug": "ingrediente-macarrao",
        "description": "Macarrão cozido al dente.",
        "short_description": "Macarrão al dente",
        "price": "1.00",
        "sort_order": 44,
    },
    {
        "name": "Mandioca",
        "slug": "ingrediente-mandioca",
        "description": "Mandioca cozida ou frita, saborosa e versátil.",
        "short_description": "Mandioca cozida",
        "price": "1.00",
        "sort_order": 45,
    },
    {
        "name": "Manga",
        "slug": "ingrediente-manga",
        "description": "Cubos de manga madura, toque doce e tropical.",
        "short_description": "Manga tropical",
        "price": "1.00",
        "sort_order": 46,
    },
    {
        "name": "Milho",
        "slug": "ingrediente-milho",
        "description": "Milho verde cozido, doce e suculento.",
        "short_description": "Milho verde",
        "price": "1.00",
        "sort_order": 47,
    },
    {
        "name": "Ovo de Codorna",
        "slug": "ingrediente-ovo-codorna",
        "description": "Ovos de codorna cozidos.",
        "short_description": "Ovo de codorna",
        "price": "1.00",
        "sort_order": 48,
    },
    {
        "name": "Palmito",
        "slug": "ingrediente-palmito",
        "description": "Palmito pupunha em rodelas, delicado e saboroso.",
        "short_description": "Palmito pupunha",
        "price": "1.00",
        "sort_order": 49,
    },
    {
        "name": "Pepino",
        "slug": "ingrediente-pepino",
        "description": "Pepino fatiado, refrescante e crocante.",
        "short_description": "Pepino refrescante",
        "price": "1.00",
        "sort_order": 50,
    },
    {
        "name": "Queijo",
        "slug": "ingrediente-queijo",
        "description": "Queijo em cubos ou ralado.",
        "short_description": "Queijo selecionado",
        "price": "1.00",
        "sort_order": 51,
    },
    {
        "name": "Tomatinho",
        "slug": "ingrediente-tomatinho",
        "description": "Tomatinhos cereja frescos, doces e coloridos.",
        "short_description": "Tomatinhos frescos",
        "price": "1.00",
        "sort_order": 52,
    },
]

MOLHOS_SALAD = [
    {
        "name": "Molho Lemon Pepper",
        "slug": "ingrediente-molho-lemon-pepper",
        "description": "Molho cítrico com pimenta-do-reino, refrescante e picante.",
        "short_description": "Cítrico com pimenta",
        "price": "1.00",
        "sort_order": 61,
    },
    {
        "name": "Molho Maracujá",
        "slug": "ingrediente-molho-maracuja",
        "description": "Molho agridoce de maracujá, tropical e aromático.",
        "short_description": "Agridoce tropical",
        "price": "1.00",
        "sort_order": 62,
    },
    {
        "name": "Molho Mostarda e Mel",
        "slug": "ingrediente-molho-mostarda-mel",
        "description": "Clássico molho de mostarda com mel, equilibrado e saboroso.",
        "short_description": "Mostarda e mel",
        "price": "1.00",
        "sort_order": 63,
    },
    {
        "name": "Molho Red Hot",
        "slug": "ingrediente-molho-red-hot",
        "description": "Molho picante estilo Buffalo, para quem gosta de emoção.",
        "short_description": "Picante estilo Buffalo",
        "price": "1.00",
        "sort_order": 64,
    },
]

# ---------------------------------------------------------------------------
# Monta a lista final com metadados de step/categoria
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "step": "base",
        "category_name": "Ingrediente - Base",
        "category_slug": "ingrediente-base",
        "category_sort_order": 10,
        "tags": ["ingrediente", "base"],
        "items": BASE,
    },
    {
        "step": "proteina",
        "category_name": "Ingrediente - Proteína",
        "category_slug": "ingrediente-proteina",
        "category_sort_order": 20,
        "tags": ["ingrediente", "proteina"],
        "items": PROTEINAS,
    },
    {
        "step": "complemento",
        "category_name": "Ingrediente - Complemento",
        "category_slug": "ingrediente-complemento",
        "category_sort_order": 30,
        "tags": ["ingrediente", "complemento"],
        "items": COMPLEMENTOS,
    },
    {
        "step": "molho",
        # Tag "ingrediente" only — NOT "molho" — ensures inferCatalogSection
        # does NOT route these to the 'molhos' section of the cardápio.
        "category_name": "Ingrediente - Molho",
        "category_slug": "ingrediente-molho-salada",
        "category_sort_order": 40,
        "tags": ["ingrediente"],
        "items": MOLHOS_SALAD,
    },
]


class Command(BaseCommand):
    help = "Seed all SaladBuilder ingredients for the given store."

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

        total_created = 0
        total_skipped = 0

        for cat_def in CATEGORIES:
            step = cat_def["step"]
            tags = cat_def["tags"]

            # ---- category ----
            if not dry_run:
                category, cat_created = StoreCategory.objects.get_or_create(
                    store=store,
                    slug=cat_def["category_slug"],
                    defaults={
                        "name": cat_def["category_name"],
                        "description": f"Ingredientes — {cat_def['category_name'].replace('Ingrediente - ', '')}",
                        "is_active": True,
                        "sort_order": cat_def["category_sort_order"],
                    },
                )
                label = "[+] Category created" if cat_created else "[=] Category exists "
                self.stdout.write(f"\n{label}: {category.name}")
            else:
                self.stdout.write(f"\n[dry] Category: {cat_def['category_name']} (step={step})")
                category = None

            # ---- products ----
            for item in cat_def["items"]:
                existing = StoreProduct.objects.filter(
                    store=store,
                    slug=item["slug"],
                ).first()

                if existing:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [~] Exists: {existing.name} — skipped"
                        )
                    )
                    total_skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [dry] Would create: {item['name']} "
                        f"(step={step}, R${item['price']}, tags={tags})"
                    )
                    total_created += 1
                    continue

                product = StoreProduct.objects.create(
                    store=store,
                    category=category,
                    name=item["name"],
                    slug=item["slug"],
                    description=item["description"],
                    short_description=item["short_description"],
                    price=item["price"],
                    stock_quantity=999,
                    track_stock=False,
                    status=StoreProduct.ProductStatus.ACTIVE,
                    tags=tags,
                    sort_order=item["sort_order"],
                    featured=False,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [+] Created: {product.name}  "
                        f"(R${product.price}, tags={product.tags})"
                    )
                )
                total_created += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {total_created} created, {total_skipped} skipped."
            )
        )
        if not dry_run and total_created > 0:
            self.stdout.write(
                "→ Acesse /cardapio — a seção 'Monte sua Salada' deve mostrar "
                "todos os ingredientes no builder."
            )
