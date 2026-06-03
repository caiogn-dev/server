# Database Query Optimization Guide

## O Problema: N+1 Queries

### Exemplo
```python
# SEM otimização: 1 + N queries
orders = StoreOrder.objects.filter(store_id=store_id)
for order in orders:
    print(order.store.name)  # Query N (uma por order!)
    print(order.customer.name)  # Query N
    for item in order.items.all():  # Query N
        print(item.product.name)  # Query N²

# Total: 1 (orders) + N (stores) + N (customers) + N (items) + N² (products) = Muito!
```

### Com Otimização
```python
# COM prefetch/select: 1 + 2 queries
orders = StoreOrder.objects.filter(store_id=store_id).select_related(
    'store',
    'customer',
).prefetch_related(
    'items__product',
)
# Total: 1 (orders) + 1 (stores + customers) + 1 (items + products) = Apenas 3!
```

## `select_related()` vs `prefetch_related()`

### select_related() — Use para FK / OneToOne
```python
# FK: Order.customer (muitos orders para 1 customer)
# OneToOne: User.profile

# ❌ Sem otimização
orders = StoreOrder.objects.all()
for order in orders:
    customer_name = order.customer.name  # Query para cada order

# ✅ Com otimização
orders = StoreOrder.objects.select_related('customer')
# SQL: SELECT ... FROM orders LEFT JOIN customers ON orders.customer_id = customers.id
```

### prefetch_related() — Use para Reverse FK / M2M
```python
# Reverse FK: Order.items (um order tem muitos items)
# M2M: Product.tags (produto tem muitos tags)

# ❌ Sem otimização
orders = StoreOrder.objects.all()
for order in orders:
    for item in order.items.all():  # Query para cada order!
        print(item.name)

# ✅ Com otimização
orders = StoreOrder.objects.prefetch_related('items')
# SQL: Query 1 seleciona orders, Query 2 seleciona TODOS os items de uma vez
```

### Nested Relationships
```python
# Order → Items → Product (muitos levels)
orders = StoreOrder.objects.prefetch_related(
    'items__product'  # items.all(), e cada item.product
)
# Queries: 1 (orders) + 1 (items) + 1 (products) = 3 total
```

## Padrões no Server2

### Pattern 1: List/Dashboard Views
```python
class StoreOrderViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = StoreOrder.objects.all()
        
        # Para list() - simples, sem detalhes
        if self.action == 'list':
            return qs.select_related(
                'store',
                'customer',
            ).prefetch_related(
                'items__product',
            )
        
        # Para retrieve() - pode incluir mais details
        if self.action == 'retrieve':
            return qs.select_related(
                'store',
                'customer',
                'invoice',
            ).prefetch_related(
                'items__product',
                'items__combos',
                'events',
                'payments',
            )
        
        return qs
```

### Pattern 2: Actions com Aggregate
```python
@action(detail=False, methods=['get'])
def stats(self, request):
    """Antes: múltiplos .count() e .aggregate() = muitas queries"""
    orders = self.get_queryset()
    
    stats = {
        'total': orders.count(),  # Query 1
        'confirmed': orders.filter(status='confirmed').count(),  # Query 2
        'revenue': orders.aggregate(Sum('total'))  # Query 3
    }
    # Total: 3 queries desnecessárias
    
    """Depois: um único aggregate()"""
    from django.db.models import Count, Sum, Case, When
    
    stats = orders.aggregate(
        total=Count('id'),
        confirmed=Count(Case(When(status='confirmed', then=1))),
        revenue=Sum('total', filter=Q(payment_status='paid')),
    )
    # Total: 1 query
```

### Pattern 3: Deeply Nested (Careful!)
```python
# Problema: too many joins = slow queries
products = Product.objects.prefetch_related(
    'categories',          # Query 2
    'tags',               # Query 3
    'reviews__author',    # Query 4
    'images',             # Query 5
    'variants__options',  # Query 6
)
# Resultado: 6 queries, mas cada query é complexa

# Solução: use apenas o que precisa para a view
# Dashboard product list: prefetch apenas categorias
# Product detail page: prefetch TUDO
```

## Checklist para Novos ViewSets

- [ ] `get_queryset()` implementado?
- [ ] FK fields têm `select_related()`?
- [ ] Reverse FK / M2M têm `prefetch_related()`?
- [ ] Diferentes actions usam diferentes prefetch? (list vs retrieve)
- [ ] Aggregate queries combinadas com `Count()` e `Sum()`?
- [ ] Testado com `django-debug-toolbar` — query count correct?
- [ ] Performance aceitável (< 500ms para list, < 200ms para retrieve)?

## Testing with django-debug-toolbar

```bash
pip install django-debug-toolbar

# settings.py
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

# urls.py
urlpatterns += [path('__debug__/', include('debug_toolbar.urls'))]
```

Abrir no navegador e ver "SQL" tab:
- Quantas queries?
- Time por query?
- N+1 detected?

## Performance Targets

- **List endpoint** (paginated): < 500ms, < 5 queries
- **Retrieve endpoint**: < 200ms, < 10 queries
- **Aggregate/stats**: < 1000ms, < 3 queries
- **Bulk operations**: 1 query por N items (não N queries)

## Common Mistakes

❌ Calling `.all()` in a loop
```python
for order in orders:
    items = order.items.all()  # Query cada vez!
```

✅ Use prefetch
```python
orders = StoreOrder.objects.prefetch_related('items')
for order in orders:
    items = order.items.all()  # No query, cached!
```

---

❌ Different prefetch per action (slow)
```python
def get_queryset(self):
    qs = StoreOrder.objects.all()
    if self.action == 'list':
        qs = qs.select_related('store')
    elif self.action == 'retrieve':
        qs = qs.select_related('store')
        # Same prefetch = wasted!
```

✅ Structure by need
```python
def get_queryset(self):
    qs = StoreOrder.objects.select_related('store')  # Common
    if self.action == 'retrieve':
        qs = qs.prefetch_related('items')  # Extra for detail
    return qs
```

---

❌ Too much prefetch (memory)
```python
orders = StoreOrder.objects.prefetch_related(
    'items__product__category__section',
    'items__combos__options__values',
    'customer__addresses__regions',
)
# Pulls too much data, slow serialization
```

✅ Only what's needed
```python
# For list: minimal
orders = StoreOrder.objects.select_related('customer')

# For detail: more
orders = StoreOrder.objects.select_related(
    'customer'
).prefetch_related(
    'items__product',
)
```

## References

- Django Docs: https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-related
- Query Optimization: https://docs.djangoproject.com/en/stable/topics/db/optimization/
- django-debug-toolbar: https://django-debug-toolbar.readthedocs.io/
