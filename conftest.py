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
