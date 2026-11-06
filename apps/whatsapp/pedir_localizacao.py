"""Como o bot pede a localização ao cliente. Um texto, um lugar.

Dono, 06/11: "clicar no alfinete" deixava subentendido — no WhatsApp não há
alfinete para tocar. E emoji de pino/clipe na mensagem também confunde: o
cliente toca no emoji achando que é botão. Por isso estes textos não têm
emoji nenhum.

Padrão: botão nativo "Enviar localização" (location_request_message) com
PEDIR_LOCALIZACAO_BOTAO. Sem botão (API recusou, task, outro canal, LLM):
PEDIR_LOCALIZACAO, com o caminho Anexar → Localização → Enviar localização atual.
"""

PEDIR_LOCALIZACAO = (
    "Para calcular a entrega, me mande sua localização: no WhatsApp, toque em "
    "*Anexar* (clipe, ou + no iPhone) → *Localização* → *Enviar localização atual*. "
    "Ou digite o endereço com número e bairro."
)

# Corpo do botão nativo "Enviar localização".
PEDIR_LOCALIZACAO_BOTAO = (
    "Para calcular a entrega, toque no botão *Enviar localização* abaixo. "
    "Se preferir, digite o endereço com número e bairro."
)

# Regra para colar nos prompts do LLM.
REGRA_LLM_PEDIR_LOCALIZACAO = (
    "Para pedir endereço/localização (ex.: calcular a taxa de entrega), use exatamente "
    f"este texto: «{PEDIR_LOCALIZACAO}». "
    'NUNCA use a palavra "alfinete" e não ponha emoji nesse pedido '
    "(nada de 📍, 📎 ou 📌: o cliente toca no emoji achando que é botão)."
)
