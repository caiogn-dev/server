import logging
import re
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from rest_framework import status

from .storefront_views import get_active_store, PublicWriteThrottle, CheckoutThrottle
from ...models import StoreLoyaltyAccount, StoreOrder
from ...services.checkout_service import CheckoutService
from ...services.loyalty_service import LoyaltyService

logger = logging.getLogger(__name__)


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


class ConquistasView(APIView):
    """GET /api/v1/stores/{slug}/conquistas/ — marcos, próxima meta e metas.

    Tudo numa chamada só: a página mostra resumo, próxima conquista e a linha
    do tempo juntos, e três requisições produziriam três estados de carga
    piscando em sequência na mesma tela.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)

        from ...services.conquistas import painel_de_conquistas
        return Response(painel_de_conquistas(store))


class CashbackResumoView(APIView):
    """Painel do cashback: os números que viram decisão, e a fila de quem
    perde saldo primeiro.

    Agrega no BANCO, nunca devolve página para o frontend somar: somar a
    primeira página produz um total menor que o real com cara de total, e
    número errado com aparência de certo é pior que número ausente.
    """
    permission_classes = [IsAuthenticated]

    PAGE_SIZE = 50
    JANELA_DE_URGENCIA = 7  # dias

    def get(self, request, store_slug):
        from decimal import Decimal
        from django.db.models import Min
        from apps.stores.models import StoreCashbackLot, StoreCashbackRedemption
        from apps.stores.services.cashback_service import CashbackService

        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)

        agora = timezone.now()
        vivos = StoreCashbackLot.objects.filter(
            store=store, remaining__gt=0, expires_at__gt=agora,
        )
        zero = Decimal('0.00')

        resumo = {
            'saldo_em_circulacao': vivos.aggregate(t=Coalesce(Sum('remaining'), zero))['t'],
            'clientes_com_saldo': vivos.values('phone').distinct().count(),
            # A campanha de hoje: saldo que morre dentro da semana. É o único
            # número desta tela que tem prazo, e por isso o único que manda
            # alguém agir agora.
            'vence_em_7_dias': vivos.filter(
                expires_at__lte=agora + timedelta(days=self.JANELA_DE_URGENCIA),
            ).aggregate(t=Coalesce(Sum('remaining'), zero))['t'],
            'saldo_de_indicacao': vivos.filter(
                origin=StoreCashbackLot.Origin.REFERRAL,
            ).aggregate(t=Coalesce(Sum('remaining'), zero))['t'],
            # Quanto o programa JÁ custou de verdade — crédito que virou
            # desconto. Saldo em circulação é promessa; isto é a conta paga.
            'ja_resgatado': StoreCashbackRedemption.objects.filter(
                store=store,
            ).aggregate(t=Coalesce(Sum('amount'), zero))['t'],
        }

        # DE ONDE VEIO O SALDO. Somar tudo num número só faz o dono achar que
        # "deve" R$ 5.000 quando R$ 4.500 já entraram no caixa: cashback de
        # compra e de indicação são custo de marketing; carteira pré-paga é
        # dinheiro que o cliente JÁ PAGOU. São contas opostas com a mesma cara.
        por_origem = {
            chave: vivos.filter(origin=chave).aggregate(
                t=Coalesce(Sum('remaining'), zero))['t']
            for chave, _ in StoreCashbackLot.Origin.choices
        }
        resumo['por_origem'] = por_origem
        resumo['saldo_pago_pelo_cliente'] = por_origem.get(
            StoreCashbackLot.Origin.PREPAID, zero)
        resumo['saldo_concedido_pela_loja'] = sum(
            (v for k, v in por_origem.items() if k != StoreCashbackLot.Origin.PREPAID),
            zero,
        )

        # ORDEM: quem vence primeiro. A pergunta desta lista é "a quem eu mando
        # mensagem hoje", e quem está prestes a perder saldo é quem responde.
        from django.db.models import Case, When, Q, DecimalField

        linhas = (
            vivos.values('phone')
            .annotate(
                saldo=Sum('remaining'),
                # A parte COMPRADA, separada: é o que o dono não pode tratar
                # como custo, e é a única que exige telefone comprovado para
                # ser gasta.
                saldo_carteira=Coalesce(Sum(Case(
                    When(origin=StoreCashbackLot.Origin.PREPAID, then='remaining'),
                    default=Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2),
                )), zero),
                vence_em=Min('expires_at'),
            )
            .order_by('vence_em', '-saldo')
        )
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE

        # Cupons de entrega numa consulta só, indexada por telefone: buscar por
        # linha faria N+1 numa tela que lista 50 clientes.
        from apps.stores.models import StoreDeliveryCoupon
        cupons_por_telefone = dict(
            StoreDeliveryCoupon.objects
            .filter(store=store, remaining__gt=0, expires_at__gt=agora)
            .values_list('phone')
            .annotate(t=Sum('remaining'))
        )

        return Response({
            'enabled': CashbackService.is_enabled(store),
            'percent': CashbackService.percent(store),
            'referral_percent': CashbackService.referral_percent(store),
            'expiry_days': CashbackService.expiry_days(store),
            'resumo': resumo,
            'count': linhas.count(),
            'results': [
                {
                    'phone': linha['phone'],
                    'saldo': linha['saldo'],
                    'saldo_carteira': linha['saldo_carteira'],
                    'cupons_entrega': cupons_por_telefone.get(linha['phone'], 0),
                    'vence_em': linha['vence_em'].isoformat(),
                    'dias_para_vencer': max(0, (linha['vence_em'] - agora).days),
                }
                for linha in linhas[start:start + self.PAGE_SIZE]
            ],
        })


class CashbackSaldoView(APIView):
    """Saldo do cliente no cardápio — por TELEFONE, sem login.

    O storefront é guest-first: exigir login para ver o próprio saldo
    esconderia o cashback de quase todo mundo, que é o erro que a fidelidade
    antiga cometeu ao chavear por `user`.

    AllowAny com throttle: o telefone vem na query e não é segredo, mas
    responder saldo sem limite viraria oráculo para descobrir quem é cliente
    da loja. O throttle de escrita pública já existe para isto.
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicWriteThrottle]

    def get(self, request, store_slug):
        from apps.stores.services.cashback_service import CashbackService

        store = get_active_store(store_slug)
        phone = (request.query_params.get('phone') or '').strip()
        if not CashbackService.is_enabled(store):
            return Response({'enabled': False, 'saldo': '0.00'})

        # O saldo MOSTRADO é o saldo GASTÁVEL por quem está perguntando: sem o
        # telefone comprovado o pré-pago não entra. Anunciar R$ 456 para quem
        # não conseguiria usá-los produziria a pior tela possível — promessa na
        # vitrine e recusa no checkout.
        from apps.stores.services.carteira_service import telefone_comprovado
        verificado = telefone_comprovado(request, phone)
        saldo = CashbackService.balance(store, phone, verificado) if phone else Decimal('0.00')
        vence = CashbackService.expires_next(store, phone, verificado) if phone else None
        return Response({
            'enabled': True,
            # A tela precisa saber que há algo a destravar. Sem isto o cliente
            # que acabou de comprar o pacote via "R$ 0,00" sem uma palavra de
            # explicação — que foi exatamente o que aconteceu no primeiro teste.
            'saldo_bloqueado': (
                bool(phone) and not verificado
                and CashbackService.tem_saldo_bloqueado(store, phone)
            ),
            'percent': CashbackService.percent(store),
            'referral_percent': CashbackService.referral_percent(store),
            'expiry_days': CashbackService.expiry_days(store),
            'saldo': saldo,
            'vence_em': vence.isoformat() if vence else None,
        })


class CarteiraView(APIView):
    """Vitrine da carteira: pacotes à venda + saldo de quem está olhando.

    Uma chamada só de propósito. A tela precisa dos dois juntos para decidir o
    que mostrar — quem já tem saldo vê "restam R$ 228", quem não tem vê a
    escada de pacotes — e duas chamadas produziriam um piscar entre os dois
    estados no meio do carregamento.

    AllowAny com throttle, pelo mesmo motivo do saldo: o telefone vem na query
    e não é segredo, mas responder sem limite viraria oráculo para descobrir
    quem é cliente da loja.
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicWriteThrottle]

    def get(self, request, store_slug):
        from apps.stores.services.carteira_service import CarteiraService
        from apps.stores.services.cashback_service import CashbackService

        store = get_active_store(store_slug)
        if not CashbackService.is_enabled(store):
            return Response({'ativa': False, 'pacotes': [], 'saldo': '0.00'})

        pacotes = CarteiraService.pacotes(store)
        phone = (request.query_params.get('phone') or '').strip()
        from apps.stores.services.carteira_service import telefone_comprovado
        verificado = telefone_comprovado(request, phone)
        estado = CarteiraService.saldo(store, phone, verificado) if phone else {
            'saldo': '0.00', 'expira_em': None, 'cupons_entrega': 0,
        }
        return Response({
            'ativa': bool(pacotes),
            'pacotes': [
                {
                    'id': p['id'], 'nome': p['nome'],
                    'paga': str(p['paga']), 'credito': str(p['credito']),
                    'bonus': str(p['bonus']),
                }
                for p in pacotes
            ],
            'validade_dias': CashbackService.expiry_days(store),
            # Duas validades, dois dinheiros: o bônus vence rápido para criar
            # urgência; o que a cliente pagou dura mais. Prometer 3 meses e a
            # tela dizer 30 dias é pior que não prometer.
            'carteira_validade_dias': CashbackService.carteira_expiry_days(store),
            'cashback_percent': str(CashbackService.percent(store)),
            # Quanto o cliente ganha por INDICAR. A tela precisa deste número
            # para montar o convite: quem convida alguém a indicar tem que
            # dizer quanto ele leva, e inventar o valor é mentir sobre
            # dinheiro. Sem isto o link de indicação não tem o que prometer.
            'referral_percent': str(CashbackService.referral_percent(store)),
            # A tela precisa saber se deve pedir a confirmação do número antes
            # de prometer o saldo comprado.
            'telefone_verificado': verificado,
            'saldo_bloqueado': (
                bool(phone) and not verificado
                and CashbackService.tem_saldo_bloqueado(store, phone)
            ),
            **estado,
        })


class CarteiraCompraView(APIView):
    """Gera a cobrança PIX de um pacote.

    O saldo NÃO entra aqui — entra no webhook, quando o PIX é pago. Creditar
    na intenção de compra daria saldo a quem só abriu a tela.
    """
    permission_classes = [AllowAny]
    throttle_classes = [CheckoutThrottle]

    def post(self, request, store_slug):
        from apps.stores.services.carteira_service import CarteiraService

        store = get_active_store(store_slug)
        try:
            resultado = CarteiraService.comprar(
                store,
                phone=(request.data.get('phone') or '').strip(),
                tier_id=(request.data.get('tier_id') or '').strip(),
                payer_name=(request.data.get('name') or '').strip(),
                payer_email=(request.data.get('email') or '').strip(),
            )
        except ValueError as e:
            # Mensagem de regra de negócio, em português e acionável — o
            # genérico "erro ao processar" deixaria o cliente sem saber que
            # faltou o celular.
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('carteira: falha ao gerar cobrança em %s', store.slug)
            return Response(
                {'error': 'Não foi possível gerar o PIX agora. Tente de novo em instantes.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(resultado, status=status.HTTP_201_CREATED)


class CashbackAjusteView(APIView):
    """Crédito manual do lojista: cortesia, reparação, brinde.

    Existe para tirar isto do shell de produção. Creditar cliente pelo console
    é como se perde dinheiro sem rastro: ninguém sabe quem deu, quanto, nem
    por quê — e no mês seguinte o saldo em circulação não fecha com nada.

    `motivo` é OBRIGATÓRIO. Um crédito sem justificativa é exatamente o buraco
    por onde some dinheiro em qualquer programa de fidelidade; o motivo fica no
    lote e no log, com o usuário que fez.

    Dono da loja apenas. Endpoint de dinheiro sem checagem de dono é IDOR, que
    já apareceu neste repositório em junho.
    """
    permission_classes = [IsAuthenticated]

    TETO = Decimal('5000.00')

    def post(self, request, store_slug):
        from decimal import InvalidOperation
        from apps.stores.services.cashback_service import CashbackService

        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)

        phone = str(request.data.get('phone') or '').strip()
        motivo = str(request.data.get('motivo') or '').strip()
        if not phone:
            return Response({'error': 'Informe o celular do cliente.'}, status=400)
        if not motivo:
            return Response({'error': 'Diga o motivo do crédito.'}, status=400)

        try:
            valor = Decimal(str(request.data.get('valor') or '0'))
        except (InvalidOperation, TypeError, ValueError):
            return Response({'error': 'Valor inválido.'}, status=400)
        if valor <= 0:
            return Response({'error': 'O valor precisa ser maior que zero.'}, status=400)
        if valor > self.TETO:
            # Teto de sanidade: um zero a mais num crédito manual é o tipo de
            # erro que só aparece no fechamento do mês.
            return Response(
                {'error': f'Valor acima do limite de R$ {self.TETO:.2f} por ajuste.'},
                status=400,
            )

        lote = CashbackService.credit_adjust(
            store, phone, valor, motivo, autor=request.user,
        )
        if lote is None:
            return Response(
                {'error': 'Não foi possível creditar. Confira o celular.'}, status=400,
            )
        return Response({
            'phone': lote.phone,
            'valor': str(lote.amount),
            'motivo': motivo,
            'vence_em': lote.expires_at.isoformat(),
            'saldo_atual': str(CashbackService.balance(store, lote.phone, verificado=True)),
        }, status=status.HTTP_201_CREATED)



class IndicacoesView(APIView):
    """Quem veio por quem.

    Nasceu de uma pergunta do dono que não tinha resposta: "a Elisangela quis
    indicar, mas como vou saber quem veio pela Elisangela?".

    O rastreio já funcionava — o link `?indica=<telefone>` vira
    `metadata.indicado_por` no pedido do amigo e credita quem indicou —, mas o
    resultado morria num total somado na tela de cashback. Programa de
    indicação que não diz QUEM indicou é só um desconto com nome bonito: a loja
    não consegue agradecer quem trouxe cliente, não sabe quem são seus
    divulgadores, e não enxerga o telefone que "indicou" trinta desconhecidos.

    O dado sempre esteve gravado: o lote de indicação guarda o telefone de quem
    indicou e aponta para o pedido do amigo. Aqui só se pergunta.

    Dono da loja apenas: são telefones e histórico de compra de clientes.
    """
    permission_classes = [IsAuthenticated]

    LIMITE = 200

    def get(self, request, store_slug):
        from apps.stores.models import StoreCashbackLot, StoreOrder
        from apps.stores.services.cashback_service import CashbackService

        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)

        lotes = (
            StoreCashbackLot.objects
            .filter(store=store, origin=StoreCashbackLot.Origin.REFERRAL)
            .select_related('order')
            .order_by('-created_at')[:self.LIMITE]
        )

        # O telefone de quem indicou não diz nada ao dono; o nome diz. Ele vem
        # dos pedidos do próprio indicador — quem indica quase sempre já é
        # cliente, e é exatamente essa pessoa que a loja quer reconhecer.
        indicadores = {(l.phone or '').strip() for l in lotes if (l.phone or '').strip()}
        nomes = {}
        if indicadores:
            for phone, nome in (
                StoreOrder.objects
                .filter(store=store, customer_phone__in=indicadores)
                .exclude(customer_name='')
                .order_by('-created_at')
                .values_list('customer_phone', 'customer_name')
            ):
                nomes.setdefault(phone, nome)

        indicacoes = []
        resumo = {}
        for lote in lotes:
            phone = (lote.phone or '').strip()
            pedido = lote.order
            indicacoes.append({
                'id': str(lote.id),
                'indicador_phone': phone,
                'indicador_nome': nomes.get(phone, ''),
                'amigo_nome': getattr(pedido, 'customer_name', '') or '',
                'amigo_phone': getattr(pedido, 'customer_phone', '') or '',
                'pedido': getattr(pedido, 'order_number', '') or '',
                'pedido_total': str(getattr(pedido, 'total', '') or ''),
                'valor': str(lote.amount),
                'data': lote.created_at.isoformat(),
            })
            agregado = resumo.setdefault(phone, {
                'phone': phone, 'nome': nomes.get(phone, ''),
                'total_indicados': 0, 'total_creditado': Decimal('0.00'),
            })
            agregado['total_indicados'] += 1
            agregado['total_creditado'] += lote.amount

        por_indicador = sorted(
            resumo.values(),
            key=lambda r: (-r['total_indicados'], -r['total_creditado']),
        )
        for r in por_indicador:
            r['total_creditado'] = str(r['total_creditado'])

        return Response({
            'indicacoes': indicacoes,
            'por_indicador': por_indicador,
            'referral_percent': str(CashbackService.referral_percent(store)),
        })
