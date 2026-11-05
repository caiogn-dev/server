#!/usr/bin/env bash
# Hot-deploy (05/11): número/marca dos apps na comanda + lote que não repete na impressora.
# Os containers estavam na versão exatamente anterior a estes 3 commits (conferido com diff).
# Efêmero até o próximo `bash deploy.sh` (a imagem não tem estas mudanças).
set -euo pipefail
cd /home/graco/WORK/server2
ARQUIVOS=(
  apps/stores/services/pedidos_da_99.py
  apps/stores/services/comanda_linhas.py
  apps/stores/services/print_service.py
  apps/stores/management/commands/numero_dos_pedidos_da_99.py
)
for c in pastita_web pastita_celery pastita_celery_beat; do
  for f in "${ARQUIVOS[@]}"; do docker cp "$f" "$c:/app/$f"; done
done
docker restart pastita_web pastita_celery pastita_celery_beat
sleep 15
docker exec pastita_web python -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.production');django.setup();from apps.stores.services import print_service as p;print('fix impressora:', hasattr(p,'_ainda_imprimindo'))"
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'pastita_web|pastita_celery'
