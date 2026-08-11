from rest_framework.routers import DefaultRouter
from .api.views import NutritionIngredientViewSet, ProductRecipeViewSet, ProductNutritionProfileViewSet

router = DefaultRouter()
router.register("ingredients", NutritionIngredientViewSet, basename="nutrition-ingredient")
router.register("recipes", ProductRecipeViewSet, basename="nutrition-recipe")
router.register("profiles", ProductNutritionProfileViewSet, basename="nutrition-profile")
urlpatterns = router.urls
