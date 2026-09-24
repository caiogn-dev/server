from django.urls import path
from rest_framework.routers import DefaultRouter
from .api.views import AlergenicosView, CustosDaLojaView, NutritionIngredientViewSet, ProductRecipeViewSet, ProductNutritionProfileViewSet
from .public_views import public_nutrition_label

router = DefaultRouter()
router.register("ingredients", NutritionIngredientViewSet, basename="nutrition-ingredient")
router.register("recipes", ProductRecipeViewSet, basename="nutrition-recipe")
router.register("profiles", ProductNutritionProfileViewSet, basename="nutrition-profile")
urlpatterns = [path("alergenicos/", AlergenicosView.as_view(), name="nutrition-alergenicos"),
               path("custos/", CustosDaLojaView.as_view(), name="nutrition-custos"),
               path("public/<uuid:product_id>/", public_nutrition_label, name="public-nutrition-label"), *router.urls]
