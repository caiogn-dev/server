"""Como o aviso chega ao dono — e o que fazer quando não chega.

A Meta só aceita texto livre até 24 h depois da última mensagem DO DONO para
o número da loja (131047 fora disso). Para o aviso das 8h ser confiável:

1. conversa aberta → texto livre (de graça, com quebras de linha);
2. fechada → modelo de UTILIDADE `vigia_do_dia`, aprovado na Meta;
3. nenhum dos dois → fica no painel, com o motivo escrito no envio.

Os nomes `janela_aberta`, `modelo_aprovado`, `_enviar_texto` e
`_enviar_modelo` são os pontos de costura dos testes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

NOME_DO_MODELO = 'vigia_do_dia'
IDIOMA = 'pt_BR'
EVENTO = 'vigia'

# Variável não pode ter quebra de linha (132018) nem abrir/fechar o corpo.
CORPO = 'Avisos de hoje da {{1}}: {{2}}\n\nPara pausar, responda PARAR AVISOS.'
EXEMPLO = [
    'Cê Saladas',
    'Ontem: 18 pedidos, R$ 1.020,00 — 12% acima da média das últimas 4 quintas. '
    '• Almôndega Premium: 3 vendidas nos últimos 5 dias abertos; o normal seria ~9 (−67%).',
]
#: A Meta corta parâmetro de corpo longo; sobra margem para o texto fixo.
LIMITE_DA_LINHA = 900


@dataclass
class Entrega:
    status: str          # enviado | so_painel | falhou
    canal: str           # texto | modelo | painel
    mensagem_id: str = ''
    erro: str = ''


def _so_digitos(telefone) -> str:
    return ''.join(ch for ch in str(telefone or '') if ch.isdigit())


def _conta_da_loja(loja):
    return getattr(loja, 'whatsapp_account', None)


def janela_aberta(conta, telefone: str) -> bool:
    from apps.automation.mensageiro import janela

    return janela.aberta(conta, telefone)


def modelo_aprovado(conta) -> bool:
    from apps.whatsapp.models import MessageTemplate

    return MessageTemplate.objects.filter(
        account_id=getattr(conta, 'id', None), name=NOME_DO_MODELO, language=IDIOMA, is_active=True,
        status=MessageTemplate.TemplateStatus.APPROVED,
    ).exists()


def _id_da_mensagem(mensagem) -> str:
    return str(getattr(mensagem, 'whatsapp_message_id', '') or getattr(mensagem, 'id', '') or '')


def _falhou(mensagem):
    from apps.whatsapp.models import Message

    if mensagem is None or getattr(mensagem, 'status', None) == Message.MessageStatus.FAILED:
        raise RuntimeError(getattr(mensagem, 'error_message', '') or 'envio falhou')
    return mensagem


def _enviar_texto(conta, telefone: str, texto: str) -> str:
    """Direto pelo MessageService: o modo humano da conversa do dono não cala
    o aviso (mesma decisão do aviso de fila humana)."""
    from apps.whatsapp.services.message_service import MessageService

    mensagem = MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto,
        metadata={'automatico': True, 'evento': EVENTO},
    )
    return _id_da_mensagem(_falhou(mensagem))


def _enviar_modelo(conta, telefone: str, nome_da_loja: str, linha: str) -> str:
    from apps.whatsapp.services.message_service import MessageService

    mensagem = MessageService().send_template_message(
        account_id=str(conta.id), to=telefone, template_name=NOME_DO_MODELO, language_code=IDIOMA,
        components=[{'type': 'body', 'parameters': [
            {'type': 'text', 'text': linha_unica(nome_da_loja, 60)},
            {'type': 'text', 'text': linha_unica(linha, LIMITE_DA_LINHA)},
        ]}],
        metadata={'automatico': True, 'evento': EVENTO, 'por_modelo': True},
    )
    return _id_da_mensagem(_falhou(mensagem))


def linha_unica(texto: str, limite: int) -> str:
    plano = ' '.join(str(texto or '').split())
    return plano if len(plano) <= limite else plano[:limite - 1].rstrip() + '…'


def entregar(loja, telefone: str, texto: str, linha: str) -> Entrega:
    """Tenta conversa aberta, depois o modelo. Nunca levanta exceção."""
    telefone = _so_digitos(telefone)
    conta = _conta_da_loja(loja)
    if not telefone:
        return Entrega('so_painel', 'painel', erro='Sem telefone do dono configurado.')
    if conta is None:
        return Entrega('so_painel', 'painel', erro='A loja não tem WhatsApp conectado.')

    erro_texto = ''
    try:
        if janela_aberta(conta, telefone):
            return Entrega('enviado', 'texto', mensagem_id=_enviar_texto(conta, telefone, texto))
    except Exception as exc:  # noqa: BLE001 — a Meta levanta de tudo; tenta o modelo
        erro_texto = str(exc)[:200]
        logger.warning('[vigia] texto livre não saiu para a loja %s: %s', loja.id, exc)

    try:
        aprovado = modelo_aprovado(conta)
    except Exception as exc:  # noqa: BLE001
        aprovado = False
        erro_texto = erro_texto or str(exc)[:200]
    if not aprovado:
        motivo = ('O dono não falou com o número da loja nas últimas 24 h e o modelo '
                  f'"{NOME_DO_MODELO}" ainda não está aprovado na Meta.')
        if erro_texto:
            return Entrega('falhou', 'texto', erro=f'{erro_texto} | {motivo}'[:300])
        return Entrega('so_painel', 'painel', erro=motivo)

    try:
        return Entrega('enviado', 'modelo',
                       mensagem_id=_enviar_modelo(conta, telefone, loja.name, linha))
    except Exception as exc:  # noqa: BLE001
        logger.warning('[vigia] modelo não saiu para a loja %s: %s', loja.id, exc)
        return Entrega('falhou', 'modelo', erro=str(exc)[:300])


def criar_modelo(conta):
    """Registra `vigia_do_dia` na WABA da conta. Idempotente — ver `mensageiro.modelo.criar_na_meta`."""
    from apps.whatsapp.models import MessageTemplate
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

    existente = MessageTemplate.objects.filter(account=conta, name=NOME_DO_MODELO, language=IDIOMA).first()
    if existente:
        return existente
    resposta = WhatsAppAPIService(conta)._make_request(  # noqa: SLF001 — não há wrapper de criação
        'POST', f'{conta.waba_id}/message_templates', data={
            'name': NOME_DO_MODELO, 'language': IDIOMA, 'category': 'UTILITY',
            'components': [{'type': 'BODY', 'text': CORPO, 'example': {'body_text': [EXEMPLO]}}],
        },
    )
    linha = MessageTemplate.objects.create(
        account=conta, template_id=str(resposta.get('id', '')), name=NOME_DO_MODELO, language=IDIOMA,
        category=MessageTemplate.TemplateCategory.UTILITY,
        status=str(resposta.get('status', 'pending')).lower(),
        components=[{'type': 'BODY', 'text': CORPO}],
    )
    logger.info('Modelo %s criado na conta %s: %s', NOME_DO_MODELO, conta.id, linha.status)
    return linha


def estado_do_modelo(conta) -> str:
    """'aprovado' | 'pendente' | 'recusado' | 'ausente' | 'sem_whatsapp' — para o painel."""
    from apps.whatsapp.models import MessageTemplate

    if conta is None:
        return 'sem_whatsapp'
    linha = MessageTemplate.objects.filter(account=conta, name=NOME_DO_MODELO, language=IDIOMA).first()
    if linha is None:
        return 'ausente'
    status = str(linha.status or '').lower()
    if status == str(MessageTemplate.TemplateStatus.APPROVED).lower():
        return 'aprovado'
    if status in ('rejected', 'disabled', 'paused'):
        return 'recusado'
    return 'pendente'
