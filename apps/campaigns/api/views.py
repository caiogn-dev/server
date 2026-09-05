"""
Campaign API views - Unified with Automation.

Note: ScheduledMessageViewSet has been moved to apps.automation.api.views.
Use /api/v1/automation/scheduled-messages/ endpoint for scheduled message operations.
"""
import logging
import traceback
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db.models import Max, Q
from django.utils import timezone
from django.core.files.storage import default_storage

from ..models import Campaign, CampaignRecipient, ContactList
from apps.core.utils import build_absolute_media_url
from apps.core.permissions import accessible_whatsapp_account_ids, accessible_store_ids
from apps.whatsapp.models import WhatsAppAccount
from ..services import CampaignService
from .serializers import (
    CampaignSerializer,
    CampaignCreateSerializer,
    CampaignRecipientSerializer,
    AddRecipientsSerializer,
    ContactListSerializer,
    ContactListCreateSerializer,
    ImportContactsSerializer,
)

logger = logging.getLogger(__name__)


def _user_can_use_account(user, account_id):
    """True se o usuário pode operar sobre a WhatsAppAccount informada.

    Sem essa checagem (IDOR), qualquer autenticado criava campanhas/listas e
    importava contatos em contas de OUTRO tenant passando account_id arbitrário.
    """
    if not account_id:
        return False
    if user.is_superuser:
        return True
    return str(account_id) in {str(i) for i in accessible_whatsapp_account_ids(user)}


from apps.campaigns.services.contatos import contatos_para_resposta, mesclar_contato
from apps.campaigns.services.optout import chaves_bloqueadas
from apps.campaigns.services.segmentos import (
    Frequencia,
    Recencia,
    aplicar_filtros,
    bairros_disponiveis,
    chaves_dos_bairros,
    chaves_que_pediram_produtos,
    descrever_filtros,
    perfis_por_telefone,
    resumo_por_segmento,
)


class SystemContactsView(APIView):
    """
    Get contacts from the system (conversations, orders, subscribers).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get system contacts",
        description="Fetch contacts from conversations, orders, and subscribers",
        parameters=[
            {
                'name': 'account_id',
                'in': 'query',
                'description': 'WhatsApp account ID to filter contacts',
                'required': False,
                'schema': {'type': 'string'}
            },
            {
                'name': 'source',
                'in': 'query',
                'description': 'Source filter: all, conversations, orders, subscribers',
                'required': False,
                'schema': {'type': 'string', 'default': 'all'}
            },
            {
                'name': 'limit',
                'in': 'query',
                'description': 'Maximum number of contacts to return',
                'required': False,
                'schema': {'type': 'integer', 'default': 100}
            }
        ]
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        source = request.query_params.get('source', 'all')
        limit = int(request.query_params.get('limit', 100))
        user = request.user

        # Chaveado pela forma canônica do telefone: a mesma pessoa chega por
        # origens diferentes com/sem DDI e com/sem o nono dígito.
        contacts = {}

        # As lojas desta audiência são resolvidas ANTES de montar a lista.
        # Buscar contato em `accessible_store_ids(user)` — as doze lojas do
        # dono — trazia cliente e inscrito de outra loja para dentro da
        # campanha, não só para dentro dos números.
        lojas = self._store_ids(request)

        from apps.stores.models import Store
        accessible_account_ids = None if user.is_superuser else list(
            accessible_whatsapp_account_ids(user)
        )

        # Get contacts from conversations
        if source in ['all', 'conversations']:
            try:
                from apps.conversations.models import Conversation
                conv_qs = Conversation.objects.all()
                if accessible_account_ids is not None:
                    conv_qs = conv_qs.filter(account_id__in=accessible_account_ids)
                if account_id:
                    conv_qs = conv_qs.filter(account_id=account_id)

                conversations = conv_qs.values(
                    'phone_number', 'contact_name'
                ).annotate(
                    last_activity=Max('updated_at')
                ).order_by('-last_activity')[:limit]

                for conv in conversations:
                    mesclar_contato(
                        contacts, conv['phone_number'], conv['contact_name'], 'conversation'
                    )
            except Exception as e:
                logger.warning(f"Error fetching conversations: {e}")

        # Get contacts from orders
        if source in ['all', 'orders']:
            try:
                from apps.stores.models import StoreOrder, StoreIntegration
                # Só as lojas desta audiência — ver `_store_ids`.
                orders_qs = StoreOrder.objects.filter(store_id__in=lojas)
                if account_id:
                    try:
                        wa_account = WhatsAppAccount.objects.get(id=account_id)
                        # DUAS formas de a loja estar ligada a um número, e a
                        # segunda era ignorada: em 28/ago/2026 NENHUMA das
                        # quatro lojas reais tinha `StoreIntegration` — Cê
                        # Saladas e Pastita ligam pelo `Store.whatsapp_account`
                        # direto. Como só a integração era consultada, filtrar
                        # por conta zerava os contatos vindos de PEDIDO e
                        # sobrava só quem tinha conversado. Ou seja: quem
                        # comprou sumia justamente da tela de campanha.
                        por_integracao = StoreIntegration.objects.filter(
                            integration_type=StoreIntegration.IntegrationType.WHATSAPP
                        ).filter(
                            Q(phone_number_id=wa_account.phone_number_id) |
                            Q(waba_id=wa_account.waba_id)
                        ).values_list('store_id', flat=True)

                        por_vinculo_direto = Store.objects.filter(
                            whatsapp_account=wa_account
                        ).values_list('id', flat=True)

                        store_ids = set(por_integracao) | set(por_vinculo_direto)
                        orders_qs = orders_qs.filter(store_id__in=store_ids)
                    except WhatsAppAccount.DoesNotExist:
                        pass

                orders = orders_qs.values(
                    'customer_phone', 'customer_name'
                ).annotate(
                    last_order=Max('created_at')
                ).order_by('-last_order')[:limit]
                
                for order in orders:
                    mesclar_contato(
                        contacts, order['customer_phone'], order['customer_name'], 'order'
                    )
            except Exception as e:
                logger.warning(f"Error fetching orders: {e}")
        
        # Get contacts from marketing subscribers
        if source in ['all', 'subscribers']:
            try:
                from apps.marketing.models import Subscriber
                sub_qs = (
                    Subscriber.objects
                    .filter(phone__isnull=False, store_id__in=lojas)
                    .exclude(phone='')
                )
                subscribers = sub_qs.values(
                    'phone', 'name', 'email'
                ).order_by('-created_at')[:limit]
                
                for sub in subscribers:
                    mesclar_contato(
                        contacts, sub['phone'], sub['name'] or sub['email'], 'subscriber'
                    )
            except Exception as e:
                logger.warning(f"Error fetching subscribers: {e}")
        
        # Get contacts from automation sessions
        if source in ['all', 'sessions']:
            try:
                from apps.automation.models import CustomerSession
                sessions_qs = CustomerSession.objects.all()
                if not user.is_superuser:
                    account_ids = accessible_whatsapp_account_ids(user)
                    sessions_qs = sessions_qs.filter(company__account_id__in=account_ids)
                if account_id:
                    sessions_qs = sessions_qs.filter(company__account_id=account_id)
                
                sessions = sessions_qs.values(
                    'phone_number', 'customer_name'
                ).annotate(
                    last_activity=Max('updated_at')
                ).order_by('-last_activity')[:limit]
                
                for session in sessions:
                    mesclar_contato(
                        contacts, session['phone_number'], session['customer_name'], 'session'
                    )
            except Exception as e:
                logger.warning(f"Error fetching sessions: {e}")
        
        # A segmentação entra AQUI, depois da deduplicação: filtrar antes
        # deixaria a mesma pessoa passar por uma origem e ser barrada por
        # outra, que é o bug que a dedup já resolveu.
        filtros = self._filtros_da_query(request)
        perfis = perfis_por_telefone(lojas)

        # O resumo é calculado ANTES dos filtros de propósito: ele existe para
        # mostrar o tamanho de cada balde e ajudar a escolher, e um resumo que
        # já obedece o filtro escolhido só sabe dizer o que foi escolhido.
        resumo = resumo_por_segmento(contacts, perfis)

        chaves_produto = None
        if filtros.get('produtos'):
            chaves_produto = chaves_que_pediram_produtos(lojas, filtros['produtos'])
            # O nome vem para a FRASE da tela. Sem isto o cabeçalho dizia
            # "Todos os contatos" com a lista já filtrada por produto.
            from apps.stores.models import StoreProduct
            filtros['produtos_nomes'] = list(
                StoreProduct.objects
                .filter(id__in=filtros['produtos'], store_id__in=lojas)
                .values_list('name', flat=True)
            )
        chaves_bairro = (
            chaves_dos_bairros(lojas, filtros['bairros'])
            if filtros.get('bairros') else None
        )

        selecionados = aplicar_filtros(
            contacts, perfis, filtros,
            chaves_por_produto=chaves_produto,
            chaves_por_bairro=chaves_bairro,
        )

        # Quem pediu para sair não pode aparecer nem como sugestão: a lista
        # desta tela é exatamente a que vira destinatário no clique seguinte.
        fora = set()
        if account_id and _user_can_use_account(user, account_id):
            try:
                conta = WhatsAppAccount.objects.get(id=account_id)
                fora = chaves_bloqueadas(conta)
            except WhatsAppAccount.DoesNotExist:
                pass
        bloqueados = len(set(selecionados) & fora)
        for chave in fora:
            selecionados.pop(chave, None)

        contact_list = [
            {k: v for k, v in c.items() if k != 'tem_wa_id'}
            for c in list(selecionados.values())[:limit]
        ]

        return Response({
            'count': len(contact_list),
            # `total` é antes do corte por `limit`: sem ele a tela diria
            # "500 contatos" para uma base de 1.200 e o dono acharia que é tudo.
            'total': len(selecionados),
            'total_sem_filtro': len(contacts),
            'excluidos_por_optout': bloqueados,
            'descricao': descrever_filtros(filtros),
            'resumo': resumo,
            'results': contact_list,
        })

    def _store_ids(self, request):
        """As lojas que definem esta audiência. NUNCA "todas as que o dono vê".

        O dono da Cê Saladas enxerga DOZE lojas (várias de demonstração). Usar
        `accessible_store_ids` inteiro fazia o seletor listar o catálogo das
        doze e — bem pior — somava os pedidos de todas no perfil de compra:
        95 "compradores" onde havia 59, e 21 "inativos" onde havia 7. Quem
        comprou na Pastita entrava como cliente da Cê Saladas, e o segmento
        "sumidos" prometia gente que nunca foi cliente daquela loja.

        Ordem de resolução, da mais específica para a menos:
          1. `store` na query (o painel sabe qual loja está aberta);
          2. as lojas ligadas à conta de WhatsApp da campanha;
          3. nada — audiência vazia é melhor que audiência de outra loja.
        """
        return resolver_lojas_da_audiencia(request)

    def _filtros_da_query(self, request):
        """Traduz a query string nos filtros de segmento.

        Valores desconhecidos são DESCARTADOS em vez de virarem erro: uma tela
        antiga mandando um segmento que não existe mais deve ver "todos", e
        não um 400 que quebra a página inteira.
        """
        from decimal import Decimal, InvalidOperation

        def lista(nome):
            bruto = request.query_params.getlist(nome) or []
            if len(bruto) == 1 and ',' in bruto[0]:
                bruto = bruto[0].split(',')
            return [v.strip() for v in bruto if v.strip()]

        def decimal(nome):
            valor = (request.query_params.get(nome) or '').strip()
            if not valor:
                return None
            try:
                return Decimal(valor.replace(',', '.'))
            except (InvalidOperation, ValueError):
                return None

        return {
            'recencia': [v for v in lista('recencia') if v in Recencia.TODAS],
            'frequencia': [v for v in lista('frequencia') if v in Frequencia.TODAS],
            'produtos': lista('produtos'),
            'bairros': lista('bairros'),
            'ticket_min': decimal('ticket_min'),
            'ticket_max': decimal('ticket_max'),
        }


def resolver_lojas_da_audiencia(request):
    """Resolve as lojas da audiência a partir da query. Ver `_store_ids`.

    Levanta `PermissionDenied` quando a `store` pedida não é do usuário: cair
    calado em "todas as lojas" foi exatamente o defeito que se conserta aqui, e
    devolver o catálogo alheio seria vazamento entre inquilinos.
    """
    from rest_framework.exceptions import PermissionDenied

    from apps.stores.models import Store

    user = request.user
    permitidas = (
        set(Store.objects.values_list('id', flat=True)) if user.is_superuser
        else set(accessible_store_ids(user))
    )

    slug_ou_id = (request.query_params.get('store') or '').strip()
    if slug_ou_id:
        loja = Store.objects.filter(slug=slug_ou_id).first()
        if loja is None:
            loja = Store.objects.filter(pk=slug_ou_id).first() if _parece_uuid(slug_ou_id) else None
        if loja is None:
            raise NotFound('Loja não encontrada.')
        if loja.id not in permitidas:
            raise PermissionDenied('Loja não pertence a este usuário.')
        return [loja.id]

    # Sem `store`: as lojas ligadas à conta de WhatsApp da campanha.
    account_id = (request.query_params.get('account_id') or '').strip()
    if account_id:
        conta = WhatsAppAccount.objects.filter(id=account_id).first()
        if conta is not None:
            from apps.stores.models import StoreIntegration
            por_vinculo = set(
                Store.objects.filter(whatsapp_account=conta).values_list('id', flat=True)
            )
            por_integracao = set(
                StoreIntegration.objects
                .filter(integration_type=StoreIntegration.IntegrationType.WHATSAPP)
                .filter(
                    Q(phone_number_id=conta.phone_number_id) | Q(waba_id=conta.waba_id)
                )
                .values_list('store_id', flat=True)
            )
            return list((por_vinculo | por_integracao) & permitidas)

    # Sem loja e sem conta não dá para saber de quem é a audiência. Devolver
    # tudo aqui é como o defeito começou.
    return list(permitidas)


def _parece_uuid(valor: str) -> bool:
    import uuid
    try:
        uuid.UUID(str(valor))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class OpcoesDeAudienciaView(APIView):
    """O que existe para escolher: bairros e produtos com pedido de verdade.

    Sem isto o painel teria que oferecer o catálogo inteiro, incluindo produtos
    que ninguém nunca pediu — e um filtro por produto sem venda devolve zero
    contatos, o que parece bug e é só falta de dado.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.stores.models import Store, StoreProduct

        store_ids = resolver_lojas_da_audiencia(request)

        produtos = (
            StoreProduct.objects
            .filter(store_id__in=store_ids, is_active=True)
            .values('id', 'name')
            .order_by('name')[:200]
        )

        return Response({
            'recencia': [
                {'valor': v, 'rotulo': Recencia.ROTULOS[v]} for v in Recencia.TODAS
            ],
            'frequencia': [
                {'valor': v, 'rotulo': Frequencia.ROTULOS[v]} for v in Frequencia.TODAS
            ],
            'bairros': bairros_disponiveis(store_ids),
            'produtos': [{'id': str(p['id']), 'nome': p['name']} for p in produtos],
        })


@extend_schema_view(
    list=extend_schema(summary="List campaigns"),
    retrieve=extend_schema(summary="Get campaign details"),
)
class CampaignViewSet(viewsets.ModelViewSet):
    """ViewSet for Campaign management."""
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'campaign_type']
    
    def get_queryset(self):
        user = self.request.user
        qs = Campaign.objects.filter(is_active=True)
        # is_staff NÃO vê campanhas/contatos (PII) cross-tenant — só superuser.
        if user.is_superuser:
            return qs
        account_ids = accessible_whatsapp_account_ids(user)
        return qs.filter(account_id__in=account_ids).distinct()
    
    @extend_schema(
        summary="Create campaign",
        request=CampaignCreateSerializer,
        responses={201: CampaignSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new campaign."""
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not _user_can_use_account(request.user, serializer.validated_data.get('account_id')):
            return Response({'error': 'Sem permissão nesta conta'}, status=status.HTTP_403_FORBIDDEN)

        service = CampaignService()
        campaign = service.create_campaign(
            **serializer.validated_data,
            created_by=request.user
        )
        
        return Response(
            CampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(summary="Upload campaign media")
    @action(
        detail=False,
        methods=['post'],
        url_path='upload-media',
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_media(self, request):
        """Upload an image/document to be used as WhatsApp campaign media."""
        import os
        import uuid as uuid_mod

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)

        mime = file_obj.content_type or ''
        if mime.startswith('image/'):
            media_type = 'image'
        elif mime == 'application/pdf' or mime.startswith('application/'):
            media_type = 'document'
        else:
            return Response(
                {'error': 'Only image or document files are supported for campaigns'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_to_save = file_obj
        if media_type == 'image' and mime not in {'image/jpeg', 'image/png'}:
            from io import BytesIO
            from django.core.files.base import ContentFile
            from PIL import Image

            image = Image.open(file_obj)
            if getattr(image, 'is_animated', False):
                image.seek(0)
            if image.mode not in {'RGB', 'RGBA'}:
                image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            if image.mode == 'RGBA':
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel('A'))
                image = background
            else:
                image = image.convert('RGB')

            output = BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
            file_to_save = ContentFile(output.getvalue())
            mime = 'image/jpeg'

        ext = '.jpg' if mime == 'image/jpeg' else (os.path.splitext(file_obj.name)[1] or '')
        saved_path = default_storage.save(
            f'campaigns/whatsapp/{uuid_mod.uuid4().hex}{ext}',
            file_to_save,
        )
        media_url = build_absolute_media_url(default_storage.url(saved_path))

        return Response({
            'media_url': media_url,
            'media_type': media_type,
            'filename': file_obj.name,
            'mime_type': mime,
        })
    
    @extend_schema(summary="Schedule campaign")
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Schedule a campaign."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR): 404 se não acessível
        scheduled_at = request.data.get('scheduled_at')
        if not scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        service = CampaignService()
        try:
            from django.utils.dateparse import parse_datetime
            scheduled_at = parse_datetime(scheduled_at)
            campaign = service.schedule_campaign(str(pk), scheduled_at)
            return Response(CampaignSerializer(campaign).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(summary="Start campaign")
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a campaign immediately."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        service = CampaignService()
        try:
            campaign = service.start_campaign(str(pk))
            logger.info(f"Campaign {pk} started successfully by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            logger.warning(f"Campaign {pk} not found")
            return Response(
                {'error': 'Campanha não encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            logger.warning(f"Campaign {pk} start validation failed: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} start error: {e}\n{traceback.format_exc()}")
            return Response(
                {'error': 'Erro ao iniciar campanha. Verifique se o serviço de filas está ativo.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(summary="Pause campaign")
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a running campaign."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        service = CampaignService()
        try:
            campaign = service.pause_campaign(str(pk))
            logger.info(f"Campaign {pk} paused by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} pause error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao pausar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Resume campaign")
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused campaign."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        service = CampaignService()
        try:
            campaign = service.resume_campaign(str(pk))
            logger.info(f"Campaign {pk} resumed by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} resume error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao retomar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Cancel campaign")
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a campaign."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        service = CampaignService()
        try:
            campaign = service.cancel_campaign(str(pk))
            logger.info(f"Campaign {pk} cancelled by user {request.user}")
            return Response(CampaignSerializer(campaign).data)
        except Campaign.DoesNotExist:
            return Response({'error': 'Campanha não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Campaign {pk} cancel error: {e}\n{traceback.format_exc()}")
            return Response({'error': 'Erro ao cancelar campanha'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(summary="Get campaign statistics")
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get campaign statistics."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        service = CampaignService()
        stats = service.get_campaign_stats(str(pk))
        return Response(stats)
    
    @extend_schema(summary="Force process campaign batch")
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Force process a campaign batch synchronously.
        Use this when Celery is not available or campaign is stuck.
        """
        service = CampaignService()
        try:
            campaign = self.get_object()  # escopo de tenant (IDOR)

            if campaign.status in [Campaign.CampaignStatus.DRAFT, Campaign.CampaignStatus.SCHEDULED]:
                campaign.status = Campaign.CampaignStatus.RUNNING
                campaign.started_at = timezone.now()
                campaign.save()
                logger.info(f"Campaign {pk} status changed to running")
            
            if campaign.status != Campaign.CampaignStatus.RUNNING:
                return Response(
                    {'error': 'Campaign is not running'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            result = service.process_campaign_batch(str(pk), batch_size=50)
            return Response(result)
            
        except Campaign.DoesNotExist:
            return Response(
                {'error': 'Campaign not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.exception(f"Error processing campaign {pk}: {e}")
            return Response(
                {'error': 'Erro ao processar lote de campanha.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(summary="Get campaign recipients")
    @action(detail=True, methods=['get'])
    def recipients(self, request, pk=None):
        """Get campaign recipients."""
        campaign = self.get_object()
        status_filter = request.query_params.get('status')
        
        recipients = campaign.recipients.all()
        if status_filter:
            recipients = recipients.filter(status=status_filter)
        
        page = self.paginate_queryset(recipients)
        if page is not None:
            serializer = CampaignRecipientSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CampaignRecipientSerializer(recipients, many=True)
        return Response(serializer.data)
    
    @extend_schema(summary="Add recipients to campaign", request=AddRecipientsSerializer)
    @action(detail=True, methods=['post'])
    def add_recipients(self, request, pk=None):
        """Add recipients to a campaign."""
        pk = str(self.get_object().id)  # escopo de tenant (IDOR)
        serializer = AddRecipientsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CampaignService()
        try:
            count = service.add_recipients(str(pk), serializer.validated_data['contacts'])
            return Response({'added': count})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(summary="List contact lists"),
    retrieve=extend_schema(summary="Get contact list details"),
)
class ContactListViewSet(viewsets.ModelViewSet):
    """ViewSet for ContactList management."""
    serializer_class = ContactListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'source']
    
    def get_queryset(self):
        user = self.request.user
        qs = ContactList.objects.filter(is_active=True)
        # is_staff NÃO vê campanhas/contatos (PII) cross-tenant — só superuser.
        if user.is_superuser:
            return qs
        account_ids = accessible_whatsapp_account_ids(user)
        return qs.filter(account_id__in=account_ids).distinct()
    
    @extend_schema(
        summary="Create contact list",
        request=ContactListCreateSerializer,
        responses={201: ContactListSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new contact list."""
        serializer = ContactListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not _user_can_use_account(request.user, serializer.validated_data.get('account_id')):
            return Response({'error': 'Sem permissão nesta conta'}, status=status.HTTP_403_FORBIDDEN)

        service = CampaignService()
        contact_list = service.create_contact_list(
            **serializer.validated_data,
            created_by=request.user
        )
        
        return Response(
            ContactListSerializer(contact_list).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(summary="Import contacts from CSV", request=ImportContactsSerializer)
    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """Import contacts from CSV."""
        serializer = ImportContactsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account_id = serializer.validated_data['account_id']
        if not _user_can_use_account(request.user, account_id):
            return Response(
                {'error': 'Sem permissão nesta conta'},
                status=status.HTTP_403_FORBIDDEN
            )

        service = CampaignService()
        try:
            contact_list = service.import_contacts_from_csv(
                account_id=account_id,
                name=serializer.validated_data['name'],
                csv_content=serializer.validated_data['csv_content'],
                created_by=request.user
            )
            return Response(
                ContactListSerializer(contact_list).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception("Error importing contacts from CSV")
            return Response(
                {'error': 'Erro ao importar contatos do CSV.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class JanelaDaAudienciaView(APIView):
    """Quantos clientes podem receber a campanha GRÁTIS, no horário escolhido.

    Sem este número o dono agenda no escuro: "manda às 20h" pode significar 10
    pessoas ou 2, e ele só descobre depois que a campanha rodou.

    `em` é o coração disto. A janela encolhe com o tempo — quem falou com a loja
    há 20 horas está dentro agora e fora daqui a cinco. "Quantos estarão dentro
    às 20h" é uma pergunta diferente de "quantos estão dentro agora", e é a que
    decide o horário do disparo.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils.dateparse import parse_datetime

        from apps.campaigns.services.janela import resumo_da_janela
        from apps.stores.models import Store

        # `get_whatsapp_account` e não uma consulta nova: a ligação
        # loja↔conta tem TRÊS caminhos (FK direta, perfil de automação e
        # integração legada), e a Cê Saladas usa um deles. Refazer a busca aqui
        # acertaria uma loja e devolveria zero para as outras.
        store_ids = resolver_lojas_da_audiencia(request)
        contas = []
        for loja in Store.objects.filter(id__in=store_ids):
            conta = loja.get_whatsapp_account()
            if conta:
                contas.append(conta.id)

        # Data meio digitada não pode virar erro vermelho na tela: cai em
        # "agora", que é a resposta certa enquanto ninguém escolheu horário.
        em = None
        bruto = (request.query_params.get('em') or '').strip()
        if bruto:
            try:
                em = parse_datetime(bruto)
            except (TypeError, ValueError):
                em = None

        return Response(resumo_da_janela(contas, em=em))
