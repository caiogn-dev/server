from django.contrib import admin
from .models import NutritionIngredient, ProductRecipe, RecipeItem, ProductNutritionProfile, NutritionProfileRevision

admin.site.register((NutritionIngredient, ProductRecipe, RecipeItem, ProductNutritionProfile, NutritionProfileRevision))
