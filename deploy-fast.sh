#!/usr/bin/env bash
# Deploy RÁPIDO do server2 via docker cp (segundos, sem rebuild de imagem).
#
# A imagem (Dockerfile.prod) NÃO monta o código-fonte — editar arquivo local
# não muda nada em produção. Este script sincroniza apps/ e config/ inteiros
# para dentro dos 3 containers (web, celery, beat) e recarrega.
#
# Por que os 3: em 18/09 o deploy copiou só no web e o celery ficou com um
# janela.py antigo — o envio de campanha quebrou com o worker "healthy".
#
# Por que HUP no web e não restart: o restart deixava a API fora por ~45 s
# (o boot do web roda migrate + collectstatic). Medido de 28/09 a 05/10:
# 78 minutos de 502, sempre no almoço. O gunicorn (sem --preload) recebe HUP,
# sobe workers novos com o código novo e só então encerra os velhos.
#
# Para deploy definitivo (deps novas, Dockerfile, etc) use ./deploy.sh (rebuild).
#
# Uso:
#   ./deploy-fast.sh             # sincroniza código + recarrega
#   ./deploy-fast.sh --migrate   # idem, rodando migrações antes de recarregar
#   ./deploy-fast.sh --sem-testes  # emergência: sobe sem suíte verde (fica no log)
set -euo pipefail
cd "$(dirname "$0")"

WEB=pastita_web
WORKERS=(pastita_celery pastita_celery_beat)

for c in "$WEB" "${WORKERS[@]}"; do
  if ! docker inspect "$c" >/dev/null 2>&1; then
    echo "ERRO: container $c não existe." >&2
    exit 1
  fi
done

# Só sobe código com a suíte verde (./testar.sh carimba .suite-verde).
# 04/09: um teste de guarda falhou no dia em que o bug voltou, e o deploy
# subiu assim mesmo — a falha sumiu no meio de outras 104.
# Emergência: --sem-testes sobe mesmo assim e fica registrado no log.
SEM_TESTES=0
for arg in "$@"; do [[ "$arg" == "--sem-testes" ]] && SEM_TESTES=1; done
assinatura_suite=$(find apps config tests -name '*.py' -type f | sort | xargs md5sum | md5sum | cut -d' ' -f1)
carimbo=$(cut -d' ' -f1 .suite-verde 2>/dev/null || true)
if [[ "$carimbo" != "$assinatura_suite" ]]; then
  if [[ "$SEM_TESTES" -eq 1 ]]; then
    echo "$(date -Iseconds) $(git rev-parse --short HEAD) $assinatura_suite" >> .deploys-sem-testes.log
    echo "==> ATENÇÃO: subindo SEM suíte verde (--sem-testes). Registrado em .deploys-sem-testes.log"
  else
    echo "ERRO: este código não tem suíte verde. Rode ./testar.sh (ou, em emergência, --sem-testes)." >&2
    exit 1
  fi
fi

echo "==> Validando sintaxe Python local..."
find apps config -name '*.py' -not -path '*/migrations/*' -print0 | xargs -0 python3 -m py_compile

sincronizar() {
  local c=$1
  docker exec "$c" rm -rf /app/apps.new /app/config.new
  docker cp apps "$c":/app/apps.new
  docker cp config "$c":/app/config.new
  docker exec "$c" sh -c 'rm -rf /app/apps /app/config && mv /app/apps.new /app/apps && mv /app/config.new /app/config'
}

for c in "$WEB" "${WORKERS[@]}"; do
  echo "==> Sincronizando apps/ e config/ para $c ..."
  sincronizar "$c"
done

echo "==> Conferindo paridade do código nos 3 containers..."
assinatura() {
  docker exec "$1" sh -c "cd /app && find apps config -name '*.py' -type f | sort | xargs md5sum | md5sum" | cut -d' ' -f1
}
local_sig=$(find apps config -name '*.py' -type f | sort | xargs md5sum | md5sum | cut -d' ' -f1)
for c in "$WEB" "${WORKERS[@]}"; do
  sig=$(assinatura "$c")
  if [[ "$sig" != "$local_sig" ]]; then
    echo "ERRO: $c ficou diferente do código local ($sig != $local_sig)." >&2
    exit 1
  fi
done
echo "    idêntico ($local_sig)"

if [[ " $* " == *" --migrate "* ]]; then
  echo "==> Rodando migrações..."
  docker exec "$WEB" python manage.py migrate
fi

workers_web() {
  docker exec "$WEB" sh -c 'ps -eo pid,ppid | awk "\$2==1 {print \$1}" | sort | tr "\n" " "'
}

antes=$(workers_web)
echo "==> Recarregando $WEB sem derrubar (HUP no gunicorn)..."
docker exec "$WEB" kill -HUP 1

echo -n "==> Aguardando workers novos"
novos=""
for _ in $(seq 1 45); do
  sleep 2
  echo -n "."
  agora=$(workers_web)
  # Pronto quando nenhum worker antigo sobrou e há 4 de pé.
  restantes=$(comm -12 <(tr ' ' '\n' <<<"$antes" | sed '/^$/d' | sort) <(tr ' ' '\n' <<<"$agora" | sed '/^$/d' | sort) | wc -l)
  total=$(tr ' ' '\n' <<<"$agora" | sed '/^$/d' | wc -l)
  if [[ "$restantes" -eq 0 && "$total" -ge 4 ]]; then novos=$agora; break; fi
done
echo
if [[ -z "$novos" ]]; then
  echo "ERRO: os workers do gunicorn não trocaram — confira: docker logs $WEB --tail 50" >&2
  exit 1
fi

echo "==> Reiniciando ${WORKERS[*]} (sem tráfego HTTP; até 60 s para terminar a tarefa em curso)..."
docker restart -t 60 "${WORKERS[@]}" >/dev/null

code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/stores/pastita/ || true)
echo "==> Smoke test GET /api/v1/stores/pastita/ -> $code"
if [[ "$code" != "200" ]]; then
  echo "ERRO: deploy suspeito — confira: docker logs $WEB --tail 50" >&2
  exit 1
fi
echo "==> Deploy OK"
