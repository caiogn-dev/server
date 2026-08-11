"""Uma pessoa, uma conversa — resolvendo o nono dígito brasileiro.

A Meta entrega o wa_id do Brasil SEM o nono dígito (`556384143551`); o pedido
feito no site grava COM ele (`5563984143551`). Como `Conversation` é única por
(account, phone_number), a mesma cliente vira duas threads na mesma conta: a
real, onde ela conversa, e uma fantasma que só recebe as notificações que o
sistema dispara.

Aqui moram as duas metades da solução:

- `conversa_canonica`: qual das threads é a de verdade. Usado no envio, para
  parar de criar fantasmas novas;
- `fundir_duplicatas`: junta as que já existem.

⚠️ Contas diferentes NUNCA se fundem. A mesma pessoa falando com a Cê Saladas e
com a Pastita são duas conversas legítimas — dos 7 "duplicados" encontrados em
10/ago, 5 eram exatamente isso e estavam certos.
"""
import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def _chave(phone: str) -> str:
    """Forma canônica de um telefone BR: sem DDI e sem o nono dígito.

    Serve só para agrupar as variantes da mesma pessoa — não é para exibir nem
    para enviar.
    """
    digitos = ''.join(filter(str.isdigit, phone or ''))
    if digitos.startswith('55') and len(digitos) > 10:
        digitos = digitos[2:]
    if len(digitos) == 11 and digitos[2] == '9':
        digitos = digitos[:2] + digitos[3:]
    return digitos


def _tem_inbound(conversa) -> bool:
    return conversa.messages.filter(direction='inbound').exists()


def _prioridade(conversa) -> tuple:
    """Ordena da mais canônica para a menos. Determinístico de propósito.

    A regra ANTERIOR era `-last_message_at`, e por isso a escolha mudava
    conforme quem tinha escrito por último: em 10/ago a mesma cliente recebeu
    uma mensagem em cada thread com 3 minutos de diferença.

    Agora: quem tem mensagem RECEBIDA do cliente ganha (é onde ela realmente
    conversa); depois quem tem mais histórico; e o desempate final é a mais
    antiga, que é estável no tempo.
    """
    return (
        0 if _tem_inbound(conversa) else 1,
        -conversa.messages.count(),
        conversa.created_at,
    )


def conversa_canonica(account, phone_number):
    """A conversa desta pessoa nesta conta, em qualquer forma do telefone."""
    from apps.conversations.models import Conversation
    from apps.core.utils import phone_variants

    candidatas = list(Conversation.objects.filter(
        account=account,
        phone_number__in=phone_variants(phone_number),
    ))
    if not candidatas:
        return None
    return sorted(candidatas, key=_prioridade)[0]


def _migrar_relacionados(origem, destino) -> dict:
    """Move tudo que aponta para `origem` e passa a apontar para `destino`.

    Genérico de propósito: são 10 modelos hoje (mensagens, notas, sessões,
    handover, intents...) e a lista cresce. Enumerar à mão aqui garante que o
    próximo modelo seja esquecido e o dado suma na fusão.
    """
    movidos = {}
    for rel in origem._meta.related_objects:
        if not rel.one_to_many and not rel.one_to_one:
            continue
        campo = rel.field.name
        modelo = rel.related_model
        linhas = modelo.objects.filter(**{campo: origem})
        for linha in linhas:
            try:
                with transaction.atomic():
                    setattr(linha, campo, destino)
                    linha.save(update_fields=[campo])
                movidos[modelo._meta.label] = movidos.get(modelo._meta.label, 0) + 1
            except IntegrityError:
                # A destino já tem o equivalente (ex.: uma sessão aberta por
                # cliente). Duplicata sem dono não serve para nada.
                logger.info(
                    '[fusao] %s duplicado descartado na fusão de %s',
                    modelo._meta.label, origem.phone_number,
                )
                linha.delete()
    return movidos


def fundir_duplicatas(account=None, aplicar: bool = True) -> list:
    """Funde as threads duplicadas que já existem.

    `aplicar=False` só relata — rodar antes de mexer no banco tem que ser
    seguro. Devolve um relatório com um item por grupo fundido.
    """
    from apps.conversations.models import Conversation

    qs = Conversation.objects.all()
    if account is not None:
        qs = qs.filter(account=account)

    grupos = {}
    for conversa in qs.select_related('account'):
        grupos.setdefault((conversa.account_id, _chave(conversa.phone_number)), []).append(conversa)

    relatorio = []
    for (account_id, chave), conversas in grupos.items():
        if len(conversas) < 2 or not chave:
            continue

        conversas.sort(key=_prioridade)
        canonica, duplicatas = conversas[0], conversas[1:]
        item = {
            'account_id': str(account_id),
            'telefone': chave,
            'canonica': canonica.phone_number,
            'absorvidas': [c.phone_number for c in duplicatas],
            'movidos': {},
        }

        if aplicar:
            for duplicata in duplicatas:
                movidos = _migrar_relacionados(duplicata, canonica)
                for modelo, qtd in movidos.items():
                    item['movidos'][modelo] = item['movidos'].get(modelo, 0) + qtd
                # O nome do contato costuma estar só na thread real; se a
                # canônica estiver sem, aproveita o da absorvida.
                if not (canonica.contact_name or '').strip() and (duplicata.contact_name or '').strip():
                    canonica.contact_name = duplicata.contact_name
                    canonica.save(update_fields=['contact_name'])
                duplicata.delete()
            logger.info('[fusao] %s absorvidas em %s', item['absorvidas'], canonica.phone_number)

        relatorio.append(item)

    return relatorio
