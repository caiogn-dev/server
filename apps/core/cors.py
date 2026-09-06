"""CORS que acompanha o cadastro da loja, não a variável de ambiente.

O produto VENDE domínio próprio. Enquanto a lista de origens era estática, cada
cliente novo com domínio próprio precisava de uma edição de env e um restart —
e até lá via a própria loja abrir e não carregar nada, porque o navegador
bloqueava toda chamada à API.

Aqui a fonte da verdade é o `custom_domain` da loja ATIVA, que é onde o dono já
digita o endereço. Ver `tests/test_cors_do_dominio_da_loja.py`.
"""
from urllib.parse import urlparse

from django.core.cache import cache

CHAVE_DO_CACHE = 'cors:dominios_de_loja'
SEGUNDOS_DE_CACHE = 300


def _hospedeiro(valor):
    """O host de uma origem ou de um domínio digitado à mão, sem o `www`."""
    if not valor or not isinstance(valor, str):
        return ''

    texto = valor.strip().lower()
    if not texto:
        return ''

    # O dono cola `https://loja.com.br/` tanto quanto digita `loja.com.br`.
    if '//' not in texto:
        texto = f'//{texto}'

    host = (urlparse(texto).hostname or '').strip('.')
    return host[4:] if host.startswith('www.') else host


def dominios_de_loja():
    """Os domínios próprios das lojas ativas, normalizados.

    Em cache: isto roda em TODA requisição com Origin, e ir ao banco a cada uma
    transformaria o CORS num gargalo.
    """
    cacheado = cache.get(CHAVE_DO_CACHE)
    if cacheado is not None:
        return cacheado

    from apps.stores.models import Store

    brutos = Store.objects.filter(status='active').exclude(
        custom_domain__isnull=True,
    ).exclude(custom_domain='').values_list('custom_domain', flat=True)

    dominios = {h for h in (_hospedeiro(d) for d in brutos) if h}
    cache.set(CHAVE_DO_CACHE, dominios, SEGUNDOS_DE_CACHE)
    return dominios


def esquecer_dominios():
    """Derruba o cache. Chamado ao salvar/apagar loja e pelos testes."""
    cache.delete(CHAVE_DO_CACHE)


def esquecer_dominios_de_loja(sender, **kwargs):
    """Handler de `post_save`/`post_delete` de `Store`."""
    esquecer_dominios()


def origem_e_de_uma_loja(origem):
    """Se esta origem é o domínio próprio de alguma loja ativa.

    Compara HOST por HOST, nunca por "termina com": `cesaladas.com.br.evil.com`
    termina com o domínio e não é ele — casar por sufixo entregaria a API a
    quem registrasse um domínio parecido.
    """
    if not origem or not isinstance(origem, str):
        return False

    # Só https: o domínio da loja é servido em https, e aceitar http exporia o
    # token de autenticação a quem estivesse no caminho.
    if not origem.strip().lower().startswith('https://'):
        return False

    host = _hospedeiro(origem)
    return bool(host) and host in dominios_de_loja()


def liberar_dominio_de_loja(sender, request, **kwargs):
    """Handler de `corsheaders.signals.check_request_enabled`."""
    return origem_e_de_uma_loja(request.headers.get('origin'))
