from decimal import Decimal
from types import SimpleNamespace

from apps.agents.services.llm_cost import accumulate_usage, estimate_cost_brl


def test_accumulate_sums_all_iterations():
    acc = {}
    for it in (100, 50, 30):
        acc = accumulate_usage(acc, SimpleNamespace(
            usage_metadata={"input_tokens": it, "output_tokens": it // 2, "total_tokens": it + it // 2}))
    assert acc["input_tokens"] == 180
    assert acc["output_tokens"] == 90
    assert acc["total_tokens"] == 270


def test_accumulate_handles_missing_or_none_usage():
    acc = accumulate_usage({}, SimpleNamespace())            # no usage_metadata attr
    acc = accumulate_usage(acc, SimpleNamespace(usage_metadata=None))  # None
    assert acc == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def test_estimate_cost_is_decimal_and_nonneg():
    cost = estimate_cost_brl("meta/llama-3.1-70b-instruct", 1000, 1000)
    assert isinstance(cost, Decimal) and cost >= 0
    # fallback model gives a positive cost
    assert estimate_cost_brl("unknown/model", 1_000_000, 1_000_000) > 0
