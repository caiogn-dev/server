"""Lote do dia por prato: EST-09102601 = Estrogonofe, 09/10/26, 1º prato do dia."""
import re
import unicodedata
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.stores.models import Store, StoreLote, StoreProduct


def hoje():
    return timezone.localdate()


def prefixo_do_prato(nome: str) -> str:
    """3 primeiras letras do nome, sem acento, em maiúsculas."""
    sem_acento = unicodedata.normalize('NFKD', nome or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]', '', sem_acento).upper()[:3] or 'LOT'


def garantir_lotes(loja, itens, fabricacao, validade_dias) -> dict:
    """itens: [(product_id, quantidade)] → {product_id: {codigo, fabricacao, validade}}.

    Mesmo prato no mesmo dia devolve o lote que já existe e soma as etiquetas.
    A trava na loja serializa quem imprime ao mesmo tempo: a sequência do dia não repete.
    """
    saida = {}
    with transaction.atomic():
        Store.objects.select_for_update().filter(pk=loja.pk).first()
        produtos = {p.id: p for p in StoreProduct.objects.filter(store=loja, id__in=[i for i, _ in itens])}
        for product_id, quantidade in itens:
            produto = produtos.get(product_id) or next((p for k, p in produtos.items() if str(k) == str(product_id)), None)
            if not produto:
                continue
            qtd = max(0, int(quantidade or 0))
            lote = StoreLote.objects.filter(store=loja, product=produto, fabricacao=fabricacao).first()
            if lote:
                StoreLote.objects.filter(pk=lote.pk).update(etiquetas=F('etiquetas') + qtd)
            else:
                seq = (StoreLote.objects.filter(store=loja, fabricacao=fabricacao).aggregate(m=Max('sequencia'))['m'] or 0) + 1
                lote = StoreLote.objects.create(
                    store=loja, product=produto, produto_nome=produto.name, sequencia=seq, etiquetas=qtd,
                    codigo=f"{prefixo_do_prato(produto.name)}-{fabricacao:%d%m%y}{seq:02d}",
                    fabricacao=fabricacao, validade=fabricacao + timedelta(days=int(validade_dias)),
                )
            saida[str(produto.id)] = {'codigo': lote.codigo, 'fabricacao': lote.fabricacao.isoformat(),
                                      'validade': lote.validade.isoformat()}
    return saida
