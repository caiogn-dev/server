"""Token usage accumulation + cost estimation (R$) for LLM calls.

Funções puras, sem dependências pesadas, para instrumentar o custo por mensagem
do agente. NÃO escreve no banco — apenas calcula. O provedor alvo é a NVIDIA
(build endpoint), cujo pricing real ainda não está consolidado.
"""

from decimal import Decimal

# Preço por 1M tokens (USD), (input, output). NVIDIA build endpoint —
# ajustar quando houver pricing real.
_PRICE_USD_PER_M = {
    "meta/llama-3.1-70b-instruct": (Decimal("0.0"), Decimal("0.0")),
}
_FALLBACK = (Decimal("0.50"), Decimal("0.50"))
_USD_BRL = Decimal("5.40")  # TODO: parametrizar via settings


def accumulate_usage(acc: dict, response) -> dict:
    """Soma input/output/total tokens de uma resposta LangChain ao acumulador.

    Robusto a usage_metadata ausente OU None (NVIDIA às vezes não retorna).
    """
    meta = getattr(response, "usage_metadata", None) or {}
    out = dict(acc)
    for k in ("input_tokens", "output_tokens", "total_tokens"):
        out[k] = out.get(k, 0) + int(meta.get(k, 0) or 0)
    return out


def estimate_cost_brl(model_name: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Estima o custo em R$ a partir dos tokens de entrada/saída."""
    pin, pout = _PRICE_USD_PER_M.get(model_name, _FALLBACK)
    usd = (Decimal(input_tokens) * pin + Decimal(output_tokens) * pout) / Decimal(1_000_000)
    return (usd * _USD_BRL).quantize(Decimal("0.000001"))
