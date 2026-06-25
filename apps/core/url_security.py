"""Guard de SSRF para URLs configuráveis (ex.: webhooks de loja).

Uma URL salva pela loja é chamada pelo backend mais tarde (server-side
request). Sem validação, um tenant pode apontar para endereços internos
(localhost, faixas privadas, 169.254.169.254 metadata) e fazer o servidor
vazar/atacar a infra. Este módulo bloqueia esses destinos no momento do save.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from django.core.exceptions import ValidationError

_ALLOWED_SCHEMES = {'http', 'https'}
_BLOCKED_HOSTNAMES = {'localhost', 'ip6-localhost', 'ip6-loopback'}
_BLOCKED_SUFFIXES = ('.local', '.internal', '.localhost')


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_webhook_url(url: str) -> str:
    """Valida que `url` aponta para um destino público http(s).

    Retorna a própria URL se válida; levanta ValidationError caso contrário.
    """
    if not url or not isinstance(url, str):
        raise ValidationError('URL inválida.')

    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValidationError('URL deve usar http ou https.')

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError('URL sem host válido.')

    host_lower = hostname.lower()
    if host_lower in _BLOCKED_HOSTNAMES or host_lower.endswith(_BLOCKED_SUFFIXES):
        raise ValidationError('URL aponta para um host interno não permitido.')

    # Se o host é um IP literal, valida diretamente.
    try:
        ip = ipaddress.ip_address(host_lower.strip('[]'))
    except ValueError:
        ip = None

    if ip is not None:
        if _ip_is_blocked(ip):
            raise ValidationError('URL aponta para um IP interno/privado não permitido.')
        return url

    # Hostname: tenta resolver e bloqueia se QUALQUER endereço for interno.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Não resolveu agora — não dá pra confirmar interno; deixa passar.
        return url

    for info in infos:
        addr = info[4][0]
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_blocked(resolved):
            raise ValidationError('URL resolve para um IP interno/privado não permitido.')

    return url
