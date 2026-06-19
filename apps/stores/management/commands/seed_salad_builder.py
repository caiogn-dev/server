"""
Popula os grupos do Salad Builder da Cê Saladas: categorias internas (base,
complemento, proteína, molhos), ingredientes individuais e o combo "Monte sua
Salada" (preço base fixo R$ 9,99).

Idempotente (update_or_create por slug). Re-executar corrige preço/categoria/imagem.

Modelo de preço:
- "Monte sua Salada" (StoreCombo) = R$ 9,99 fixo (base).
- Alface = R$ 0 (base obrigatória, grátis).
- Complementos / proteínas = somam seu preço.
- Molho = incluso (grátis, tratado no front).
- Total = 9,99 + Σ complementos + Σ proteínas.

Imagens: CDN de ingredientes (placeholder/mock, trocar por fotos reais depois).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreCombo

CDN = 'https://img.spoonacular.com/ingredients_500x500/'

# Categorias internas do builder (is_builder_group=True) + bebidas (visível).
CATEGORIES = [
    {'slug': 'base',        'name': 'Base',         'sort': 10, 'builder': True},
    {'slug': 'complemento', 'name': 'Complementos', 'sort': 11, 'builder': True},
    {'slug': 'proteina',    'name': 'Proteínas',    'sort': 12, 'builder': True},
    {'slug': 'bebidas',     'name': 'Bebidas',      'sort': 20, 'builder': False},
]

# Ingredientes: (nome, categoria_slug, preço, imagem_cdn)
INGREDIENTS = [
    # Base — grátis (o preço base vive no combo "Monte sua Salada")
    ('Alface', 'base', '0.00', 'iceberg-lettuce.jpg'),

    # Complementos
    ('Repolho', 'complemento', '2.99', 'cabbage.jpg'),
    ('Abobrinha', 'complemento', '2.99', 'zucchini.jpg'),
    ('Alho poró', 'complemento', '2.99', 'leeks.jpg'),
    ('Cebola roxa', 'complemento', '2.99', 'red-onion.png'),
    ('Cenoura ralada', 'complemento', '2.99', 'carrots.jpg'),
    ('Mandioca', 'complemento', '2.99', 'cassava.jpg'),
    ('Milho', 'complemento', '1.99', 'corn.png'),
    ('Gergelim negro', 'complemento', '1.20', 'sesame-seeds.png'),
    ('Azeitona', 'complemento', '3.99', 'black-olives.jpg'),
    ('Batata inglesa', 'complemento', '3.99', 'potatoes-yukon-gold.png'),
    ('Brócolis', 'complemento', '3.99', 'broccoli.jpg'),
    ('Chips de moranga', 'complemento', '3.99', 'butternut-squash.jpg'),
    ('Macarrão penne', 'complemento', '3.99', 'penne.jpg'),
    ('Manga', 'complemento', '3.99', 'mango.jpg'),
    ('Palmito', 'complemento', '3.99', 'hearts-of-palm.png'),
    ('Tomate cereja', 'complemento', '4.99', 'cherry-tomatoes.png'),
    ('Queijo', 'complemento', '5.99', 'cheddar-cheese.png'),

    # Proteínas
    ('Ovinho de codorna', 'proteina', '3.99', 'quail-eggs.jpg'),
    ('Castanha de caju', 'proteina', '9.99', 'cashews.jpg'),
    ('Frango em pedaços', 'proteina', '14.99', 'cooked-chicken-breast.png'),
    ('Bacon', 'proteina', '15.99', 'cooked-bacon.jpg'),
    ('Almôndega', 'proteina', '16.99', 'meatballs.png'),
    ('Tilápia', 'proteina', '17.99', 'fish-fillet.jpg'),

    # Bebida (cross-sell)
    ('Suco de laranja 500ml', 'bebidas', '12.00', 'orange-juice.jpg'),
]

COMBO = {
    'slug': 'monte-sua-salada',
    'name': 'Monte sua Salada',
    'price': '9.99',
    'description': 'Monte sua salada do zero: base de alface + 1 molho incluso. '
                   'Adicione complementos e proteínas do seu jeito.',
}


class Command(BaseCommand):
    help = 'Popula categorias, ingredientes e combo base do Salad Builder (Cê Saladas).'

    def add_arguments(self, parser):
        parser.add_argument('--store', default='ce-saladas', help='Slug da loja')

    @transaction.atomic
    def handle(self, *args, **options):
        store = Store.objects.get(slug=options['store'])
        self.stdout.write(f'Loja: {store.name} ({store.slug})')

        # 1) Categorias do builder (+ marcar molhos como builder group)
        # is_builder_group controla SÓ a visibilidade no cardápio (esconde os
        # ingredientes crus). Os grupos do builder são fixos no frontend
        # (base, complemento, proteina, molhos) — molho aparece no cardápio E no builder.
        cat_map = {}
        for c in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store, slug=c['slug'],
                defaults={'name': c['name'], 'sort_order': c['sort'],
                          'is_builder_group': c['builder'], 'is_active': True},
            )
            cat_map[c['slug']] = cat
        # molhos já existe e é VISÍVEL no cardápio (mas também é passo do builder)
        molhos = StoreCategory.objects.filter(store=store, slug='molhos').first()
        if molhos and molhos.is_builder_group:
            molhos.is_builder_group = False
            molhos.save(update_fields=['is_builder_group'])
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categorias do builder'))

        # 2) Ingredientes
        n = 0
        for sort, (name, cat_slug, price, img) in enumerate(INGREDIENTS):
            StoreProduct.objects.update_or_create(
                store=store, slug=slugify(name),
                defaults={
                    'category': cat_map.get(cat_slug),
                    'name': name,
                    'price': Decimal(price),
                    'main_image_url': CDN + img,
                    'track_stock': False,
                    'is_active': True,
                    'status': StoreProduct.ProductStatus.ACTIVE,
                    'sort_order': sort,
                },
            )
            n += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {n} ingredientes'))

        # 3) Combo base "Monte sua Salada" (preço base fixo)
        combo, created = StoreCombo.objects.update_or_create(
            store=store, slug=COMBO['slug'],
            defaults={'name': COMBO['name'], 'price': Decimal(COMBO['price']),
                      'description': COMBO['description'], 'is_active': True,
                      'track_stock': False},
        )
        self.stdout.write(self.style.SUCCESS(
            f'✅ Combo base "{combo.name}" = R$ {combo.price} ({"criado" if created else "atualizado"})'))

        self.stdout.write(self.style.SUCCESS('\n✅ Salad Builder populado.'))
