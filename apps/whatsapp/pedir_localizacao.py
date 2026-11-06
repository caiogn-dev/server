"""Como o bot pede a localização ao cliente. Um texto, um lugar.

Dono, 06/11: "clicar no alfinete" deixava subentendido — no WhatsApp não há
alfinete para tocar. O caminho real é o clipe 📎 (Android) ou o + (iPhone) →
Localização → Enviar localização atual. Handlers e prompts do LLM usam este
texto; o LLM é proibido de falar "alfinete".
"""

PEDIR_LOCALIZACAO = (
    "📍 Para calcular a entrega, me mande sua localização: toque no 📎 "
    "(no iPhone, no +) → *Localização* → *Enviar localização atual*.\n"
    "Se preferir, digite o endereço com número e bairro."
)

# Regra para colar nos prompts do LLM.
REGRA_LLM_PEDIR_LOCALIZACAO = (
    "Para pedir endereço/localização (ex.: calcular a taxa de entrega), use exatamente "
    f"este texto: «{PEDIR_LOCALIZACAO}». "
    'NUNCA use a palavra "alfinete".'
)
