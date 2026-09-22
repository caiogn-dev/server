"""Campanha de comentário no painel do lojista."""
from collections import Counter

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import logging

from ..campanhas import regras, sorteio
from ..models import CampanhaDeComentario, ParticipacaoNoComentario

logger = logging.getLogger(__name__)


class ParticipacaoSerializer(serializers.ModelSerializer):
    motivo_em_portugues = serializers.SerializerMethodField()

    class Meta:
        model = ParticipacaoNoComentario
        fields = [
            'id', 'username', 'texto', 'amigos_marcados', 'aceita', 'motivo',
            'motivo_em_portugues', 'dm_enviada', 'ganhador', 'created_at',
        ]

    def get_motivo_em_portugues(self, obj):
        return regras.MOTIVOS.get(obj.motivo, '')


class CampanhaDeComentarioSerializer(serializers.ModelSerializer):
    participando = serializers.SerializerMethodField()
    no_ar = serializers.SerializerMethodField()

    class Meta:
        model = CampanhaDeComentario
        fields = [
            'id', 'account', 'nome', 'tipo', 'media_id', 'palavra_chave',
            'exige_marcar_amigos', 'exige_seguir', 'mensagem_dm', 'resposta_publica',
            'comeca_em', 'termina_em', 'ativa', 'participando', 'no_ar', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_participando(self, obj):
        return obj.participacoes.filter(aceita=True).count()

    def get_no_ar(self, obj):
        return obj.esta_no_ar()

    def validate_account(self, account):
        if account.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('Essa conta do Instagram não é sua.')
        return account


class CampanhaDeComentarioViewSet(viewsets.ModelViewSet):
    """Promoções amarradas a uma publicação — só as da conta de quem pede."""

    serializer_class = CampanhaDeComentarioSerializer
    permission_classes = [IsAuthenticated]
    queryset = CampanhaDeComentario.objects.all()

    def get_queryset(self):
        return (
            self.queryset.filter(account__user=self.request.user)
            .select_related('account')
        )

    @action(detail=True, methods=['get'])
    def placar(self, request, pk=None):
        """Quem entrou, quem ficou de fora e o motivo — em português."""
        campanha = self.get_object()
        participacoes = campanha.participacoes.all()
        de_fora = [p.motivo for p in participacoes if not p.aceita]
        contagem = Counter(m for m in de_fora if m)

        return Response({
            'participando': sum(1 for p in participacoes if p.aceita),
            'de_fora': len(de_fora),
            'ganhadores': ParticipacaoSerializer(
                [p for p in participacoes if p.ganhador], many=True,
            ).data,
            'motivos': [
                {'motivo': regras.MOTIVOS.get(m, m), 'quantas': q}
                for m, q in contagem.most_common()
            ],
        })

    @action(detail=True, methods=['get'])
    def participantes(self, request, pk=None):
        campanha = self.get_object()
        so_validos = request.query_params.get('validos') == '1'
        fila = campanha.participacoes.all()
        if so_validos:
            fila = fila.filter(aceita=True)
        return Response(ParticipacaoSerializer(fila[:500], many=True).data)

    @action(detail=True, methods=['get'])
    def comentarios(self, request, pk=None):
        """Os comentários reais do post, cada um com o que aconteceu com ele.

        O webhook conta o que chegou; isto mostra o post como ele está agora —
        inclusive o comentário cujo webhook ainda não chegou.
        """
        from ..services.instagram_api import InstagramAPI

        campanha = self.get_object()
        try:
            resposta = InstagramAPI(campanha.account).get(
                f'{campanha.media_id}/comments',
                params={'fields': 'id,text,username,timestamp,like_count', 'limit': 25},
            )
        except Exception as erro:
            logger.warning(
                'Instagram: não deu para ler comentários de %s: %s', campanha.media_id, erro,
            )
            return Response(
                {
                    'codigo': 'reconectar',
                    'detail': 'A Meta recusou o acesso a esta conta. Conecte o Instagram de novo.',
                },
                status=status.HTTP_409_CONFLICT,
            )

        participacoes = {
            p.comment_id: p for p in campanha.participacoes.all()
        }
        saida = []
        for item in resposta.get('data', []):
            p = participacoes.get(item.get('id'))
            if p is None:
                situacao, motivo = 'aguardando', ''
            elif p.aceita:
                situacao = 'recebeu' if p.dm_enviada else 'participando'
                motivo = p.erro_da_dm
            else:
                situacao, motivo = 'de_fora', regras.MOTIVOS.get(p.motivo, p.motivo)
            saida.append({
                'id': item.get('id'),
                'username': item.get('username') or '',
                'texto': item.get('text') or '',
                'quando': item.get('timestamp'),
                'curtidas': item.get('like_count') or 0,
                'situacao': situacao,
                'motivo': motivo,
                'ganhador': bool(p and p.ganhador),
            })
        return Response(saida)

    @action(detail=True, methods=['post'])
    def sortear(self, request, pk=None):
        campanha = self.get_object()
        try:
            quantidade = max(1, int(request.data.get('quantidade', 1)))
        except (TypeError, ValueError):
            quantidade = 1

        ganhadores = sorteio.sortear(campanha, quantidade=quantidade)
        return Response({
            'ganhadores': ParticipacaoSerializer(ganhadores, many=True).data,
            'restam': sorteio.elegiveis(campanha).count(),
        })
