"""URL absoluta da logo de uma bandeira.

Fica FORA de `bandeiras.py` de proposito: aquele modulo e puro (sem Django) e
os testes dependem disso. Aqui e onde o caminho estatico vira endereco, e para
isso precisamos do dominio — que so o Django sabe.

A URL e absoluta porque quem consome esta config e outro dominio (o cardapio e
o painel), e caminho relativo apontaria para o servidor errado.
"""
import logging

from django.conf import settings
from django.templatetags.static import static

from . import bandeiras

logger = logging.getLogger(__name__)


def url_da_logo(valor):
    """Endereço completo da logo, ou '' se a bandeira não tiver uma.

    🚨 NUNCA levanta. O whitenoise roda com `ManifestStaticFilesStorage`, que
    exige `collectstatic`: se o arquivo não estiver no manifesto, `static()`
    dispara ValueError. E esta função é chamada de dentro da configuração de
    pagamento — o caminho crítico do checkout.

    Uma logo faltando tem que degradar para "sem logo", NUNCA para 500. O
    cliente com bandeira sem imagem vê o nome e paga; o cliente com HTTP 500
    não vê tela nenhuma.
    """
    caminho = bandeiras.logo(valor)
    if not caminho:
        return ''
    try:
        estatico = static(caminho)
    except Exception:
        logger.warning(
            'Logo de bandeira ausente no manifesto estático: %s '
            '(rodou collectstatic no deploy?)', caminho,
        )
        return ''
    if estatico.startswith(('http://', 'https://')):
        return estatico
    base = (getattr(settings, 'BASE_URL', '') or '').rstrip('/')
    return f'{base}{estatico}' if base else estatico


def catalogo_com_logo():
    """O catálogo inteiro, com a logo já resolvida — o que o painel recebe."""
    return [
        {'value': b['value'], 'label': b['label'], 'logo': url_da_logo(b['value'])}
        for b in bandeiras.CATALOGO
    ]


def marcas_da_loja(valores):
    """As bandeiras que ESTA loja aceita, com rótulo e logo — o que o cardápio recebe."""
    return [
        {'value': v, 'label': bandeiras.rotulo(v), 'logo': url_da_logo(v)}
        for v in valores
    ]
