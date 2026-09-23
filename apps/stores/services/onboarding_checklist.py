"""
Checklist de onboarding ("Primeiros passos") — estado 100% DERIVADO de dados
reais do Store. Sem model novo, sem flag manual. Cada passo é uma função de
derivação isolada. O frontend mapeia key -> rota/label de ação; aqui devolvemos
key/label/done (label é a cópia curta do passo).
"""

# (key, label, função de derivação)
_STEPS = [
    ('account', 'Conta criada', lambda s: True),
    ('logo', 'Adicionar logo da loja', lambda s: bool(s.logo or s.logo_url)),
    ('product', 'Cadastrar 1º produto', lambda s: s.products.exists()),
    ('delivery', 'Configurar entrega', lambda s: s.delivery_zones.exists()),
    ('hours', 'Definir horário de funcionamento', lambda s: bool(s.operating_hours)),
    ('whatsapp', 'Conectar o WhatsApp da loja', lambda s: _whatsapp_conectado(s)),
    ('payment', 'Conectar meio de recebimento', lambda s: _recebe_pagamento(s)),
]


def _whatsapp_conectado(store):
    """A loja consegue ATENDER pelo WhatsApp?

    Este passo olhava `store.whatsapp_number` — um campo de texto que o dono
    digita. Em 22/09, quatro das seis lojas tinham o passo VERDE e nenhuma
    WABA conectada; a Solo e Zelo tinha como "número" o próprio `waba_id`
    quebrado, colado no campo errado, e nada acusou.

    Número escrito não recebe mensagem. A resposta é a conta conectada.

    `is_active=False` NÃO conta: conta caída (COEX DISCONNECTED, token
    revogado) não atende ninguém, e dar o passo por pronto esconderia
    justamente a queda que o dono precisa ver.

    Também é pré-condição de escala: quem conecta a própria WABA paga as
    próprias mensagens da Meta. Enquanto o checklist mentir, ninguém é
    obrigado a conectar.

    Usa `get_whatsapp_account()` — o acessor canônico, que já sabe procurar
    pelo vínculo direto E pela integração. Escrever a busca aqui criaria a
    segunda cópia de "como achar o WhatsApp da loja", e as duas divergiriam.
    """
    conta = store.get_whatsapp_account()
    if conta is not None and conta.is_active:
        return True

    # Loja grandfather segue no número digitado — decisão do dono em 22/09.
    # A exigência de conectar existe para CLIENTE NOVO: é ela que faz a conta
    # de mensagem da Meta ficar com quem vende. Loja pré-SaaS é atendida pelo
    # próprio dono, no aparelho dele; exigir embedded signup ali seria criar
    # trabalho sem destravar nada.
    #
    # `billing_exempt` já é a marca de "as regras do SaaS não valem aqui" e é
    # o que `billing.is_billing_exempt()` usa. Uma segunda flag para o mesmo
    # conceito criaria duas verdades sobre quem é legado.
    #
    # Isentar de conectar NÃO é isentar de ter WhatsApp: sem número nenhum o
    # passo continua pendente.
    from apps.stores import billing

    if billing.is_billing_exempt(store):
        return bool((store.whatsapp_number or '').strip())
    return False


def _recebe_pagamento(store):
    """A loja consegue receber o dinheiro de um pedido?

    Este passo entrou depois do 1º cliente pago: ele fechou logo, banner, cor e
    tagline, o checklist dizia 3/6, e nenhum dos 6 passos falava de pagamento.
    A loja dele acumulou 4 carrinhos e 3 checkouts barrados com "sem gateway
    próprio e sem usa_gateway_da_plataforma" — dava para bater 6/6 e não
    receber um centavo.

    Espelha `CheckoutService.get_payment_credentials`: gateway próprio LIGADO
    e com token, ou opt-in explícito pelo gateway da plataforma. Gateway
    desligado não recebe, então não conta como pronto.
    """
    if getattr(store, 'usa_gateway_da_plataforma', False):
        return True
    return store.payment_gateways.filter(
        is_enabled=True,
    ).exclude(access_token='').exists()


def build_checklist(store):
    steps = [{'key': k, 'label': lbl, 'done': bool(fn(store))} for k, lbl, fn in _STEPS]
    completed = sum(1 for s in steps if s['done'])
    total = len(steps)
    return {
        'steps': steps,
        'completed': completed,
        'total': total,
        'all_done': completed == total,
    }
