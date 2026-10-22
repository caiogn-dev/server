"""Layout da comanda (painel → Impressoras → Layout da comanda).

Contrato §4 em docs/comanda-no-servidor.md. O layout mora em
`Store.metadata['comanda']`; a prévia devolve as MESMAS linhas que viram
bytes na impressora, então o painel desenha exatamente o que vai sair.
"""
import uuid

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import user_can_access_store
from apps.stores.models import Store, StoreOrder, StorePrintAgent, StorePrintJob
from apps.stores.services import comanda_linhas
from apps.stores.services.comanda_escpos import escpos_b64_da_comanda
# Módulo, não a função: lida na hora da chamada (patch em teste vale aqui).
from apps.stores.services import print_service
from apps.stores.services.print_service import TEMPLATES_COM_ESCPOS, payload_do_pedido
from ..serializers import StorePrintJobSerializer


class _DaComanda(APIView):
    permission_classes = [IsAuthenticated]

    def loja(self, request, store_slug) -> Store:
        loja = Store.objects.filter(slug=store_slug).first()
        if loja is None:
            raise NotFound('Loja não encontrada.')
        if not user_can_access_store(request.user, loja):
            raise PermissionDenied('Sem acesso a esta loja.')
        return loja

    def layout(self, request, loja) -> dict:
        """O mandado no corpo (ainda não salvo) > o salvo na loja > o padrão."""
        enviado = request.data.get('layout') if hasattr(request.data, 'get') else None
        if enviado is None:
            return comanda_linhas.layout_da_loja(loja)
        return comanda_linhas.validar_layout(enviado)

    def ultimo_pedido(self, loja):
        return StoreOrder.objects.filter(store=loja).order_by('-created_at').first()


def _invalido(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ComandaLayoutView(_DaComanda):
    def get(self, request, store_slug):
        return Response(comanda_linhas.layout_da_loja(self.loja(request, store_slug)))

    def put(self, request, store_slug):
        loja = self.loja(request, store_slug)
        try:
            layout = comanda_linhas.validar_layout(request.data)
        except comanda_linhas.LayoutInvalido as exc:
            return _invalido(exc)
        # Só a chave `comanda`: o metadata guarda etiquetas, alertas etc.
        loja.metadata = {**(loja.metadata or {}), 'comanda': layout}
        loja.save(update_fields=['metadata'])
        return Response(layout)


class ComandaPreviaView(_DaComanda):
    def post(self, request, store_slug):
        loja = self.loja(request, store_slug)
        try:
            layout = self.layout(request, loja)
        except comanda_linhas.LayoutInvalido as exc:
            return _invalido(exc)
        template = request.data.get('template') or 'kitchen_ticket'
        if template not in TEMPLATES_COM_ESCPOS:
            return _invalido(f'template inválido: {template}')

        pedido_id = request.data.get('pedido_id')
        if pedido_id:
            try:
                uuid.UUID(str(pedido_id))
            except ValueError:
                raise NotFound('Pedido não encontrado.') from None
            # Filtra pela loja: pedido de outra loja é 404, nunca a comanda dela.
            pedido = get_object_or_404(StoreOrder, pk=pedido_id, store=loja)
        else:
            pedido = self.ultimo_pedido(loja)

        if pedido is not None:
            payload = payload_do_pedido(pedido, template=template)
        else:
            payload = {**comanda_linhas.pedido_de_exemplo(loja), 'template': template}
        return Response({
            'linhas': comanda_linhas.linhas_da_comanda(payload, layout),
            'colunas': layout['colunas'],
            'pedido': payload['order']['order_number'],
        })


class ComandaImprimirTesteView(_DaComanda):
    def post(self, request, store_slug):
        loja = self.loja(request, store_slug)
        try:
            layout = self.layout(request, loja)
        except comanda_linhas.LayoutInvalido as exc:
            return _invalido(exc)

        pedido = self.ultimo_pedido(loja)
        if pedido is not None:
            # Dedupe desligado: cada clique em "Imprimir teste" é um papel.
            job = print_service.enqueue_order_print_job(
                pedido, source=StorePrintJob.Source.TEST, dedupe=False, layout=layout,
                requested_by=getattr(request.user, 'username', '') or '',
            ).job
        else:
            payload = comanda_linhas.pedido_de_exemplo(loja)
            payload['escpos_b64'] = escpos_b64_da_comanda(payload, layout)
            # Mesmo alvo do enqueue: um agente que imprime comanda, senão a
            # Zebra de etiqueta da loja pega o teste e falha.
            alvo = next((
                a for a in StorePrintAgent.objects.filter(
                    store=loja, station='kitchen', is_active=True,
                    status=StorePrintAgent.AgentStatus.ACTIVE,
                ).order_by('created_at')
                if a.imprime_o(StorePrintAgent.IMPRIME_COMANDA)
            ), None)
            job = StorePrintJob.objects.create(
                store=loja, station='kitchen', target_agent=alvo, template=StorePrintJob.Template.KITCHEN_TICKET,
                source=StorePrintJob.Source.TEST, payload=payload,
                title=f'{loja.name} · teste da comanda',
                metadata={'requested_by': getattr(request.user, 'username', '') or ''},
            )
        return Response(StorePrintJobSerializer(job).data, status=status.HTTP_201_CREATED)
