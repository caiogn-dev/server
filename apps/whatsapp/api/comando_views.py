"""Endpoint dos atalhos "/" do inbox.

A tela manda o comando já interpretado do lado dela; aqui ele é interpretado de
NOVO e executado. Reinterpretar não é desperdício: o cliente HTTP não é fonte
confiável para decidir se `/cancelar` precisa de confirmação, e essa decisão
cancela vendas.

Origem: em 13/ago consertar um pedido errado custou à dona 5 minutos e uma
troca de tela, com a cliente esperando.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class ExecutarComandoView(APIView):
    """POST /api/v1/whatsapp/comandos/executar/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.conversations.models import Conversation
        from apps.whatsapp.services.comandos import executar, interpretar

        texto = (request.data.get('texto') or '').strip()
        conversa_id = request.data.get('conversation_id')
        confirmado = bool(request.data.get('confirmado'))

        comando = interpretar(texto)
        if comando is None or not comando.conhecido:
            return Response(
                {'ok': False, 'texto': 'Comando não reconhecido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conversa = Conversation.objects.filter(id=conversa_id).first()
        if conversa is None:
            return Response(
                {'ok': False, 'texto': 'Conversa não encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Escopo por loja do usuário: sem isto, um dono conseguiria cancelar o
        # pedido de outra loja mandando um id de conversa qualquer.
        loja = self._loja_do_usuario(request.user, conversa)
        if loja is None:
            return Response(
                {'ok': False, 'texto': 'Conversa não pertence a esta loja.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        resultado = executar(
            comando.nome, comando.argumento,
            conversa=conversa, store=loja, confirmado=confirmado,
        )

        # Quem manda para a cliente é o inbox, pelo mesmo `send_text` que ele
        # já usa e que já tem trava de duplo envio. Abrir um segundo caminho de
        # envio no servidor criaria duas formas de a mesma mensagem sair — e
        # mensagem duplicada foi o defeito de 12/ago.
        return Response({
            'ok': resultado.ok,
            'texto': resultado.texto,
            'enviar_ao_cliente': resultado.ok and resultado.enviar_ao_cliente,
            'precisa_confirmar': comando.precisa_confirmar and not confirmado,
        })

    @staticmethod
    def _loja_do_usuario(user, conversa):
        """A loja da conversa, se este usuário puder agir nela.

        ⚠️ Duas armadilhas, as duas encontradas em produção em 14/ago.

        **1. `Conversation` NÃO tem campo `store`.** A primeira versão fazia
        `getattr(conversa, 'store', None)`, recebia None e devolvia 403 em TODA
        conversa. O default do getattr engoliu o erro: nenhuma exceção, só uma
        negativa silenciosa. O caminho real é o que os handlers do bot já
        usavam: conversa → account → company_profile → store.

        **2. A regra de acesso é `user_can_access_store`, e não uma minha.** A
        segunda versão checava `owner` e `StoreTeamMember` à mão e continuava
        negando: existem DOIS usuários com o mesmo e-mail (`graccius` id 1 e
        `graco` id 14), a loja pertence a um e a sessão do painel é do outro. A
        regra canônica cobre owner, staff M2M e membro de equipe — e é a mesma
        que o resto do painel usa para listar pedidos e produtos.

        Escrever a terceira versão de uma regra que já existe é o defeito que
        este projeto repete: a cópia sempre diverge da original.
        """
        from apps.core.permissions import user_can_access_store

        perfil = getattr(getattr(conversa, 'account', None), 'company_profile', None)
        loja = getattr(perfil, 'store', None)
        if loja is None:
            return None

        return loja if user_can_access_store(user, loja) else None
