"""Trava de segurança: pytest NUNCA roda contra o banco de produção.

07/ago/2026 — descobrimos que a suíte inteira rodava contra `pastita`, o banco
da loja viva. Não havia banco de teste configurado: o `DATABASE_URL` apontava
para o pgbouncer de produção e o Django usava aquilo mesmo.

O `TestCase` faz rollback e foi o que evitou o desastre, mas falha em dois
casos que aconteceram de verdade:

- `TransactionTestCase` commita — não há rollback nenhum;
- execução interrompida no meio deixa o dado gravado (foi assim que o usuário
  `ws-test` foi parar no banco da loja em 05/ago).

Configuração se corrige com um arquivo; configuração ERRADA se repete. Esta
trava roda antes de qualquer teste, independente do settings escolhido, e
aborta a sessão em vez de confiar que a variável de ambiente está certa.

Para rodar a suíte:

    pytest -q                       # usa config.settings.test (pytest.ini)
    DJANGO_SETTINGS_MODULE=config.settings.test pytest -q
"""
import pytest

# Bancos que jamais podem ser alvo de teste.
BANCOS_DE_PRODUCAO = {'pastita'}
# Hosts que não suportam CREATE DATABASE — o pytest precisa disso para montar
# o banco `test_*`, e sem ele acaba usando o banco apontado (produção).
HOSTS_PROIBIDOS = {'pastita_pgbouncer'}


def pytest_configure(config):
    """Aborta a sessão se o alvo for produção."""
    from django.conf import settings

    db = settings.DATABASES.get('default', {})
    nome = (db.get('NAME') or '').strip()
    host = (db.get('HOST') or '').strip()
    nome_de_teste = ((db.get('TEST') or {}).get('NAME') or '').strip()

    problemas = []
    if nome in BANCOS_DE_PRODUCAO:
        problemas.append(
            f"o banco configurado é '{nome}' — isso é PRODUÇÃO."
        )
    if host in HOSTS_PROIBIDOS:
        problemas.append(
            f"o host é '{host}' (pgbouncer), que não suporta CREATE DATABASE: "
            f"o pytest não consegue criar o banco de teste e acaba escrevendo "
            f"no banco apontado."
        )
    if nome_de_teste and nome_de_teste in BANCOS_DE_PRODUCAO:
        problemas.append(
            f"TEST['NAME'] é '{nome_de_teste}' — isso é PRODUÇÃO."
        )

    # O cache também não pode ser o de produção. O banco foi isolado em
    # 07/ago e o cache ficou para trás: a suíte escrevia no Redis da loja viva
    # (cardápio, sessões do bot) e, de quebra, herdava o contador de rate limit
    # entre rodadas — 43 testes falhavam com 429 sem nenhuma regressão real.
    cache_backend = (settings.CACHES.get('default', {}).get('BACKEND') or '')
    cache_local = (settings.CACHES.get('default', {}).get('LOCATION') or '')
    if 'redis' in cache_backend.lower() or 'redis://' in str(cache_local).lower():
        problemas.append(
            f"o cache aponta para Redis ({cache_local or cache_backend}) — "
            f"os testes escreveriam no cache de produção e herdariam o "
            f"contador de rate limit entre rodadas."
        )

    if problemas:
        raise pytest.UsageError(
            '\n\n  RECUSANDO RODAR: a suíte apontaria para o banco de produção.\n\n'
            + ''.join(f'  - {p}\n' for p in problemas)
            + '\n  Rode com o settings de teste:\n\n'
              '      DJANGO_SETTINGS_MODULE=config.settings.test pytest -q\n\n'
              '  Contexto: em 05/ago um teste criou o usuário `ws-test` dentro do\n'
              '  banco da loja. O rollback do TestCase não cobre TransactionTestCase\n'
              '  nem execução interrompida.\n'
        )


@pytest.fixture(autouse=True)
def _cache_limpo_entre_testes():
    """Cada teste começa com o cache vazio.

    O contador de rate limit do DRF mora no cache. Sem esta limpeza ele ACUMULA
    ao longo da sessão: a suíte faz milhares de requisições, estoura `anon`
    (120/min) e, a partir daí, testes que nada têm a ver com throttle começam a
    receber 429 — fidelidade, contratos do app, IDOR, LGPD.

    O sintoma é traiçoeiro porque depende da ORDEM e do RELÓGIO: os mesmos
    testes passam quando rodados sozinhos e falham na suíte inteira, o que se
    parece muito com regressão. Em 08/ago isso custou três diagnósticos errados
    antes de alguém ler o corpo da resposta e encontrar `rate_limit_exceeded`.

    Os testes que verificam o rate limit de propósito continuam funcionando:
    eles fazem as 121 requisições DENTRO do próprio teste.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sem_chamada_real_ao_mercadopago(monkeypatch):
    """Nenhum teste fala com o Mercado Pago de verdade.

    Em 08/ago/2026 a suíte gerou SEIS cobranças PIX reais de R$ 179 na conta da
    empresa. O harness roda com `--env-file .env` (o de produção), e
    `test_active_untouched` chamava `enforce_subscription_lifecycle()` sem
    mockar o SDK: com `BILLING_PIX_ENABLED=true` herdado do ambiente, a task foi
    até a API e criou cobrança de verdade, uma por execução.

    Desligar a flag no settings de teste resolve ESTE caminho. Esta trava
    resolve a CLASSE: qualquer chamada ao SDK que escape de um mock estoura na
    hora, com a mensagem dizendo o que fazer, em vez de gastar dinheiro em
    silêncio e aparecer semanas depois no extrato.

    Teste que precisa exercitar o fluxo continua livre para mockar
    `subscription_service._sdk` — o patch dele tem precedência sobre este.
    """
    def _proibido(*args, **kwargs):
        raise AssertionError(
            'Teste tentou chamar o Mercado Pago DE VERDADE.\n'
            'Mocke `apps.stores.services.subscription_service._sdk` no seu teste.\n'
            'Isto já custou 6 cobranças reais de R$ 179 na conta da empresa.'
        )

    try:
        from apps.stores.services import subscription_service

        monkeypatch.setattr(subscription_service, '_sdk', _proibido, raising=False)
    except Exception:  # pragma: no cover - app pode não estar carregado
        pass
    yield
