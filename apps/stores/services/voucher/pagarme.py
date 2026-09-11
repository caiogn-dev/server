"""Implementação do VoucherProvider em cima da API do Pagar.me v5."""
import logging

import requests

from apps.stores.services import pagarme_orders
from .base import DadosDoVoucher, ResultadoDaCobranca, VoucherProvider

logger = logging.getLogger(__name__)

FALHA_DE_REDE = (
    'Não conseguimos falar com a operadora do vale agora. '
    'Tente de novo em instantes ou pague no PIX.'
)


class PagarmeVoucherProvider(VoucherProvider):
    def __init__(self, gateway):
        self.gateway = gateway

    def bandeiras(self):
        config = getattr(self.gateway, 'configuration', None) or {}
        marcas = config.get('voucher_brands') or []
        return [str(m).strip().lower() for m in marcas if str(m).strip()]

    def cobrar(self, order, dados: DadosDoVoucher, total=None) -> ResultadoDaCobranca:
        bandeira = (dados.brand or '').strip().lower()
        if bandeira not in self.bandeiras():
            # Recusa antes da rede: a loja não habilitou essa bandeira.
            return ResultadoDaCobranca(
                aprovado=False, status='failed', external_id=None,
                mensagem='Esta loja não aceita essa bandeira de vale.', bruto={},
            )

        try:
            payload = pagarme_orders.build_voucher_payload(
                order,
                card_token=dados.card_token,
                brand=bandeira,
                holder_name=dados.holder_name,
                holder_document=dados.holder_document,
                total=total,
            )
        except ValueError as erro:
            logger.warning('Voucher recusado antes da rede: %s', erro)
            return ResultadoDaCobranca(
                aprovado=False, status='failed', external_id=None,
                mensagem='Esta bandeira de vale não está disponível.', bruto={},
            )

        try:
            status_code, body = pagarme_orders.create_order(self.gateway.api_key, payload)
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as erro:
            # Nunca deixar exceção de rede subir para o checkout: o cliente
            # veria erro 500 numa tela de pagamento.
            logger.error('Pagar.me inacessível no voucher: %s', erro)
            return ResultadoDaCobranca(
                aprovado=False, status='failed', external_id=None,
                mensagem=FALHA_DE_REDE, bruto={},
            )

        ok, status, external_id, motivo = pagarme_orders.interpret(status_code, body)
        mensagem = '' if ok and status == 'approved' else pagarme_orders.mensagem_de_recusa(motivo)
        return ResultadoDaCobranca(
            aprovado=bool(ok and status == 'approved'),
            status=status, external_id=external_id,
            mensagem=mensagem, bruto=body or {},
        )
