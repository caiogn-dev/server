#!/bin/bash
# SDD test helper: sincroniza o source do host (container é baked, sem volume)
# para dentro de pastita_web e roda pytest com os args passados.
# Uso: bash scripts/sdd-test.sh apps/core/tests/test_no_bom.py -v
set -e
docker cp pytest.ini pastita_web:/app/pytest.ini >/dev/null
docker cp apps/. pastita_web:/app/apps/ >/dev/null
docker compose exec -T web python -m pytest "$@"
