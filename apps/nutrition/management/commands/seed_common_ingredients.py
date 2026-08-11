from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.nutrition.models import NutritionIngredient


# TACO, 4ª edição (NEPA/UNICAMP, 2011), por 100 g. Açúcares ausentes na
# fonte ficam NULL: zero seria uma afirmação nutricional incorreta.
ROWS = [
 ("Arroz, integral, cozido","Arroz integral cozido","grãos",124,25.8,2.6,1.0,2.7,1),
 ("Arroz, tipo 1, cozido","Arroz branco cozido","grãos",128,28.1,2.5,.2,1.6,1),
 ("Feijão, carioca, cozido","Feijão carioca cozido","leguminosas",76,13.6,4.8,.5,8.5,2),
 ("Feijão, preto, cozido","Feijão preto cozido","leguminosas",77,14.0,4.5,.5,8.4,2),
 ("Frango, peito, sem pele, grelhado","Frango grelhado","carnes",159,0,32.0,2.5,0,50),
 ("Frango, peito, sem pele, cozido","Frango cozido","carnes",163,0,31.5,3.2,0,36),
 ("Carne bovina, acém, sem gordura, cozido","Carne bovina cozida","carnes",215,0,27.3,10.9,0,56),
 ("Carne bovina, patinho, sem gordura, grelhado","Carne moída (patinho)","carnes",219,0,35.9,7.3,0,60),
 ("Ovo, galinha, inteiro, cozido","Ovo cozido","ovos",146,.6,13.3,9.5,0,146),
 ("Alface, crespa, crua","Alface","vegetais",11,1.7,1.3,.2,1.8,3),
 ("Agrião, cru","Agrião","vegetais",17,2.3,2.7,.2,2.1,7),
 ("Rúcula, crua","Rúcula","vegetais",13,2.2,1.8,.1,1.7,9),
 ("Tomate, com semente, cru","Tomate","vegetais",15,3.1,1.1,.2,1.2,1),
 ("Cenoura, crua","Cenoura","vegetais",34,7.7,1.3,.2,3.2,3),
 ("Beterraba, crua","Beterraba","vegetais",49,11.1,1.9,.1,3.4,10),
 ("Pepino, cru","Pepino","vegetais",10,2.0,.9,.0,1.1,0),
 ("Chuchu, cozido","Chuchu","vegetais",19,4.8,.4,.0,1.0,2),
 ("Abobrinha, italiana, cozida","Abobrinha","vegetais",15,3.0,1.1,.2,1.6,1),
 ("Brócolis, cozido","Brócolis","vegetais",25,4.4,2.1,.5,3.4,2),
 ("Couve, manteiga, refogada","Couve","vegetais",90,8.7,1.7,6.6,5.7,11),
 ("Espinafre, Nova Zelândia, refogado","Espinafre","vegetais",67,4.2,2.7,5.4,2.5,47),
 ("Batata, inglesa, cozida","Batata cozida","tubérculos",52,11.9,1.2,.0,1.3,2),
 ("Batata, doce, cozida","Batata doce","tubérculos",77,18.4,.6,.1,2.2,3),
 ("Macarrão, trigo, cru, cozido","Macarrão cozido","massas",157,30.9,5.8,.9,1.8,1),
 ("Azeite, de oliva, extra virgem","Azeite de oliva","óleos",884,0,0,100,0,0),
 ("Óleo, de soja","Óleo de soja","óleos",884,0,0,100,0,0),
 ("Sal, dietético","Sal dietético","temperos",0,0,0,0,0,23432),
 ("Limão, tahiti, cru","Limão","frutas",32,11.1,.9,.1,1.2,1),
 ("Vinagre","Vinagre","temperos",18,.6,0,0,0,1),
 ("Maçã, Fuji, com casca, crua","Maçã","frutas",56,15.2,.3,0,1.3,0),
 ("Banana, prata, crua","Banana","frutas",98,26.0,1.3,.1,2.0,0),
 ("Laranja, pêra, crua","Laranja","frutas",37,8.9,1.0,.1,.8,0),
 ("Mamão, Papaia, cru","Mamão","frutas",40,10.4,.5,.1,1.0,2),
]


class Command(BaseCommand):
    help = "Carrega ingredientes comuns da TACO sem sobrescrever ajustes existentes."
    def handle(self, *args, **options):
        created = 0
        for canonical, display, category, kcal, carb, protein, fat, fiber, sodium in ROWS:
            _, was_created = NutritionIngredient.objects.get_or_create(
                store=None, canonical_name=canonical, preparation_state="",
                defaults={"display_name": display, "category": category, "source": "taco",
                          "source_edition": "4ª edição, 2011", "source_reference": "https://nepa.unicamp.br/taco/",
                          "energy_kcal": Decimal(str(kcal)), "carbohydrates_g": Decimal(str(carb)),
                          "protein_g": Decimal(str(protein)), "total_fat_g": Decimal(str(fat)),
                          "fiber_g": Decimal(str(fiber)), "sodium_mg": Decimal(str(sodium))},
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"{created} criados; {len(ROWS)-created} já existiam."))
