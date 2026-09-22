"""Convidar colaborador para uma loja.

POR QUE ESTE MÓDULO EXISTE

O CRUD de equipe está no ar desde junho e nenhuma loja o usa: em 22/09 havia
4 membros no total e a Cê Saladas tinha ZERO. Dois motivos, medidos:

1. `TeamMemberCreateSerializer.user_id` era `UUIDField`, e a chave do `User`
   deste projeto é `AutoField` (inteiro). Toda criação voltava 400
   "Deve ser um UUID válido" — o endpoint NUNCA conseguiu criar um membro.
   As 4 linhas existentes nasceram por shell/admin em junho.

2. Mesmo corrigido, pedir o id de um usuário não serve ao dono da loja: ele
   não sabe o id de ninguém, e a regra da casa é que o painel não mostra id,
   token nem endereço de API.

Telefone é a identidade natural aqui: é como o cliente entra (OTP do
WhatsApp), é a chave do bot e é o que o dono sabe de cor do funcionário.

A resolução de pessoa reusa `CustomerIdentityService.resolve_user`, que já
trata as variações de formato ('63 99999-0001' e '+5563999990001' são a mesma
pessoa). Escrever outra aqui criaria a segunda cópia da regra que já custou
sete cópias de "gruda 55" em agosto.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError as DjangoValidationError

from apps.core.services.customer_identity import CustomerIdentityService
from apps.core.utils import normalize_phone_number
from apps.stores.models import StoreTeamMember

logger = logging.getLogger(__name__)

#: Menos que isso não é telefone brasileiro com DDD (2 do DDD + 8 do número).
MINIMO_DE_DIGITOS = 10


def telefone_valido(telefone: str) -> str:
    """O telefone normalizado, ou levanta com mensagem para a tela."""
    digitos = CustomerIdentityService.digits_only(telefone or '')
    if len(digitos) < MINIMO_DE_DIGITOS:
        raise DjangoValidationError(
            'Informe o telefone com DDD, por exemplo 63 99999-0001.'
        )
    return normalize_phone_number(telefone) or telefone


def convidar(store, *, telefone: str = '', nome: str = '', usuario=None,
             papel: str = StoreTeamMember.Role.OPERATOR, convidado_por=None):
    """Põe alguém na equipe da loja. Devolve (membro, criado).

    Reconvidar não é erro: `unique_together` é (tenant, user) e DELETE é soft
    delete, então convidar de volta quem saiu tem que REATIVAR em vez de
    estourar IntegrityError. Reconvidar quem já está dentro atualiza o papel —
    é o que o dono espera de um formulário que ele preencheu de novo.
    """
    if usuario is None:
        telefone = telefone_valido(telefone)
        usuario, _perfil, _criado = CustomerIdentityService.resolve_user(
            phone=telefone, full_name=nome, create=True,
        )

    membro, criado = StoreTeamMember.objects.get_or_create(
        tenant=store,
        user=usuario,
        defaults={
            'role': papel,
            'is_active': True,
            'invited_by': convidado_por,
            'created_by': convidado_por,
        },
    )
    if not criado:
        membro.role = papel
        membro.is_active = True
        membro.save(update_fields=['role', 'is_active', 'updated_at'])
        logger.info(
            '[equipe] Membro reconvidado em %s: user=%s papel=%s',
            store.slug, usuario.pk, papel,
        )
    return membro, criado
