"""
Custom logging formatters for structured logging.

Todo log e todo evento do GlitchTip passam por `redact_secrets`. Limpar aqui
fecha o vazamento em um lugar só: trocar `logger.error(f"{e}")` por
`logger.exception()` em cada handler não resolve, porque o traceback repete
`str(e)` no campo `exception`.
"""
import json
import logging
import re
from datetime import datetime, timezone

REDACTED = '[REDACTED]'
_PROFUNDIDADE_MAXIMA = 12
_TAMANHO_MAXIMO_ENTRE_ASPAS = 4096

_NOMES_SENSIVEIS = (
    r'access_token|refresh_token|id_token|auth_token|api_token|bearer_token|'
    r'verify_token|token|client_secret|app_secret|secret_key|webhook_secret|secret|'
    r'x-api-key|api[_-]?key|password|passwd|senha'
)

_CAMPOS_SENSIVEIS = frozenset({
    'access_token', 'refresh_token', 'id_token', 'auth_token', 'api_token',
    'bearer_token', 'verify_token', 'token', 'client_secret', 'app_secret',
    'secret_key', 'webhook_secret', 'secret', 'x_api_key', 'api_key', 'apikey',
    'password', 'passwd', 'senha', 'authorization', 'cookie', 'set_cookie',
})

_AUTHORIZATION = re.compile(
    r'''(authorization\\?["']?\s*[:=]\s*\\?["']?)'''
    r'''(?:(?:bearer|token|basic)\s+)?[^\s"'\\,;}]+''',
    re.IGNORECASE,
)
_CHAVE_E_VALOR = re.compile(
    rf'''(?<![\w-])({_NOMES_SENSIVEIS})(\\?["']?\s*[:=]\s*)'''
    rf'''(?:\\?"[^"]{{0,{_TAMANHO_MAXIMO_ENTRE_ASPAS}}}"'''
    rf'''|\\?'[^']{{0,{_TAMANHO_MAXIMO_ENTRE_ASPAS}}}\''''
    r'''|[^\s&,;'"}\])]+)''',
    re.IGNORECASE,
)
_SENHA_NA_URL = re.compile(r'(://[^\s/:@]{0,256}:)[^\s/@]{1,256}(@)')
_FORMATOS_CONHECIDOS = re.compile(
    r'\bBearer\s+[A-Za-z0-9._~+/=-]{16,}'
    r'|\bToken\s+[a-f0-9]{40}\b'
    r'|\bAPP_USR-[\w-]{10,}'  # Mercado Pago
    r'|\bTEST-\d{6,}-[\w-]+'  # Mercado Pago sandbox
    r'|\bEAA[A-Za-z0-9]{20,}'  # Meta
    r'|\bnvapi-[\w-]{16,}'  # NVIDIA NIM
    r'|\bsk-(?:[a-z]+-)?[A-Za-z0-9_-]{16,}'  # OpenAI, Anthropic
    r'|\bAIza[\w-]{30,}'  # Google
    r'|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_\w{20,}'
    r'|\bre_[A-Za-z0-9]{8,}_[A-Za-z0-9]{16,}'  # Resend
    r'|\bwhsec_[A-Za-z0-9+/=]{16,}'
    r'|\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]+'  # JWT
)


def redact_secrets(texto: str) -> str:
    """Troca credenciais por [REDACTED], mantendo o resto do texto legível."""
    texto = _AUTHORIZATION.sub(rf'\g<1>{REDACTED}', texto)
    texto = _CHAVE_E_VALOR.sub(rf'\g<1>\g<2>{REDACTED}', texto)
    texto = _SENHA_NA_URL.sub(rf'\g<1>{REDACTED}\g<2>', texto)
    return _FORMATOS_CONHECIDOS.sub(REDACTED, texto)


def _campo_sensivel(nome) -> bool:
    return isinstance(nome, str) and nome.lower().replace('-', '_') in _CAMPOS_SENSIVEIS


def _limpar(valor, profundidade=0):
    """Limpa strings em qualquer nível e mascara campos pelo nome."""
    if isinstance(valor, str):
        return redact_secrets(valor)
    if profundidade >= _PROFUNDIDADE_MAXIMA:
        return REDACTED if isinstance(valor, (dict, list, tuple, set)) else valor
    if isinstance(valor, dict):
        return {
            chave: REDACTED if _campo_sensivel(chave) else _limpar(item, profundidade + 1)
            for chave, item in valor.items()
        }
    if isinstance(valor, (list, tuple, set)):
        return [_limpar(item, profundidade + 1) for item in valor]
    return valor


def scrub_sentry_event(event, hint=None):
    """`before_send` do Sentry: o SDK manda o evento sem passar pelo formatter."""
    try:
        return _limpar(event)
    except Exception:
        logging.getLogger(__name__).warning('Evento do Sentry descartado: falha ao limpar segredos.')
        return None


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': redact_secrets(record.getMessage()),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id

        if record.exc_info:
            log_data['exception'] = redact_secrets(self.formatException(record.exc_info))

        if hasattr(record, '__dict__'):
            extra_fields = {
                k: v for k, v in record.__dict__.items()
                if k not in [
                    'name', 'msg', 'args', 'created', 'filename', 'funcName',
                    'levelname', 'levelno', 'lineno', 'module', 'msecs',
                    'pathname', 'process', 'processName', 'relativeCreated',
                    'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                    'message', 'request_id'
                ]
            }
            if extra_fields:
                log_data['extra'] = _limpar(extra_fields)

        return json.dumps(log_data, default=lambda valor: redact_secrets(str(valor)))
