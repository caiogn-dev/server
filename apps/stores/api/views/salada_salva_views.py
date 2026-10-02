"""Saladas criadas pelo cliente — ver `apps/stores/models/salada_salva.py`.

GET    /api/v1/stores/{slug}/saladas/        as saladas do número provado
POST   /api/v1/stores/{slug}/saladas/        {"saladas": [...]} — sobe/atualiza (por client_id)
DELETE /api/v1/stores/{slug}/saladas/{id}/   apaga uma

Exige login pelo código do WhatsApp: sem número provado, 403. A wishlist
confia no telefone do corpo da requisição; aqui o número vem SÓ da prova.
"""
import uuid

from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import SaladaSalva
from apps.stores.services.carteira_service import telefone_provado

from .storefront_views import PublicWriteThrottle, get_active_store

LIMITE_POR_NUMERO = 50
LIMITE_DE_INGREDIENTES = 60


class EntradaInvalida(ValueError):
    pass


def _texto(valor, limite):
    return str(valor or '').strip()[:limite]


def _ingrediente(bruto):
    if not isinstance(bruto, dict):
        raise EntradaInvalida('ingrediente precisa ser objeto')
    nome = _texto(bruto.get('name'), 120)
    ident = _texto(bruto.get('id'), 64)
    if not nome or not ident:
        raise EntradaInvalida('ingrediente precisa de id e name')
    foto = _texto(bruto.get('image_url'), 500)
    return {
        'id': ident,
        'name': nome,
        'role': _texto(bruto.get('role'), 40),
        'role_label': _texto(bruto.get('role_label'), 60),
        # Volta para a tela como <img src>: só https, nada de javascript:/data:.
        'image_url': foto if foto.startswith('https://') else '',
    }


def _salada(bruta):
    if not isinstance(bruta, dict):
        raise EntradaInvalida('salada precisa ser objeto')
    try:
        client_id = uuid.UUID(str(bruta.get('client_id')))
    except (TypeError, ValueError):
        raise EntradaInvalida('client_id inválido')
    nome = _texto(bruta.get('nome'), 40)
    if not nome:
        raise EntradaInvalida('nome é obrigatório')
    ingredientes = bruta.get('ingredientes')
    if not isinstance(ingredientes, list) or not ingredientes or len(ingredientes) > LIMITE_DE_INGREDIENTES:
        raise EntradaInvalida('ingredientes precisa ser lista não vazia')
    return client_id, nome, [_ingrediente(i) for i in ingredientes]


def _saida(s):
    return {
        'id': str(s.id),
        'client_id': str(s.client_id),
        'nome': s.nome,
        'ingredientes': s.ingredientes,
        'atualizado_em': s.atualizado_em.isoformat(),
    }


def _do_numero(store, telefone):
    from apps.core.utils import phone_variants
    # wa_id vem sem o nono dígito e o site grava com ele: o mesmo número.
    return SaladaSalva.objects.filter(store=store, telefone__in=list(phone_variants(telefone)) or [telefone])


class _ComNumeroProvado(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PublicWriteThrottle]

    def _contexto(self, request, store_slug):
        telefone = telefone_provado(request)
        return get_active_store(store_slug), telefone


class SaladasSalvasView(_ComNumeroProvado):
    def get(self, request, store_slug):
        store, telefone = self._contexto(request, store_slug)
        if not telefone:
            return Response({'error': 'telefone_nao_verificado'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'saladas': [_saida(s) for s in _do_numero(store, telefone)]})

    def post(self, request, store_slug):
        store, telefone = self._contexto(request, store_slug)
        if not telefone:
            return Response({'error': 'telefone_nao_verificado'}, status=status.HTTP_403_FORBIDDEN)
        brutas = request.data.get('saladas') if isinstance(request.data, dict) else None
        if not isinstance(brutas, list) or len(brutas) > LIMITE_POR_NUMERO:
            return Response({'error': 'saladas precisa ser lista'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limpas = [_salada(b) for b in brutas]
        except EntradaInvalida as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            existentes = {s.client_id: s for s in _do_numero(store, telefone).select_for_update()}
            vagas = LIMITE_POR_NUMERO - len(existentes)
            for client_id, nome, ingredientes in limpas:
                atual = existentes.get(client_id)
                if atual:
                    atual.nome, atual.ingredientes = nome, ingredientes
                    atual.save(update_fields=['nome', 'ingredientes', 'atualizado_em'])
                elif vagas > 0:
                    existentes[client_id] = SaladaSalva.objects.create(
                        store=store, telefone=telefone, client_id=client_id,
                        nome=nome, ingredientes=ingredientes,
                    )
                    vagas -= 1
        return Response({'saladas': [_saida(s) for s in _do_numero(store, telefone)]})


class SaladaSalvaDetalheView(_ComNumeroProvado):
    def delete(self, request, store_slug, pk):
        store, telefone = self._contexto(request, store_slug)
        if not telefone:
            return Response({'error': 'telefone_nao_verificado'}, status=status.HTTP_403_FORBIDDEN)
        apagadas, _ = _do_numero(store, telefone).filter(pk=pk).delete()
        if not apagadas:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
