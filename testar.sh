#!/usr/bin/env bash
# Roda a suíte inteira do server2 e, se passar, carimba o código como "verde".
#
# Por que existe: em 04/09 o commit 3b8e17f5 quebrou o histórico do cliente
# (telefone sem o nono dígito) e o teste que guardava isso desde maio passou a
# falhar no mesmo dia. Ninguém viu: a suíte já tinha ~105 falhas acumuladas e
# o deploy não olhava teste nenhum. Corrigido em 08/10, junto com as 105.
#
# O deploy-fast.sh só sobe código cuja assinatura esteja carimbada aqui.
#
# Uso:
#   ./testar.sh                 # suíte inteira (~20 min), carimba se verde
#   TEST_DB_HOST=outro ./testar.sh   # outro banco de teste (duas sessões não
#                                    # podem dividir o mesmo — ver memória)
set -euo pipefail
cd "$(dirname "$0")"

DB_HOST="${TEST_DB_HOST:-pastita_test_db3}"
CARIMBO=.suite-verde

# Mesma assinatura que o deploy-fast.sh confere: código + testes.
assinatura() {
  find apps config tests -name '*.py' -type f | sort | xargs md5sum | md5sum | cut -d' ' -f1
}

antes=$(assinatura)
echo "==> Suíte inteira em $DB_HOST (assinatura $antes)..."
rm -f "$CARIMBO"

set +e
docker run --rm --network sdd_test_net -v "$PWD:/app" -w /app \
  --entrypoint /opt/venv/bin/python \
  -e DJANGO_SETTINGS_MODULE=config.settings.test -e TEST_DB_HOST="$DB_HOST" \
  pastita_backend:latest -m pytest -q --no-header -p no:cacheprovider --create-db \
  2>&1 | tee .suite-ultima.log | grep -E "^(FAILED|ERROR) |[0-9]+ (passed|failed)"
status=${PIPESTATUS[0]}
set -e

if [[ "$status" -ne 0 ]]; then
  echo "==> VERMELHO (exit $status). Log completo: .suite-ultima.log" >&2
  exit "$status"
fi
if [[ "$(assinatura)" != "$antes" ]]; then
  echo "==> Código mudou durante a suíte — rode de novo para carimbar." >&2
  exit 1
fi
echo "$antes $(date -Iseconds) $(git rev-parse --short HEAD)" > "$CARIMBO"
echo "==> VERDE — carimbado ($antes)"
