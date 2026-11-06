"""Importar o extrato de repasse da 99 pelo painel.

    POST /api/v1/stores/reports/99food/extrato/?store=<slug>
         JSON {texto, data?, gravar?}  ou  multipart {arquivo (.csv/.xlsx), data?, gravar?}

`texto` aceita CSV com cabeçalho ou o texto copiado do 99store. Sem `gravar`
é prévia: mostra o que seria conciliado e não grava nada. Loja fora do
alcance do usuário (`accessible_store_ids`) é 404.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import accessible_store_ids

from ..models import Store
from ..services import repasse_99

LIMITE_DO_ARQUIVO = 2 * 1024 * 1024
_VERDADE = {True, 'true', 'True', '1', 1, 'sim'}


def _loja(request):
    param = request.query_params.get('store') or ''
    if not param:
        return None
    qs = Store.objects.filter(id__in=accessible_store_ids(request.user))
    try:
        uuid.UUID(param)
        return qs.filter(id=param).first()
    except (ValueError, AttributeError):
        return qs.filter(slug=param).first()


def _linhas(request, data_padrao):
    arquivo = request.FILES.get('arquivo')
    if arquivo is not None:
        if arquivo.size > LIMITE_DO_ARQUIVO:
            raise ValueError('Arquivo grande demais.')
        conteudo = arquivo.read()
        if conteudo[:2] == b'PK':  # .xlsx é um zip
            return repasse_99.ler_planilha(conteudo, data_padrao=data_padrao)
        for codificacao in ('utf-8-sig', 'latin-1'):
            try:
                texto = conteudo.decode(codificacao)
                break
            except UnicodeDecodeError:
                continue
        return repasse_99.ler_qualquer(texto, data_padrao=data_padrao)
    texto = str(request.data.get('texto') or '')
    if not texto.strip():
        raise ValueError('Cole o extrato ou envie o arquivo.')
    return repasse_99.ler_qualquer(texto, data_padrao=data_padrao)


def _dinheiro(valor) -> str:
    return str(Decimal(valor or 0).quantize(Decimal('0.01')))


class ImportarExtrato99View(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        loja = _loja(request)
        if loja is None:
            return Response({'error': 'Loja não encontrada'}, status=404)
        try:
            data_padrao = date.fromisoformat(request.data['data']) if request.data.get('data') else None
        except (TypeError, ValueError):
            return Response({'error': 'Data inválida.'}, status=400)
        try:
            linhas = _linhas(request, data_padrao)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        if not linhas:
            return Response({'error': 'Não achei pedidos nesse extrato.'}, status=400)

        gravar = request.data.get('gravar') in _VERDADE
        resultado = repasse_99.conciliar(loja, linhas, gravar=gravar)

        divergentes = {id(l) for l, _p, _v in resultado['divergentes']}
        sem_pedido = {id(l) for l in resultado['sem_pedido']}
        pedidos = {id(l): p for l, p in resultado['conciliados']}
        saida = []
        for linha in linhas:
            pedido = pedidos.get(id(linha))
            situacao = ('sem_pedido' if id(linha) in sem_pedido
                        else 'divergente' if id(linha) in divergentes else 'conciliado')
            saida.append({
                'pedido': linha.pedido,
                'data': linha.data.isoformat() if linha.data else None,
                'venda': _dinheiro(linha.venda) if linha.venda is not None else None,
                'recebido': _dinheiro(linha.recebido),
                'situacao': situacao,
                'numero_do_pedido': pedido.order_number if pedido else None,
            })
        conciliadas = [l for l, _ in resultado['conciliados']]
        return Response({
            'conciliados': len(conciliadas),
            'sem_pedido': len(resultado['sem_pedido']),
            'divergentes': len(resultado['divergentes']),
            'venda': _dinheiro(sum((l.venda or 0 for l in conciliadas), Decimal('0'))),
            'recebido': _dinheiro(sum((l.recebido for l in conciliadas), Decimal('0'))),
            'gravado': gravar,
            'linhas': saida,
        })
