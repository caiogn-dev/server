# apps/core/tests/test_no_bom.py
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[3]  # .../server2 (inside container: /app)
BOM = b"\xef\xbb\xbf"

CANDIDATES = [
    "apps/stores/services/checkout_service.py",
    "apps/core/services/dashboard_stats.py",
]

@pytest.mark.parametrize("rel", CANDIDATES)
def test_source_has_no_utf8_bom(rel):
    head = (REPO / rel).read_bytes()[:3]
    assert head != BOM, f"{rel} começa com BOM UTF-8 (quebra radon/xenon)"
