"""Mensagem pronta para o entregador (22/10).

O dono mandava à mão no WhatsApp do motoboy:

    ALINE NASCHE - +55 (11) 97537-3744

    QUADRA 505 SUL, Alameda 18, 8, Plano Diretor Sul, Palmas, TO
    77016458

    https://maps.app.goo.gl/...

Aqui sai igual, montado do pedido, com o que a comanda já sabe: se é para
cobrar, quanto e como (maquininha, dinheiro e troco). Endereço e cobrança
usam as mesmas regras do papel (print_service / comanda_linhas) — o motoboy
não pode ler uma coisa no WhatsApp e outra na comanda.
"""
from decimal import Decimal
from urllib.parse import quote, urlencode

from apps.core.utils import format_phone_for_display
from apps.stores.models import StoreOrder
from apps.stores.services.comanda_linhas import _FORMAS, _dinheiro
from apps.stores.services.print_service import _troco_da_comanda


def _endereco(order: StoreOrder) -> tuple[str, str]:
    """(endereço numa linha, CEP) — no formato que o dono mandava."""
    a = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    from apps.core.services.customer_identity import CustomerIdentityService
    numero = str(a.get('numero') or a.get('number') or '')
    complemento = str(a.get('complemento') or a.get('complement') or '')
    bairro = str(a.get('bairro') or a.get('neighborhood') or '')
    cidade = str(a.get('cidade') or a.get('city') or '')
    uf = str(a.get('estado') or a.get('state') or '')
    rua = CustomerIdentityService.rua_sem_cauda(
        str(a.get('rua') or a.get('street') or ''),
        numero=numero, complemento=complemento, bairro=bairro, cidade=cidade, uf=uf,
    )
    cep = str(a.get('cep') or a.get('zip_code') or '')
    partes = [p for p in [rua, numero, complemento, bairro, cidade, uf] if p]
    if rua:
        return ', '.join(partes), cep
    return str(a.get('raw_address') or a.get('address') or ''), cep


def _mapa(order: StoreOrder, endereco: str) -> str:
    lat, lng = order.delivery_lat, order.delivery_lng
    if lat is not None and lng is not None:
        alvo = f'{Decimal(lat).normalize()},{Decimal(lng).normalize()}'
    elif endereco:
        alvo = endereco
    else:
        return ''
    return 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': alvo}, quote_via=quote)


def _cobranca(order: StoreOrder) -> list[str]:
    forma = _FORMAS.get(order.payment_method or '', (order.payment_method or '').upper())
    if order.payment_status == 'paid':
        return [' · '.join(filter(None, ['Pago', forma])) + ' — não cobrar']
    if order.total <= 0 or order.payment_method == 'sem_cobranca':
        return ['Sem cobrança']
    linhas = [f'COBRAR {_dinheiro(order.total)}' + (f' — {forma}' if forma else '')]
    if order.payment_method == 'card_on_delivery':
        linhas[0] += ' (levar maquininha)'
    troco = _troco_da_comanda(order)
    if troco['change_for'] is not None:
        if Decimal(troco['change_for']) == 0:
            linhas.append('Sem troco')
        else:
            linhas.append(f"Troco para {_dinheiro(troco['change_for'])} — levar {_dinheiro(troco['change_due'])}")
    return linhas


def texto_para_entregador(order: StoreOrder) -> str:
    cliente = ' - '.join(filter(None, [order.customer_name, format_phone_for_display(order.customer_phone or '')]))
    endereco, cep = _endereco(order)
    blocos = [
        f'*Pedido {order.order_number}*',
        cliente,
        '\n'.join(filter(None, [endereco, cep, f'Ref: {order.delivery_notes}' if order.delivery_notes else ''])),
        _mapa(order, endereco),
        '\n'.join(_cobranca(order)),
    ]
    return '\n\n'.join(b for b in blocos if b)


def whatsapp_do_entregador(order: StoreOrder, texto: str) -> str:
    """Link wa.me com o texto. Sem entregador (ou sem telefone), o WhatsApp
    abre para escolher o contato."""
    from apps.core.utils import normalize_phone_number
    numero = normalize_phone_number(getattr(order.entregador, 'telefone', '') or '') if order.entregador_id else ''
    return f'https://wa.me/{numero}?' + urlencode({'text': texto}, quote_via=quote)


class NaoEnviado(Exception):
    """Motivo em português, para o painel mostrar como veio."""


def enviar_ao_entregador(order: StoreOrder) -> str:
    """Manda o texto pelo WhatsApp da loja (API), como mensagem normal.

    Só dentro da janela de 24 h: o entregador precisa ter escrito para o número
    da loja nesse prazo — fora dela a Meta recusa texto livre (131047), e
    modelo aprovado o dono não quis (22/10). Devolve o id da mensagem.
    """
    from apps.automation.mensageiro import janela
    from apps.core.utils import normalize_phone_number
    from apps.whatsapp.models import Message
    from apps.whatsapp.services.message_service import MessageService

    entregador = order.entregador
    if entregador is None:
        raise NaoEnviado('Escolha o entregador do pedido primeiro.')
    telefone = normalize_phone_number(entregador.telefone or '')
    if not telefone:
        raise NaoEnviado(f'{entregador.nome} não tem WhatsApp cadastrado em Equipe e entregas.')
    conta = getattr(order.store, 'whatsapp_account', None)
    if conta is None:
        raise NaoEnviado('A loja não tem WhatsApp conectado.')
    if not janela.aberta(conta, telefone):
        raise NaoEnviado(
            f'{entregador.nome} não mandou mensagem para a loja nas últimas 24 h — '
            'peça um "oi" dele no WhatsApp da loja e envie de novo.')

    mensagem = MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto_para_entregador(order),
        metadata={'automatico': True, 'evento': 'entregador', 'pedido': str(order.id)},
    )
    if mensagem is None or getattr(mensagem, 'status', None) == Message.MessageStatus.FAILED:
        raise NaoEnviado(getattr(mensagem, 'error_message', '') or 'O WhatsApp recusou o envio.')
    return str(getattr(mensagem, 'whatsapp_message_id', '') or getattr(mensagem, 'id', ''))
