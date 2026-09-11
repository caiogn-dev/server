"""A junta do pagamento por voucher.

Um método só. É o que a Volus vai implementar depois sem que checkout, modelo
ou máquina de estados precisem mudar.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DadosDoVoucher:
    """O que o cliente mandou do browser.

    Note o que NÃO está aqui: número do cartão e CVV. Eles ficam no browser e
    viram `card_token` antes de sair de lá. Acrescentar um campo de PAN aqui
    colocaria o Cardapidex dentro do escopo PCI.
    """
    card_token: str
    brand: str
    holder_name: str
    holder_document: str


@dataclass(frozen=True)
class ResultadoDaCobranca:
    aprovado: bool
    status: str            # 'approved' | 'pending' | 'failed'
    external_id: str | None
    mensagem: str          # em português, pronto para a tela
    bruto: dict = field(default_factory=dict)


class VoucherProvider(ABC):
    """Contrato de um trilho de vale-refeição/alimentação."""

    @abstractmethod
    def cobrar(self, order, dados: DadosDoVoucher, total=None) -> ResultadoDaCobranca:
        """Cobra o valor cheio do pedido. Tudo ou nada — nunca parcial."""
