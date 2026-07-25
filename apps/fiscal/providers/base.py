"""Contrato comum dos emissores de NFC-e.

Trocar de provedor (Focus ↔ SEFAZ direto) é trocar a chave `provider` na
config fiscal da loja — o resto do sistema só conhece esta interface.
"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class EmitResult:
    status: str                      # authorized | rejected | pending | error
    chave_acesso: str = ''
    numero: str = ''
    serie: str = ''
    qrcode_url: str = ''
    danfe_url: str = ''
    xml_url: str = ''
    error_message: str = ''
    raw: dict = field(default_factory=dict)


class FiscalProvider:
    """Interface. `config` é o dict store.metadata['fiscal']."""

    def __init__(self, config: dict):
        self.config = config or {}

    def emit_nfce(self, *, ref: str, payload: dict) -> EmitResult:
        raise NotImplementedError

    def cancel_nfce(self, *, ref: str, justificativa: str) -> EmitResult:
        raise NotImplementedError


class FiscalNotConfigured(Exception):
    """Loja sem config fiscal suficiente para emitir."""
