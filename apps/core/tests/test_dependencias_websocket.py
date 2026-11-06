"""
Trava das dependências de WebSocket e da família langchain (06/11).

O requirements.txt prendia websockets<14 "para evitar transfer_data_task
AttributeError". Esse erro vinha do protocolo LEGADO do websockets
(websockets.legacy.server.WebSocketServerProtocol), que o uvicorn antigo usava
em `--ws auto`. O uvicorn atual (0.54) escolhe a implementação sans-I/O
(WebSocketsSansIOProtocol), que não toca em transfer_data_task. Com isso o
websockets pode subir e as CVEs de langchain/langgraph-sdk/langsmith fecham.

Se alguém rebaixar o uvicorn (auto voltando ao legado) ou travar de novo o
websockets/langchain em versão vulnerável, estes testes quebram.
"""
from importlib.metadata import version

from packaging.version import Version


def test_uvicorn_ws_auto_usa_implementacao_sansio():
    from uvicorn.config import Config
    from uvicorn.protocols.websockets.auto import AutoWebSocketsProtocol
    from uvicorn.protocols.websockets.websockets_sansio_impl import (
        WebSocketsSansIOProtocol,
    )

    assert AutoWebSocketsProtocol is WebSocketsSansIOProtocol

    # É isso que o gunicorn + UvicornWorker do Dockerfile.prod carrega (ws='auto').
    config = Config(app="config.asgi:application")
    config.load()
    assert config.ws_protocol_class is WebSocketsSansIOProtocol


def test_websockets_fora_da_trava_antiga():
    assert Version(version("websockets")) >= Version("15")


def test_familia_langchain_sem_cve():
    assert Version(version("langchain")) >= Version("1.3.9")  # PYSEC-2026-2192
    assert Version(version("langgraph-sdk")) >= Version("0.4.4")  # PYSEC-2026-4240
    assert Version(version("langsmith")) >= Version("0.8.18")  # CVE-2026-59152
