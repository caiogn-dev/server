"""Provider Focus NFe (https://focusnfe.com.br) — API v2 de NFC-e.

A Focus cuida de XML, assinatura, SEFAZ e contingência; a gente manda JSON.
Homologação e produção mudam só a URL base + token.
"""
import logging

import requests

from .base import EmitResult, FiscalNotConfigured, FiscalProvider

logger = logging.getLogger(__name__)

PROD_URL = 'https://api.focusnfe.com.br'
HOMOLOG_URL = 'https://homologacao.focusnfe.com.br'


class FocusProvider(FiscalProvider):
    @property
    def base_url(self) -> str:
        return PROD_URL if self.config.get('ambiente') == 'producao' else HOMOLOG_URL

    def _auth(self):
        token = self.config.get('focus_token')
        if not token:
            raise FiscalNotConfigured('focus_token ausente na config fiscal da loja')
        return (token, '')

    @staticmethod
    def _to_result(data: dict) -> EmitResult:
        status_map = {
            'autorizado': 'authorized',
            'cancelado': 'cancelled',
            'erro_autorizacao': 'rejected',
            'processando_autorizacao': 'pending',
        }
        status = status_map.get(data.get('status', ''), 'error')
        mensagem = data.get('mensagem_sefaz') or data.get('mensagem') or ''
        return EmitResult(
            status=status,
            chave_acesso=data.get('chave_nfe') or data.get('chave') or '',
            numero=str(data.get('numero') or ''),
            serie=str(data.get('serie') or ''),
            qrcode_url=data.get('qrcode_url') or data.get('url_consulta_nf') or '',
            danfe_url=data.get('caminho_danfe') or '',
            xml_url=data.get('caminho_xml_nota_fiscal') or '',
            error_message=mensagem if status in ('rejected', 'error') else '',
            raw=data,
        )

    def _emit(self, recurso: str, ref: str, payload: dict) -> EmitResult:
        resp = requests.post(
            f'{self.base_url}/v2/{recurso}',
            params={'ref': ref},
            json=payload,
            auth=self._auth(),
            timeout=30,
        )
        if resp.status_code == 422:
            # ref já usada — consulta o que existe (idempotência)
            return self._consult(recurso, ref)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 and 'status' not in data:
            return EmitResult(status='error', error_message=str(data or resp.status_code), raw=data)
        return self._to_result(data)

    def _consult(self, recurso: str, ref: str) -> EmitResult:
        resp = requests.get(f'{self.base_url}/v2/{recurso}/{ref}', auth=self._auth(), timeout=30)
        return self._to_result(resp.json() if resp.content else {})

    def _cancel(self, recurso: str, ref: str, justificativa: str) -> EmitResult:
        resp = requests.delete(
            f'{self.base_url}/v2/{recurso}/{ref}',
            json={'justificativa': justificativa},
            auth=self._auth(),
            timeout=30,
        )
        return self._to_result(resp.json() if resp.content else {})

    # NFC-e (modelo 65) e NF-e (modelo 55) são recursos distintos na API;
    # só muda o caminho, o resto do contrato é idêntico.
    def emit_nfce(self, *, ref: str, payload: dict) -> EmitResult:
        return self._emit('nfce', ref, payload)

    def emit_nfe(self, *, ref: str, payload: dict) -> EmitResult:
        return self._emit('nfe', ref, payload)

    def consult(self, *, ref: str, modelo: str = '65') -> EmitResult:
        return self._consult('nfe' if modelo == '55' else 'nfce', ref)

    def cancel_nfce(self, *, ref: str, justificativa: str) -> EmitResult:
        return self._cancel('nfce', ref, justificativa)

    def cancel_nfe(self, *, ref: str, justificativa: str) -> EmitResult:
        return self._cancel('nfe', ref, justificativa)
