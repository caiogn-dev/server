"""Voz do cliente → texto, pelo Whisper large-v3 hospedado na NVIDIA (NVCF/Riva).

Medido em 23/11 com áudio real de cliente (ogg/opus do WhatsApp, 15 s):
- whisper-large-v3: 1,5 s, transcrição perfeita em português;
- parakeet multilíngue: 1,6 s, mas trocou palavras ("Faze gather personalizar tabo").

Nunca levanta exceção: sem chave, sem biblioteca ou com a NVIDIA fora, devolve
'' e o áudio segue como antes (entra no inbox, o bot não responde).
"""
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

WHISPER_NA_NVIDIA = 'b702f636-f60c-4a3d-a6f4-f3568c13bd7d'
SERVIDOR = 'grpc.nvcf.nvidia.com:443'
LIMITE_S = 20


def transcrever(conteudo: bytes, idioma: str = 'pt') -> str:
    if not conteudo:
        return ''
    chave = getattr(settings, 'NVIDIA_API_KEY', '') or ''
    if not chave:
        return ''
    try:
        import riva.client
    except ImportError:
        logger.warning('[transcricao] nvidia-riva-client não instalado — áudio fica sem texto')
        return ''

    funcao = os.environ.get('NVIDIA_ASR_FUNCTION_ID') or WHISPER_NA_NVIDIA
    try:
        auth = riva.client.Auth(
            uri=SERVIDOR,
            use_ssl=True,
            metadata_args=[['function-id', funcao], ['authorization', f'Bearer {chave}']],
        )
        config = riva.client.RecognitionConfig(
            language_code=idioma,
            max_alternatives=1,
            enable_automatic_punctuation=True,
        )
        # future=True: a chamada síncrona do Riva não tem timeout, e isto roda
        # dentro do processamento do webhook — NVIDIA lenta não pode prender o worker.
        pendente = riva.client.ASRService(auth).offline_recognize(conteudo, config, future=True)
        resposta = pendente.result(timeout=LIMITE_S)
    except Exception as exc:  # NVIDIA fora / timeout / formato
        logger.warning('[transcricao] falhou: %s', exc)
        return ''

    trechos = []
    for resultado in getattr(resposta, 'results', None) or []:
        alternativas = getattr(resultado, 'alternatives', None) or []
        if alternativas:
            texto = (getattr(alternativas[0], 'transcript', '') or '').strip()
            if texto:
                trechos.append(texto)
    return ' '.join(trechos)

