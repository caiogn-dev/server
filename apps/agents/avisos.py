"""Textos fixos que o agente manda quando não tem resposta de verdade.

Mora num módulo sem dependência nenhuma porque o pipeline do WhatsApp precisa
reconhecer estes textos sem importar o grafo (que puxa LangChain inteiro).
"""

#: O LLM falhou (timeout, 5xx, modelo fora do ar). Não é resposta: é um aviso.
#: Em 08-14/set/2026 o NIM estourou o tempo 23 vezes e, quando o cliente tinha
#: mandado 2 ou 3 mensagens seguidas, este texto chegava 2 ou 3 vezes em 1s.
MENSAGEM_DE_ERRO_DO_LLM = "Desculpa, tive um probleminha aqui. Pode repetir?"
