"""
Testes de persistência de grupos de combo do tipo "produtos" (product_options).

Cobre o gap do _sync_groups: até a migration 0040 o serializer só gravava
variant_limits e descartava grupos sem produto-âncora. Estes testes garantem:
- criar combo com grupo de PRODUTOS (title + product_options) persiste tudo
- editar combo adiciona/remove product_options corretamente
- grupo de VARIANTES continua funcionando (sem regressão)
- PublicComboSerializer expõe groups com product_options
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreProduct, StoreProductVariant, StoreCombo
from apps.stores.models.combo_group import (
    ComboProductGroup,
    ComboProductGroupProductOption,
)
from apps.stores.api.serializers import (
    StoreComboSerializer,
    PublicComboSerializer,
)

User = get_user_model()


class ComboProductGroupSyncTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner, status='active'
        )
        self.salada_caesar = StoreProduct.objects.create(
            store=self.store, name='Caesar', slug='caesar',
            price=Decimal('20.00'), track_stock=True, stock_quantity=50,
        )
        self.salada_tropical = StoreProduct.objects.create(
            store=self.store, name='Tropical', slug='tropical',
            price=Decimal('22.00'), track_stock=True, stock_quantity=50,
        )
        self.salada_vegana = StoreProduct.objects.create(
            store=self.store, name='Vegana', slug='vegana',
            price=Decimal('25.00'), track_stock=True, stock_quantity=50,
        )

    def _product_group_payload(self, options):
        return {
            'store': str(self.store.id),
            'name': 'Combo 5 Saladas',
            'slug': 'combo-5-saladas',
            'price': '90.00',
            'is_active': True,
            'groups': [{
                'title': 'Escolha 5 saladas',
                'is_required': True,
                'min_selections': 1,
                'max_selections': 5,
                'allow_duplicate_variants': True,
                'position': 0,
                'product_options': options,
            }],
        }

    def test_create_product_group_persists_options_and_title(self):
        """Grupo sem âncora (title + product_options) deve ser gravado."""
        payload = self._product_group_payload([
            {'product_id': str(self.salada_caesar.id), 'max_selections': 2,
             'price_override': None},
            {'product_id': str(self.salada_tropical.id), 'max_selections': 1,
             'price_override': '18.00'},
        ])
        serializer = StoreComboSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        combo = serializer.save()

        groups = list(combo.groups.all())
        self.assertEqual(len(groups), 1)
        group = groups[0]
        # Grupo de produtos: sem produto-âncora, com title preenchido
        self.assertIsNone(group.product_id)
        self.assertEqual(group.title, 'Escolha 5 saladas')
        self.assertEqual(group.max_selections, 5)

        options = list(group.product_options.order_by('position'))
        self.assertEqual(len(options), 2)
        by_product = {str(o.product_id): o for o in options}
        self.assertEqual(by_product[str(self.salada_caesar.id)].max_selections, 2)
        self.assertIsNone(by_product[str(self.salada_caesar.id)].price_override)
        self.assertEqual(
            by_product[str(self.salada_tropical.id)].price_override,
            Decimal('18.00'),
        )

    def test_update_product_group_replaces_options(self):
        """Editar troca o conjunto de options (remove o que saiu, adiciona o novo)."""
        create = StoreComboSerializer(data=self._product_group_payload([
            {'product_id': str(self.salada_caesar.id), 'max_selections': 1,
             'price_override': None},
        ]))
        self.assertTrue(create.is_valid(), create.errors)
        combo = create.save()

        # Edita: remove caesar, adiciona tropical + vegana
        update = StoreComboSerializer(combo, data=self._product_group_payload([
            {'product_id': str(self.salada_tropical.id), 'max_selections': 1,
             'price_override': None},
            {'product_id': str(self.salada_vegana.id), 'max_selections': 3,
             'price_override': None},
        ]))
        self.assertTrue(update.is_valid(), update.errors)
        combo = update.save()

        group = combo.groups.get()
        product_ids = set(
            str(o.product_id) for o in group.product_options.all()
        )
        self.assertEqual(
            product_ids,
            {str(self.salada_tropical.id), str(self.salada_vegana.id)},
        )
        # Não deve sobrar nenhuma option órfã no banco
        self.assertEqual(
            ComboProductGroupProductOption.objects.filter(
                product=self.salada_caesar
            ).count(),
            0,
        )

    def test_variant_group_still_works(self):
        """Regressão: grupo de variantes (produto-âncora) continua persistindo."""
        product = StoreProduct.objects.create(
            store=self.store, name='Rondelli', slug='rondelli',
            price=Decimal('29.90'), track_stock=True, stock_quantity=100,
        )
        v_frango = StoreProductVariant.objects.create(
            product=product, name='Frango', stock_quantity=20,
        )
        payload = {
            'store': str(self.store.id),
            'name': 'Combo Rondelli',
            'slug': 'combo-rondelli',
            'price': '45.00',
            'is_active': True,
            'groups': [{
                'product_id': str(product.id),
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1,
                'variant_limits': [
                    {'variant_id': str(v_frango.id), 'max_selections': 2},
                ],
            }],
        }
        serializer = StoreComboSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        combo = serializer.save()

        group = combo.groups.get()
        self.assertEqual(str(group.product_id), str(product.id))
        self.assertEqual(group.variant_limits.count(), 1)

    def test_image_url_is_writable(self):
        """Regressão: image_url do combo deve salvar (era read-only/method field)."""
        payload = {
            'store': str(self.store.id),
            'name': 'Combo com Imagem',
            'slug': 'combo-com-imagem',
            'price': '30.00',
            'is_active': True,
            'image_url': 'https://cdn.exemplo.com/combo.jpg',
        }
        serializer = StoreComboSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        combo = serializer.save()
        combo.refresh_from_db()
        self.assertEqual(combo.image_url, 'https://cdn.exemplo.com/combo.jpg')
        # E a saída serializada reflete a imagem
        self.assertIn('combo.jpg', StoreComboSerializer(combo).data['image_url'])

    def test_public_serializer_exposes_product_options(self):
        """PublicComboSerializer deve expor groups com product_options."""
        create = StoreComboSerializer(data=self._product_group_payload([
            {'product_id': str(self.salada_caesar.id), 'max_selections': 2,
             'price_override': None},
        ]))
        self.assertTrue(create.is_valid(), create.errors)
        combo = create.save()

        data = PublicComboSerializer(combo).data
        self.assertIn('groups', data)
        self.assertEqual(len(data['groups']), 1)
        group = data['groups'][0]
        self.assertEqual(group['title'], 'Escolha 5 saladas')
        self.assertEqual(len(group['product_options']), 1)
        self.assertEqual(
            group['product_options'][0]['product_id'],
            str(self.salada_caesar.id),
        )
