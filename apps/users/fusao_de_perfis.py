"""Funde os perfis de CRM (`UnifiedUser`) que são a mesma pessoa.

A camada de login já tem `fusao_de_contas`. Esta é a de CRM, que o PDV, o bot,
o inbox e os endereços usam: o WhatsApp entregava o telefone sem o nono dígito
e o site com ele, e cada porta criava um perfil (69 pessoas em 15/set).

QUEM FICA: o perfil com login; depois o com mais cadastros de loja; depois o
com mais pedidos; depois o visto primeiro. O resto migra para ele — endereço do
mesmo lugar não é duplicado (completa o que falta), nome real vence apelido,
e-mail e google_id só entram se quem fica não tem.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction

from apps.core.utils import normalize_phone_number

logger = logging.getLogger(__name__)


@dataclass
class PlanoDePerfil:
    telefone: str
    fica: object
    saem: list = field(default_factory=list)


def _cadastros(u) -> int:
    from apps.stores.models import StoreCustomer
    return StoreCustomer.objects.filter(unified_user=u).count()


def planejar() -> list:
    """Um plano por pessoa duplicada. Não escreve."""
    from apps.users.models import UnifiedUser
    grupos = defaultdict(list)
    for u in UnifiedUser.objects.exclude(phone_number=''):
        canonico = normalize_phone_number(u.phone_number) or u.phone_number
        grupos[canonico].append(u)
    planos = []
    for telefone, perfis in sorted(grupos.items()):
        if len(perfis) < 2:
            continue
        perfis.sort(key=lambda u: (
            u.django_user_id is None,
            -_cadastros(u),
            -(u.total_orders or 0),
            u.first_seen_at.timestamp() if u.first_seen_at else float('inf'),
        ))
        logins = [u for u in perfis if u.django_user_id]
        if len(logins) > 1:
            logger.warning('perfis %s: %d logins diferentes — fica de fora', telefone, len(logins))
            continue
        planos.append(PlanoDePerfil(telefone=telefone, fica=perfis[0], saem=perfis[1:]))
    return planos


def _nome_melhor(atual: str, outro: str) -> str:
    from apps.core.services.customer_identity import CustomerIdentityService as CIS
    atual, outro = (atual or '').strip(), (outro or '').strip()
    if not atual or CIS.is_placeholder_name(atual):
        return outro or atual
    # "Wanny" × "Wanny Tapajos": o nome completo que começa igual vence.
    if outro and len(outro) > len(atual) and CIS.chave_de_texto(outro).startswith(CIS.chave_de_texto(atual)):
        return outro
    return atual


def _fundir_enderecos(fica, sai) -> None:
    from apps.core.services.customer_identity import CustomerIdentityService as CIS
    from apps.users.models import UserAddress
    meus = list(UserAddress.objects.filter(unified_user=fica))
    for a in UserAddress.objects.filter(unified_user=sai):
        chave = CIS.chave_do_lugar(a.street, a.number, a.complement)
        igual = next((m for m in meus if m.tenant_id == a.tenant_id
                      and CIS.chave_do_lugar(m.street, m.number, m.complement) == chave), None)
        if igual is None:
            a.unified_user = fica
            a.is_default = a.is_default and not any(m.is_default and m.tenant_id == a.tenant_id for m in meus)
            a.save(update_fields=['unified_user', 'is_default'])
            meus.append(a)
            continue
        faltando = [c for c in ('neighborhood', 'complement', 'zip_code', 'lat', 'lng')
                    if getattr(a, c) and not getattr(igual, c)]
        for c in faltando:
            setattr(igual, c, getattr(a, c))
        if faltando:
            igual.save(update_fields=faltando)
        a.delete()


def _repontar(fica, sai) -> None:
    from apps.users.models import UnifiedUser
    for rel in UnifiedUser._meta.related_objects:
        modelo = rel.related_model
        if modelo.__name__ == 'UserAddress':
            continue
        campo = rel.field.name
        for linha in modelo.objects.filter(**{campo: sai}):
            setattr(linha, campo, fica)
            try:
                with transaction.atomic():
                    linha.save(update_fields=[campo])
            except IntegrityError:
                logger.info('perfis: %s #%s colidiu ao repontar; descartado', modelo.__name__, linha.pk)
                with transaction.atomic():
                    linha.delete()


@transaction.atomic
def aplicar(planos: list) -> int:
    fundidos = 0
    for plano in planos:
        fica = plano.fica
        herdar = {}
        for sai in plano.saem:
            fica.name = _nome_melhor(fica.name, sai.name)
            for campo in ('email', 'google_id', 'profile_picture'):
                if not getattr(fica, campo) and getattr(sai, campo) and campo not in herdar:
                    herdar[campo] = getattr(sai, campo)
            for campo, escolha in (('first_seen_at', min), ('last_seen_at', max), ('last_order_at', max)):
                valores = [v for v in (getattr(fica, campo), getattr(sai, campo)) if v]
                if valores:
                    setattr(fica, campo, escolha(valores))
            fica.total_orders = max(fica.total_orders or 0, sai.total_orders or 0)
            fica.total_spent = max(fica.total_spent or 0, sai.total_spent or 0)
            _fundir_enderecos(fica, sai)
            _repontar(fica, sai)
            sai.delete()
            fundidos += 1
        # Só depois de apagar os outros: e-mail, google_id e telefone são únicos.
        for campo, valor in herdar.items():
            setattr(fica, campo, valor)
        fica.phone_number = plano.telefone
        fica.save()
    return fundidos
