"""Por que cada destinatário recebeu, falhou ou ficou de fora — em português.

Até 19/09/2026 os pulados não tinham motivo gravado (352 na campanha de
18/09) e as falhas mostravam o erro cru da Meta em inglês. O dono via "28
destinatários" e um chute sobre as falhas.

`explicar` é a fonte única do texto que o painel mostra. Pulados antigos, sem
código, são deduzidos: pediu para parar se o número está na lista de saída;
senão, fora da janela quando a campanha era "só janela aberta".
"""
from typing import Optional, Set

FORA_DA_JANELA = 'fora_da_janela'
JANELA_FECHOU_NO_ENVIO = 'janela_fechou_no_envio'
PEDIU_PARA_PARAR = 'pediu_para_parar'

_TEXTO_DO_PULO = {
    FORA_DA_JANELA: (
        'Fora da janela de 24h: não falou com a loja nas últimas 24h, e texto '
        'livre só pode ir para quem falou.'
    ),
    JANELA_FECHOU_NO_ENVIO: (
        'A janela de 24h fechou enquanto a campanha era enviada.'
    ),
    PEDIU_PARA_PARAR: 'Pediu para parar de receber promoções.',
}

#: Erros da Meta que aparecem de verdade nas campanhas. O texto diz de quem é
#: o problema — do cliente, da Meta ou nosso — porque isso muda o que fazer.
_ERROS_DA_META = {
    '131049': (
        'A Meta segurou: esta pessoa já recebeu muitas promoções de empresas '
        'nos últimos dias (limite de marketing da Meta). Tente em outro dia.'
    ),
    '130472': (
        'A Meta segurou: o número participa de um teste da Meta e não recebe '
        'promoções.'
    ),
    '131026': 'Número sem WhatsApp, ou que não aceita esta mensagem.',
    '131047': (
        'Janela de 24h fechada: texto livre só vai para quem falou com a loja '
        'nas últimas 24h.'
    ),
    '131048': 'A Meta limitou o envio da conta (muitas mensagens em pouco tempo).',
    '131050': 'A pessoa bloqueou mensagens de marketing no WhatsApp.',
    '131051': 'Tipo de mensagem não suportado.',
    '132000': 'O template não bate com os dados enviados (problema nosso).',
    '132001': 'O template não existe ou não foi aprovado.',
    '100': 'Parâmetro inválido na mensagem (problema nosso, não do cliente).',
}


def _codigo(recipient) -> str:
    codigo = (recipient.error_code or '').strip()
    if not codigo:
        mensagem = recipient.error_message or ''
        if '(#100)' in mensagem:
            return '100'
    return codigo


def explicar(recipient, bloqueadas: Optional[Set[str]] = None,
             so_janela: Optional[bool] = None) -> dict:
    """{'situacao': ..., 'motivo': ...} de um destinatário.

    `bloqueadas` e `so_janela` podem vir prontos (lista de pessoas: uma
    consulta, não uma por linha); sem eles, são buscados aqui.
    """
    from apps.campaigns.models import CampaignRecipient
    status = CampaignRecipient.RecipientStatus

    if recipient.status == status.READ:
        return {'situacao': 'leu', 'motivo': 'Recebeu e leu.'}
    if recipient.status == status.DELIVERED:
        return {'situacao': 'recebeu', 'motivo': 'Chegou no celular, ainda não leu.'}
    if recipient.status == status.SENT:
        return {'situacao': 'recebeu', 'motivo': 'Enviada; aguardando o WhatsApp confirmar a entrega.'}
    if recipient.status == status.PENDING:
        return {'situacao': 'na_fila', 'motivo': 'Ainda na fila de envio.'}

    if recipient.status == status.FAILED:
        codigo = _codigo(recipient)
        texto = _ERROS_DA_META.get(codigo)
        if not texto:
            texto = f'O WhatsApp recusou a mensagem (código {codigo}).' if codigo else 'O WhatsApp recusou a mensagem.'
        return {'situacao': 'falhou', 'motivo': texto}

    # Pulado.
    codigo = (recipient.error_code or '').strip()
    if codigo in _TEXTO_DO_PULO:
        return {'situacao': 'ficou_de_fora', 'motivo': _TEXTO_DO_PULO[codigo]}
    # Pulado antigo, sem motivo gravado (antes de 19/09): deduz.
    from .contatos import chave_do_telefone
    if bloqueadas is None:
        from .optout import chaves_bloqueadas
        bloqueadas = chaves_bloqueadas(recipient.campaign.account)
    if chave_do_telefone(recipient.phone_number) in bloqueadas:
        return {'situacao': 'ficou_de_fora', 'motivo': _TEXTO_DO_PULO[PEDIU_PARA_PARAR]}
    if so_janela is None:
        from .janela import MARCA
        so_janela = bool((recipient.campaign.audience_filters or {}).get(MARCA))
    if so_janela:
        return {'situacao': 'ficou_de_fora', 'motivo': _TEXTO_DO_PULO[FORA_DA_JANELA]}
    return {'situacao': 'ficou_de_fora', 'motivo': 'Ficou de fora do envio.'}
