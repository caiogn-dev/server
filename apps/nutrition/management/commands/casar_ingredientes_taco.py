"""
Liga os ingredientes que a loja cadastrou aos alimentos equivalentes da TACO.

Depois do `import_taco_table` a base pública tem 597 alimentos, mas as receitas
das lojas continuam apontando para ingredientes próprios sem nenhum valor
nutricional — "Abacaxi", "Mandioca cozida", "Queijo mucarela" com tudo nulo. O
resultado é tabela vazia no produto.

Este comando propõe o casamento e, com `--aplicar`, copia os valores da TACO
para o ingrediente da loja, gravando de onde vieram.

Por padrão **não grava nada**: mostra a tabela de sugestões com a nota de
confiança para o dono conferir. Copiar valor errado para dentro de uma etiqueta
é pior que etiqueta vazia.

Alergênicos não são tocados: a TACO não tem esse dado, e `allergens_reviewed`
continua como estava.

Usage:
    python manage.py casar_ingredientes_taco
    python manage.py casar_ingredientes_taco --loja ce-saladas
    python manage.py casar_ingredientes_taco --minimo 0.75 --aplicar
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.nutrition.models import NUTRIENT_FIELDS, NutritionIngredient
from apps.nutrition.services.correspondencia import sugerir

logger = logging.getLogger(__name__)

# Acima disso o casamento é seguro o bastante para aplicar em lote quando o
# dono pedir; abaixo, entra na lista de conferência manual.
CONFIANCA_PADRAO = 0.70


class Command(BaseCommand):
    help = "Sugere (e opcionalmente aplica) o casamento dos ingredientes da loja com a TACO"

    def add_arguments(self, parser):
        parser.add_argument("--loja", help="Slug da loja; sem isso, todas")
        parser.add_argument("--minimo", type=float, default=CONFIANCA_PADRAO,
                            help=f"Nota mínima para sugerir (padrão {CONFIANCA_PADRAO})")
        parser.add_argument("--aplicar", action="store_true",
                            help="Copia os valores da TACO para o ingrediente da loja")

    def handle(self, *args, **options):
        minimo = options["minimo"]

        taco = list(NutritionIngredient.objects.filter(
            source=NutritionIngredient.Source.TACO, store__isnull=True, energy_kcal__isnull=False,
        ))
        if not taco:
            raise CommandError("Nenhum alimento TACO na base. Rode import_taco_table antes.")
        self.stdout.write(f"📚 {len(taco)} alimentos TACO disponíveis como referência")

        # Só o que está EM USO numa receita e sem dado — o resto é ruído de
        # cadastro que ninguém vai imprimir.
        pendentes = NutritionIngredient.objects.filter(
            recipe_items__isnull=False, energy_kcal__isnull=True,
        ).distinct()
        if options["loja"]:
            pendentes = pendentes.filter(store__slug=options["loja"])
        pendentes = list(pendentes.order_by("display_name"))

        if not pendentes:
            self.stdout.write(self.style.SUCCESS("✅ Nenhum ingrediente de receita sem dado nutricional."))
            return

        self.stdout.write(f"🔎 {len(pendentes)} ingredientes de receita sem dado nutricional\n")

        casados, sem_par = [], []
        for ing in pendentes:
            propostas = sugerir(ing.display_name, taco, minimo=minimo)
            if propostas:
                casados.append((ing, propostas))
            else:
                sem_par.append(ing)

        for ing, propostas in casados:
            melhor, nota = propostas[0]
            marca = "✓" if nota >= CONFIANCA_PADRAO else "?"
            self.stdout.write(f"  {marca} {ing.display_name:38.38} → {melhor.display_name:40.40} ({nota:.2f})")
            for outro, n in propostas[1:]:
                self.stdout.write(f"      alternativa: {outro.display_name:36.36} ({n:.2f})")

        if sem_par:
            self.stdout.write(self.style.WARNING(f"\n⚠️  {len(sem_par)} sem equivalente na TACO "
                                                 "(prato pronto, receita composta ou nome muito próprio):"))
            for ing in sem_par:
                self.stdout.write(f"      {ing.display_name}")
            self.stdout.write("      Esses precisam de valor do fabricante, laudo, ou de virar receita própria.")

        if not options["aplicar"]:
            self.stdout.write(self.style.WARNING(
                f"\nNada foi gravado. Confira a lista e rode de novo com --aplicar "
                f"(ou ajuste --minimo, hoje em {minimo})."))
            return

        aplicados = self._aplicar(casados)
        self.stdout.write(self.style.SUCCESS(f"\n✅ {aplicados} ingredientes receberam valores da TACO"))
        self.stdout.write("   A origem ficou gravada em source_code/source_edition e nas notas.")

    @transaction.atomic
    def _aplicar(self, casados):
        aplicados = 0
        for ing, propostas in casados:
            melhor, nota = propostas[0]
            for campo in NUTRIENT_FIELDS:
                setattr(ing, campo, getattr(melhor, campo))
            ing.source = NutritionIngredient.Source.TACO
            ing.source_code = melhor.source_code
            ing.source_edition = melhor.source_edition
            # A nota fica registrada: quem abrir o cadastro daqui a seis meses
            # precisa saber que o valor veio de um palpite de nome, não de laudo.
            origem = (f"Valores copiados de TACO #{melhor.source_code} "
                      f"({melhor.display_name}) por correspondência de nome "
                      f"(confiança {nota:.2f}). Revisar se a preparação for diferente.")
            ing.notes = f"{ing.notes}\n{origem}".strip() if ing.notes else origem
            ing.save(update_fields=[*NUTRIENT_FIELDS, "source", "source_code",
                                    "source_edition", "notes", "updated_at"])
            aplicados += 1
        return aplicados
