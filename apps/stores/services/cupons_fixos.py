"""Cupons de código FIXO — o que substituiu os três geradores.

O sistema criava um código único por pessoa em três pontos. Medido em produção
na Cê Saladas antes de desligar:

    AVALIA5-XXXXXX   13 criados   0 usados
    INDICA-XXXX       0 criados   0 usados
    AMIGO5-XXXX       0 criados   0 usados

Zero redenções em todos. A causa não é o desconto — é o código: ninguém digita
`AVALIA5-F34854` no carrinho. E o efeito colateral foi a lista de cupons do
painel virar depósito: 33 cupons, 27 ativos, 7 sem um único uso.

Código fixo e curto resolve os dois lados. O cliente dita no WhatsApp, lembra
no dia seguinte e manda print pro amigo. O dono vê dois cupons na lista, não
duzentos.

A ATRIBUIÇÃO — que era a razão de o código ser pessoal — migrou para o
cashback: quem indica ganha saldo (CashbackService.credit_referral), e o
vínculo vive em StoreCoupon.metadata['owner_phone'] nos cupons de parceiro.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

CODIGO_DE_FEEDBACK = 'FEEDBACK10'
CODIGO_DE_INDICACAO = 'INDICA10'

DESCONTO = 10
LIMITE_DE_USOS = 1000
VALIDADE_EM_DIAS = 60

# Prefixos dos geradores aposentados. Só isto é desativado na limpeza — um
# cupom de verdade nunca começa assim.
PREFIXOS_GERADOS = ('AVALIA5-', 'INDICA-', 'AMIGO5-')


class CuponsFixos:

    @staticmethod
    def _garantir(store, code: str, descricao: str, **extras):
        """Devolve SEMPRE o mesmo cupom da loja, revalidando se preciso.

        Renovar em vez de criar outro é o ponto do arquivo: `get_or_create` com
        um código novo é exatamente o gerador que estamos removendo. E a
        renovação nunca mexe em `used_count` — o contador é histórico da loja,
        não estado do cupom.
        """
        from apps.stores.models import StoreCoupon

        agora = timezone.now()
        campos = {
            'description': descricao,
            'discount_type': 'percentage',
            'discount_value': DESCONTO,
            'usage_limit': LIMITE_DE_USOS,
            'usage_limit_per_user': 1,
            'is_active': True,
            'valid_from': agora,
            'valid_until': agora + timedelta(days=VALIDADE_EM_DIAS),
            **extras,
        }
        cupom, criado = StoreCoupon.objects.get_or_create(
            store=store, code=code, defaults=campos,
        )
        if not criado and (not cupom.is_active or cupom.valid_until <= agora):
            for campo, valor in campos.items():
                setattr(cupom, campo, valor)
            cupom.save(update_fields=list(campos.keys()) + ['updated_at'])
        return cupom

    @staticmethod
    def de_feedback(store):
        """FEEDBACK10 — quem avalia a loja ganha 10%, uma vez."""
        return CuponsFixos._garantir(
            store, CODIGO_DE_FEEDBACK, 'Obrigado por avaliar a gente',
        )

    @staticmethod
    def de_indicacao(store):
        """INDICA10 — o amigo indicado ganha 10% no primeiro pedido.

        Sem telefone no metadata: este cupom é de todo mundo. Quem indica é
        recompensado em cashback, não em cupom pessoal.
        """
        return CuponsFixos._garantir(
            store, CODIGO_DE_INDICACAO, 'Indicação de amigo — primeiro pedido',
            first_order_only=True,
        )

    @staticmethod
    def aposentar_gerados(store) -> int:
        """Desativa os cupons dos geradores antigos que NUNCA foram usados.

        Cupom já usado fica de pé: tem cliente com ele na mão, e desativar
        seria quebrar uma promessa por causa de faxina. Devolve quantos saíram.
        """
        from django.db.models import Q
        from apps.stores.models import StoreCoupon

        filtro = Q()
        for prefixo in PREFIXOS_GERADOS:
            filtro |= Q(code__startswith=prefixo)
        return StoreCoupon.objects.filter(
            filtro, store=store, is_active=True, used_count=0,
        ).update(is_active=False)
