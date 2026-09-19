"""A janela de 24 horas do WhatsApp: quem a loja pode responder de graça.

A REGRA É DA META, não nossa. Dentro de 24 horas contadas da última mensagem
que a CLIENTE mandou, a loja responde texto livre sem custo. Fora disso só sai
template aprovado, cobrado por conversa.

PARA QUE ISTO EXISTE: o dono quer mandar o card da promoção do dia seguinte às
20h para quem já falou com a loja — "já é um aviso e menos gastos, pois ainda
teremos a janela de 24h". A audiência é exatamente essa: conversa cuja última
mensagem da cliente tem menos de 24 horas.

A ARMADILHA: a lista tem que ser feita NA HORA DO ENVIO, nunca no agendamento.
Quem escolhe às 15h e agenda para 20h estaria mandando para uma lista de 15h —
e quem falou às 14h de ontem já está fora às 20h de hoje. O envio falharia com
131047 por destinatário, em silêncio, porque campanha registra erro e segue.

Por isso `em=` existe: a mesma conta pode ser feita para o instante do envio.
"""
from __future__ import annotations

from datetime import time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .contatos import chave_do_telefone

#: A janela da Meta. Constante nomeada porque aparece em texto de tela também —
#: e porque o dia em que a Meta mudar isso, muda num lugar só.
JANELA_HORAS = 24


def quando_fecha(ultima_mensagem_da_cliente):
    """Até que horas a loja pode responder de graça. `None` se ela nunca falou."""
    if not ultima_mensagem_da_cliente:
        return None
    return ultima_mensagem_da_cliente + timedelta(hours=JANELA_HORAS)


def chaves_com_janela_aberta(account_ids, em=None) -> set:
    """Telefones (na chave canônica) que podem receber texto livre em `em`.

    `em` default = agora. Passe o horário do ENVIO ao montar campanha agendada.

    A chave é a mesma da deduplicação de contatos: o wa_id chega sem o nono
    dígito e o pedido tem com ele, e sem colapsar isso metade da audiência não
    casaria com os segmentos de compra — a campanha sairia para menos gente do
    que podia, sem ninguém perceber.
    """
    from apps.conversations.models import Conversation

    momento = em or timezone.now()
    limite = momento - timedelta(hours=JANELA_HORAS)

    conversas = (
        Conversation.objects
        .filter(account_id__in=list(account_ids))
        .filter(last_customer_message_at__gt=limite)
        .filter(last_customer_message_at__lte=momento)
        .values_list('phone_number', 'last_customer_message_at')
    )
    return {
        chave for telefone, _ in conversas
        if (chave := chave_do_telefone(telefone))
    }


def resumo_da_janela(account_ids, em=None) -> dict:
    """Quantos estão dentro e quantos ficaram de fora, para a tela mostrar.

    "Fora da janela" não é erro — é "não é para essa pessoa hoje". Mas o dono
    precisa ver o número: se 80 dos 90 estão fora, a campanha grátis não é a
    ferramenta certa naquele horário.
    """
    from apps.conversations.models import Conversation

    momento = em or timezone.now()
    dentro = chaves_com_janela_aberta(account_ids, em=momento)

    todos = {
        chave
        for telefone in Conversation.objects
        .filter(account_id__in=list(account_ids))
        .exclude(last_customer_message_at=None)
        .values_list('phone_number', flat=True)
        if (chave := chave_do_telefone(telefone))
    }
    return {
        'dentro': len(dentro),
        'fora': len(todos - dentro),
        'medido_em': momento.isoformat(),
        'janela_horas': JANELA_HORAS,
    }


#: A faixa em que a loja pode falar. Fora dela, ninguém recebe (D4): promoção
#: às 23h não é lembrete, é incômodo — e o cliente que bloqueia some para sempre.
INICIO_DO_DIA = 8
FIM_DO_DIA = 21
#: Quanto antes de a janela fechar a pessoa é antecipada (D3).
ANTECIPACAO = timedelta(hours=1)


def horario_alvo(fecha_em, horario_campanha, fuso: str):
    """Quando ESTA pessoa recebe — ou `None` se não dá para mandar de graça.

    Regra, na ordem (spec, seção 3):
      1. sem janela (nunca falou) → fora;
      2. alvo = min(horário da campanha, fecha_em − 1h);
      3. alvo no silêncio → recua para as 21:00 mais recentes ANTES dele;
      4. alvo em outro dia (local) que o da campanha → fora (D5);
      5. alvo já depois do fechamento → fora.
    """
    if fecha_em is None:
        return None

    zona = ZoneInfo(fuso or 'America/Sao_Paulo')
    alvo = min(horario_campanha, fecha_em - ANTECIPACAO)

    local = alvo.astimezone(zona)
    if local.time() < time(INICIO_DO_DIA) or local.time() > time(FIM_DO_DIA):
        # As 21:00 mais recentes ANTES do alvo: 22:30 → 21:00 do mesmo dia;
        # 05:00 → 21:00 da véspera.
        fim = local.replace(hour=FIM_DO_DIA, minute=0, second=0, microsecond=0)
        if fim > local:
            fim -= timedelta(days=1)
        alvo = fim.astimezone(alvo.tzinfo)

    if alvo.astimezone(zona).date() != horario_campanha.astimezone(zona).date():
        return None
    if alvo >= fecha_em:
        return None
    return alvo


def fechamentos_por_chave(account_ids) -> dict:
    """{chave do telefone: quando a janela fecha}. Só quem já falou entra.

    Para a rodada (task 3) comparar `fecha_em` contra o horário-alvo de CADA
    destinatário — `chaves_com_janela_aberta` só diz dentro/fora AGORA, não
    quando cada um fecha.

    Mesma chave canônica do recorte e da dedupe: o wa_id chega sem o nono
    dígito e o pedido tem com ele. Duas conversas do mesmo cliente → vale a
    mensagem MAIS NOVA, senão descartaríamos quem está dentro da janela.
    """
    from apps.conversations.models import Conversation

    mapa = {}
    linhas = (
        Conversation.objects
        .filter(account_id__in=list(account_ids))
        .exclude(last_customer_message_at=None)
        .values_list('phone_number', 'last_customer_message_at')
    )
    for telefone, ultima in linhas:
        chave = chave_do_telefone(telefone)
        if not chave:
            continue
        fecha = ultima + timedelta(hours=JANELA_HORAS)
        if chave not in mapa or fecha > mapa[chave]:
            mapa[chave] = fecha
    return mapa


def fuso_da_campanha(campaign) -> str:
    """O fuso da LOJA dona da conta — o container roda em UTC.

    A ligação loja→conta tem dois caminhos no sentido inverso: FK direta
    (`Store.whatsapp_account`) e perfil de automação (`CompanyProfile.account`,
    acessível como `Store.automation_profile`). Sem loja em nenhum dos dois,
    cai no fuso do settings — não dá para deixar `horario_alvo` sem fuso.
    """
    from django.conf import settings
    from apps.stores.models import Store

    loja = (
        Store.objects.filter(whatsapp_account_id=campaign.account_id).first()
        or Store.objects.filter(automation_profile__account_id=campaign.account_id).first()
    )
    return getattr(loja, 'timezone', None) or settings.TIME_ZONE


#: A marca que diz "esta campanha é a grátis". Fica em `audience_filters`, que
#: já é onde a campanha guarda quem recebe.
MARCA = 'somente_janela_aberta'


def recortar_para_a_janela(campaign) -> dict:
    """Tira da lista quem não pode receber texto livre AGORA.

    Chamado no INÍCIO do envio, nunca no agendamento: quem monta a campanha às
    15h e agenda para 20h está escolhendo uma lista de 15h, e quem falou com a
    loja às 14h de ontem já saiu da janela às 20h de hoje.

    Fora da janela vira SKIPPED, não FAILED. Não é erro — é "não é para essa
    pessoa hoje". Marcar como falha inflaria a taxa de erro da campanha e
    esconderia falha de verdade no meio.

    Quem já recebeu não é tocado: campanha retomada não reprocessa envio feito.
    """
    from apps.campaigns.models import CampaignRecipient

    if not (campaign.audience_filters or {}).get(MARCA):
        return {'dentro': 0, 'pulados': 0}

    abertas = chaves_com_janela_aberta([campaign.account_id])

    pendentes = campaign.recipients.filter(
        status=CampaignRecipient.RecipientStatus.PENDING,
    )
    fora = [
        r.id for r in pendentes
        if chave_do_telefone(r.phone_number) not in abertas
    ]
    if fora:
        from .motivos import FORA_DA_JANELA
        CampaignRecipient.objects.filter(id__in=fora).update(
            status=CampaignRecipient.RecipientStatus.SKIPPED,
            error_code=FORA_DA_JANELA,
        )
    # Conta DEPOIS do corte: `pendentes` é queryset preguiçoso e contá-lo antes
    # devolveria a lista inteira, dizendo ao dono que a campanha vai para mais
    # gente do que realmente vai.
    return {
        'dentro': campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING,
        ).count(),
        'pulados': len(fora),
    }
