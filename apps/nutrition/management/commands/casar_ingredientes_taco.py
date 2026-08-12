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
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.nutrition.models import NUTRIENT_FIELDS, NutritionIngredient
from apps.nutrition.services.correspondencia import nome_completo, sugerir

logger = logging.getLogger(__name__)

# Acima disso o casamento é seguro o bastante para aplicar em lote quando o
# dono pedir; abaixo, entra na lista de conferência manual.
CONFIANCA_PADRAO = 0.70

BASES_PUBLICAS = (NutritionIngredient.Source.TACO, NutritionIngredient.Source.POF,
                  NutritionIngredient.Source.TBCA)


def _completude(ingrediente):
    """Quantos dos 10 nutrientes da etiqueta o candidato tem preenchido."""
    return sum(getattr(ingrediente, campo) is not None for campo in NUTRIENT_FIELDS)


class Command(BaseCommand):
    help = "Sugere (e opcionalmente aplica) o casamento dos ingredientes da loja com a TACO"

    def add_arguments(self, parser):
        parser.add_argument("--loja", help="Slug da loja; sem isso, todas")
        parser.add_argument("--minimo", type=float, default=CONFIANCA_PADRAO,
                            help=f"Nota mínima para sugerir (padrão {CONFIANCA_PADRAO})")
        parser.add_argument("--aplicar", action="store_true",
                            help="Copia os valores da base pública para o ingrediente da loja")
        parser.add_argument("--par", action="append", default=[], metavar="ORIGEM::DESTINO[::PREPARO]",
                            help="Casamento confirmado por uma pessoa, quando o comparador de "
                                 "nome não chega lá (ex.: 'Frango, peito, sem pele, cozido::"
                                 "Peito De Galinha Ou Frango::COZIDO(A)'). Repetível.")
        parser.add_argument("--completar", action="store_true",
                            help="Preenche SÓ os nutrientes que faltam em ingredientes que já "
                                 "têm dado (ex.: açúcar e trans, que a TACO não mede e a POF sim)")

    def handle(self, *args, **options):
        minimo = options["minimo"]

        taco = list(NutritionIngredient.objects.filter(
            source__in=BASES_PUBLICAS, store__isnull=True, energy_kcal__isnull=False,
        ))
        if not taco:
            raise CommandError("Nenhum alimento de base pública. Rode import_taco_table "
                               "e/ou import_pof_table antes.")
        # Com TACO e POF na mesma base, o mesmo alimento aparece duas vezes. A
        # POF costuma ganhar por ter açúcar de adição, saturada e trans, mas a
        # decisão é por candidato: vence quem tem mais nutriente preenchido,
        # não a fonte "preferida" no abstrato.
        taco.sort(key=_completude, reverse=True)
        por_fonte = Counter(i.source for i in taco)
        self.stdout.write(f"📚 {len(taco)} alimentos de referência: "
                          + ", ".join(f"{n} {f}" for f, n in por_fonte.most_common()))

        if options["par"]:
            return self._pares_confirmados(options)

        if options["completar"]:
            return self._completar(taco, options)

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
            self.stdout.write(self.style.WARNING(f"\n⚠️  {len(sem_par)} sem equivalente nas bases públicas "
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
        self.stdout.write(self.style.SUCCESS(f"\n✅ {aplicados} ingredientes receberam valores das bases públicas"))
        self.stdout.write("   A origem ficou gravada em source_code/source_edition e nas notas.")

    @transaction.atomic
    def _aplicar(self, casados):
        aplicados = 0
        for ing, propostas in casados:
            melhor, nota = propostas[0]
            for campo in NUTRIENT_FIELDS:
                setattr(ing, campo, getattr(melhor, campo))
            # A fonte é a do candidato, não "TACO" fixo: com a POF na base o
            # match vem das duas, e gravar a fonte errada quebra a auditoria da
            # etiqueta lá na frente.
            ing.source = melhor.source
            ing.source_code = melhor.source_code
            ing.source_edition = melhor.source_edition
            # A nota fica registrada: quem abrir o cadastro daqui a seis meses
            # precisa saber que o valor veio de um palpite de nome, não de laudo.
            origem = (f"Valores copiados de {melhor.get_source_display()} "
                      f"#{melhor.source_code} ({melhor.display_name}) por "
                      f"correspondência de nome (confiança {nota:.2f}). "
                      f"Revisar se a preparação for diferente.")
            ing.notes = f"{ing.notes}\n{origem}".strip() if ing.notes else origem
            ing.save(update_fields=[*NUTRIENT_FIELDS, "source", "source_code",
                                    "source_edition", "notes", "updated_at"])
            aplicados += 1
        return aplicados

    def _completar(self, publicos, options):
        """Preenche só os nutrientes ausentes, sem tocar no que já foi medido.

        É a mescla de fontes que a etiqueta precisa: a TACO mede muito bem o
        que mede, mas não tem açúcar de adição nem gordura trans em alimento
        nenhum — e esses são dois dos três gatilhos da lupa frontal. A POF tem.

        Regra: valor existente NUNCA é sobrescrito. Misturar duas medições do
        mesmo nutriente produziria um número que não é verdade em fonte
        nenhuma; preencher buraco com a outra fonte, registrando qual, é
        prática normal de rotulagem.
        """
        from django.db.models import Q

        falta_algum = Q()
        for campo in NUTRIENT_FIELDS:
            falta_algum |= Q(**{f"{campo}__isnull": True})

        alvos = NutritionIngredient.objects.filter(
            falta_algum, recipe_items__isnull=False, energy_kcal__isnull=False,
        ).distinct()
        if options["loja"]:
            alvos = alvos.filter(Q(store__slug=options["loja"]) | Q(store__isnull=True))
        alvos = list(alvos.order_by("display_name"))

        self.stdout.write(f"🧩 {len(alvos)} ingredientes de receita com dado incompleto\n")

        planos = []
        for ing in alvos:
            buracos = [c for c in NUTRIENT_FIELDS if getattr(ing, c) is None]
            candidatos = [c for c in publicos if c.pk != ing.pk]
            propostas = sugerir(nome_completo(ing), candidatos, minimo=options["minimo"])
            escolhido = next(
                ((c, n) for c, n in propostas
                 if any(getattr(c, campo) is not None for campo in buracos)), None)
            if not escolhido:
                continue
            fonte, nota = escolhido
            preenche = [c for c in buracos if getattr(fonte, c) is not None]
            planos.append((ing, fonte, nota, preenche))
            self.stdout.write(f"  {ing.display_name:34.34} ← {fonte.display_name:30.30} "
                              f"({nota:.2f}) {', '.join(preenche)}")

        if not options["aplicar"]:
            self.stdout.write(self.style.WARNING(
                f"\n{len(planos)} complementos possíveis. Nada gravado — rode com --aplicar."))
            return

        with transaction.atomic():
            for ing, fonte, nota, campos in planos:
                for campo in campos:
                    setattr(ing, campo, getattr(fonte, campo))
                origem = (f"Complementado com {fonte.get_source_display()} #{fonte.source_code} "
                          f"({fonte.display_name}) nos campos {', '.join(campos)} "
                          f"(confiança {nota:.2f}). Valores já medidos foram preservados.")
                ing.notes = f"{ing.notes}\n{origem}".strip() if ing.notes else origem
                ing.save(update_fields=[*campos, "notes", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"\n✅ {len(planos)} ingredientes complementados"))

    def _pares_confirmados(self, options):
        """Aplica casamentos que uma pessoa confirmou, por nome exato.

        O comparador de nome erra nos casos que dependem de saber o mundo:
        "Frango, peito, sem pele, cozido" e "Peito De Galinha Ou Frango" são a
        mesma comida, mas nenhuma métrica de string sabe que galinha e frango
        são sinônimos. Em vez de baixar o corte — o que deixaria passar
        "Estrogonofe de frango" casando com "Steak de frango" —, a decisão
        humana entra explícita e fica no histórico do comando.

        Preenche só o que falta, como o --completar: os valores que a loja já
        tem medidos são mais específicos que os da base pública.
        """
        aplicados = 0
        for par in options["par"]:
            partes = [p.strip() for p in par.split("::")]
            if len(partes) < 2:
                self.stdout.write(self.style.ERROR(f"  ✗ formato inválido: {par!r}"))
                continue
            origem, destino, preparo = partes[0], partes[1], (partes[2] if len(partes) > 2 else None)

            alvo = NutritionIngredient.objects.filter(display_name=origem).first()
            if not alvo:
                self.stdout.write(self.style.ERROR(f"  ✗ ingrediente não encontrado: {origem!r}"))
                continue

            candidatos = NutritionIngredient.objects.filter(store__isnull=True, display_name=destino)
            if preparo is not None:
                candidatos = candidatos.filter(preparation_state=preparo)
            fonte = candidatos.first()
            if not fonte:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ referência não encontrada: {destino!r}"
                    + (f" [{preparo}]" if preparo else "")))
                continue

            buracos = [c for c in NUTRIENT_FIELDS
                       if getattr(alvo, c) is None and getattr(fonte, c) is not None]
            if not buracos:
                self.stdout.write(f"  = {origem[:40]} já está completo")
                continue

            self.stdout.write(f"  {origem[:34]:36} ← {fonte.display_name[:26]:28} "
                              f"[{fonte.preparation_state or '-'}] {', '.join(buracos)}")
            if not options["aplicar"]:
                continue

            for campo in buracos:
                setattr(alvo, campo, getattr(fonte, campo))
            origem_nota = (f"Complementado com {fonte.get_source_display()} #{fonte.source_code} "
                           f"({fonte.display_name}"
                           + (f", {fonte.preparation_state}" if fonte.preparation_state else "")
                           + f") nos campos {', '.join(buracos)}. "
                           "Correspondência confirmada por uma pessoa, não pelo comparador de nome. "
                           "Valores já medidos foram preservados.")
            alvo.notes = f"{alvo.notes}\n{origem_nota}".strip() if alvo.notes else origem_nota
            alvo.save(update_fields=[*buracos, "notes", "updated_at"])
            aplicados += 1

        if options["aplicar"]:
            self.stdout.write(self.style.SUCCESS(f"\n✅ {aplicados} pares confirmados aplicados"))
        else:
            self.stdout.write(self.style.WARNING("\nNada gravado — rode com --aplicar."))
