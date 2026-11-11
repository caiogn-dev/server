#!/usr/bin/env bash
# Grava as credenciais do Uber Direct no .env do server2 e testa na hora.
# Uso:  bash scripts/uber_direct_env.sh
# Os segredos são digitados aqui (sem eco) e nunca aparecem na tela.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env"
[ -f "$ENV_FILE" ] || { echo "Não achei $ENV_FILE em $(pwd)"; exit 1; }

[ -t 0 ] || { echo "Rode num terminal de verdade (ssh/terminal), não pelo ! do Claude: os segredos precisam ser digitados."; exit 1; }

cp "$ENV_FILE" "$ENV_FILE.bak-uber-$(date +%Y%m%d-%H%M%S)"

ask() {  # ask VAR "pergunta" secret(0/1)
  local var="$1" prompt="$2" secret="$3" atual val
  atual="$(grep -E "^${var}=" "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  if [ "$secret" = 1 ]; then
    read -r -s -p "$prompt [Enter mantém o atual]: " val; echo >&2
  else
    read -r -p "$prompt [${atual:-vazio}]: " val
  fi
  printf '%s' "${val:-$atual}"
}

upsert() {  # upsert VAR VALOR
  local var="$1" val="$2" tmp
  [ -n "$val" ] || { echo "  (pulei $var: valor vazio)"; return 0; }
  tmp="$(mktemp)"
  if grep -qE "^${var}=" "$ENV_FILE"; then
    awk -v k="$var" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"; printf '%s=%s\n' "$var" "$val" >> "$tmp"
  fi
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

echo "== Uber Direct (direct.uber.com → Gerenciar → Desenvolvedor)"
CUSTOMER_ID="$(ask UBER_CUSTOMER_ID 'Customer ID' 0)"
CLIENT_ID="$(ask UBER_API_KEY 'Client ID' 0)"
CLIENT_SECRET="$(ask UBER_CLIENT_SECRET 'Client Secret' 1)"
SIGNING_KEY="$(ask UBER_WEBHOOK_SIGNING_KEY 'Webhook signing key (pode deixar vazio por enquanto)' 1)"

[ -n "$CUSTOMER_ID" ] && [ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ] || { echo "Faltou Customer ID, Client ID ou Secret."; exit 1; }

upsert UBER_CUSTOMER_ID "$CUSTOMER_ID"
upsert UBER_API_KEY "$CLIENT_ID"
upsert UBER_CLIENT_SECRET "$CLIENT_SECRET"
upsert UBER_API_BASE_URL "https://api.uber.com/v1/customers/${CUSTOMER_ID}/deliveries"
[ -n "$SIGNING_KEY" ] && upsert UBER_WEBHOOK_SIGNING_KEY "$SIGNING_KEY"
echo "✔ .env atualizado (backup ao lado)."

echo "== Testando token..."
TOKEN="$(curl -s -m 15 -X POST https://auth.uber.com/oauth/v2/token \
  --data-urlencode "client_id=$CLIENT_ID" --data-urlencode "client_secret=$CLIENT_SECRET" \
  -d grant_type=client_credentials -d scope=eats.deliveries \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("access_token") or "ERRO:"+json.dumps(d))')"
case "$TOKEN" in ERRO:*) echo "✘ Token falhou: ${TOKEN#ERRO:}"; exit 1;; esac
echo "✔ Token ok (escopo eats.deliveries)."

echo "== Testando cotação (não cria entrega, não cobra)..."
python3 - "$CUSTOMER_ID" "$TOKEN" <<'EOF'
import sys, json, urllib.request
cid, tok = sys.argv[1], sys.argv[2]
a = lambda s, z: json.dumps({"street_address": [s], "city": "Palmas", "state": "TO", "zip_code": z, "country": "BR"})
body = {"pickup_address": a("Quadra 104 Norte, Avenida LO 2", "77006-022"),
        "dropoff_address": a("Quadra 403 Sul, Alameda 10", "77015-570")}
req = urllib.request.Request(f"https://api.uber.com/v1/customers/{cid}/delivery_quotes",
                             data=json.dumps(body).encode(),
                             headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
try:
    d = json.load(urllib.request.urlopen(req, timeout=20))
    print(f"✔ Cotação ok: R$ {d['fee']/100:.2f}, entrega em ~{d.get('duration')} min")
except urllib.error.HTTPError as e:
    print(f"✘ Cotação falhou ({e.code}): {e.read().decode()[:300]}"); sys.exit(1)
EOF

echo
echo "Pronto. Os containers só leem o .env quando são recriados — eu faço isso no deploy."
