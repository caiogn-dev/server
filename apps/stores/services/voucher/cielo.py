"""VoucherProvider em cima da API E-commerce Cielo — o trilho da Alelo."""
import logging

import requests

from apps.stores.services import cielo_ecommerce
from .base import DadosDoVoucher, ResultadoDaCobranca, VoucherProvider

logger = logging.getLogger(__name__)


class CieloVoucherProvider(VoucherProvider):
    """`bandeiras()` vem da base: só o que a Cielo cobra (hoje, Alelo) E que a
    loja marcou."""

    TRILHO = 'cielo'

    def _falha(self, mensagem, bruto=None, external_id=None):
        return ResultadoDaCobranca(
            aprovado=False, status='failed', external_id=external_id,
            mensagem=mensagem, bruto=bruto or {},
        )

    def _resultado(self, status_code, body):
        ok, status, payment_id, _motivo = cielo_ecommerce.interpret(status_code, body)
        mensagem = ''
        if status == 'failed':
            pagamento = (body.get('Payment') or {}) if isinstance(body, dict) else {}
            mensagem = cielo_ecommerce.mensagem_de_recusa(
                pagamento.get('ReturnCode'), pagamento.get('ReturnMessage'),
            )
        elif status == 'refunded':
            mensagem = cielo_ecommerce.RECUSA_GENERICA
        return ResultadoDaCobranca(
            aprovado=bool(ok and status == 'approved'),
            status=status, external_id=payment_id, mensagem=mensagem,
            bruto=body if isinstance(body, dict) else {'erros': body},
        )

    def _procurar_venda_perdida(self, order):
        """A resposta do POST se perdeu. A venda pode ter sido capturada.

        Devolve o resultado real se achar a venda, `failed` se a Cielo garante
        que ela não existe, e `pending` se nem a consulta respondeu — porque aí
        ninguém sabe, e "falhou" liberaria o cliente para pagar duas vezes.
        """
        g = self.gateway
        try:
            status_code, achadas = cielo_ecommerce.consultar_por_pedido(
                g.public_key, g.api_key, cielo_ecommerce.merchant_order_id(order),
                sandbox=g.is_sandbox,
            )
            pagamentos = (achadas or {}).get('Payments') or [] if isinstance(achadas, dict) else []
            if status_code != 200 or not pagamentos:
                return self._falha(cielo_ecommerce.FALHA_DE_REDE)
            payment_id = pagamentos[-1].get('PaymentId')
            status_code, detalhe = cielo_ecommerce.consultar_venda(
                g.public_key, g.api_key, payment_id, sandbox=g.is_sandbox,
            )
        except requests.RequestException as erro:
            logger.error('[cielo] venda do pedido %s em estado DESCONHECIDO: %s', order.id, erro)
            return ResultadoDaCobranca(
                aprovado=False, status='pending', external_id=None, mensagem='', bruto={},
            )
        return self._resultado(status_code, detalhe)

    def cobrar(self, order, dados: DadosDoVoucher, total=None) -> ResultadoDaCobranca:
        bandeira = (dados.brand or '').strip().lower()
        if bandeira not in self.bandeiras():
            return self._falha('Esta loja não aceita essa bandeira de vale.')

        payload = cielo_ecommerce.build_sale_payload(
            order, payment_token=dados.card_token, holder_name=dados.holder_name,
            holder_document=dados.holder_document, total=total,
        )
        g = self.gateway
        try:
            status_code, body = cielo_ecommerce.criar_venda(
                g.public_key, g.api_key, payload, sandbox=g.is_sandbox,
            )
        except requests.RequestException as erro:
            logger.error('[cielo] POST da venda do pedido %s falhou: %s', order.id, erro)
            return self._procurar_venda_perdida(order)

        return self._resultado(status_code, body)
