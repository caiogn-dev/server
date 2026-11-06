"""Preço R$ 0,00 em item publicado só com a marca de brinde."""
from decimal import Decimal

from rest_framework import serializers


def checar_preco_zero(preco, publicado: bool, brinde: bool, campo: str = 'price'):
    if preco is None or not publicado or brinde:
        return
    if Decimal(str(preco)) <= 0:
        raise serializers.ValidationError({
            campo: 'Preço zerado. Informe o valor ou marque como brinde.',
        })
