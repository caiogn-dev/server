"""Texto dos avisos de status do pedido — o mesmo que o dono vê no painel.

Até 19/10/2026 a tela "Modelos de mensagem" do painel mostrava uma lista fixa
do front, e o que saía para o cliente era outra coisa (a AutoMessage da loja,
com o texto padrão antigo). A Maria Vitória, de RETIRADA, recebeu "Em breve
estará a caminho!". Os textos abaixo são os do painel, preenchidos com dado
real do pedido; linha cujo dado falta some inteira.
"""
import re

#: Textos padrão dos avisos de status, por evento. Chaves entre chaves simples.
TEXTOS_PADRAO = {
    'order_confirmed': (
        "✅ *Pedido Confirmado!*\n\n"
        "Olá {primeiro_nome}, recebemos seu pedido #{order_number}.\n\n"
        "💰 *Total:* R$ {total}\n"
        "⏱️ *Tempo:* {tempo} min\n\n"
        "Vamos preparar com carinho!"
    ),
    'order_preparing': (
        "👨‍🍳 *Seu pedido está sendo preparado!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Pedido #{order_number} em preparação.\n"
        "⏱️ Falta aproximadamente {tempo} minutos!"
    ),
    'order_out_for_delivery': (
        "🛵 *Seu pedido saiu para entrega!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Pedido #{order_number} a caminho!\n"
        "📍 {endereco}"
    ),
    'order_delivered': (
        "✨ *Pedido {entregue_ou_retirado}!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Seu pedido #{order_number} foi {entregue_ou_retirado}! 🎉\n\n"
        "Esperamos que aproveite!"
    ),
}

_CHAVE = re.compile(r'\{(\w+)\}')


def renderizar_aviso(texto: str, contexto: dict) -> str:
    """Troca `{chave}` pelo valor. Linha com chave conhecida e vazia some.

    Chave que não está no contexto fica como está — o texto é do dono, e
    apagar uma linha que ele escreveu por causa de um nome errado esconderia o
    erro em vez de mostrá-lo.
    """
    linhas = []
    for linha in (texto or '').split('\n'):
        chaves = _CHAVE.findall(linha)
        if any(c in contexto and contexto[c] in (None, '') for c in chaves):
            continue
        linhas.append(_CHAVE.sub(
            lambda m: str(contexto[m.group(1)]) if m.group(1) in contexto else m.group(0),
            linha,
        ))
    resultado = '\n'.join(linhas)
    resultado = re.sub(r'\n{3,}', '\n\n', resultado)
    return resultado.strip()


def _reais(valor) -> str:
    try:
        return f"{float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return ''


def _endereco(endereco) -> str:
    if not endereco:
        return ''
    if isinstance(endereco, str):
        return endereco
    if not isinstance(endereco, dict):
        return ''
    if endereco.get('formatted'):
        return str(endereco['formatted'])
    rua = endereco.get('street') or endereco.get('address') or ''
    partes = [
        f"{rua}, {endereco['number']}" if rua and endereco.get('number') else rua,
        endereco.get('complement'),
        endereco.get('neighborhood'),
        endereco.get('city'),
    ]
    return ' - '.join(str(p) for p in partes if p)


def variaveis_do_pedido(pedido) -> dict:
    """Variáveis que os avisos de status entendem, com o dado do pedido."""
    eh_retirada = pedido.delivery_method in ('pickup', 'digital')
    nome = (pedido.customer_name or '').strip()
    tempo = pedido.prep_minutes
    if tempo is None:
        tempo = getattr(pedido.store, 'default_prep_minutes', 0) if pedido.store_id else 0
    return {
        'customer_name': nome,
        # Sem nome, "Olá cliente," — sumir com a linha levaria junto o número
        # do pedido ("Olá {primeiro_nome}, recebemos seu pedido #...").
        'primeiro_nome': nome.split()[0].capitalize() if nome else 'cliente',
        'order_number': pedido.order_number,
        'order_total': pedido.total,
        'total': _reais(pedido.total),
        'tempo': tempo or '',
        'endereco': '' if eh_retirada else _endereco(pedido.delivery_address),
        'entregue_ou_retirado': 'retirado' if eh_retirada else 'entregue',
        'proximo_passo': 'Pode vir buscar! 😊' if eh_retirada else 'Já vai sair para entrega.',
    }
