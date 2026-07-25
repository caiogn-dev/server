"""Provider SEFAZ direto — emissão própria, custo zero por nota.

Estrutura pronta; a implementação real entra quando existir o certificado
digital A1 da loja. Checklist para ativar:

1. Certificado A1 (.pfx) do CNPJ + senha → guardar caminho/senha na config
   fiscal da loja (`cert_path`, `cert_password`) ou em storage seguro.
2. CSC + id do CSC emitidos no portal da SEFAZ-TO (`csc`, `csc_id`).
3. Instalar libs de emissão na imagem (ex.: pynfe ou erpbrasil.edoc) e
   implementar `emit_nfce`: montar o XML da NFC-e (layout 4.00), assinar com
   o A1, transmitir pro webservice de autorização da SEFAZ-TO e montar a URL
   do QR Code com o CSC.
4. Contingência offline (tpEmis=9) para quando a SEFAZ estiver fora.

Enquanto isso, qualquer tentativa de uso falha com mensagem clara — a config
`provider: 'focus'` continua sendo o caminho ativo.
"""
from .base import EmitResult, FiscalNotConfigured, FiscalProvider


class SefazProvider(FiscalProvider):
    def emit_nfce(self, *, ref: str, payload: dict) -> EmitResult:
        raise FiscalNotConfigured(
            'Emissão direta SEFAZ ainda não ativada: falta o certificado A1 '
            '(cert_path/cert_password) e o CSC na config fiscal da loja. '
            'Use provider "focus" ou complete o checklist em apps/fiscal/providers/sefaz.py.'
        )

    def cancel_nfce(self, *, ref: str, justificativa: str) -> EmitResult:
        raise FiscalNotConfigured('Emissão direta SEFAZ ainda não ativada.')
