"""Textos fixos que o agente manda quando não tem resposta de verdade.

Mora num módulo sem dependência nenhuma porque o pipeline do WhatsApp precisa
reconhecer estes textos sem importar o grafo (que puxa LangChain inteiro).
"""

#: O LLM falhou (timeout, 5xx, modelo fora do ar). Não é resposta: é um aviso.
#: Em 08-14/set/2026 o NIM estourou o tempo 23 vezes e, quando o cliente tinha
#: mandado 2 ou 3 mensagens seguidas, este texto chegava 2 ou 3 vezes em 1s.
MENSAGEM_DE_ERRO_DO_LLM = "Desculpa, tive um probleminha aqui. Pode repetir?"

#: As variantes que já saíram para clientes. O texto mudou de lugar e de
#: redação ao longo do tempo (grafo, serviço do LangGraph, versões antigas em
#: produção), e reconhecer só uma deixa as outras passarem como se fossem
#: resposta de verdade — foi assim que o cliente continuou recebendo desculpa
#: mesmo com o caminho do atendente pronto.
AVISOS_DE_FALHA = (
    MENSAGEM_DE_ERRO_DO_LLM,
    'Desculpa, tive um problema. Pode repetir?',
    'Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?',
)


def e_aviso_de_falha(texto) -> bool:
    """O texto é um aviso de falha da IA, e não uma resposta?"""
    limpo = (texto or '').strip()
    return any(limpo == aviso for aviso in AVISOS_DE_FALHA)
