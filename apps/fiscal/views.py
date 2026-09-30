"""API da página de Notas fiscais do painel.

Base: /api/v1/stores/{store_slug}/fiscal/
"""
import logging
import uuid as uuid_module

from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import user_can_access_store
from apps.stores.models import Store, StoreOrder

from . import destinatarios
from .consulta_cnpj import ConsultaIndisponivel, consultar_cnpj
from .envio import EnvioFalhou, EnvioInvalido, email_sugerido, enviar_nota_por_email
from .documents import classificar, cnpj_valido, limpar
from .models import DestinatarioFiscal, FiscalDocument
from .providers.base import FiscalNotConfigured
from .services import (
    ambiente_da_loja, cancel_nfce, documento_do_consumidor, emit_nfce_for_order,
    get_fiscal_config, refresh_fiscal_document,
)

logger = logging.getLogger(__name__)

LIMITE_DA_LISTA = 200
LIMITE_DE_PEDIDOS = 30
# Consultar o provedor custa uma chamada de rede por nota: só as poucas que
# ainda estão em processamento, e nunca a lista inteira.
MAXIMO_DE_CONSULTAS = 5

PEDIDO_SEM_NOTA = ('cancelled', 'failed', 'refunded')


def _uuid(valor):
    try:
        return uuid_module.UUID(str(valor))
    except (ValueError, TypeError):
        return None


def _loja_do_painel(request, store_slug: str) -> Store:
    """A loja da URL, só para quem é dela. Toda view daqui passa por aqui:
    nota fiscal carrega CNPJ, endereço e valor de venda de terceiros."""
    try:
        uuid_module.UUID(str(store_slug))
        store = get_object_or_404(Store, pk=store_slug)
    except ValueError:
        store = get_object_or_404(Store, slug=store_slug)
    if not user_can_access_store(request.user, store):
        raise PermissionDenied('Sem permissão para esta loja.')
    return store


def _destinatario_do_pedido(order) -> dict | None:
    metadata = order.metadata or {}
    retrato = metadata.get('destinatario_nota')
    if isinstance(retrato, dict) and retrato.get('documento'):
        return {'documento': retrato.get('documento'), 'nome': retrato.get('nome') or order.customer_name}
    documento = limpar(documento_do_consumidor(order))
    if documento:
        return {'documento': documento, 'nome': order.customer_name}
    return None


def _emails_dos_destinatarios(store, docs) -> dict:
    """documento → e-mail do cadastro, numa consulta só para a lista inteira."""
    documentos = {limpar(documento_do_consumidor(d.order)) for d in docs} - {''}
    if not documentos:
        return {}
    return dict(
        DestinatarioFiscal.objects.filter(store=store, documento__in=documentos)
        .values_list('documento', 'email')
    )


def nota_como_dict(doc: FiscalDocument, emails: dict | None = None) -> dict:
    order = doc.order
    if emails is None:
        sugerido = email_sugerido(doc)
    else:
        sugerido = emails.get(limpar(documento_do_consumidor(order)), '')
    return {
        'id': str(doc.id),
        'status': doc.status,
        'modelo': doc.modelo,
        'ambiente': doc.ambiente,
        'provider': doc.provider,
        'chave_acesso': doc.chave_acesso,
        'numero': doc.numero,
        'serie': doc.serie,
        'qrcode_url': doc.qrcode_url,
        'danfe_url': doc.danfe_url,
        'xml_url': doc.xml_url,
        'error_message': doc.error_message,
        'created_at': doc.created_at,
        'email_enviado_para': doc.email_enviado_para,
        'email_enviado_em': doc.email_enviado_em,
        'email_sugerido': sugerido,
        'pedido': {
            'id': str(order.id),
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'total': order.total,
        },
        'destinatario': _destinatario_do_pedido(order),
    }


class NotasView(APIView):
    """GET notas/ — as notas da loja no ambiente em que ela está agora."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = _loja_do_painel(request, store_slug)
        ambiente = ambiente_da_loja(store)
        base = FiscalDocument.objects.filter(store=store, ambiente=ambiente).select_related('order')

        inicio_do_mes = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        autorizadas_no_mes = base.filter(
            status=FiscalDocument.Status.AUTHORIZED, created_at__gte=inicio_do_mes,
        )
        resumo = {
            'autorizadas_no_mes': autorizadas_no_mes.count(),
            'valor_no_mes': autorizadas_no_mes.aggregate(v=Sum('order__total'))['v'] or 0,
            'nao_sairam': base.filter(
                status__in=[FiscalDocument.Status.REJECTED, FiscalDocument.Status.ERROR],
            ).count(),
            'processando': base.filter(status=FiscalDocument.Status.PENDING).count(),
        }

        notas = base
        filtro_status = request.query_params.get('status')
        if filtro_status in FiscalDocument.Status.values:
            notas = notas.filter(status=filtro_status)
        filtro_modelo = request.query_params.get('modelo')
        if filtro_modelo in FiscalDocument.Modelo.values:
            notas = notas.filter(modelo=filtro_modelo)
        busca = (request.query_params.get('q') or '').strip()
        if busca:
            digitos = limpar(busca)
            criterio = (
                Q(numero__icontains=busca)
                | Q(order__order_number__icontains=busca)
                | Q(order__customer_name__icontains=busca)
                | Q(order__metadata__destinatario_nota__nome__icontains=busca)
            )
            if digitos:
                criterio |= Q(chave_acesso__icontains=digitos) | Q(order__metadata__cpf_nota__icontains=digitos)
            notas = notas.filter(criterio)

        lista = list(notas[:LIMITE_DA_LISTA])
        consultas = 0
        for indice, doc in enumerate(lista):
            if doc.status == FiscalDocument.Status.PENDING and consultas < MAXIMO_DE_CONSULTAS:
                lista[indice] = refresh_fiscal_document(doc)
                consultas += 1

        emails = _emails_dos_destinatarios(store, lista)
        return Response({
            'habilitado': bool(get_fiscal_config(store).get('habilitado')),
            'ambiente': ambiente,
            'resumo': resumo,
            'notas': [nota_como_dict(doc, emails) for doc in lista],
        })


class EmitirNotaView(APIView):
    """POST notas/emitir/ — pedido + modelo + (na NF-e) para quem a nota sai."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = _loja_do_painel(request, store_slug)

        order_id = _uuid(request.data.get('order_id'))
        order = StoreOrder.objects.filter(store=store, pk=order_id).first() if order_id else None
        if order is None:
            return Response({'error': 'Pedido não encontrado nesta loja.'}, status=status.HTTP_404_NOT_FOUND)

        modelo = str(request.data.get('modelo') or FiscalDocument.Modelo.NFCE)
        if modelo not in FiscalDocument.Modelo.values:
            return Response(
                {'error': 'Modelo de nota inválido. Use 65 (NFC-e) ou 55 (NF-e).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            destinatario = self._destinatario(request, store, order, modelo)
        except destinatarios.DestinatarioInvalido as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if destinatario is not None:
            destinatarios.carimbar_no_pedido(order, destinatario)

        try:
            doc = emit_nfce_for_order(order, modelo=modelo)
        except FiscalNotConfigured as exc:
            logger.warning('emitir nota: recusada pedido=%s loja=%s: %s', order.id, store.id, exc)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # A nota já existe na SEFAZ: e-mail que falha não a desfaz. O erro vai
        # na resposta e o operador reenvia pela lista.
        email_erro = ''
        if request.data.get('enviar_email') and doc.status == FiscalDocument.Status.AUTHORIZED:
            try:
                doc = enviar_nota_por_email(doc)
            except (EnvioInvalido, EnvioFalhou) as exc:
                email_erro = str(exc)

        return Response(
            {**nota_como_dict(doc), 'email_erro': email_erro},
            status=status.HTTP_201_CREATED if doc.status == 'authorized' else status.HTTP_200_OK,
        )

    @staticmethod
    def _destinatario(request, store, order, modelo):
        """O destinatário digitado agora, o salvo escolhido pelo id, ou nenhum
        (NFC-e de consumidor não identificado; NF-e cai na validação do payload)."""
        salvo_id = request.data.get('destinatario_id')
        dados = request.data.get('destinatario')
        if dados:
            limpo = destinatarios.normalizar(dados, modelo)
            return destinatarios.registrar(store, limpo, customer=destinatarios.cliente_do_pedido(order))
        if salvo_id:
            salvo_id = _uuid(salvo_id)
            salvo = DestinatarioFiscal.objects.filter(store=store, pk=salvo_id).first() if salvo_id else None
            if salvo is None:
                raise destinatarios.DestinatarioInvalido('Destinatário não encontrado nesta loja.')
            # Cadastro antigo pode estar incompleto para o modelo pedido agora.
            destinatarios.normalizar(destinatarios.como_dict(salvo), modelo)
            return salvo
        return None


class CancelarNotaView(APIView):
    """POST notas/{id}/cancelar/ — janela legal de 30 minutos."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug, pk):
        store = _loja_do_painel(request, store_slug)
        doc = get_object_or_404(FiscalDocument.objects.select_related('order'), store=store, pk=pk)
        try:
            doc = cancel_nfce(doc, request.data.get('justificativa', ''))
        except (ValueError, FiscalNotConfigured) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Falha ao cancelar nota %s', doc.id)
            return Response(
                {'error': 'Falha de comunicação com o provedor fiscal. Tente novamente.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(nota_como_dict(doc))


class EnviarNotaPorEmailView(APIView):
    """POST notas/{id}/enviar-email/ — DANFE e XML no e-mail do destinatário."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug, pk):
        store = _loja_do_painel(request, store_slug)
        doc = get_object_or_404(FiscalDocument.objects.select_related('order', 'store'), store=store, pk=pk)
        try:
            doc = enviar_nota_por_email(doc, str(request.data.get('email') or ''))
        except EnvioInvalido as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except EnvioFalhou:
            return Response(
                {'error': 'O e-mail não saiu. Tente novamente em instantes.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(nota_como_dict(doc))


class DestinatariosView(APIView):
    """GET/POST destinatarios/ — o cadastro de quem recebe nota."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = _loja_do_painel(request, store_slug)
        lista = DestinatarioFiscal.objects.filter(store=store)
        busca = (request.query_params.get('q') or '').strip()
        if busca:
            criterio = Q(nome__icontains=busca)
            if limpar(busca):
                criterio |= Q(documento__icontains=limpar(busca))
            lista = lista.filter(criterio)
        return Response([destinatarios.como_dict(d) for d in lista[:50]])

    def post(self, request, store_slug):
        store = _loja_do_painel(request, store_slug)
        try:
            # Cadastro aceita endereço incompleto (serve à NFC-e); quem exige
            # tudo é a emissão da NF-e.
            limpo = destinatarios.normalizar(request.data, FiscalDocument.Modelo.NFCE)
        except destinatarios.DestinatarioInvalido as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        salvo = destinatarios.registrar(store, limpo)
        return Response(destinatarios.como_dict(salvo), status=status.HTTP_201_CREATED)


class DestinatarioView(APIView):
    """DELETE destinatarios/{id}/ — sai do cadastro; as notas já emitidas
    guardam o próprio retrato e não mudam."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, store_slug, pk):
        store = _loja_do_painel(request, store_slug)
        get_object_or_404(DestinatarioFiscal, store=store, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PedidosParaNotaView(APIView):
    """GET pedidos/?q= — pedidos recentes para vincular à nota, com o que cada
    um já tem emitido e o que o pedido já sabe do destinatário."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = _loja_do_painel(request, store_slug)
        ambiente = ambiente_da_loja(store)
        pedidos = StoreOrder.objects.filter(store=store).exclude(status__in=PEDIDO_SEM_NOTA)
        # `id` traz um pedido só — é como o detalhe do pedido abre a emissão
        # já com ele escolhido, mesmo que seja antigo e fora dos recentes.
        unico = _uuid(request.query_params.get('id'))
        if unico:
            pedidos = StoreOrder.objects.filter(store=store, pk=unico)
        busca = (request.query_params.get('q') or '').strip()
        if busca:
            criterio = Q(order_number__icontains=busca) | Q(customer_name__icontains=busca)
            if limpar(busca):
                criterio |= Q(customer_phone__icontains=limpar(busca))
            pedidos = pedidos.filter(criterio)
        pedidos = list(pedidos.order_by('-created_at')[:LIMITE_DE_PEDIDOS])

        notas_por_pedido: dict = {}
        documentos = FiscalDocument.objects.filter(
            order__in=pedidos, ambiente=ambiente,
        ).exclude(status=FiscalDocument.Status.CANCELLED).order_by('created_at')
        for doc in documentos:
            # A última tentativa de cada modelo é a que vale.
            notas_por_pedido.setdefault(doc.order_id, {})[doc.modelo] = doc.status

        salvos = {
            d.documento: d for d in DestinatarioFiscal.objects.filter(
                store=store,
                documento__in=[limpar(documento_do_consumidor(p)) for p in pedidos if documento_do_consumidor(p)],
            )
        }

        return Response([
            {
                'id': str(p.id),
                'order_number': p.order_number,
                'customer_name': p.customer_name,
                'total': p.total,
                'created_at': p.created_at,
                'delivery_method': p.delivery_method,
                'notas': [
                    {'modelo': modelo, 'status': situacao}
                    for modelo, situacao in sorted(notas_por_pedido.get(p.id, {}).items())
                ],
                'sugestao': self._sugestao(p, salvos),
            }
            for p in pedidos
        ])

    @staticmethod
    def _sugestao(order, salvos: dict) -> dict:
        """O que já dá para preencher sozinho: retrato da última emissão,
        depois o cadastro do documento, depois o que o pedido carrega."""
        metadata = order.metadata or {}
        retrato = metadata.get('destinatario_nota')
        if isinstance(retrato, dict) and retrato.get('documento'):
            return {
                'documento': retrato.get('documento') or '',
                'nome': retrato.get('nome') or '',
                'inscricao_estadual': retrato.get('inscricao_estadual') or '',
                'email': getattr(salvos.get(retrato.get('documento')), 'email', ''),
                'endereco': retrato.get('endereco') or {},
            }
        _, documento = classificar(documento_do_consumidor(order))
        salvo = salvos.get(documento)
        if salvo is not None:
            dados = destinatarios.como_dict(salvo)
            return {
                chave: dados[chave]
                for chave in ('documento', 'nome', 'inscricao_estadual', 'email', 'endereco')
            }
        endereco = order.delivery_address if isinstance(order.delivery_address, dict) else {}
        return {
            'documento': documento,
            'nome': order.customer_name,
            'inscricao_estadual': str(metadata.get('ie_nota') or ''),
            'email': '',
            'endereco': {
                campo: str(endereco.get(campo) or '') for campo in destinatarios.CAMPOS_DO_ENDERECO
            },
        }


class ConsultaCnpjView(APIView):
    """GET cnpj/{cnpj}/ — cadastro público, para o operador não digitar."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug, cnpj):
        _loja_do_painel(request, store_slug)
        if not cnpj_valido(cnpj):
            return Response({'error': 'CNPJ inválido — confira o número.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            dados = consultar_cnpj(cnpj)
        except ConsultaIndisponivel:
            return Response(
                {'error': 'Consulta de CNPJ fora do ar. Preencha os dados à mão.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if dados is None:
            return Response({'error': 'CNPJ não encontrado na Receita.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(dados)
