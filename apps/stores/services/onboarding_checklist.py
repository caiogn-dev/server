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
    ('whatsapp', 'Informar WhatsApp', lambda s: bool(s.whatsapp_number)),
]


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
