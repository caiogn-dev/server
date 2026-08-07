import re

from django.db.models import Count, ExpressionWrapper, F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from .storefront_views import get_active_store, PublicWriteThrottle
from ...models import StoreLoyaltyAccount, StoreOrder
from ...services.checkout_service import CheckoutService
from ...services.loyalty_service import LoyaltyService


def _user_phone(user) -> str:
    """Telefone verificado do usuário: UserProfile.phone, ou o padrão
    cliente_<digits> do username criado pelo fluxo de OTP."""
    profile = getattr(user, 'profile', None)
    phone = getattr(profile, 'phone', '') or ''
    if phone:
        return phone
    match = re.fullmatch(r'cliente_(\d{10,13})', user.username or '')
    return match.group(1) if match else ''


def resolve_loyalty_status_for_user(store, user) -> dict:
    """Status de fidelidade do usuário autenticado, com fallback por telefone.

    O checkout pode ter resolvido o customer dos pedidos para OUTRO usuário
    (identidade fragmentada por canal). Se a conta própria está vazia, usa o
    telefone verificado da sessão para achar a conta operante — a mesma
    resolução do guest-status, então display e crédito ficam consistentes.
    """
    status = CheckoutService.get_loyalty_status(store, user)
    if status.get('qualified_salads') or status.get('rewards_redeemed'):
        return status
    phone = _user_phone(user)
    if not phone:
        return status
    other = LoyaltyGuestStatusView()._resolve_user(store, phone)
    if other and other.id != user.id:
        alt = CheckoutService.get_loyalty_status(store, other)
        if alt.get('qualified_salads') or alt.get('rewards_redeemed'):
            return alt
    return status


class LoyaltyStatusView(APIView):
    """GET — returns current loyalty progress for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        loyalty = resolve_loyalty_status_for_user(store, request.user)
        return Response(loyalty)


class LoyaltyRedeemCheckView(APIView):
    """POST — pre-flight check: confirms user has a reward available to redeem.
    Returns 409 if no reward is available.
    Actual redemption happens at checkout via use_loyalty_reward=True."""
    permission_classes = [IsAuthenticated]

    def post(self, request, store_slug):
        store = get_active_store(store_slug)
        loyalty = resolve_loyalty_status_for_user(store, request.user)
        if not loyalty.get('can_redeem'):
            return Response(
                {'error': 'Nenhuma recompensa disponível', 'loyalty': loyalty},
                status=409,
            )
        return Response({'success': True, 'loyalty': loyalty})


def _falta_para_o_brinde(threshold: int):
    """Quantos itens faltam para o cliente fechar o cartão atual.

    `qualified_count % threshold` é o progresso; o que falta é o complemento.
    Quem acabou de fechar (resto 0) fica com `falta = threshold`, ou seja, no
    fim da fila — está no começo de um cartão novo, não perto de ganhar.
    """
    progresso = ExpressionWrapper(
        F('qualified_count') % Value(threshold), output_field=IntegerField(),
    )
    return ExpressionWrapper(
        Value(threshold) - progresso, output_field=IntegerField(),
    )


class LoyaltyAccountsView(APIView):
    """Listagem de contas de fidelidade da loja (dash). Dono ou superuser."""
    permission_classes = [IsAuthenticated]

    PAGE_SIZE = 50

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)
        threshold, _enabled = LoyaltyService._config(store)
        # ORDEM: quem está mais perto de fechar o cartão primeiro.
        #
        # Era `-updated_at`, que responde "quem comprou por último" — pergunta
        # que a lista de pedidos já responde melhor. A pergunta desta tela é
        # outra: a quem eu mando mensagem hoje. Quem está a 1 item do brinde
        # converte com um empurrão; quem acabou de começar, não.
        #
        # Desempate por `-qualified_count`: entre dois clientes a 1 item, o que
        # já comprou mais no total é o mais valioso.
        qs = (StoreLoyaltyAccount.objects.filter(store=store)
              .select_related('user')
              .annotate(_falta=_falta_para_o_brinde(threshold))
              .order_by('_falta', '-qualified_count', '-updated_at'))
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE
        results = []
        for acc in qs[start:start + self.PAGE_SIZE]:
            earned = acc.qualified_count // threshold
            results.append({
                'user_id': str(acc.user_id),
                'display_name': acc.user.get_full_name() or acc.user.username,
                'email': acc.user.email,
                'qualified_count': acc.qualified_count,
                'redeemed_count': acc.redeemed_count,
                'progress': acc.qualified_count % threshold,
                'available_rewards': max(0, earned - acc.redeemed_count),
                # Quantos itens faltam — o frontend não precisa refazer a conta
                # com o threshold, que ele recebe por outro caminho e pode
                # divergir.
                'falta': acc.qualified_count % threshold and threshold - (acc.qualified_count % threshold) or threshold,
                'updated_at': acc.updated_at.isoformat(),
            })
        payload = {'count': qs.count(), 'results': results}

        # `?resumo=1` — agregado do BANCO INTEIRO, não da página.
        #
        # A tentação é somar no frontend a partir da lista, e é justamente o
        # que não se pode fazer: a lista vem de 50 em 50, então somar a
        # primeira página produz um número menor que o real com cara de total.
        # Número errado com aparência de certo é pior que número ausente —
        # ninguém desconfia dele.
        #
        # Opcional de propósito: a listagem já é consumida por outra tela e
        # não deve carregar peso extra porque um consumidor novo precisa disso.
        if request.query_params.get('resumo') in ('1', 'true', 'True'):
            payload['resumo'] = self._resumo(qs, threshold)

        return Response(payload)

    @staticmethod
    def _resumo(qs, threshold):
        ganhos = ExpressionWrapper(
            F('qualified_count') / Value(threshold), output_field=IntegerField(),
        )
        disponiveis = ExpressionWrapper(
            F('qualified_count') / Value(threshold) - F('redeemed_count'),
            output_field=IntegerField(),
        )
        agg = qs.aggregate(
            participantes=Count('id'),
            brindes_ganhos=Coalesce(Sum(ganhos), 0),
            brindes_resgatados=Coalesce(Sum('redeemed_count'), 0),
            # Greatest(…, 0): resgate manual e restauração de backup produzem
            # `redeemed_count` maior que o ganho. Um "-3 brindes disponíveis"
            # na tela destrói a confiança em todos os outros números.
            brindes_disponiveis=Coalesce(
                Sum(Greatest(disponiveis, Value(0), output_field=IntegerField())), 0,
            ),
            # "Quase lá" = falta exatamente 1 item. É o corte acionável:
            # "falta 1 para você ganhar" é mensagem que se manda hoje e
            # converte; "falta 5" não é.
        )
        # "Quase lá" = falta exatamente 1 item para fechar o cartão. É o corte
        # acionável: "falta 1 para você ganhar" é mensagem que se manda hoje e
        # converte; "falta 5" não é. Conta separada porque o módulo dentro de
        # `filter=` não é portável entre bancos — e é um COUNT barato.
        agg['quase_la'] = qs.annotate(falta=_falta_para_o_brinde(threshold)).filter(
            falta=1,
        ).count()
        return agg


class LoyaltyGuestStatusView(APIView):
    """POST — status de fidelidade para guest (sem login) identificado só por telefone.

    Storefront não tem login real: clientes são guests (useGuestInfo, 90 dias).
    Resolve o usuário pelo último pedido da loja vinculado a esse telefone
    (mesmas variantes usadas pelo bot em LoyaltyStatusHandler) e devolve o
    mesmo formato de status do endpoint autenticado — nunca PII (nome/email).
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicWriteThrottle]

    @staticmethod
    def _build_phone_variants(raw_phone: str) -> list:
        from apps.core.utils import normalize_phone_number
        raw_phone = raw_phone or ''
        normalized = normalize_phone_number(raw_phone)
        digits_only = ''.join(filter(str.isdigit, raw_phone))
        variants = [raw_phone, normalized, digits_only]
        if normalized:
            variants.append(f'+{normalized}')
        # Autofill (Google/iOS) grava com +55 e pedidos antigos sem — casa os
        # dois sentidos: versão local (sem código do país) e versão com 55.
        if digits_only.startswith('55') and len(digits_only) in (12, 13):
            local = digits_only[2:]
            variants.extend([local, f'+55{local}'])
        elif digits_only and len(digits_only) in (10, 11):
            variants.extend([f'55{digits_only}', f'+55{digits_only}'])
        return [value for value in dict.fromkeys(v for v in variants if v)]

    def _resolve_user(self, store, phone):
        phone_variants = self._build_phone_variants(phone)
        if not phone_variants:
            return None
        order = (StoreOrder.objects
                 .filter(store=store, customer_phone__in=phone_variants, customer__isnull=False)
                 .order_by('-created_at').first())
        return order.customer if order else None

    def post(self, request, store_slug):
        store = get_active_store(store_slug)
        phone = request.data.get('phone') or ''
        user = self._resolve_user(store, phone)
        loyalty = CheckoutService.get_loyalty_status(store, user)
        return Response(loyalty)
