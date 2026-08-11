from django.db.models import Q
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.nutrition.models import NutritionIngredient, ProductRecipe, ProductNutritionProfile
from .serializers import NutritionIngredientSerializer, ProductRecipeSerializer, ProductNutritionProfileSerializer


def stores_for(user):
    return Q(store__owner=user) | Q(store__staff=user)


class NutritionIngredientViewSet(viewsets.ModelViewSet):
    serializer_class = NutritionIngredientSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("canonical_name", "display_name", "category", "source_code")
    ordering_fields = ("display_name", "category", "source")

    def get_queryset(self):
        qs = NutritionIngredient.objects.filter(is_active=True)
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(store__isnull=True) | stores_for(self.request.user)).distinct()
        store = self.request.query_params.get("store")
        category = self.request.query_params.get("category")
        if store:
            qs = qs.filter(Q(store__isnull=True) | Q(store_id=store))
        if category:
            qs = qs.filter(category=category)
        return qs

    def perform_destroy(self, instance):
        if instance.store_id is None and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Ingredientes oficiais globais são somente leitura.")
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))


class ProductRecipeViewSet(viewsets.ModelViewSet):
    serializer_class = ProductRecipeSerializer
    permission_classes = (IsAuthenticated,)
    def get_queryset(self):
        qs = ProductRecipe.objects.select_related("product", "product__store").prefetch_related("items__ingredient")
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(product__store__owner=self.request.user) | Q(product__store__staff=self.request.user)).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs


class ProductNutritionProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProductNutritionProfileSerializer
    permission_classes = (IsAuthenticated,)
    def get_queryset(self):
        qs = ProductNutritionProfile.objects.select_related("product", "recipe")
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(product__store__owner=self.request.user) | Q(product__store__staff=self.request.user)).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs
