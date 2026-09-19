"""Provider Focus NFe (https://focusnfe.com.br) — API v2 de NFC-e.

A Focus cuida de XML, assinatura, SEFAZ e contingência; a gente manda JSON.
Homologação e produção mudam só a URL base + token.
"""
import logging
import re

import requests

from .base import EmitResult, FiscalNotConfigured, FiscalProvider

logger = logging.getLogger(__name__)

PROD_URL = 'https://api.focusnfe.com.br'
HOMOLOG_URL = 'https://homologacao.focusnfe.com.br'



# A Focus usa 422 para toda validação reprovada — certificado ausente, empresa
# não habilitada, campo inválido. Só a referência repetida quer dizer "essa
# nota já existe, vá consultar"; tratar os outros assim troca o motivo real
# pelo 404 da consulta ("Nota fiscal não encontrada") e cega quem está
# configurando.
CODIGOS_REF_DUPLICADA = {
    'nfe_referencia_duplicada',
    'nfce_referencia_duplicada',
    'referencia_duplicada',
}


def _e_ref_duplicada(data: dict) -> bool:
    return str((data or {}).get('codigo') or '') in CODIGOS_REF_DUPLICADA



def _com_detalhamento(mensagem: str, data: dict) -> str:
    """Junta o detalhamento de campo à mensagem.

    "verifique o detalhamento dos erros" é inútil sem o detalhamento: quem está
    configurando a loja precisa do NOME DO CAMPO para saber o que corrigir.
    """
    erros = (data or {}).get('erros') or []
    partes = []
    for erro in erros:
        if isinstance(erro, dict):
            campo = erro.get('campo') or ''
            texto = erro.get('mensagem') or ''
            partes.append(f'{campo}: {texto}'.strip(': ').strip())
        elif erro:
            partes.append(str(erro))
    if not partes:
        return mensagem
    return f'{mensagem} — ' + '; '.join(partes) if mensagem else '; '.join(partes)


class FocusProvider(FiscalProvider):
    @property
    def base_url(self) -> str:
        return PROD_URL if self.config.get('ambiente') == 'producao' else HOMOLOG_URL

    def _auth(self):
        token = self.config.get('focus_token')
        if not token:
            raise FiscalNotConfigured('focus_token ausente na config fiscal da loja')
        return (token, '')

    def _link(self, caminho: str) -> str:
        """A Focus devolve DANFE/XML como caminho relativo ao host da API;
        sem o host o link abre no domínio do painel."""
        caminho = caminho or ''
        return f'{self.base_url}{caminho}' if caminho.startswith('/') else caminho

    def _to_result(self, data: dict) -> EmitResult:
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
            # Vem "NFe" + 44 dígitos; a chave são os dígitos (coluna de 44).
            chave_acesso=re.sub(r'\D', '', str(data.get('chave_nfe') or data.get('chave') or '')),
            numero=str(data.get('numero') or ''),
            serie=str(data.get('serie') or ''),
            qrcode_url=data.get('qrcode_url') or data.get('url_consulta_nf') or '',
            danfe_url=self._link(data.get('caminho_danfe')),
            xml_url=self._link(data.get('caminho_xml_nota_fiscal')),
            error_message=(
                _com_detalhamento(mensagem, data) if status in ('rejected', 'error') else ''
            ),
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
        data = resp.json() if resp.content else {}
        if resp.status_code == 422 and _e_ref_duplicada(data):
            # só ESTE 422 significa "já emiti essa" — consulta o que existe
            return self._consult(recurso, ref)
        if resp.status_code >= 400 and 'status' not in data:
            # a mensagem da Focus é legível; o dict cru não é tela de usuário
            motivo = (data or {}).get('mensagem') or str(data or resp.status_code)
            return EmitResult(
                status='error', error_message=_com_detalhamento(motivo, data), raw=data,
            )
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
